from __future__ import annotations

from inteligenciomica_eval.domain.ports import (
    CriticalAnnotation,
    FriedmanReport,
    MLMReport,
    NemenyiPair,
    ResultFrame,
    WilcoxonReport,
)

_DEFAULT_WILCOXON = WilcoxonReport(
    metric="final_score",
    base_a="ID_230K",
    base_b="IDx_400k",
    statistic=0.0,
    p_value=0.03,
    p_value_corrected=None,
    significant=True,
    n_pairs=13,
    effect_size_r=0.35,
)
_DEFAULT_FRIEDMAN = FriedmanReport(
    metric="final_score",
    chi2_statistic=8.4,
    p_value=0.015,
    p_value_corrected=None,
    significant=True,
    n_groups=3,
    n_blocks=13,
    nemenyi_pairs=(
        NemenyiPair(llm_a="llm-a", llm_b="llm-b", p_value=0.02, significant=True),
    ),
)
_DEFAULT_MLM = MLMReport(
    formula="final_score ~ base * llm + (1 | question_id)",
    base_effect_coef=0.12,
    base_effect_p_value=0.03,
    llm_effect_p_values={"llm-b": 0.04, "llm-c": 0.12},
    interaction_p_value=0.08,
    interaction_significant=False,
    aic=118.0,
    n_observations=78,
    convergence_warning=False,
)


class FakeGoldChunkReader:
    """In-memory GoldChunkReaderPort returning planted gold-chunk lists.

    Args:
        mapping: question_id → list of gold chunk ID strings. Unknown question IDs
            fall back to ``default_golds``.
        default_golds: chunk IDs returned when the question_id is not in mapping.
    """

    def __init__(
        self,
        mapping: dict[str, list[str]] | None = None,
        *,
        default_golds: list[str] | None = None,
    ) -> None:
        self._mapping: dict[str, list[str]] = mapping or {}
        self._default_golds: list[str] = (
            default_golds
            if default_golds is not None
            else [
                "gold-chunk-0",
                "gold-chunk-1",
            ]
        )

    def gold_for(self, question_id: str) -> list[str]:
        """Return planted gold chunk IDs for *question_id*.

        Args:
            question_id: identifier of the question.

        Returns:
            List of gold chunk ID strings (new list each call).
        """
        return list(self._mapping.get(question_id, self._default_golds))


class FakeAnnotationReader:
    """In-memory AnnotationReaderPort returning planted critical annotations.

    Args:
        mapping: run_id → list of CriticalAnnotation objects. Unknown run IDs
            return an empty list.
    """

    def __init__(
        self,
        mapping: dict[str, list[CriticalAnnotation]] | None = None,
    ) -> None:
        self._mapping: dict[str, list[CriticalAnnotation]] = mapping or {}

    def read(self, run_id: str) -> list[CriticalAnnotation]:
        """Return the planted annotations for *run_id*.

        Args:
            run_id: run identifier to look up.

        Returns:
            List of CriticalAnnotation objects; empty list for unknown run IDs.
        """
        return list(self._mapping.get(run_id, []))


class FakeStats:
    """In-memory StatsPort returning fixed deterministic statistical reports.

    Args:
        wilcoxon: fixed WilcoxonReport to return. Defaults to canonical values.
        friedman: fixed FriedmanReport to return. Defaults to canonical values.
        mlm: fixed MLMReport to return. Defaults to canonical values.
    """

    def __init__(
        self,
        *,
        wilcoxon: WilcoxonReport | None = None,
        friedman: FriedmanReport | None = None,
        mlm: MLMReport | None = None,
    ) -> None:
        self._wilcoxon = wilcoxon if wilcoxon is not None else _DEFAULT_WILCOXON
        self._friedman = friedman if friedman is not None else _DEFAULT_FRIEDMAN
        self._mlm = mlm if mlm is not None else _DEFAULT_MLM

    def wilcoxon_paired(self, frame: ResultFrame, metric: str) -> WilcoxonReport:
        """Return the configured WilcoxonReport.

        Args:
            frame: result frame (accepted but unused).
            metric: metric name (accepted but unused).

        Returns:
            Fixed WilcoxonReport.
        """
        return self._wilcoxon

    def friedman_nemenyi(self, frame: ResultFrame, metric: str) -> FriedmanReport:
        """Return the configured FriedmanReport.

        Args:
            frame: result frame (accepted but unused).
            metric: metric name (accepted but unused).

        Returns:
            Fixed FriedmanReport.
        """
        return self._friedman

    def mixed_linear_model(self, frame: ResultFrame, formula: str) -> MLMReport:
        """Return a MLMReport with the passed *formula* and fixed numeric fields.

        Args:
            frame: result frame (accepted but unused).
            formula: Wilkinson formula string used as the returned report's formula.

        Returns:
            MLMReport with the given formula and the configured fields.
        """
        return MLMReport(
            formula=formula,
            base_effect_coef=self._mlm.base_effect_coef,
            base_effect_p_value=self._mlm.base_effect_p_value,
            llm_effect_p_values=dict(self._mlm.llm_effect_p_values),
            interaction_p_value=self._mlm.interaction_p_value,
            interaction_significant=self._mlm.interaction_significant,
            aic=self._mlm.aic,
            n_observations=self._mlm.n_observations,
            convergence_warning=self._mlm.convergence_warning,
        )
