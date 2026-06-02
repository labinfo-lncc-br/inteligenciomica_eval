"""Adapters estatísticos: Wilcoxon, Friedman+Nemenyi, Modelo Linear Misto.

TAREFA-404 (ADR-011, §5.1 StatsPort). Três adapters concretos que implementam
``StatsPort`` estruturalmente. Cada um tem um método primário real; os outros dois
levantam ``NotImplementedError`` — mas todos os 3 métodos estão presentes para que
``isinstance(adapter, StatsPort)`` passe com ``@runtime_checkable``.

Dependências de I/O (scipy, statsmodels, scikit-posthocs, pandas) ficam SOMENTE
neste módulo de infraestrutura — proibidas em ``domain/`` e ``application/``
pelo import-linter (.importlinter contratos 1 e 2).
"""

from __future__ import annotations

import math
import re
import time
from typing import Any

import pandas as pd
import scikit_posthocs as sp
import statsmodels.formula.api as smf
import structlog
from scipy.stats import friedmanchisquare, norm, wilcoxon

from inteligenciomica_eval.domain.entities import EvaluationResult
from inteligenciomica_eval.domain.ports import ResultFrame
from inteligenciomica_eval.domain.value_objects import (
    FriedmanReport,
    MLMReport,
    NemenyiPair,
    WilcoxonReport,
)
from inteligenciomica_eval.infrastructure.config.adapter_configs import (
    StatsAdapterConfig,
)

logger = structlog.get_logger(__name__)

# Regex para extrair a variável de efeitos aleatórios no estilo R/lme4.
# Exemplo: "final_score ~ base * llm + (1 | question_id)" → groups_var = "question_id"
_RE_RANDOM_EFFECT = re.compile(r"\+\s*\(1\s*\|\s*(\w+)\s*\)")


# ---------------------------------------------------------------------------
# Helpers internos — sem exposição pública
# ---------------------------------------------------------------------------


def _get_metric_value(result: EvaluationResult, metric: str) -> float:
    """Extrai o valor numérico de uma métrica de um EvaluationResult.

    Args:
        result: resultado de avaliação.
        metric: ``"final_score"`` ou qualquer campo de ``MetricVector``.

    Returns:
        Valor float (pode ser NaN).

    Raises:
        AttributeError: se a métrica não existir em ``MetricVector``.
    """
    if metric == "final_score":
        return result.final_score.value
    return float(getattr(result.metrics, metric))


def _parse_formula(formula: str) -> tuple[str, str]:
    """Remove sintaxe de efeitos aleatórios R/lme4 e extrai a variável de grupos.

    Args:
        formula: fórmula Wilkinson (ex.: ``"y ~ a * b + (1 | group)"``).

    Returns:
        Tupla ``(formula_limpa, groups_var)`` para statsmodels.
    """
    m = _RE_RANDOM_EFFECT.search(formula)
    groups_var = m.group(1) if m else "question_id"
    clean = _RE_RANDOM_EFFECT.sub("", formula).strip().rstrip("+").strip()
    return clean, groups_var


def _result_frame_to_df(frame: ResultFrame) -> pd.DataFrame:
    """Converte ResultFrame para pandas DataFrame com todas as colunas analíticas.

    Args:
        frame: conjunto de resultados de avaliação.

    Returns:
        DataFrame com colunas: ``question_id``, ``base``, ``llm``, ``seed``,
        ``final_score``, e os 8 campos de ``MetricVector``.
    """
    rows = []
    for r in frame.results:
        rows.append(
            {
                "question_id": r.answer.question.question_id,
                "base": r.answer.base.value,
                "llm": r.answer.llm.value,
                "seed": r.answer.seed.value,
                "final_score": r.final_score.value,
                "answer_correctness": r.metrics.answer_correctness,
                "answer_similarity": r.metrics.answer_similarity,
                "faithfulness": r.metrics.faithfulness,
                "context_precision": r.metrics.context_precision,
                "context_recall": r.metrics.context_recall,
                "answer_relevancy": r.metrics.answer_relevancy,
                "bertscore_f1": r.metrics.bertscore_f1,
                "rubric_biomed_score": r.metrics.rubric_biomed_score,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Adapter 1 — WilcoxonAdapter
# ---------------------------------------------------------------------------


class WilcoxonAdapter:
    """Teste de Wilcoxon pareado entre as duas bases de conhecimento (TAREFA-404).

    Pareia observações por ``(question_id, seed)``. Extrai as duas bases do
    ``ResultFrame`` em ordem alfabética. Retorna ``significant=False`` com
    ``p_value=1.0`` e ``n_pairs=0`` para amostra insuficiente (< ``min_pairs``)
    ou se houver < 2 bases — sem levantar exceção (ADR-007).

    Os métodos ``friedman_nemenyi`` e ``mixed_linear_model`` levantam
    ``NotImplementedError`` — use ``FriedmanNemenyiAdapter`` e
    ``MixedLinearModelAdapter`` para essas análises. Todos os 3 métodos do
    ``StatsPort`` estão presentes para que ``isinstance(adapter, StatsPort)``
    passe com ``@runtime_checkable``.

    Args:
        config: configuração (alpha, min_pairs, método de correção).
    """

    def __init__(self, config: StatsAdapterConfig | None = None) -> None:
        self._cfg = config or StatsAdapterConfig()

    def wilcoxon_paired(self, frame: ResultFrame, metric: str) -> WilcoxonReport:
        """Executa Wilcoxon pareado para a métrica sobre as 2 bases do frame.

        Args:
            frame: resultados contendo as duas bases a comparar.
            metric: nome da métrica (``"final_score"`` ou campo MetricVector).

        Returns:
            :class:`WilcoxonReport` com estatística, p-valor e effect size r.
        """
        t0 = time.perf_counter()

        bases = sorted({r.answer.base.value for r in frame.results})
        if len(bases) < 2:
            logger.warning(
                "wilcoxon_insufficient_bases",
                metric=metric,
                n_bases=len(bases),
            )
            base_a = bases[0] if bases else "?"
            base_b = "?"
            return self._degenerate(metric=metric, base_a=base_a, base_b=base_b)

        base_a, base_b = bases[0], bases[1]

        by_base_a: dict[tuple[str, int], float] = {}
        by_base_b: dict[tuple[str, int], float] = {}
        for r in frame.results:
            key = (r.answer.question.question_id, r.answer.seed.value)
            val = _get_metric_value(r, metric)
            if math.isnan(val):
                continue
            if r.answer.base.value == base_a:
                by_base_a[key] = val
            elif r.answer.base.value == base_b:
                by_base_b[key] = val

        common = sorted(set(by_base_a) & set(by_base_b))
        n_pairs = len(common)

        if n_pairs < self._cfg.min_pairs_wilcoxon:
            logger.warning(
                "wilcoxon_insufficient_pairs",
                metric=metric,
                n_pairs=n_pairs,
                min_required=self._cfg.min_pairs_wilcoxon,
            )
            return self._degenerate(metric=metric, base_a=base_a, base_b=base_b)

        x = [by_base_a[k] for k in common]
        y = [by_base_b[k] for k in common]

        stat, p = wilcoxon(x, y, alternative="two-sided", zero_method="wilcox")
        stat_f = float(stat)
        p_f = float(p)

        z = float(norm.ppf(1.0 - p_f / 2.0))
        effect_size_r: float | None = z / math.sqrt(n_pairs) if n_pairs > 0 else None

        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "wilcoxon_paired_computed",
            metric=metric,
            base_a=base_a,
            base_b=base_b,
            statistic=stat_f,
            p_value=p_f,
            n_pairs=n_pairs,
            effect_size_r=effect_size_r,
            latency_ms=latency_ms,
        )

        return WilcoxonReport(
            metric=metric,
            base_a=base_a,
            base_b=base_b,
            statistic=stat_f,
            p_value=p_f,
            p_value_corrected=None,
            significant=p_f < self._cfg.alpha,
            n_pairs=n_pairs,
            effect_size_r=effect_size_r,
        )

    def _degenerate(self, *, metric: str, base_a: str, base_b: str) -> WilcoxonReport:
        return WilcoxonReport(
            metric=metric,
            base_a=base_a,
            base_b=base_b,
            statistic=0.0,
            p_value=1.0,
            p_value_corrected=None,
            significant=False,
            n_pairs=0,
            effect_size_r=None,
        )

    # Métodos do StatsPort não implementados por este adapter
    def friedman_nemenyi(self, frame: ResultFrame, metric: str) -> FriedmanReport:
        """Não implementado — use FriedmanNemenyiAdapter."""
        raise NotImplementedError("Use FriedmanNemenyiAdapter.friedman_nemenyi")

    def mixed_linear_model(self, frame: ResultFrame, formula: str) -> MLMReport:
        """Não implementado — use MixedLinearModelAdapter."""
        raise NotImplementedError("Use MixedLinearModelAdapter.mixed_linear_model")


# ---------------------------------------------------------------------------
# Adapter 2 — FriedmanNemenyiAdapter
# ---------------------------------------------------------------------------


class FriedmanNemenyiAdapter:
    """Teste de Friedman + pós-hoc Nemenyi sobre LLMs (TAREFA-404).

    Bloqueia por ``(question_id, seed, base)``. Pós-hoc só é calculado quando
    ``p_value < alpha``. Retorna ``significant=False`` com ``nemenyi_pairs=()``
    se < 3 LLMs — sem exceção (ADR-007).

    Os métodos ``wilcoxon_paired`` e ``mixed_linear_model`` levantam
    ``NotImplementedError``.

    Args:
        config: configuração (alpha, etc.).
    """

    def __init__(self, config: StatsAdapterConfig | None = None) -> None:
        self._cfg = config or StatsAdapterConfig()

    def friedman_nemenyi(self, frame: ResultFrame, metric: str) -> FriedmanReport:
        """Executa Friedman + Nemenyi pós-hoc sobre os LLMs do frame.

        Args:
            frame: resultados com múltiplos LLMs.
            metric: nome da métrica.

        Returns:
            :class:`FriedmanReport` com chi², p-valor e pares Nemenyi.
        """
        t0 = time.perf_counter()

        llms = sorted({r.answer.llm.value for r in frame.results})
        n_groups = len(llms)

        if n_groups < 3:
            logger.warning(
                "friedman_insufficient_groups",
                metric=metric,
                n_groups=n_groups,
                min_required=3,
            )
            return self._degenerate(metric=metric, n_groups=n_groups)

        # Indexar por LLM → {(question_id, seed, base): metric_value}
        by_llm: dict[str, dict[tuple[str, int, str], float]] = {llm: {} for llm in llms}
        for r in frame.results:
            llm = r.answer.llm.value
            if llm not in by_llm:
                continue
            key = (
                r.answer.question.question_id,
                r.answer.seed.value,
                r.answer.base.value,
            )
            val = _get_metric_value(r, metric)
            if not math.isnan(val):
                by_llm[llm][key] = val

        # Blocos comuns a todos os LLMs
        common_blocks = sorted(
            set.intersection(*[set(by_llm[llm].keys()) for llm in llms])
        )
        n_blocks = len(common_blocks)

        if n_blocks < 1:
            logger.warning(
                "friedman_no_common_blocks",
                metric=metric,
                n_groups=n_groups,
            )
            return self._degenerate(metric=metric, n_groups=n_groups)

        # Matriz (n_blocks, n_groups) para Friedman e Nemenyi
        import numpy as np  # local import — numpy é transitivo de scipy

        groups_arrays = [[by_llm[llm][b] for b in common_blocks] for llm in llms]
        data_matrix = np.array(groups_arrays).T  # (n_blocks, n_groups)

        stat, p = friedmanchisquare(*groups_arrays)
        stat_f = float(stat)
        p_f = float(p)
        significant = p_f < self._cfg.alpha

        # Médias por grupo — usadas para determinar o vencedor em cada par Nemenyi
        mean_scores = [float(np.mean(groups_arrays[k])) for k in range(n_groups)]

        nemenyi_pairs: list[NemenyiPair] = []
        if significant:
            ph = sp.posthoc_nemenyi_friedman(data_matrix)
            for i in range(n_groups):
                for j in range(i + 1, n_groups):
                    pv = float(ph.iloc[i, j])
                    pair_sig = pv < self._cfg.alpha
                    # Vencedor: LLM com média superior no bloco; None se não significativo
                    winner: str | None = None
                    if pair_sig:
                        winner = llms[i] if mean_scores[i] > mean_scores[j] else llms[j]
                    nemenyi_pairs.append(
                        NemenyiPair(
                            llm_a=llms[i],
                            llm_b=llms[j],
                            p_value=pv,
                            significant=pair_sig,
                            winner=winner,
                        )
                    )

        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "friedman_nemenyi_computed",
            metric=metric,
            chi2_statistic=stat_f,
            p_value=p_f,
            n_groups=n_groups,
            n_blocks=n_blocks,
            n_nemenyi_pairs=len(nemenyi_pairs),
            latency_ms=latency_ms,
        )

        return FriedmanReport(
            metric=metric,
            chi2_statistic=stat_f,
            p_value=p_f,
            p_value_corrected=None,
            significant=significant,
            n_groups=n_groups,
            n_blocks=n_blocks,
            nemenyi_pairs=tuple(nemenyi_pairs),
        )

    def _degenerate(self, *, metric: str, n_groups: int) -> FriedmanReport:
        return FriedmanReport(
            metric=metric,
            chi2_statistic=0.0,
            p_value=1.0,
            p_value_corrected=None,
            significant=False,
            n_groups=n_groups,
            n_blocks=0,
            nemenyi_pairs=(),
        )

    # Métodos do StatsPort não implementados por este adapter
    def wilcoxon_paired(self, frame: ResultFrame, metric: str) -> WilcoxonReport:
        """Não implementado — use WilcoxonAdapter."""
        raise NotImplementedError("Use WilcoxonAdapter.wilcoxon_paired")

    def mixed_linear_model(self, frame: ResultFrame, formula: str) -> MLMReport:
        """Não implementado — use MixedLinearModelAdapter."""
        raise NotImplementedError("Use MixedLinearModelAdapter.mixed_linear_model")


# ---------------------------------------------------------------------------
# Adapter 3 — MixedLinearModelAdapter
# ---------------------------------------------------------------------------


class MixedLinearModelAdapter:
    """Modelo linear misto via statsmodels.formula.api (TAREFA-404, ADR-011).

    Converte ``ResultFrame`` para ``pandas.DataFrame`` internamente. Suporta a
    sintaxe R/lme4 ``(1 | grupo)`` na fórmula — o adapter extrai a variável de
    grupos e limpa a fórmula antes de passar ao statsmodels. Em falha numérica
    ou não-convergência, retorna p-values NaN e ``convergence_warning=True`` —
    nunca propaga exceção (ADR-007).

    Os métodos ``wilcoxon_paired`` e ``friedman_nemenyi`` levantam
    ``NotImplementedError``.

    Args:
        config: configuração (alpha, reml, etc.).
    """

    def __init__(self, config: StatsAdapterConfig | None = None) -> None:
        self._cfg = config or StatsAdapterConfig()

    def mixed_linear_model(self, frame: ResultFrame, formula: str) -> MLMReport:
        """Ajusta modelo linear misto com a fórmula Wilkinson fornecida.

        Args:
            frame: resultados de avaliação.
            formula: fórmula Wilkinson (ex.:
                ``"final_score ~ base * llm + (1 | question_id)"``).

        Returns:
            :class:`MLMReport` com coeficientes, p-valores e AIC.
        """
        t0 = time.perf_counter()
        df = _result_frame_to_df(frame)

        clean_formula, groups_var = _parse_formula(formula)
        if groups_var not in df.columns:
            logger.warning(
                "mlm_groups_column_missing",
                groups_var=groups_var,
                formula=formula,
            )
            groups_var = "question_id"

        try:
            model = smf.mixedlm(clean_formula, data=df, groups=df[groups_var])
            result = model.fit(reml=self._cfg.reml, method="lbfgs")

            if not bool(getattr(result, "converged", True)):
                logger.warning(
                    "mlm_non_convergence",
                    formula=formula,
                )
                return self._degenerate(formula=formula, convergence_warning=True)

            convergence_warning = False
            params: Any = result.params
            pvalues: Any = result.pvalues

            base_effect_coef, base_effect_p_value = self._extract_main_effect(
                params, pvalues, "base"
            )
            llm_effect_p_values = self._extract_group_effects(pvalues, "llm")
            interaction_p_value = self._extract_interaction_p(pvalues)
            interaction_significant = (
                interaction_p_value < self._cfg.alpha
                if not math.isnan(interaction_p_value)
                else False
            )

            aic = float(result.aic)
            n_obs = int(result.nobs)

        except Exception as exc:
            logger.warning(
                "mlm_numerical_failure",
                formula=formula,
                error=str(exc),
            )
            return self._degenerate(formula=formula)

        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "mlm_computed",
            formula=formula,
            base_effect_coef=base_effect_coef,
            base_effect_p_value=base_effect_p_value,
            interaction_p_value=interaction_p_value,
            interaction_significant=interaction_significant,
            aic=aic,
            n_observations=n_obs,
            convergence_warning=convergence_warning,
            latency_ms=latency_ms,
        )

        return MLMReport(
            formula=formula,
            base_effect_coef=base_effect_coef,
            base_effect_p_value=base_effect_p_value,
            llm_effect_p_values=llm_effect_p_values,
            interaction_p_value=interaction_p_value,
            interaction_significant=interaction_significant,
            aic=aic,
            n_observations=n_obs,
            convergence_warning=convergence_warning,
        )

    @staticmethod
    def _is_main_effect(name: str, variable: str) -> bool:
        """Retorna True se o coeficiente é efeito principal de ``variable``."""
        lower = name.lower()
        return variable in lower and ":" not in name and "intercept" not in lower

    def _extract_main_effect(
        self,
        params: Any,
        pvalues: Any,
        variable: str,
    ) -> tuple[float, float]:
        keys = [k for k in params.index if self._is_main_effect(k, variable)]
        if not keys:
            return float("nan"), float("nan")
        return float(params[keys[0]]), float(pvalues[keys[0]])

    def _extract_group_effects(self, pvalues: Any, variable: str) -> dict[str, float]:
        keys = [k for k in pvalues.index if self._is_main_effect(k, variable)]
        return {k: float(pvalues[k]) for k in keys}

    def _extract_interaction_p(self, pvalues: Any) -> float:
        int_keys = [k for k in pvalues.index if ":" in k]
        return float(pvalues[int_keys[0]]) if int_keys else float("nan")

    def _degenerate(
        self, *, formula: str, convergence_warning: bool = True
    ) -> MLMReport:
        return MLMReport(
            formula=formula,
            base_effect_coef=float("nan"),
            base_effect_p_value=float("nan"),
            llm_effect_p_values={},
            interaction_p_value=float("nan"),
            interaction_significant=False,
            aic=float("nan"),
            n_observations=0,
            convergence_warning=convergence_warning,
        )

    # Métodos do StatsPort não implementados por este adapter
    def wilcoxon_paired(self, frame: ResultFrame, metric: str) -> WilcoxonReport:
        """Não implementado — use WilcoxonAdapter."""
        raise NotImplementedError("Use WilcoxonAdapter.wilcoxon_paired")

    def friedman_nemenyi(self, frame: ResultFrame, metric: str) -> FriedmanReport:
        """Não implementado — use FriedmanNemenyiAdapter."""
        raise NotImplementedError("Use FriedmanNemenyiAdapter.friedman_nemenyi")
