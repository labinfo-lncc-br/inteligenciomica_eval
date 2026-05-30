"""RunJudgePassUseCase — Passada 3 da arquitetura de 3 passadas (ADR-004).

Avalia cada linha via rubrica biomédica (PrometheusJudge, VLLM_BATCH_INVARIANT=1),
persistindo rubric_biomed_score + FinalScore recalculado com
regime=DeterminismRegime.JUDGE (ADR-003).

Processamento SEQUENCIAL e em ORDEM ESTÁVEL por row_id (garante reprodutibilidade
de submissão ao juiz batch-invariant — mesmas linhas na mesma ordem em re-runs).

NaN-propagation (ADR-007): JudgeUnavailableError após max_judge_retries tentativas
→ rubric_biomed_score=NaN + FinalScore(NaN) persistidos.

Decisão de design documentada: linhas com final_score=NaN (métricas RAGAS
ainda não calculadas ou NaN da Passada 2) são PROCESSADAS. O juiz avalia
a resposta diretamente (question + answer), independente do RAGAS. Isso
permite diagnóstico parcial e evita bloquear Passada 3 por falha da Passada 2
(ADR-004: passadas são independentes na leitura).

Desvios conscientes em relação à spec (TAREFA-306):
1. ``score_calc: FinalScoreCalculator`` adicionado ao construtor — não está
   na spec, mas necessário para recompute do FinalScore após preencher
   rubric_biomed_score. ``FinalScoreCalculator`` vem de domain.services
   (importação permitida pela application).
2. ``config: JudgePassConfig`` (dataclass de aplicação) em vez de ``RoundConfig``
   (infrastructure — import-linter Contract 2/4). Os campos necessários
   (max_judge_retries, retry_backoff_s, log_progress_every) não existem em
   RoundConfig; são parâmetros de orquestração.
"""

from __future__ import annotations

import asyncio
import dataclasses
import math
import time
from dataclasses import dataclass

import structlog

from inteligenciomica_eval.domain.entities import EvaluationResult
from inteligenciomica_eval.domain.errors import JudgeUnavailableError
from inteligenciomica_eval.domain.ports import (
    EvaluationSample,
    ResultReaderPort,
    ResultWriterPort,
    RubricJudgePort,
    RubricResult,
)
from inteligenciomica_eval.domain.services.final_score import FinalScoreCalculator
from inteligenciomica_eval.domain.value_objects import DeterminismRegime

_log = structlog.get_logger(__name__)

_NAN = float("nan")
_NAN_RUBRIC = RubricResult(score=_NAN, feedback="[judge_unavailable_after_retries]")


@dataclass(frozen=True, slots=True)
class JudgePassConfig:
    """Configuração da Passada 3 do juiz (ADR-004).

    Args:
        max_judge_retries: tentativas máximas (1 inicial + N-1 retries) em
            JudgeUnavailableError antes de aceitar rubric_biomed_score=NaN (ADR-007).
        retry_backoff_s: espera entre tentativas em segundos (default 5 s; use 0
            em testes para velocidade).
        log_progress_every: frequência de log de progresso (linhas julgadas).
    """

    max_judge_retries: int = 3
    retry_backoff_s: float = 5.0
    log_progress_every: int = 10


@dataclass(frozen=True, slots=True)
class JudgePassReport:
    """Relatório de execução da Passada 3 do juiz (ADR-004).

    Args:
        run_id: identificador da rodada.
        round_id: identificador do round no armazenamento.
        n_judged: linhas com rubric_biomed_score não-NaN após julgamento.
        n_skipped: linhas puladas por idempotência (rubric_biomed_score já não-NaN).
        n_skipped_missing_generation: linhas sem generated_answer.
        n_nan: linhas onde rubric_biomed_score ficou NaN (retries esgotados ou
            resultado NaN do juiz — ADR-007).
        duration_s: duração total da passada em segundos.
        batch_invariant_assumed: o use case assume que o servidor do juiz foi
            configurado com VLLM_BATCH_INVARIANT=1 pelo VLLMServerManager (ADR-003).
            Auditoria: verificar VLLMServerManager e wiring para confirmar.
    """

    run_id: str
    round_id: str
    n_judged: int
    n_skipped: int
    n_skipped_missing_generation: int
    n_nan: int
    duration_s: float
    batch_invariant_assumed: bool = True


class RunJudgePassUseCase:
    """Passada 3 da arquitetura de 3 passadas (ADR-004): julga e persiste rubrica.

    Carrega linhas da Passada 2 via reader, avalia cada uma sequencialmente com
    o LLM-juiz biomédico (RubricJudgePort) em ordem estável por row_id, e persiste
    rubric_biomed_score + FinalScore recalculado via writer.update_metrics com
    regime=DeterminismRegime.JUDGE.

    Args:
        judge: port de rubrica biomédica (Prometheus, VLLM_BATCH_INVARIANT=1).
        writer: port de persistência (update_metrics para linhas existentes).
        reader: port de leitura (carrega linhas da Passada 2 por round_id).
        score_calc: serviço de domínio de FinalScore ponderado (TAREFA-006).
        config: parâmetros da passada (retries, backoff, progresso).
    """

    def __init__(
        self,
        *,
        judge: RubricJudgePort,
        writer: ResultWriterPort,
        reader: ResultReaderPort,
        score_calc: FinalScoreCalculator,
        config: JudgePassConfig | None = None,
    ) -> None:
        self._judge = judge
        self._writer = writer
        self._reader = reader
        self._score_calc = score_calc
        self._config = config if config is not None else JudgePassConfig()

    async def execute(
        self,
        *,
        run_id: str,
        round_id: str,
        phase: str | None = None,
    ) -> JudgePassReport:
        """Executa a passada do juiz para todas as linhas elegíveis.

        Processamento SEQUENCIAL em ORDEM ESTÁVEL por ``row_id`` (ADR-003):
        garante que o juiz batch-invariant receba linhas na mesma sequência
        em re-runs — essencial para reprodutibilidade de resultados.

        Args:
            run_id: identificador da rodada (proveniência, logging).
            round_id: identificador do round no armazenamento (filtro reader).
            phase: fase do experimento (``"A"`` ou ``"B"``); ``None`` processa ambas.

        Returns:
            :class:`JudgePassReport` com totais de julgamento, skips e NaN.
        """
        t_start = time.monotonic()
        n_judged = 0
        n_skipped = 0
        n_skipped_missing_generation = 0
        n_nan = 0

        frame = self._reader.load(round_id=round_id, phase=phase)

        eligible: list[EvaluationResult] = []
        for result in frame.results:
            if not math.isnan(result.metrics.rubric_biomed_score):
                n_skipped += 1
                continue
            if not result.answer.generated_answer:
                n_skipped_missing_generation += 1
                _log.warning(
                    "judge_skipped_missing_generation",
                    run_id=run_id,
                    round_id=round_id,
                    row_id=result.answer.row_id.value,
                    question_id=result.answer.question.question_id,
                )
                continue
            if math.isnan(result.final_score.value):
                _log.info(
                    "judge_processing_nan_final_score",
                    run_id=run_id,
                    round_id=round_id,
                    row_id=result.answer.row_id.value,
                    question_id=result.answer.question.question_id,
                )
            eligible.append(result)

        # Ordem estável por row_id — garante submissão idêntica ao juiz em re-runs.
        eligible.sort(key=lambda r: r.answer.row_id.value)

        _log.info(
            "judge_pass_started",
            run_id=run_id,
            round_id=round_id,
            n_eligible=len(eligible),
            n_skipped=n_skipped,
            n_skipped_missing_generation=n_skipped_missing_generation,
        )

        for judged_count, result in enumerate(eligible, start=1):
            sample = self._make_sample(result)
            rubric = await self._judge_with_retry(sample, run_id=run_id)

            new_metrics = dataclasses.replace(
                result.metrics, rubric_biomed_score=rubric.score
            )
            new_score = self._score_calc.compute(new_metrics)
            self._writer.update_metrics(
                result.answer.row_id,
                metrics=new_metrics,
                final_score=new_score,
                regime=DeterminismRegime.JUDGE,
            )

            if math.isnan(rubric.score):
                n_nan += 1
            else:
                n_judged += 1
                _log.info(
                    "judge_completed",
                    run_id=run_id,
                    round_id=round_id,
                    question_id=sample.question_id,
                    rubric_score=rubric.score,
                    final_score=new_score.value,
                )

            if judged_count % self._config.log_progress_every == 0:
                _log.info(
                    "judge_progress",
                    run_id=run_id,
                    round_id=round_id,
                    judged_count=judged_count,
                    n_judged=n_judged,
                    n_nan=n_nan,
                )

        duration_s = time.monotonic() - t_start
        _log.info(
            "judge_pass_completed",
            run_id=run_id,
            round_id=round_id,
            n_judged=n_judged,
            n_skipped=n_skipped,
            n_skipped_missing_generation=n_skipped_missing_generation,
            n_nan=n_nan,
            duration_s=round(duration_s, 3),
        )
        return JudgePassReport(
            run_id=run_id,
            round_id=round_id,
            n_judged=n_judged,
            n_skipped=n_skipped,
            n_skipped_missing_generation=n_skipped_missing_generation,
            n_nan=n_nan,
            duration_s=duration_s,
        )

    @staticmethod
    def _make_sample(result: EvaluationResult) -> EvaluationSample:
        """Constrói EvaluationSample a partir de um EvaluationResult."""
        return EvaluationSample(
            question_id=result.answer.question.question_id,
            question=result.answer.question.text,
            ground_truth=result.answer.question.ground_truth,
            generated_answer=result.answer.generated_answer,
            contexts=result.answer.retrieved_chunks_text,
        )

    async def _judge_with_retry(
        self,
        sample: EvaluationSample,
        *,
        run_id: str,
    ) -> RubricResult:
        """Chama judge.score com retry em JudgeUnavailableError (ADR-007).

        Tenta até max_judge_retries vezes (total); ao esgotar, retorna
        RubricResult com score=NaN (ADR-007: NaN é estado legítimo).

        Args:
            sample: amostra a avaliar.
            run_id: identificador da rodada (logging).

        Returns:
            :class:`RubricResult` do juiz, ou NaN-sentinel se retries esgotados.
        """
        for attempt in range(1, self._config.max_judge_retries + 1):
            try:
                return await self._judge.score(sample)
            except JudgeUnavailableError as exc:
                is_last = attempt == self._config.max_judge_retries
                _log.warning(
                    "judge_unavailable",
                    run_id=run_id,
                    question_id=sample.question_id,
                    attempt=attempt,
                    max_retries=self._config.max_judge_retries,
                    action="fail" if is_last else "retry",
                    error=str(exc),
                )
                if is_last:
                    return _NAN_RUBRIC
                await asyncio.sleep(self._config.retry_backoff_s)
        return _NAN_RUBRIC  # satisfaz o type-checker (inalcançável)
