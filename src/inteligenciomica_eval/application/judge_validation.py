"""JudgeValidationUseCase — validação amostral humana do juiz LLM (TAREFA-602).

Implementa o cálculo de Cohen's κ entre o juiz LLM (rubric_biomed_score binarizado)
e o anotador humano (critical_failure_flag), conforme §9.5 e §14.9 da arquitetura.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

import structlog

from inteligenciomica_eval.domain.errors import InsufficientAnnotationError
from inteligenciomica_eval.domain.ports import KappaCalculatorPort, ResultReaderPort

_log = structlog.get_logger(__name__)

KappaInterpretation = Literal[
    "fraca", "razoável", "moderada", "substancial", "quase-perfeita"
]


@dataclass(frozen=True)
class JudgeValidationConfig:
    """Configuração do cálculo de Cohen's κ para validação do juiz.

    Args:
        binarization_threshold: limiar de binarização do score do juiz;
            ``judge_binary = 1 if rubric_biomed_score < threshold else 0``.
        min_sample_size: mínimo de amostras válidas exigido; levanta
            ``InsufficientAnnotationError`` se ``n_valid < min_sample_size``.
    """

    binarization_threshold: float = 0.50
    min_sample_size: int = 10


@dataclass(frozen=True)
class JudgeValidationResult:
    """Resultado da validação amostral do juiz LLM via Cohen's κ.

    Args:
        n_total: total de linhas no Parquet para o run_id/round_id.
        n_annotated: linhas com critical_failure_flag não-nulo.
        n_valid: linhas com rubric_biomed_score não-NaN E flag não-nulo.
        n_excluded_nan: linhas excluídas por NaN do juiz (= n_annotated - n_valid).
        cohen_kappa: coeficiente kappa de Cohen calculado.
        kappa_interpretation: categoria de Landis & Koch correspondente.
        confusion_matrix: contagens TP/TN/FP/FN.
        binarization_threshold: limiar usado na binarização.
        judge_model: modelo do juiz lido do Parquet.
        batch_invariant_confirmed: todos os registros têm batch_invariant=True?
        discordances: lista de dicts com detalhes das discordâncias (row_id,
            rubric_biomed_score, judge_binary, critical_failure_flag).
    """

    n_total: int
    n_annotated: int
    n_valid: int
    n_excluded_nan: int
    cohen_kappa: float
    kappa_interpretation: KappaInterpretation
    confusion_matrix: dict[str, int]
    binarization_threshold: float
    judge_model: str
    batch_invariant_confirmed: bool
    discordances: list[dict[str, object]] = field(default_factory=list)


def _interpret_kappa(kappa: float) -> KappaInterpretation:
    """Converte valor numérico de κ para categoria de Landis & Koch (5 níveis).

    Args:
        kappa: coeficiente de Cohen em [-1, 1].

    Returns:
        Categoria textual da escala de Landis & Koch.
    """
    if kappa >= 0.80:
        return "quase-perfeita"
    if kappa >= 0.60:
        return "substancial"
    if kappa >= 0.40:
        return "moderada"
    if kappa >= 0.20:
        return "razoável"
    return "fraca"


class JudgeValidationUseCase:
    """Calcula Cohen's κ entre juiz LLM e anotador humano.

    Não recebe ``report_path`` — retorna ``JudgeValidationResult`` puro.
    A geração do relatório em disco é responsabilidade da CLI (TAREFA-602 §4).

    Args:
        reader: port de leitura de resultados do Parquet.
        kappa_calculator: implementação de KappaCalculatorPort.
        config: parâmetros de binarização e tamanho mínimo.
    """

    def __init__(
        self,
        reader: ResultReaderPort,
        kappa_calculator: KappaCalculatorPort,
        config: JudgeValidationConfig,
    ) -> None:
        self._reader = reader
        self._kappa = kappa_calculator
        self._config = config

    def run(self, run_id: str, round_id: str) -> JudgeValidationResult:
        """Executa a validação do juiz para o run/rodada especificados.

        Args:
            run_id: identificador do run de avaliação.
            round_id: identificador da rodada.

        Returns:
            ``JudgeValidationResult`` com κ, interpretação, matriz e metadados.

        Raises:
            InsufficientAnnotationError: quando ``n_valid < config.min_sample_size``.
        """
        frame = self._reader.load(round_id=round_id, run_id=run_id)
        results = list(frame.results)

        n_total = len(results)
        threshold = self._config.binarization_threshold

        # --- Coletar modelos e verificar batch_invariant ---
        judge_models: set[str] = set()
        batch_invariant_flags: list[bool] = []
        for r in results:
            judge_models.add(r.answer.llm.value)
            batch_invariant_flags.append(r.batch_invariant)

        judge_model = ", ".join(sorted(judge_models)) if judge_models else "unknown"
        if len(judge_models) > 1:
            _log.warning(
                "judge_validation_multiple_models",
                models=sorted(judge_models),
                run_id=run_id,
                round_id=round_id,
            )

        batch_invariant_confirmed = (
            all(batch_invariant_flags) if batch_invariant_flags else False
        )
        if not batch_invariant_confirmed:
            _log.warning(
                "judge_validation_non_deterministic",
                run_id=run_id,
                round_id=round_id,
                message=(
                    "batch_invariant=False em algum registro — juiz pode não ser "
                    "determinístico; a comparação κ pode ser inválida (ADR-003)."
                ),
            )

        # --- Filtrar linhas anotadas ---
        annotated = [r for r in results if r.critical_failure_flag is not None]
        n_annotated = len(annotated)

        # --- Filtrar linhas válidas (anotadas E score não-NaN) ---
        valid = [r for r in annotated if not math.isnan(r.metrics.rubric_biomed_score)]
        n_valid = len(valid)
        n_excluded_nan = n_annotated - n_valid

        if n_excluded_nan > 0:
            _log.warning(
                "judge_validation_nan_excluded",
                n_excluded_nan=n_excluded_nan,
                run_id=run_id,
                round_id=round_id,
                message=(
                    f"{n_excluded_nan} linha(s) com anotação mas sem rubric_biomed_score "
                    "(NaN do juiz) excluídas do cálculo de κ."
                ),
            )

        if n_valid < self._config.min_sample_size:
            raise InsufficientAnnotationError(
                n_valid=n_valid,
                min_required=self._config.min_sample_size,
            )

        # --- Binarização: score < threshold → judge_binary = 1 (falha) ---
        y_true: list[int] = []
        y_pred: list[int] = []
        discordances: list[dict[str, object]] = []

        for r in valid:
            human_flag = int(r.critical_failure_flag)  # type: ignore[arg-type]
            score = r.metrics.rubric_biomed_score
            judge_binary = 1 if score < threshold else 0

            y_true.append(human_flag)
            y_pred.append(judge_binary)

            if human_flag != judge_binary:
                discordances.append(
                    {
                        "row_id": r.answer.row_id.value,
                        "rubric_biomed_score": score,
                        "judge_binary": judge_binary,
                        "critical_failure_flag": human_flag,
                    }
                )

        # --- Cohen's κ ---
        kappa = self._kappa.compute(y_true, y_pred)
        interpretation = _interpret_kappa(kappa)

        # --- Matriz de confusão: humano é referência (y_true), juiz é predição (y_pred) ---
        tp = sum(
            1 for ht, jp in zip(y_true, y_pred, strict=True) if ht == 1 and jp == 1
        )
        tn = sum(
            1 for ht, jp in zip(y_true, y_pred, strict=True) if ht == 0 and jp == 0
        )
        fp = sum(
            1 for ht, jp in zip(y_true, y_pred, strict=True) if ht == 0 and jp == 1
        )
        fn = sum(
            1 for ht, jp in zip(y_true, y_pred, strict=True) if ht == 1 and jp == 0
        )

        _log.info(
            "judge_validation_completed",
            run_id=run_id,
            round_id=round_id,
            n_total=n_total,
            n_annotated=n_annotated,
            n_valid=n_valid,
            n_excluded_nan=n_excluded_nan,
            cohen_kappa=round(kappa, 6),
            kappa_interpretation=interpretation,
            batch_invariant_confirmed=batch_invariant_confirmed,
        )

        return JudgeValidationResult(
            n_total=n_total,
            n_annotated=n_annotated,
            n_valid=n_valid,
            n_excluded_nan=n_excluded_nan,
            cohen_kappa=kappa,
            kappa_interpretation=interpretation,
            confusion_matrix={"TP": tp, "TN": tn, "FP": fp, "FN": fn},
            binarization_threshold=threshold,
            judge_model=judge_model,
            batch_invariant_confirmed=batch_invariant_confirmed,
            discordances=discordances,
        )
