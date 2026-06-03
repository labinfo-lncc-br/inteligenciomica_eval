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
from inteligenciomica_eval.domain.services.rank_score import (
    DEFAULT_WEIGHTS,
    RankScoreCalculator,
    RankScoreInputs,
)
from inteligenciomica_eval.domain.value_objects import RankScore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GOLDEN_PATH = Path(__file__).parents[3] / "golden" / "rank_score_cases.json"


def _inputs(**overrides: float) -> RankScoreInputs:
    defaults: dict[str, float] = {
        "median_score": 0.5,
        "failure_rate": 0.2,
        "win_rate": 0.5,
        "critical_failure_rate": 0.1,
    }
    defaults.update(overrides)
    return RankScoreInputs(**defaults)


def _calc(weights: dict[str, float] | None = None) -> RankScoreCalculator:
    return RankScoreCalculator(weights if weights is not None else DEFAULT_WEIGHTS)


# ---------------------------------------------------------------------------
# Construction — weight validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_construction_default_weights_ok() -> None:
    RankScoreCalculator(DEFAULT_WEIGHTS)


@pytest.mark.unit
def test_construction_custom_valid_weights_ok() -> None:
    RankScoreCalculator(
        {
            "median": 0.60,
            "one_minus_failure": 0.20,
            "win_rate": 0.10,
            "critical_failure_penalty": 0.10,
        }
    )


@pytest.mark.unit
def test_construction_partial_weights_ok() -> None:
    RankScoreCalculator({"median": 0.80})


@pytest.mark.unit
def test_construction_empty_weights_ok() -> None:
    RankScoreCalculator({})


@pytest.mark.unit
@pytest.mark.parametrize(
    "bad_val",
    [-0.01, -1.0, float("-inf"), float("inf"), float("nan")],
)
def test_construction_invalid_weight_value_raises(bad_val: float) -> None:
    with pytest.raises(WeightsDoNotSumToOneError):
        RankScoreCalculator({"median": bad_val})


@pytest.mark.unit
def test_construction_zero_weight_is_valid() -> None:
    # reforçado: mata mutante val<0.0→val<=0.0 em rank_score.py:__init__ (mutmut_10).
    # Zero é não-negativo — deve ser aceito sem exceção.
    RankScoreCalculator({"median": 0.0})


@pytest.mark.unit
def test_construction_unknown_key_raises_config_error() -> None:
    with pytest.raises(ConfigValidationError) as exc_info:
        RankScoreCalculator({"nonexistent_key": 0.5})
    assert "nonexistent_key" in exc_info.value.field


@pytest.mark.unit
def test_construction_stores_defensive_copy() -> None:
    # With failure_rate=1.0, win_rate=0.0, critical=0.0, only the median term
    # contributes: value = median_weight * 1.0 = 0.50.  After mutation the calc
    # must still use the original median weight (0.50), not 0.0.
    mutable: dict[str, float] = {"median": 0.50}
    calc = RankScoreCalculator(mutable)
    mutable["median"] = 0.0
    result = calc.compute(
        _inputs(
            median_score=1.0, failure_rate=1.0, win_rate=0.0, critical_failure_rate=0.0
        )
    )
    assert result.value == pytest.approx(0.50, abs=1e-12)


# ---------------------------------------------------------------------------
# compute — correctness (hand-calculated)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_perfect_config_returns_085() -> None:
    # 0.50*1.0 + 0.20*(1-0.0) + 0.15*1.0 - 0.15*0.0 = 0.85
    inp = _inputs(
        median_score=1.0, failure_rate=0.0, win_rate=1.0, critical_failure_rate=0.0
    )
    assert _calc().compute(inp).value == pytest.approx(0.85, abs=1e-12)


@pytest.mark.unit
def test_compute_worst_config_is_negative() -> None:
    # 0.50*0.0 + 0.20*(1-1.0) + 0.15*0.0 - 0.15*1.0 = -0.15
    inp = _inputs(
        median_score=0.0, failure_rate=1.0, win_rate=0.0, critical_failure_rate=1.0
    )
    result = _calc().compute(inp)
    assert result.value == pytest.approx(-0.15, abs=1e-12)
    assert result.value < 0.0, (
        "Worst config must produce a negative RankScore (no clamp)"
    )


@pytest.mark.unit
def test_compute_high_critical_failure_is_negative() -> None:
    # 0.50*0.1 + 0.20*0.1 + 0.15*0.1 - 0.15*1.0 = -0.065
    inp = _inputs(
        median_score=0.1, failure_rate=0.9, win_rate=0.1, critical_failure_rate=1.0
    )
    result = _calc().compute(inp)
    assert result.value == pytest.approx(-0.065, abs=1e-12)
    assert result.value < 0.0


@pytest.mark.unit
def test_compute_moderate_good() -> None:
    # 0.50*0.7 + 0.20*0.8 + 0.15*0.6 - 0.15*0.1 = 0.585
    inp = _inputs(
        median_score=0.7, failure_rate=0.2, win_rate=0.6, critical_failure_rate=0.1
    )
    assert _calc().compute(inp).value == pytest.approx(0.585, abs=1e-9)


@pytest.mark.unit
def test_compute_returns_rank_score_instance() -> None:
    result = _calc().compute(_inputs())
    assert isinstance(result, RankScore)


@pytest.mark.unit
def test_compute_empty_weights_uses_defaults() -> None:
    calc_empty = RankScoreCalculator({})
    calc_default = RankScoreCalculator(DEFAULT_WEIGHTS)
    inp = _inputs()
    assert calc_empty.compute(inp).value == pytest.approx(
        calc_default.compute(inp).value, abs=1e-12
    )


@pytest.mark.unit
def test_compute_custom_weights_exact_value() -> None:
    # reforçado: mata mutantes de chave-string em rank_score.py:compute
    # (mutmut_13/17/18/22/26/27/31/35/36/40/44/45).
    # Todos os 4 pesos são definidos com valores distintos dos defaults;
    # o valor esperado é calculado pela fórmula canônica com esses pesos.
    # Qualquer chave corrompida (None, "XXmedianXX", "MEDIAN", etc.) faz
    # _weights.get cair no default → resultado diverge dos 0.67 esperados.
    custom_weights = {
        "median": 0.40,
        "one_minus_failure": 0.30,
        "win_rate": 0.20,
        "critical_failure_penalty": 0.10,
    }
    calc = RankScoreCalculator(custom_weights)
    inp = RankScoreInputs(
        median_score=0.8,
        failure_rate=0.2,
        win_rate=0.6,
        critical_failure_rate=0.1,
    )
    # 0.40*0.8 + 0.30*(1-0.2) + 0.20*0.6 - 0.10*0.1 = 0.32 + 0.24 + 0.12 - 0.01 = 0.67
    assert calc.compute(inp).value == pytest.approx(0.67, abs=1e-9)


# ---------------------------------------------------------------------------
# compute — NaN propagation (ADR-007)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "nan_field",
    ["median_score", "failure_rate", "win_rate", "critical_failure_rate"],
)
def test_compute_any_nan_input_propagates_to_nan(nan_field: str) -> None:
    inp = _inputs(**{nan_field: float("nan")})
    result = _calc().compute(inp)
    assert math.isnan(result.value)


@pytest.mark.unit
def test_compute_all_nan_returns_nan() -> None:
    inp = RankScoreInputs(
        median_score=float("nan"),
        failure_rate=float("nan"),
        win_rate=float("nan"),
        critical_failure_rate=float("nan"),
    )
    assert math.isnan(_calc().compute(inp).value)


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
def test_golden_rank_score(case_data: dict[str, Any]) -> None:
    raw: dict[str, float | None] = case_data["inputs"]
    kwargs = {k: float("nan") if v is None else float(v) for k, v in raw.items()}
    inp = RankScoreInputs(**kwargs)
    calc = RankScoreCalculator(DEFAULT_WEIGHTS)
    result = calc.compute(inp)
    expected = case_data["expected"]
    if expected is None:
        assert math.isnan(result.value), (
            f"Case {case_data['id']}: expected NaN but got {result.value}"
        )
    else:
        assert result.value == pytest.approx(float(expected), abs=1e-9), (
            f"Case {case_data['id']}: expected {expected}, got {result.value}"
        )


# ---------------------------------------------------------------------------
# Property-based tests (hypothesis)
# ---------------------------------------------------------------------------

_frac = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


@pytest.mark.unit
@given(
    median=_frac,
    failure=_frac,
    win=_frac,
    crit1=_frac,
    crit2=_frac,
)
@settings(max_examples=400)
def test_hypothesis_increasing_critical_never_increases_rank_score(
    median: float,
    failure: float,
    win: float,
    crit1: float,
    crit2: float,
) -> None:
    """Aumentar CriticalFailureRate (demais fixos) NUNCA aumenta o RankScore."""
    assume(crit1 <= crit2)
    calc = _calc()
    inp1 = RankScoreInputs(
        median_score=median,
        failure_rate=failure,
        win_rate=win,
        critical_failure_rate=crit1,
    )
    inp2 = RankScoreInputs(
        median_score=median,
        failure_rate=failure,
        win_rate=win,
        critical_failure_rate=crit2,
    )
    r1 = calc.compute(inp1).value
    r2 = calc.compute(inp2).value
    assert r1 >= r2 - 1e-12


@pytest.mark.unit
@given(
    median1=_frac,
    median2=_frac,
    failure=_frac,
    win=_frac,
    crit=_frac,
)
@settings(max_examples=400)
def test_hypothesis_increasing_median_never_decreases_rank_score(
    median1: float,
    median2: float,
    failure: float,
    win: float,
    crit: float,
) -> None:
    """Aumentar MedianScore (demais fixos) NUNCA diminui o RankScore."""
    assume(median1 <= median2)
    calc = _calc()
    inp1 = RankScoreInputs(
        median_score=median1,
        failure_rate=failure,
        win_rate=win,
        critical_failure_rate=crit,
    )
    inp2 = RankScoreInputs(
        median_score=median2,
        failure_rate=failure,
        win_rate=win,
        critical_failure_rate=crit,
    )
    r1 = calc.compute(inp1).value
    r2 = calc.compute(inp2).value
    assert r1 <= r2 + 1e-12


@pytest.mark.unit
@given(
    median=_frac,
    failure=_frac,
    win=_frac,
    crit=_frac,
)
@settings(max_examples=200)
def test_hypothesis_deterministic(
    median: float,
    failure: float,
    win: float,
    crit: float,
) -> None:
    calc = _calc()
    inp = RankScoreInputs(
        median_score=median,
        failure_rate=failure,
        win_rate=win,
        critical_failure_rate=crit,
    )
    assert calc.compute(inp).value == calc.compute(inp).value
