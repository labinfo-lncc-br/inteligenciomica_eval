from __future__ import annotations

from inteligenciomica_eval.domain.ports import (
    AuxMetrics,
    EvaluationSample,
    Layer1Metrics,
    RubricResult,
)

_NAN = float("nan")

_DEFAULT_LAYER1 = Layer1Metrics(
    answer_correctness=0.80,
    answer_similarity=0.75,
    faithfulness=0.90,
    context_precision=0.85,
    context_recall=0.70,
    answer_relevancy=0.88,
)
_NAN_LAYER1 = Layer1Metrics(
    answer_correctness=_NAN,
    answer_similarity=_NAN,
    faithfulness=_NAN,
    context_precision=_NAN,
    context_recall=_NAN,
    answer_relevancy=_NAN,
)

_DEFAULT_RUBRIC = RubricResult(score=4.0, feedback="Canonical rubric feedback.")
_NAN_RUBRIC = RubricResult(
    score=_NAN, feedback="Parsing failed after retries (ADR-007)."
)

_DEFAULT_AUX = AuxMetrics(bertscore_f1=0.82)
_NAN_AUX = AuxMetrics(bertscore_f1=_NAN)


class FakeMetricSuite:
    """In-memory MetricSuitePort returning fixed or all-NaN Layer1Metrics.

    Args:
        fixed: Layer1Metrics to return for every sample. Defaults to canonical values.
        inject_nan: when True, ignore ``fixed`` and return all-NaN metrics to exercise
            the ADR-007 NaN-propagation path in use cases.
    """

    def __init__(
        self,
        fixed: Layer1Metrics | None = None,
        *,
        inject_nan: bool = False,
    ) -> None:
        self._fixed = fixed if fixed is not None else _DEFAULT_LAYER1
        self._inject_nan = inject_nan

    def score(self, sample: EvaluationSample) -> Layer1Metrics:
        """Return the configured Layer1Metrics.

        Args:
            sample: evaluation sample (accepted but unused).

        Returns:
            Configured Layer1Metrics; all-NaN when inject_nan is True.
        """
        return _NAN_LAYER1 if self._inject_nan else self._fixed


class FakeRubricJudge:
    """In-memory RubricJudgePort returning a fixed or NaN-score RubricResult.

    Args:
        fixed: RubricResult to return for every sample. Defaults to score=4.0.
        inject_nan: when True, ignore ``fixed`` and return a NaN-score result,
            simulating retry exhaustion as described in ADR-007.
    """

    def __init__(
        self,
        fixed: RubricResult | None = None,
        *,
        inject_nan: bool = False,
    ) -> None:
        self._fixed = fixed if fixed is not None else _DEFAULT_RUBRIC
        self._inject_nan = inject_nan

    def score(self, sample: EvaluationSample) -> RubricResult:
        """Return the configured RubricResult.

        Args:
            sample: evaluation sample (accepted but unused).

        Returns:
            Configured RubricResult; NaN score when inject_nan is True.
        """
        return _NAN_RUBRIC if self._inject_nan else self._fixed


class FakeDeterministicMetric:
    """In-memory DeterministicMetricPort returning fixed or NaN AuxMetrics.

    Args:
        fixed: AuxMetrics to return for every pair. Defaults to bertscore_f1=0.82.
        inject_nan: when True, ignore ``fixed`` and return NaN bertscore_f1.
    """

    def __init__(
        self,
        fixed: AuxMetrics | None = None,
        *,
        inject_nan: bool = False,
    ) -> None:
        self._fixed = fixed if fixed is not None else _DEFAULT_AUX
        self._inject_nan = inject_nan

    def score(self, *, answer: str, ground_truth: str) -> AuxMetrics:
        """Return the configured AuxMetrics.

        Args:
            answer: generated answer text (accepted but unused).
            ground_truth: reference answer text (accepted but unused).

        Returns:
            Configured AuxMetrics; NaN bertscore_f1 when inject_nan is True.
        """
        return _NAN_AUX if self._inject_nan else self._fixed
