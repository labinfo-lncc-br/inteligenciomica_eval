from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
)
from inteligenciomica_eval.domain.services.aggregation import (
    AggregationService,
    _critical_failure_rate,
    _iqr,
    _valid_scores,
    _win_rates,
)
from inteligenciomica_eval.domain.services.rank_score import (
    DEFAULT_WEIGHTS,
    RankScoreCalculator,
)
from inteligenciomica_eval.domain.value_objects import (
    BaseId,
    DeterminismRegime,
    FinalScore,
    LLMId,
    MetricVector,
    RowId,
    Seed,
)

# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

_GOLDEN_PATH = Path(__file__).parents[3] / "golden" / "aggregation_cases.json"

_NAN_MV = MetricVector(
    answer_correctness=float("nan"),
    answer_similarity=float("nan"),
    faithfulness=float("nan"),
    context_precision=float("nan"),
    context_recall=float("nan"),
    answer_relevancy=float("nan"),
    bertscore_f1=float("nan"),
    rubric_biomed_score=float("nan"),
)


def _make_result(
    *,
    base: str = "IDx_400k",
    llm: str = "llm-a",
    seed: int = 0,
    question_id: str = "q1",
    final_score: float | None = None,
    flag: int | None = None,
) -> EvaluationResult:
    """Build a minimal EvaluationResult for testing."""
    score = float("nan") if final_score is None else final_score
    row_id = RowId.from_cell(
        run_id="test",
        phase="A",
        base=base,
        llm=llm,
        seed=seed,
        question_id=question_id,
    )
    question = Question(
        question_id=question_id,
        text=f"Question {question_id}",
        ground_truth=f"Answer {question_id}",
    )
    answer = GeneratedAnswer(
        row_id=row_id,
        question=question,
        base=BaseId(base),
        llm=LLMId(llm),
        seed=Seed(seed),
        phase="A",
        generated_answer="Generated.",
        retrieved_chunk_ids=(),
        retrieved_chunks_text=(),
        retrieval_scores=(),
    )
    return EvaluationResult(
        answer=answer,
        metrics=_NAN_MV,
        final_score=FinalScore(score),
        determinism_regime=DeterminismRegime.JUDGE,
        critical_failure_flag=flag,
        critical_failure_note=None,
    )


def _default_service() -> AggregationService:
    return AggregationService(RankScoreCalculator(DEFAULT_WEIGHTS))


# ---------------------------------------------------------------------------
# _valid_scores helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_valid_scores_filters_nan() -> None:
    results = [
        _make_result(final_score=0.8),
        _make_result(final_score=None),
        _make_result(final_score=0.6),
    ]
    assert _valid_scores(results) == [0.8, 0.6]


@pytest.mark.unit
def test_valid_scores_all_nan_returns_empty() -> None:
    results = [_make_result(final_score=None) for _ in range(3)]
    assert _valid_scores(results) == []


# ---------------------------------------------------------------------------
# _iqr helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_iqr_returns_nan_for_empty() -> None:
    assert math.isnan(_iqr([]))


@pytest.mark.unit
def test_iqr_returns_nan_for_single_value() -> None:
    assert math.isnan(_iqr([0.5]))


@pytest.mark.unit
def test_iqr_two_values_inclusive() -> None:
    # [0.70, 0.80]: Q1 = 0.725, Q3 = 0.775, IQR = 0.05
    result = _iqr([0.70, 0.80])
    assert result == pytest.approx(0.05, abs=1e-9)


@pytest.mark.unit
def test_iqr_three_values_inclusive() -> None:
    # [0.70, 0.80, 0.90]: Q1=0.75, Q3=0.85, IQR=0.10
    result = _iqr([0.70, 0.80, 0.90])
    assert result == pytest.approx(0.10, abs=1e-9)


@pytest.mark.unit
def test_iqr_identical_values_is_zero() -> None:
    assert _iqr([0.5, 0.5, 0.5, 0.5]) == pytest.approx(0.0, abs=1e-12)


# ---------------------------------------------------------------------------
# _critical_failure_rate helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_critical_rate_all_none_returns_nan() -> None:
    results = [_make_result(flag=None) for _ in range(3)]
    assert math.isnan(_critical_failure_rate(results))


@pytest.mark.unit
def test_critical_rate_ignores_none_in_denominator() -> None:
    # 1 annotated (flag=1), 1 annotated (flag=0), 1 unannotated (flag=None)
    results = [
        _make_result(flag=1),
        _make_result(flag=0),
        _make_result(flag=None),  # excluded from denominator
    ]
    # denominator=2, numerator=1 → 0.5
    assert _critical_failure_rate(results) == pytest.approx(0.5, abs=1e-12)


@pytest.mark.unit
def test_critical_rate_all_annotated_none_critical() -> None:
    results = [_make_result(flag=0) for _ in range(4)]
    assert _critical_failure_rate(results) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.unit
def test_critical_rate_all_critical() -> None:
    results = [_make_result(flag=1) for _ in range(3)]
    assert _critical_failure_rate(results) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.unit
def test_critical_rate_mixed_with_nones() -> None:
    # flags: 1, 1, 0, None, None → denominator=3, numerator=2 → 2/3
    results = [
        _make_result(flag=1),
        _make_result(flag=1),
        _make_result(flag=0),
        _make_result(flag=None),
        _make_result(flag=None),
    ]
    assert _critical_failure_rate(results) == pytest.approx(2 / 3, abs=1e-12)


# ---------------------------------------------------------------------------
# _win_rates helper
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_win_rates_single_config_wins_all() -> None:
    groups: dict[tuple[str, str], list[EvaluationResult]] = {
        ("IDx_400k", "llm-a"): [
            _make_result(question_id="q1", final_score=0.8),
            _make_result(question_id="q2", final_score=0.7),
        ]
    }
    rates = _win_rates(groups)
    assert rates[("IDx_400k", "llm-a")] == pytest.approx(1.0, abs=1e-12)


@pytest.mark.unit
def test_win_rates_tie_splits_evenly() -> None:
    groups: dict[tuple[str, str], list[EvaluationResult]] = {
        ("IDx_400k", "llm-a"): [_make_result(question_id="q1", final_score=0.8)],
        ("IDx_400k", "llm-b"): [_make_result(question_id="q1", final_score=0.8)],
    }
    rates = _win_rates(groups)
    assert rates[("IDx_400k", "llm-a")] == pytest.approx(0.5, abs=1e-12)
    assert rates[("IDx_400k", "llm-b")] == pytest.approx(0.5, abs=1e-12)


@pytest.mark.unit
def test_win_rates_config_with_nan_gets_zero_for_that_question() -> None:
    groups: dict[tuple[str, str], list[EvaluationResult]] = {
        ("IDx_400k", "llm-a"): [_make_result(question_id="q1", final_score=0.8)],
        ("IDx_400k", "llm-b"): [_make_result(question_id="q1", final_score=None)],
    }
    rates = _win_rates(groups)
    assert rates[("IDx_400k", "llm-a")] == pytest.approx(1.0, abs=1e-12)
    assert rates[("IDx_400k", "llm-b")] == pytest.approx(0.0, abs=1e-12)


@pytest.mark.unit
def test_win_rates_all_nan_for_question_nobody_wins() -> None:
    # 2 questions; q1 all NaN, q2 has a winner
    groups: dict[tuple[str, str], list[EvaluationResult]] = {
        ("IDx_400k", "llm-a"): [
            _make_result(question_id="q1", final_score=None),
            _make_result(question_id="q2", final_score=0.8),
        ],
        ("IDx_400k", "llm-b"): [
            _make_result(question_id="q1", final_score=None),
            _make_result(question_id="q2", final_score=0.6),
        ],
    }
    rates = _win_rates(groups)
    # A wins q2; nobody wins q1 (all NaN). total questions=2.
    assert rates[("IDx_400k", "llm-a")] == pytest.approx(0.5, abs=1e-12)
    assert rates[("IDx_400k", "llm-b")] == pytest.approx(0.0, abs=1e-12)


@pytest.mark.unit
def test_win_rates_empty_groups() -> None:
    assert _win_rates({}) == {}


# ---------------------------------------------------------------------------
# AggregationService — construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_service_construction_stores_calculator() -> None:
    calc = RankScoreCalculator(DEFAULT_WEIGHTS)
    svc = AggregationService(calc)
    assert svc._rank_calculator is calc


# ---------------------------------------------------------------------------
# aggregate_all — empty / trivial
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_aggregate_all_empty_returns_empty_tuple() -> None:
    result = _default_service().aggregate_all([], threshold=0.70)
    assert result == ()


@pytest.mark.unit
def test_aggregate_all_returns_tuple() -> None:
    results = [_make_result(final_score=0.8, flag=0)]
    aggs = _default_service().aggregate_all(results, threshold=0.70)
    assert isinstance(aggs, tuple)


@pytest.mark.unit
def test_aggregate_all_single_result_single_config() -> None:
    results = [_make_result(final_score=0.8, flag=0)]
    aggs = _default_service().aggregate_all(results, threshold=0.70)
    assert len(aggs) == 1


# ---------------------------------------------------------------------------
# aggregate_all — correctness: NaN exclusion (ADR-007)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_aggregate_all_nan_excluded_from_stats() -> None:
    results = [
        _make_result(question_id="q1", final_score=0.8, flag=0),
        _make_result(question_id="q2", final_score=None, flag=None),  # NaN
        _make_result(question_id="q3", final_score=0.6, flag=0),
    ]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    assert agg.n_observations == 2
    assert agg.n_excluded_nan == 1
    assert not math.isnan(agg.mean_score)
    assert agg.mean_score == pytest.approx(0.7, abs=1e-9)


@pytest.mark.unit
def test_aggregate_all_all_nan_returns_nan_aggregates() -> None:
    results = [
        _make_result(question_id=f"q{i}", final_score=None, flag=None) for i in range(3)
    ]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    assert agg.n_observations == 0
    assert agg.n_excluded_nan == 3
    assert math.isnan(agg.mean_score)
    assert math.isnan(agg.median_score)
    assert math.isnan(agg.min_score)
    assert math.isnan(agg.iqr)
    assert math.isnan(agg.failure_rate)


@pytest.mark.unit
def test_aggregate_all_nan_excluded_reported_correctly() -> None:
    results = [
        _make_result(question_id="q1", final_score=0.9, flag=0),
        _make_result(question_id="q2", final_score=None, flag=None),
        _make_result(question_id="q3", final_score=None, flag=None),
    ]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    assert agg.n_excluded_nan == 2
    assert agg.n_observations == 1


# ---------------------------------------------------------------------------
# aggregate_all — failure_rate uses EvaluationResult.is_failure
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_aggregate_all_failure_rate_uses_threshold_correctly() -> None:
    # 0.70 < threshold → failure; 0.70 at threshold is NOT a failure (strict <)
    results = [
        _make_result(question_id="q1", final_score=0.69, flag=0),  # failure
        _make_result(question_id="q2", final_score=0.70, flag=0),  # NOT failure
        _make_result(question_id="q3", final_score=0.80, flag=0),  # NOT failure
    ]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    assert agg.failure_rate == pytest.approx(1 / 3, abs=1e-12)


@pytest.mark.unit
def test_aggregate_all_failure_rate_zero_when_all_pass() -> None:
    results = [
        _make_result(question_id=f"q{i}", final_score=0.80 + i * 0.01, flag=0)
        for i in range(5)
    ]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    assert agg.failure_rate == pytest.approx(0.0, abs=1e-12)


@pytest.mark.unit
def test_aggregate_all_failure_rate_one_when_all_fail() -> None:
    results = [
        _make_result(question_id=f"q{i}", final_score=0.60, flag=0) for i in range(3)
    ]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    assert agg.failure_rate == pytest.approx(1.0, abs=1e-12)


@pytest.mark.unit
def test_aggregate_all_failure_rate_nan_excluded_from_denominator() -> None:
    # 1 failing, 1 NaN, 1 passing → failure_rate = 1/2 (NaN out of denominator)
    results = [
        _make_result(question_id="q1", final_score=0.50, flag=0),  # failure
        _make_result(question_id="q2", final_score=None, flag=None),  # NaN excluded
        _make_result(question_id="q3", final_score=0.80, flag=0),  # pass
    ]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    assert agg.failure_rate == pytest.approx(0.5, abs=1e-12)


# ---------------------------------------------------------------------------
# aggregate_all — critical_failure_rate ignores None flags
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_aggregate_all_critical_rate_none_flags_nan() -> None:
    results = [
        _make_result(question_id=f"q{i}", final_score=0.8, flag=None) for i in range(3)
    ]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    assert math.isnan(agg.critical_failure_rate)


@pytest.mark.unit
def test_aggregate_all_critical_rate_none_not_in_denominator() -> None:
    # 1 critical, 2 non-critical, 2 unannotated
    results = [
        _make_result(question_id="q1", final_score=0.5, flag=1),
        _make_result(question_id="q2", final_score=0.8, flag=0),
        _make_result(question_id="q3", final_score=0.7, flag=0),
        _make_result(question_id="q4", final_score=0.9, flag=None),
        _make_result(question_id="q5", final_score=0.6, flag=None),
    ]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    # denominator = 3 (only annotated), numerator = 1
    assert agg.critical_failure_rate == pytest.approx(1 / 3, abs=1e-12)


@pytest.mark.unit
def test_critical_rate_nan_score_annotated_counts_in_denominator() -> None:
    # A row with NaN final_score but a non-None flag IS counted in critical_failure_rate.
    # ADR-007 NaN exclusion applies only to score-based aggregates (mean/median/min/IQR/
    # failure_rate). critical_failure_rate is a human-annotation metric governed by
    # ADR-010: only flag=None is excluded from the denominator — NaN scores are not.
    results = [
        _make_result(question_id="q1", final_score=None, flag=1),  # NaN score, critical
        _make_result(
            question_id="q2", final_score=0.8, flag=0
        ),  # valid score, not critical
    ]
    # denominator=2 (both annotated regardless of score), numerator=1 → 0.5
    assert _critical_failure_rate(results) == pytest.approx(0.5, abs=1e-12)


@pytest.mark.unit
def test_aggregate_all_critical_rate_nan_score_annotated_counts() -> None:
    # Same deliberate behaviour exercised via the full service.
    # n_observations=1 (only q2 valid); n_excluded_nan=1 (q1 NaN score).
    # critical_failure_rate: denominator=2 (both annotated), numerator=1 → 0.5.
    results = [
        _make_result(question_id="q1", final_score=None, flag=1),
        _make_result(question_id="q2", final_score=0.8, flag=0),
    ]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    assert agg.n_observations == 1
    assert agg.n_excluded_nan == 1
    assert agg.critical_failure_rate == pytest.approx(0.5, abs=1e-12)


# ---------------------------------------------------------------------------
# aggregate_all — win_rate cross-config
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_aggregate_all_win_rate_clear_winner() -> None:
    results = [
        _make_result(
            base="IDx_400k", llm="llm-a", question_id="q1", final_score=0.9, flag=0
        ),
        _make_result(
            base="IDx_400k", llm="llm-a", question_id="q2", final_score=0.8, flag=0
        ),
        _make_result(
            base="IDx_400k", llm="llm-b", question_id="q1", final_score=0.5, flag=0
        ),
        _make_result(
            base="IDx_400k", llm="llm-b", question_id="q2", final_score=0.4, flag=0
        ),
    ]
    aggs = _default_service().aggregate_all(results, threshold=0.70)
    a_agg = next(a for a in aggs if a.llm.value == "llm-a")
    b_agg = next(a for a in aggs if a.llm.value == "llm-b")
    assert a_agg.win_rate == pytest.approx(1.0, abs=1e-12)
    assert b_agg.win_rate == pytest.approx(0.0, abs=1e-12)


@pytest.mark.unit
def test_aggregate_all_win_rate_tie_is_split() -> None:
    results = [
        _make_result(
            base="IDx_400k", llm="llm-a", question_id="q1", final_score=0.8, flag=0
        ),
        _make_result(
            base="IDx_400k", llm="llm-b", question_id="q1", final_score=0.8, flag=0
        ),
    ]
    aggs = _default_service().aggregate_all(results, threshold=0.70)
    assert len(aggs) == 2
    for agg in aggs:
        assert agg.win_rate == pytest.approx(0.5, abs=1e-12)


@pytest.mark.unit
def test_aggregate_all_win_rate_three_way_tie() -> None:
    results = [
        _make_result(
            base="IDx_400k", llm=f"llm-{c}", question_id="q1", final_score=0.7, flag=0
        )
        for c in ["a", "b", "c"]
    ]
    aggs = _default_service().aggregate_all(results, threshold=0.70)
    for agg in aggs:
        assert agg.win_rate == pytest.approx(1 / 3, abs=1e-12)


# ---------------------------------------------------------------------------
# aggregate_all — rank_score delegation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_aggregate_all_rank_score_nan_when_critical_rate_nan() -> None:
    # No annotations → critical_rate=NaN → rank_score=NaN
    results = [
        _make_result(question_id="q1", final_score=0.8, flag=None),
        _make_result(question_id="q2", final_score=0.7, flag=None),
    ]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    assert math.isnan(agg.rank_score.value)


@pytest.mark.unit
def test_aggregate_all_rank_score_computed_correctly() -> None:
    # median=0.80, failure_rate=0.0, win_rate=1.0, critical_rate=0.0
    # rank = 0.50*0.80 + 0.20*1.0 + 0.15*1.0 - 0.15*0.0 = 0.75
    results = [
        _make_result(question_id="q1", final_score=0.8, flag=0),
        _make_result(question_id="q2", final_score=0.8, flag=0),
    ]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    assert agg.rank_score.value == pytest.approx(0.75, abs=1e-9)


# ---------------------------------------------------------------------------
# aggregate_all — ordering and grouping
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_aggregate_all_output_ordered_by_base_then_llm() -> None:
    results = [
        _make_result(
            base="IDx_400k", llm="llm-z", question_id="q1", final_score=0.8, flag=0
        ),
        _make_result(
            base="IDx_400k", llm="llm-a", question_id="q1", final_score=0.7, flag=0
        ),
        _make_result(
            base="ID_230K", llm="llm-a", question_id="q1", final_score=0.9, flag=0
        ),
    ]
    aggs = _default_service().aggregate_all(results, threshold=0.70)
    keys = [(a.base.value, a.llm.value) for a in aggs]
    assert keys == sorted(keys)


@pytest.mark.unit
def test_aggregate_all_groups_by_base_and_llm() -> None:
    results = [
        _make_result(
            base="IDx_400k", llm="llm-a", question_id="q1", final_score=0.8, flag=0
        ),
        _make_result(
            base="IDx_400k", llm="llm-a", question_id="q2", final_score=0.9, flag=0
        ),
        _make_result(
            base="IDx_400k", llm="llm-b", question_id="q1", final_score=0.6, flag=0
        ),
    ]
    aggs = _default_service().aggregate_all(results, threshold=0.70)
    assert len(aggs) == 2
    a_agg = next(a for a in aggs if a.llm.value == "llm-a")
    assert a_agg.n_observations == 2


# ---------------------------------------------------------------------------
# aggregate_all — IQR edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_aggregate_all_iqr_nan_for_single_observation() -> None:
    results = [_make_result(question_id="q1", final_score=0.8, flag=0)]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    assert math.isnan(agg.iqr)


@pytest.mark.unit
def test_aggregate_all_iqr_zero_for_identical_values() -> None:
    results = [
        _make_result(question_id=f"q{i}", final_score=0.8, flag=0) for i in range(4)
    ]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    assert agg.iqr == pytest.approx(0.0, abs=1e-12)


# ---------------------------------------------------------------------------
# aggregate_all — determinism
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_aggregate_all_is_deterministic() -> None:
    results = [
        _make_result(
            base="IDx_400k", llm="llm-a", question_id="q1", final_score=0.8, flag=0
        ),
        _make_result(
            base="IDx_400k", llm="llm-b", question_id="q1", final_score=0.6, flag=1
        ),
    ]
    svc = _default_service()
    aggs1 = svc.aggregate_all(results, threshold=0.70)
    aggs2 = svc.aggregate_all(results, threshold=0.70)
    assert len(aggs1) == len(aggs2)
    for a1, a2 in zip(aggs1, aggs2, strict=True):
        assert a1.mean_score == a2.mean_score
        assert a1.win_rate == a2.win_rate
        assert a1.rank_score.value == a2.rank_score.value


# ---------------------------------------------------------------------------
# aggregate_all — ConfigAggregate is frozen
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_config_aggregate_is_frozen() -> None:
    results = [_make_result(question_id="q1", final_score=0.8, flag=0)]
    agg = _default_service().aggregate_all(results, threshold=0.70)[0]
    with pytest.raises((AttributeError, TypeError)):
        agg.mean_score = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Golden dataset
# ---------------------------------------------------------------------------


def _load_golden() -> list[dict[str, Any]]:
    return json.loads(_GOLDEN_PATH.read_text())  # type: ignore[no-any-return]


def _make_result_from_json(row: dict[str, Any]) -> EvaluationResult:
    return _make_result(
        base=row["base"],
        llm=row["llm"],
        seed=row["seed"],
        question_id=row["question_id"],
        final_score=row["final_score"],  # None → NaN via factory
        flag=row["critical_failure_flag"],
    )


@pytest.mark.unit
def test_golden_file_exists() -> None:
    assert _GOLDEN_PATH.exists(), f"Golden file not found: {_GOLDEN_PATH}"


@pytest.mark.unit
def test_golden_has_at_least_four_cases() -> None:
    assert len(_load_golden()) >= 4


@pytest.mark.unit
@pytest.mark.parametrize("case", _load_golden(), ids=lambda c: c["id"])
def test_golden_aggregation_case(case: dict[str, Any]) -> None:
    results = [_make_result_from_json(r) for r in case["results"]]
    svc = AggregationService(RankScoreCalculator(DEFAULT_WEIGHTS))
    aggs = svc.aggregate_all(results, threshold=float(case["threshold"]))

    expected_list: list[dict[str, Any]] = case["expected"]
    assert len(aggs) == len(expected_list)

    agg_by_key = {(a.base.value, a.llm.value): a for a in aggs}

    for exp in expected_list:
        key = (exp["base"], exp["llm"])
        assert key in agg_by_key, f"Config {key} not found in output"
        agg = agg_by_key[key]

        def _check(field: str, got: float, want: float | None) -> None:
            if want is None:
                assert math.isnan(got), f"{field}: expected NaN, got {got}"
            else:
                assert got == pytest.approx(float(want), abs=1e-9), (
                    f"{field}: expected {want}, got {got}"
                )

        _check("mean_score", agg.mean_score, exp["mean_score"])
        _check("median_score", agg.median_score, exp["median_score"])
        _check("min_score", agg.min_score, exp["min_score"])
        _check("iqr", agg.iqr, exp["iqr"])
        _check("failure_rate", agg.failure_rate, exp["failure_rate"])
        _check(
            "critical_failure_rate",
            agg.critical_failure_rate,
            exp["critical_failure_rate"],
        )
        _check("win_rate", agg.win_rate, exp["win_rate"])
        _check("rank_score", agg.rank_score.value, exp["rank_score"])

        assert agg.n_observations == exp["n_observations"], (
            f"n_observations: expected {exp['n_observations']}, got {agg.n_observations}"
        )
        assert agg.n_excluded_nan == exp["n_excluded_nan"], (
            f"n_excluded_nan: expected {exp['n_excluded_nan']}, got {agg.n_excluded_nan}"
        )
