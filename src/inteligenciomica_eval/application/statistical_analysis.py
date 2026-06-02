"""StatisticalAnalysisUseCase — TAREFA-405 (ADR-011, §14.7).

Use case de application que orquestra os três adapters de estatística
(Wilcoxon, Friedman+Nemenyi, MLM) e aplica correção para múltiplos testes
(Benjamini-Hochberg ou Holm) via ``statsmodels.stats.multitest.multipletests``.

Decisão de análise: a estatística é executada sobre o Experimento A (``phase="A"``).
O Experimento B (``phase="B"``) usa base fixa como diagnóstico complementar -
não é incluído nesta análise principal (§8.1-8.5, doc-base).

Contrato de importação: ``statsmodels.stats.multitest`` é o único sub-módulo de
statsmodels permitido em application (utilitário de correção, não de análise
estatística). A exceção está registrada em ``.importlinter``
(``ignore_imports = application.statistical_analysis -> statsmodels``).
As libs de análise estatística (``scipy``, ``statsmodels.formula``, etc.) ficam
exclusivamente nos adapters de infraestrutura.
"""

from __future__ import annotations

import dataclasses
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from statsmodels.stats.multitest import multipletests

from inteligenciomica_eval.domain.ports import (
    FriedmanReport,
    MLMReport,
    ResultReaderPort,
    StatsPort,
    WilcoxonReport,
)
from inteligenciomica_eval.domain.value_objects import StatsReport

_log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# Mapeamento de nomes canônicos do projeto para os identificadores do statsmodels
_CORRECTION_METHOD_MAP: dict[str, str] = {
    "benjamini-hochberg": "fdr_bh",
    "holm": "holm",
}


@dataclass(frozen=True)
class StatisticsInput:
    """Input DTO para StatisticalAnalysisUseCase.

    Args:
        run_id: identificador do run de avaliação a analisar.
        round_id: identificador da rodada (ex.: ``"round_1"``).
        metrics: tupla de métricas a testar; padrão ``("final_score",)``.
        tests: subconjunto de testes a executar — ``"wilcoxon"``, ``"friedman"``,
            ``"mlm"`` ou ``"all"`` para todos os três.
        alpha: nível de significância (padrão 0.05).
        correction_method: método de correção múltipla — ``"benjamini-hochberg"``
            (FDR, padrão) ou ``"holm"`` (FWER).
    """

    run_id: str
    round_id: str
    metrics: tuple[str, ...] = ("final_score",)
    tests: tuple[str, ...] = ("all",)
    alpha: float = 0.05
    correction_method: str = "benjamini-hochberg"


def _nan_to_null(obj: Any) -> Any:
    """Substitui float NaN por None para serialização JSON válida (RFC 8259)."""
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: _nan_to_null(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_nan_to_null(v) for v in obj]
    return obj


def _derive_top_llm_by_friedman(
    friedman_reports: list[FriedmanReport],
) -> str | None:
    """Identifica o LLM com mais vitórias nos pares Nemenyi significativos.

    Conta as vitórias de cada LLM usando ``NemenyiPair.winner`` (populado pelo
    ``FriedmanNemenyiAdapter`` como o LLM com média superior no bloco). Em
    empate, retorna o primeiro em ordem alfabética. Retorna ``None`` se não
    houver vitórias registradas (pares não significativos ou ``winner=None``).

    Args:
        friedman_reports: lista de relatórios Friedman+Nemenyi (com correção
            já aplicada).

    Returns:
        Identificador do LLM com mais vitórias ou ``None``.
    """
    wins: dict[str, int] = {}
    for report in friedman_reports:
        for pair in report.nemenyi_pairs:
            if pair.significant and pair.winner is not None:
                wins[pair.winner] = wins.get(pair.winner, 0) + 1
    if not wins:
        return None
    max_count = max(wins.values())
    candidates = sorted(k for k, v in wins.items() if v == max_count)
    return candidates[0]


def _apply_multiple_correction(
    wilcoxon_reports: list[WilcoxonReport],
    friedman_reports: list[FriedmanReport],
    method: str,
    alpha: float,
) -> tuple[list[WilcoxonReport], list[FriedmanReport]]:
    """Aplica correção para múltiplos testes (BH ou Holm) via ``multipletests``.

    Coleta todos os p-values não-NaN dos Wilcoxon e Friedman reports, aplica
    ``statsmodels.stats.multitest.multipletests`` e devolve cópias atualizadas
    dos reports com ``p_value_corrected`` e ``significant`` preenchidos.

    Os MLMReports NÃO são incluídos nesta correção — eles testam hipóteses
    diferentes (efeito de interação, §8.3) e são analisados separadamente.

    Args:
        wilcoxon_reports: lista de WilcoxonReport com p_values brutos.
        friedman_reports: lista de FriedmanReport com p_values brutos.
        method: ``"benjamini-hochberg"`` ou ``"holm"``.
        alpha: nível de significância.

    Returns:
        Par ``(wilcoxon_reports_atualizados, friedman_reports_atualizados)``.
    """
    all_p: list[float] = []
    positions: list[tuple[str, int]] = []  # ("w" | "f", índice na lista)

    for i, wr in enumerate(wilcoxon_reports):
        if not math.isnan(wr.p_value):
            all_p.append(wr.p_value)
            positions.append(("w", i))

    for i, fr in enumerate(friedman_reports):
        if not math.isnan(fr.p_value):
            all_p.append(fr.p_value)
            positions.append(("f", i))

    if not all_p:
        return wilcoxon_reports, friedman_reports

    sm_method = _CORRECTION_METHOD_MAP.get(method, method)
    _, p_corrected_arr, _, _ = multipletests(all_p, alpha=alpha, method=sm_method)

    new_wilcoxon = list(wilcoxon_reports)
    new_friedman = list(friedman_reports)

    for k, (kind, idx) in enumerate(positions):
        p_corr = float(p_corrected_arr[k])
        if kind == "w":
            new_wilcoxon[idx] = dataclasses.replace(
                new_wilcoxon[idx],
                p_value_corrected=p_corr,
                significant=p_corr < alpha,
            )
        else:
            new_friedman[idx] = dataclasses.replace(
                new_friedman[idx],
                p_value_corrected=p_corr,
                significant=p_corr < alpha,
            )

    return new_wilcoxon, new_friedman


class StatisticalAnalysisUseCase:
    """Orquestra a bateria estatística completa para um run/rodada (TAREFA-405).

    Lê os resultados da Fase A via ``ResultReaderPort``, executa os testes
    selecionados (Wilcoxon, Friedman+Nemenyi, MLM), aplica correção para
    múltiplos testes nos p-values de Wilcoxon e Friedman e produz um
    ``StatsReport`` com síntese executiva. O relatório é persistido como JSON
    em ``data_dir`` e retornado ao caller.

    Args:
        reader: port de leitura de resultados (``ResultReaderPort``).
        wilcoxon_adapter: adapter para teste de Wilcoxon pareado (``StatsPort``).
        friedman_adapter: adapter para Friedman+Nemenyi (``StatsPort``).
        mlm_adapter: adapter para modelo linear misto (``StatsPort``).
        data_dir: diretório onde o JSON de análise será gravado.
    """

    def __init__(
        self,
        reader: ResultReaderPort,
        wilcoxon_adapter: StatsPort,
        friedman_adapter: StatsPort,
        mlm_adapter: StatsPort,
        data_dir: Path,
    ) -> None:
        self._reader = reader
        self._wilcoxon = wilcoxon_adapter
        self._friedman = friedman_adapter
        self._mlm = mlm_adapter
        self._data_dir = data_dir

    def execute(self, inp: StatisticsInput) -> StatsReport:
        """Executa análise estatística e persiste o relatório JSON.

        Carrega resultados da Fase A (``phase="A"``), executa os testes
        selecionados por ``inp.tests``, aplica correção BH ou Holm aos
        p-values de Wilcoxon e Friedman, deriva os campos de síntese e
        grava ``{run_id}_{round_id}_stats.json`` em ``data_dir``.

        Args:
            inp: parâmetros de entrada com run_id, round_id, métricas, testes
                e configuração de correção.

        Returns:
            :class:`~inteligenciomica_eval.domain.value_objects.StatsReport`
            com todos os resultados e campos de síntese preenchidos.
        """
        t0 = time.monotonic()

        frame = self._reader.load(
            round_id=inp.round_id,
            phase="A",
            run_id=inp.run_id,
        )

        run_wilcoxon = "wilcoxon" in inp.tests or "all" in inp.tests
        run_friedman = "friedman" in inp.tests or "all" in inp.tests
        run_mlm = "mlm" in inp.tests or "all" in inp.tests

        wilcoxon_reports: list[WilcoxonReport] = []
        friedman_reports: list[FriedmanReport] = []
        mlm_reports: list[MLMReport] = []

        for metric in inp.metrics:
            if run_wilcoxon:
                wilcoxon_reports.append(self._wilcoxon.wilcoxon_paired(frame, metric))
            if run_friedman:
                friedman_reports.append(self._friedman.friedman_nemenyi(frame, metric))
            if run_mlm:
                formula = f"{metric} ~ base * llm + (1 | question_id)"
                mlm_reports.append(self._mlm.mixed_linear_model(frame, formula))

        wilcoxon_reports, friedman_reports = _apply_multiple_correction(
            wilcoxon_reports,
            friedman_reports,
            inp.correction_method,
            inp.alpha,
        )

        base_difference_significant = any(r.significant for r in wilcoxon_reports)
        llm_difference_significant = any(r.significant for r in friedman_reports)
        interaction_significant = any(
            not math.isnan(r.interaction_p_value) and r.interaction_p_value < inp.alpha
            for r in mlm_reports
        )
        top_llm = _derive_top_llm_by_friedman(friedman_reports)

        report = StatsReport(
            run_id=inp.run_id,
            round_id=inp.round_id,
            wilcoxon_reports=tuple(wilcoxon_reports),
            friedman_reports=tuple(friedman_reports),
            mlm_reports=tuple(mlm_reports),
            correction_method=inp.correction_method,
            alpha=inp.alpha,
            base_difference_significant=base_difference_significant,
            llm_difference_significant=llm_difference_significant,
            interaction_significant=interaction_significant,
            top_llm_by_friedman=top_llm,
        )

        output_path = self._data_dir / f"{inp.run_id}_{inp.round_id}_stats.json"
        output_path.write_text(
            json.dumps(_nan_to_null(dataclasses.asdict(report)), indent=2),
            encoding="utf-8",
        )

        latency_ms = int((time.monotonic() - t0) * 1000)
        _log.info(
            "statistical_analysis_completed",
            run_id=inp.run_id,
            round_id=inp.round_id,
            n_wilcoxon=len(wilcoxon_reports),
            n_friedman=len(friedman_reports),
            n_mlm=len(mlm_reports),
            base_difference_significant=base_difference_significant,
            llm_difference_significant=llm_difference_significant,
            interaction_significant=interaction_significant,
            top_llm_by_friedman=top_llm,
            latency_ms=latency_ms,
        )

        return report
