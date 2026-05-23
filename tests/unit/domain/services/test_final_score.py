from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from inteligenciomica_eval.domain.errors import (
    ConfigValidationError,
    WeightsDoNotSumToOneError,
)
from inteligenciomica_eval.domain.services.final_score import (
    DEFAULT_WEIGHTS,
    FinalScoreCalculator,
)
from inteligenciomica_eval.domain.value_objects import FinalScore, MetricVector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GOLDEN_PATH = Path(__file__).parents[3] / "golden" / "final_score_cases.json"

_ALL_FIELDS = (
    "answer_correctness",
    "answer_similarity",
    "faithfulness",
    "context_precision",
    "context_recall",
    "answer_relevancy",
    "bertscore_f1",
    "rubric_biomed_score",
)


def _mv(**overrides: float) -> MetricVector:
    """Build a MetricVector with all fields defaulting to 0.5."""
    defaults: dict[str, float] = dict.fromkeys(_ALL_FIELDS, 0.5)
    defaults.update(overrides)
    return MetricVector(**defaults)


def _calc(weights: dict[str, float] | None = None) -> FinalScoreCalculator:
    return FinalScoreCalculator(weights if weights is not None else DEFAULT_WEIGHTS)


# ---------------------------------------------------------------------------
# Construction — weight validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_construction_default_weights_ok() -> None:
    FinalScoreCalculator(DEFAULT_WEIGHTS)


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_sum",
    [0.0, 0.5, 1.1, 2.0, -1.0, 0.99999999, 1.00000001],
)
def test_construction_weights_not_sum_to_one_raises(bad_sum: float) -> None:
    # Build weights that deliberately don't sum to 1.0.
    w = {"answer_correctness": bad_sum}
    with pytest.raises(WeightsDoNotSumToOneError) as exc_info:
        FinalScoreCalculator(w)
    assert math.isclose(exc_info.value.actual_sum, bad_sum, rel_tol=1e-12)


@pytest.mark.unit
def test_construction_weights_exactly_one_ok() -> None:
    FinalScoreCalculator({"answer_correctness": 1.0})


@pytest.mark.unit
def test_construction_unknown_metric_raises_config_error() -> None:
    w = {"nonexistent_metric": 0.5, "answer_correctness": 0.5}
    with pytest.raises(ConfigValidationError) as exc_info:
        FinalScoreCalculator(w)
    assert "nonexistent_metric" in exc_info.value.field


@pytest.mark.unit
def test_construction_stores_defensive_copy() -> None:
    mutable: dict[str, float] = dict(DEFAULT_WEIGHTS)
    calc = FinalScoreCalculator(mutable)
    mutable["answer_correctness"] = 0.0
    result = calc.compute(_mv())
    assert result.value == pytest.approx(
        sum(w * 0.5 for w in DEFAULT_WEIGHTS.values()), abs=1e-12
    )


# ---------------------------------------------------------------------------
# compute — correctness (hand-calculated values)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_all_ones_returns_one() -> None:
    mv = _mv(**dict.fromkeys(_ALL_FIELDS, 1.0))
    assert _calc().compute(mv).value == pytest.approx(1.0, abs=1e-12)


@pytest.mark.unit
def test_compute_all_zeros_returns_zero() -> None:
    mv = _mv(**dict.fromkeys(_ALL_FIELDS, 0.0))
    assert _calc().compute(mv).value == pytest.approx(0.0, abs=1e-12)


@pytest.mark.unit
def test_compute_only_answer_correctness_one() -> None:
    mv = _mv(**{**dict.fromkeys(_ALL_FIELDS, 0.0), "answer_correctness": 1.0})
    assert _calc().compute(mv).value == pytest.approx(0.45, abs=1e-12)


@pytest.mark.unit
def test_compute_mixed_moderate() -> None:
    # 0.45*0.8 + 0.20*0.6 + 0.15*0.7 + 0.10*0.5 + 0.05*0.4 + 0.05*0.3 = 0.670
    mv = _mv(
        answer_correctness=0.8,
        faithfulness=0.6,
        rubric_biomed_score=0.7,
        context_recall=0.5,
        context_precision=0.4,
        answer_relevancy=0.3,
    )
    assert _calc().compute(mv).value == pytest.approx(0.670, abs=1e-9)


@pytest.mark.unit
def test_compute_mixed_high() -> None:
    # 0.45*0.9 + 0.20*0.8 + 0.15*0.7 + 0.10*0.6 + 0.05*0.5 + 0.05*0.4 = 0.775
    mv = _mv(
        answer_correctness=0.9,
        faithfulness=0.8,
        rubric_biomed_score=0.7,
        context_recall=0.6,
        context_precision=0.5,
        answer_relevancy=0.4,
    )
    assert _calc().compute(mv).value == pytest.approx(0.775, abs=1e-9)


@pytest.mark.unit
def test_compute_returns_final_score_instance() -> None:
    result = _calc().compute(_mv())
    assert isinstance(result, FinalScore)


# ---------------------------------------------------------------------------
# compute — NaN propagation (ADR-007)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "nan_field",
    [
        "answer_correctness",
        "faithfulness",
        "rubric_biomed_score",
        "context_recall",
        "context_precision",
        "answer_relevancy",
    ],
)
def test_compute_nan_in_weighted_metric_propagates(nan_field: str) -> None:
    mv = _mv(**{nan_field: float("nan")})
    result = _calc().compute(mv)
    assert math.isnan(result.value)


@pytest.mark.unit
@pytest.mark.parametrize("aux_field", ["answer_similarity", "bertscore_f1"])
def test_compute_nan_in_auxiliary_metric_does_not_propagate(aux_field: str) -> None:
    mv = _mv(**{aux_field: float("nan")})
    result = _calc().compute(mv)
    assert not math.isnan(result.value)


@pytest.mark.unit
def test_compute_nan_all_weighted_metrics_returns_nan() -> None:
    nan_overrides = {f: float("nan") for f in DEFAULT_WEIGHTS}
    mv = _mv(**nan_overrides)
    result = _calc().compute(mv)
    assert math.isnan(result.value)


@pytest.mark.unit
def test_compute_nan_only_in_auxiliary_yields_correct_value() -> None:
    mv = _mv(
        answer_similarity=float("nan"),
        bertscore_f1=float("nan"),
        **dict.fromkeys(DEFAULT_WEIGHTS.keys(), 0.5),  # type: ignore[arg-type]
    )
    expected = sum(0.5 * w for w in DEFAULT_WEIGHTS.values())
    assert _calc().compute(mv).value == pytest.approx(expected, abs=1e-12)


# ---------------------------------------------------------------------------
# compute — zero-weight metric with NaN must NOT propagate
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_zero_weight_nan_metric_does_not_propagate() -> None:
    # Construct weights that give zero to answer_correctness.
    w = {**DEFAULT_WEIGHTS, "answer_correctness": 0.0, "faithfulness": 0.65}
    calc = FinalScoreCalculator(w)
    mv = _mv(answer_correctness=float("nan"))
    result = calc.compute(mv)
    assert not math.isnan(result.value)


# ---------------------------------------------------------------------------
# Golden dataset
# ---------------------------------------------------------------------------


def _load_golden() -> list[dict[str, Any]]:
    return json.loads(_GOLDEN_PATH.read_text())  # type: ignore[no-any-return]


@pytest.mark.unit
def test_golden_file_exists() -> None:
    assert _GOLDEN_PATH.exists(), f"Golden file not found: {_GOLDEN_PATH}"


@pytest.mark.unit
def test_golden_has_at_least_five_cases() -> None:
    assert len(_load_golden()) >= 5


@pytest.mark.unit
@pytest.mark.parametrize("case_data", _load_golden(), ids=lambda c: c["id"])
def test_golden_final_score(case_data: dict[str, Any]) -> None:
    raw_metrics: dict[str, float | None] = case_data["metrics"]
    metrics_kwargs = {
        k: float("nan") if v is None else float(v) for k, v in raw_metrics.items()
    }
    mv = MetricVector(**metrics_kwargs)
    calc = FinalScoreCalculator(DEFAULT_WEIGHTS)
    result = calc.compute(mv)
    expected = case_data["expected"]
    if expected is None:
        assert math.isnan(result.value), f"Expected NaN but got {result.value}"
    else:
        assert result.value == pytest.approx(float(expected), abs=1e-9), (
            f"Case {case_data['id']}: expected {expected}, got {result.value}"
        )


# ---------------------------------------------------------------------------
# Property-based tests (hypothesis)
# ---------------------------------------------------------------------------

_score = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


@pytest.mark.unit
@given(
    ac=_score,
    f=_score,
    rbs=_score,
    cr=_score,
    cp=_score,
    ar=_score,
)
@settings(max_examples=300)
def test_hypothesis_result_in_unit_interval(
    ac: float,
    f: float,
    rbs: float,
    cr: float,
    cp: float,
    ar: float,
) -> None:
    mv = _mv(
        answer_correctness=ac,
        faithfulness=f,
        rubric_biomed_score=rbs,
        context_recall=cr,
        context_precision=cp,
        answer_relevancy=ar,
    )
    result = _calc().compute(mv)
    assert 0.0 <= result.value <= 1.0


@pytest.mark.unit
@given(
    ac1=_score,
    ac2=_score,
    f=_score,
    rbs=_score,
    cr=_score,
    cp=_score,
    ar=_score,
)
@settings(max_examples=300)
def test_hypothesis_monotone_answer_correctness(
    ac1: float,
    ac2: float,
    f: float,
    rbs: float,
    cr: float,
    cp: float,
    ar: float,
) -> None:
    assume(ac1 <= ac2)
    common = {
        "faithfulness": f,
        "rubric_biomed_score": rbs,
        "context_recall": cr,
        "context_precision": cp,
        "answer_relevancy": ar,
    }
    mv1 = _mv(answer_correctness=ac1, **common)
    mv2 = _mv(answer_correctness=ac2, **common)
    calc = _calc()
    r1 = calc.compute(mv1).value
    r2 = calc.compute(mv2).value
    assert r1 <= r2 + 1e-12


@pytest.mark.unit
@given(
    ac=_score,
    f=_score,
    rbs=_score,
    cr=_score,
    cp=_score,
    ar=_score,
)
@settings(max_examples=200)
def test_hypothesis_same_input_same_output(
    ac: float,
    f: float,
    rbs: float,
    cr: float,
    cp: float,
    ar: float,
) -> None:
    mv = _mv(
        answer_correctness=ac,
        faithfulness=f,
        rubric_biomed_score=rbs,
        context_recall=cr,
        context_precision=cp,
        answer_relevancy=ar,
    )
    calc = _calc()
    assert calc.compute(mv).value == calc.compute(mv).value
