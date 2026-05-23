from __future__ import annotations

import dataclasses
import math

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from inteligenciomica_eval.domain.errors import (
    InteligenciomicaEvalError,
    InvalidBaseIdError,
    InvalidLLMIdError,
    InvalidSeedError,
    ScoreOutOfRangeError,
)
from inteligenciomica_eval.domain.value_objects import (
    BaseId,
    DeterminismRegime,
    FinalScore,
    LLMId,
    MetricVector,
    RankScore,
    RowId,
    Seed,
)

# ---------------------------------------------------------------------------
# DeterminismRegime
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_determinism_regime_judge_value() -> None:
    assert DeterminismRegime.JUDGE.value == "judge"


@pytest.mark.unit
def test_determinism_regime_generator_value() -> None:
    assert DeterminismRegime.GENERATOR.value == "generator"


@pytest.mark.unit
def test_determinism_regime_has_exactly_two_members() -> None:
    assert {m.name for m in DeterminismRegime} == {"JUDGE", "GENERATOR"}


# ---------------------------------------------------------------------------
# BaseId
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("valid", ["IDx_400k", "ID_230K", "fixed"])
def test_base_id_valid_values(valid: str) -> None:
    assert BaseId(valid).value == valid


@pytest.mark.unit
@pytest.mark.parametrize(
    "invalid",
    ["", "unknown", "IDx_400K", "Fixed", "IDx400k", "ID_230k", " fixed"],
)
def test_base_id_invalid_raises(invalid: str) -> None:
    with pytest.raises(InvalidBaseIdError) as exc_info:
        BaseId(invalid)
    assert exc_info.value.base_id == invalid


@pytest.mark.unit
def test_base_id_is_frozen() -> None:
    b = BaseId("fixed")
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.value = "IDx_400k"  # type: ignore[misc]


@pytest.mark.unit
def test_base_id_is_subclass_of_domain_error() -> None:
    with pytest.raises(InteligenciomicaEvalError):
        BaseId("not-valid")


# ---------------------------------------------------------------------------
# LLMId
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "valid",
    ["gpt-4o", "llama-3.1-8b", "mistral-7b-instruct", "a", "model_v2"],
)
def test_llm_id_valid(valid: str) -> None:
    assert LLMId(valid).value == valid


@pytest.mark.unit
def test_llm_id_empty_raises() -> None:
    with pytest.raises(InvalidLLMIdError) as exc_info:
        LLMId("")
    assert exc_info.value.llm_id == ""


@pytest.mark.unit
@pytest.mark.parametrize(
    "invalid",
    ["gpt 4o", "llama 3.1", " model", "model ", "a b c"],
)
def test_llm_id_space_raises(invalid: str) -> None:
    with pytest.raises(InvalidLLMIdError) as exc_info:
        LLMId(invalid)
    assert exc_info.value.llm_id == invalid


@pytest.mark.unit
def test_llm_id_is_frozen() -> None:
    llm = LLMId("gpt-4o")
    with pytest.raises(dataclasses.FrozenInstanceError):
        llm.value = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("valid", [0, 1, 42, 999_999, 2**31])
def test_seed_valid(valid: int) -> None:
    assert Seed(valid).value == valid


@pytest.mark.unit
@pytest.mark.parametrize("invalid", [-1, -42, -1_000_000])
def test_seed_negative_raises(invalid: int) -> None:
    with pytest.raises(InvalidSeedError) as exc_info:
        Seed(invalid)
    assert exc_info.value.seed == invalid


@pytest.mark.unit
def test_seed_zero_is_valid() -> None:
    assert Seed(0).value == 0


@pytest.mark.unit
def test_seed_is_frozen() -> None:
    s = Seed(42)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.value = 0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FinalScore
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("valid", [0.0, 0.5, 1.0, 0.999])
def test_final_score_valid_range(valid: float) -> None:
    assert FinalScore(valid).value == valid


@pytest.mark.unit
def test_final_score_nan_is_valid() -> None:
    fs = FinalScore(float("nan"))
    assert math.isnan(fs.value)


@pytest.mark.unit
@pytest.mark.parametrize(
    "invalid",
    [-0.001, 1.001, -1.0, 2.0, float("inf"), float("-inf")],
)
def test_final_score_out_of_range_raises(invalid: float) -> None:
    with pytest.raises(ScoreOutOfRangeError) as exc_info:
        FinalScore(invalid)
    assert exc_info.value.score == invalid
    assert exc_info.value.min_val == 0.0
    assert exc_info.value.max_val == 1.0


@pytest.mark.unit
def test_final_score_boundary_zero() -> None:
    assert FinalScore(0.0).value == 0.0


@pytest.mark.unit
def test_final_score_boundary_one() -> None:
    assert FinalScore(1.0).value == 1.0


@pytest.mark.unit
@given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
def test_final_score_hypothesis_accepts_unit_interval(v: float) -> None:
    FinalScore(v)


@pytest.mark.unit
@given(st.floats(allow_nan=False).filter(lambda x: not (0.0 <= x <= 1.0)))
def test_final_score_hypothesis_rejects_outside_unit_interval(v: float) -> None:
    with pytest.raises(ScoreOutOfRangeError):
        FinalScore(v)


@pytest.mark.unit
def test_final_score_hypothesis_nan_is_valid() -> None:
    FinalScore(float("nan"))


# ---------------------------------------------------------------------------
# RankScore
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    "valid",
    [0.0, -1.5, 2.5, -100.0, 1e10, float("nan")],
)
def test_rank_score_valid(valid: float) -> None:
    rs = RankScore(valid)
    if math.isnan(valid):
        assert math.isnan(rs.value)
    else:
        assert rs.value == valid


@pytest.mark.unit
@pytest.mark.parametrize("invalid", [float("inf"), float("-inf")])
def test_rank_score_inf_raises(invalid: float) -> None:
    with pytest.raises(InteligenciomicaEvalError, match="finite"):
        RankScore(invalid)


@pytest.mark.unit
def test_rank_score_negative_is_allowed() -> None:
    assert RankScore(-999.9).value == pytest.approx(-999.9)


@pytest.mark.unit
@pytest.mark.parametrize(
    "non_float",
    [1, 0, -1, True, False],  # int e bool não são float
)
def test_rank_score_rejects_non_float_with_domain_error(non_float: object) -> None:
    with pytest.raises(InteligenciomicaEvalError, match="must be a float"):
        RankScore(non_float)  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.parametrize("non_float", ["0.5", None, [], {}])
def test_rank_score_rejects_wrong_type_with_domain_error(non_float: object) -> None:
    with pytest.raises(InteligenciomicaEvalError, match="must be a float"):
        RankScore(non_float)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# MetricVector
# ---------------------------------------------------------------------------

_METRIC_FIELD_NAMES = (
    "answer_correctness",
    "answer_similarity",
    "faithfulness",
    "context_precision",
    "context_recall",
    "answer_relevancy",
    "bertscore_f1",
    "rubric_biomed_score",
)


def _make_metric_vector(**overrides: float) -> MetricVector:
    defaults = dict.fromkeys(_METRIC_FIELD_NAMES, 0.5)
    defaults.update(overrides)
    return MetricVector(**defaults)


@pytest.mark.unit
def test_metric_vector_no_nan_fields() -> None:
    mv = _make_metric_vector()
    assert mv.nan_fields() == ()


@pytest.mark.unit
def test_metric_vector_single_nan_field() -> None:
    mv = _make_metric_vector(faithfulness=float("nan"))
    assert mv.nan_fields() == ("faithfulness",)


@pytest.mark.unit
def test_metric_vector_multiple_nan_fields() -> None:
    nan = float("nan")
    mv = _make_metric_vector(
        answer_correctness=nan,
        faithfulness=nan,
        context_recall=nan,
    )
    assert set(mv.nan_fields()) == {
        "answer_correctness",
        "faithfulness",
        "context_recall",
    }
    assert len(mv.nan_fields()) == 3


@pytest.mark.unit
def test_metric_vector_all_nan_fields() -> None:
    nan = float("nan")
    mv = MetricVector(
        answer_correctness=nan,
        answer_similarity=nan,
        faithfulness=nan,
        context_precision=nan,
        context_recall=nan,
        answer_relevancy=nan,
        bertscore_f1=nan,
        rubric_biomed_score=nan,
    )
    assert set(mv.nan_fields()) == set(_METRIC_FIELD_NAMES)


@pytest.mark.unit
def test_metric_vector_nan_fields_order_matches_declaration() -> None:
    nan = float("nan")
    mv = _make_metric_vector(answer_correctness=nan, bertscore_f1=nan)
    result = mv.nan_fields()
    assert result == ("answer_correctness", "bertscore_f1")


@pytest.mark.unit
def test_metric_vector_is_frozen() -> None:
    mv = _make_metric_vector()
    with pytest.raises(dataclasses.FrozenInstanceError):
        mv.faithfulness = 1.0  # type: ignore[misc]


@pytest.mark.unit
def test_metric_vector_accepts_valid_floats_and_negatives() -> None:
    mv = _make_metric_vector(rubric_biomed_score=-0.5)
    assert mv.rubric_biomed_score == pytest.approx(-0.5)


# ---------------------------------------------------------------------------
# RowId
# ---------------------------------------------------------------------------

_CELL_KWARGS: dict[str, str | int] = {
    "run_id": "run-001",
    "phase": "eval",
    "base": "IDx_400k",
    "llm": "gpt-4o",
    "seed": 42,
    "question_id": "q001",
}


@pytest.mark.unit
def test_row_id_from_cell_produces_valid_sha256_hex() -> None:
    row_id = RowId.from_cell(**_CELL_KWARGS)  # type: ignore[arg-type]
    assert len(row_id.value) == 64
    assert all(c in "0123456789abcdef" for c in row_id.value)


@pytest.mark.unit
def test_row_id_from_cell_is_deterministic() -> None:
    r1 = RowId.from_cell(**_CELL_KWARGS)  # type: ignore[arg-type]
    r2 = RowId.from_cell(**_CELL_KWARGS)  # type: ignore[arg-type]
    assert r1 == r2


@pytest.mark.unit
def test_row_id_from_cell_different_seed_produces_different_id() -> None:
    r1 = RowId.from_cell(
        run_id="run-001",
        phase="eval",
        base="IDx_400k",
        llm="gpt-4o",
        seed=42,
        question_id="q001",
    )
    r2 = RowId.from_cell(
        run_id="run-001",
        phase="eval",
        base="IDx_400k",
        llm="gpt-4o",
        seed=43,
        question_id="q001",
    )
    assert r1 != r2


@pytest.mark.unit
def test_row_id_from_cell_different_llm_produces_different_id() -> None:
    r1 = RowId.from_cell(
        run_id="r", phase="p", base="fixed", llm="gpt-4o", seed=0, question_id="q"
    )
    r2 = RowId.from_cell(
        run_id="r", phase="p", base="fixed", llm="llama-3", seed=0, question_id="q"
    )
    assert r1 != r2


@pytest.mark.unit
def test_row_id_constructor_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        RowId("abc123")


@pytest.mark.unit
def test_row_id_constructor_rejects_uppercase_hex() -> None:
    # hashlib produz lowercase; uppercase é considerado inválido para consistência
    valid_lower = RowId.from_cell(
        run_id="r", phase="p", base="fixed", llm="m", seed=0, question_id="q"
    ).value
    with pytest.raises(ValueError):
        RowId(valid_lower.upper())


@pytest.mark.unit
def test_row_id_constructor_accepts_valid_digest() -> None:
    digest = "a" * 64
    row_id = RowId(digest)
    assert row_id.value == digest


@pytest.mark.unit
def test_row_id_is_frozen() -> None:
    row_id = RowId.from_cell(**_CELL_KWARGS)  # type: ignore[arg-type]
    with pytest.raises(dataclasses.FrozenInstanceError):
        row_id.value = "x" * 64  # type: ignore[misc]


# --- Property-based: RowId.from_cell é determinístico ---

_text = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(blacklist_categories=("Cs",)),
)


@pytest.mark.unit
@given(
    run_id=_text,
    phase=_text,
    base=_text,
    llm=_text,
    seed=st.integers(min_value=0, max_value=10**9),
    question_id=_text,
)
@settings(max_examples=150)
def test_row_id_from_cell_hypothesis_same_inputs_same_hash(
    run_id: str,
    phase: str,
    base: str,
    llm: str,
    seed: int,
    question_id: str,
) -> None:
    r1 = RowId.from_cell(
        run_id=run_id,
        phase=phase,
        base=base,
        llm=llm,
        seed=seed,
        question_id=question_id,
    )
    r2 = RowId.from_cell(
        run_id=run_id,
        phase=phase,
        base=base,
        llm=llm,
        seed=seed,
        question_id=question_id,
    )
    assert r1 == r2


@pytest.mark.unit
@given(
    run_id=_text,
    phase=_text,
    base=_text,
    llm=_text,
    seed1=st.integers(min_value=0, max_value=10**6),
    seed2=st.integers(min_value=0, max_value=10**6),
    question_id=_text,
)
def test_row_id_from_cell_hypothesis_different_seed_different_hash(
    run_id: str,
    phase: str,
    base: str,
    llm: str,
    seed1: int,
    seed2: int,
    question_id: str,
) -> None:
    assume(seed1 != seed2)
    r1 = RowId.from_cell(
        run_id=run_id,
        phase=phase,
        base=base,
        llm=llm,
        seed=seed1,
        question_id=question_id,
    )
    r2 = RowId.from_cell(
        run_id=run_id,
        phase=phase,
        base=base,
        llm=llm,
        seed=seed2,
        question_id=question_id,
    )
    assert r1 != r2
