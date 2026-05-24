from __future__ import annotations

import math
import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from inteligenciomica_eval.domain.entities import EvaluationResult
from inteligenciomica_eval.domain.services.rank_score import (
    RankScoreCalculator,
    RankScoreInputs,
)
from inteligenciomica_eval.domain.value_objects import BaseId, LLMId, RankScore


@dataclass(frozen=True, slots=True)
class ConfigAggregate:
    """Agregado de métricas para uma configuração {base, llm} (§7.2 doc-base).

    Campos numéricos são ``NaN`` quando não computáveis (e.g., nenhuma observação
    válida, ou ausência total de anotações de falha crítica).

    IQR calculado com ``statistics.quantiles(data, n=4, method='inclusive')``
    (percentis por interpolação linear — quantis tipo Tukey/inclusive, Python ≥ 3.10).
    Retorna ``NaN`` se ``n_observations < 2``.

    ``critical_failure_rate``: somente observações com ``critical_failure_flag ≠ None``
    entram no denominador (ADR-010 — Camada 3 opcional). Retorna ``NaN`` se nenhuma
    observação foi anotada.

    Args:
        base: identificador da base de conhecimento.
        llm: identificador do modelo LLM.
        mean_score: média aritmética dos FinalScores válidos (não-NaN).
        median_score: mediana dos FinalScores válidos.
        min_score: mínimo dos FinalScores válidos.
        iqr: intervalo interquartil (Q3-Q1) dos FinalScores válidos.
        failure_rate: fração de observações válidas com FinalScore < threshold,
            calculada via ``EvaluationResult.is_failure(threshold)``.
        critical_failure_rate: fração de observações *anotadas* com
            ``critical_failure_flag == 1`` (flag ``None`` excluída do denominador).
        win_rate: fração de perguntas em que esta config supera as demais;
            empate de k configs resulta em 1/k por config.
        rank_score: score composto de ranking (§7.3 doc-base).
        n_observations: número de observações com FinalScore válido (não-NaN).
        n_excluded_nan: número de observações excluídas por FinalScore NaN.
    """

    base: BaseId
    llm: LLMId
    mean_score: float
    median_score: float
    min_score: float
    iqr: float
    failure_rate: float
    critical_failure_rate: float
    win_rate: float
    rank_score: RankScore
    n_observations: int
    n_excluded_nan: int


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _valid_scores(results: list[EvaluationResult]) -> list[float]:
    """Return non-NaN FinalScore values for the group."""
    return [r.final_score.value for r in results if not math.isnan(r.final_score.value)]


def _iqr(values: list[float]) -> float:
    """IQR = Q3 - Q1 via ``statistics.quantiles(method='inclusive')``.

    Uses the inclusive (Tukey) linear-interpolation method. Returns ``NaN``
    for fewer than 2 values — IQR is undefined for a single point.
    """
    if len(values) < 2:
        return float("nan")
    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return q3 - q1


def _critical_failure_rate(results: list[EvaluationResult]) -> float:
    """Fração de observações *anotadas* com ``critical_failure_flag == 1``.

    Observações com ``flag = None`` (Camada 3 não executada) são excluídas
    do denominador (ADR-010). Retorna ``NaN`` se nenhuma observação foi anotada.
    """
    annotated = [r for r in results if r.critical_failure_flag is not None]
    if not annotated:
        return float("nan")
    critical_count = sum(1 for r in annotated if r.critical_failure_flag == 1)
    return critical_count / len(annotated)


def _win_rates(
    groups: dict[tuple[str, str], list[EvaluationResult]],
) -> dict[tuple[str, str], float]:
    """Compute win_rate per config by comparing all configs per question_id.

    For each question_id the per-config score is the mean of valid FinalScores
    for that (config, question_id) pair. Configs with no valid score for a question
    receive 0 fractional wins. When k configs share the maximum score for a question
    each receives 1/k (tie-splitting). win_rate = total_wins / n_distinct_questions.
    """
    all_qids: set[str] = set()
    for grp in groups.values():
        for r in grp:
            all_qids.add(r.answer.question.question_id)

    n_questions = len(all_qids)
    if n_questions == 0:
        return {k: float("nan") for k in groups}

    config_q_mean: dict[tuple[str, str], dict[str, float]] = {}
    for key, grp in groups.items():
        q_acc: dict[str, list[float]] = defaultdict(list)
        for r in grp:
            s = r.final_score.value
            if not math.isnan(s):
                q_acc[r.answer.question.question_id].append(s)
        config_q_mean[key] = {
            qid: statistics.mean(scores) for qid, scores in q_acc.items()
        }

    config_keys = list(groups.keys())
    wins: dict[tuple[str, str], float] = dict.fromkeys(config_keys, 0.0)

    for qid in all_qids:
        q_scores = [
            (key, config_q_mean[key][qid])
            for key in config_keys
            if qid in config_q_mean[key]
        ]
        if not q_scores:
            continue
        max_score = max(s for _, s in q_scores)
        tied = [key for key, s in q_scores if s == max_score]
        share = 1.0 / len(tied)
        for key in tied:
            wins[key] += share

    return {key: wins[key] / n_questions for key in config_keys}


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AggregationService:
    """Serviço de domínio para agregação de EvaluationResults por configuração {base, llm}.

    Agrupa resultados por (base, llm), computa agregados estatísticos (§7.2),
    resolve win_rate cross-config por question_id e delega o cálculo de rank_score ao
    ``RankScoreCalculator`` injetado (§7.3).

    Puro: stdlib apenas (``math``, ``statistics``, ``collections``); sem pandas/numpy;
    sem I/O. Determinístico; sem estado mutável entre chamadas.

    Args:
        rank_calculator: instância de ``RankScoreCalculator`` (injeção de dependência).
    """

    def __init__(self, rank_calculator: RankScoreCalculator) -> None:
        self._rank_calculator = rank_calculator

    def aggregate_all(
        self,
        results: Sequence[EvaluationResult],
        *,
        threshold: float,
    ) -> tuple[ConfigAggregate, ...]:
        """Agrega resultados por config e resolve win_rate cross-config.

        Agrupa por (base, llm), calcula mean/median/min/IQR/failure_rate/
        critical_failure_rate, resolve win_rate comparando todas as configs por
        question_id, e computa rank_score via ``RankScoreCalculator``.

        NaN propagation (ADR-007): FinalScores NaN são excluídos de todos os
        cálculos numéricos e contados em ``n_excluded_nan``. Se todas as
        observações de uma config forem NaN, os agregados numéricos são NaN e
        ``n_observations = 0``.

        Args:
            results: sequência de ``EvaluationResult`` materializados.
            threshold: limiar de falha passado a ``EvaluationResult.is_failure()``
                (ex.: ``0.70``).

        Returns:
            Tupla de ``ConfigAggregate``, ordenada por ``(base.value, llm.value)``.
        """
        groups: dict[tuple[str, str], list[EvaluationResult]] = defaultdict(list)
        for r in results:
            groups[(r.answer.base.value, r.answer.llm.value)].append(r)

        if not groups:
            return ()

        win_rate_map = _win_rates(groups)

        out: list[ConfigAggregate] = []
        for key in sorted(groups):
            base_val, llm_val = key
            grp = groups[key]
            valid = _valid_scores(grp)
            n_excl = len(grp) - len(valid)
            n_obs = len(valid)

            if n_obs == 0:
                mean_s = median_s = min_s = iqr_s = fail_r = float("nan")
            else:
                mean_s = statistics.mean(valid)
                median_s = statistics.median(valid)
                min_s = min(valid)
                iqr_s = _iqr(valid)
                fail_r = sum(1 for r in grp if r.is_failure(threshold)) / n_obs

            crit_r = _critical_failure_rate(grp)
            wr = win_rate_map[key]

            rank_inputs = RankScoreInputs(
                median_score=median_s,
                failure_rate=fail_r,
                win_rate=wr,
                critical_failure_rate=crit_r,
            )
            rank_s = self._rank_calculator.compute(rank_inputs)

            out.append(
                ConfigAggregate(
                    base=BaseId(base_val),
                    llm=LLMId(llm_val),
                    mean_score=mean_s,
                    median_score=median_s,
                    min_score=min_s,
                    iqr=iqr_s,
                    failure_rate=fail_r,
                    critical_failure_rate=crit_r,
                    win_rate=wr,
                    rank_score=rank_s,
                    n_observations=n_obs,
                    n_excluded_nan=n_excl,
                )
            )

        return tuple(out)
