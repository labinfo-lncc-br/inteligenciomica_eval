from __future__ import annotations

import dataclasses
import math

import pytest

from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
)
from inteligenciomica_eval.domain.errors import (
    InteligenciomicaEvalError,
    InvalidCriticalFailureFlagError,
    InvalidPhaseError,
    RetrievalTupleLengthMismatchError,
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
# Factories
# ---------------------------------------------------------------------------

_NAN = float("nan")


def _make_question(
    question_id: str = "q01",
    text: str = "O que é RAG?",
    ground_truth: str = "Retrieval-Augmented Generation.",
) -> Question:
    return Question(question_id=question_id, text=text, ground_truth=ground_truth)


def _make_row_id() -> RowId:
    return RowId.from_cell(
        run_id="run-001",
        phase="A",
        base="IDx_400k",
        llm="gpt-4o",
        seed=0,
        question_id="q01",
    )


def _make_answer(
    phase: str = "A",
    base: str = "IDx_400k",
    chunk_ids: tuple[str, ...] = ("c1", "c2"),
    chunks_text: tuple[str, ...] = ("texto1", "texto2"),
    scores: tuple[float, ...] = (0.9, 0.8),
) -> GeneratedAnswer:
    row_id = RowId.from_cell(
        run_id="run-001",
        phase=phase,
        base=base,
        llm="gpt-4o",
        seed=0,
        question_id="q01",
    )
    return GeneratedAnswer(
        row_id=row_id,
        question=_make_question(),
        base=BaseId(base),
        llm=LLMId("gpt-4o"),
        seed=Seed(0),
        phase=phase,
        generated_answer="Resposta gerada.",
        retrieved_chunk_ids=chunk_ids,
        retrieved_chunks_text=chunks_text,
        retrieval_scores=scores,
    )


def _make_metrics(value: float = 0.8) -> MetricVector:
    return MetricVector(
        answer_correctness=value,
        answer_similarity=value,
        faithfulness=value,
        context_precision=value,
        context_recall=value,
        answer_relevancy=value,
        bertscore_f1=value,
        rubric_biomed_score=value,
    )


def _make_eval(
    phase: str = "A",
    base: str = "IDx_400k",
    metric_value: float = 0.8,
    final: float = 0.8,
    regime: DeterminismRegime = DeterminismRegime.JUDGE,
    flag: int | None = None,
    note: str | None = None,
) -> EvaluationResult:
    return EvaluationResult(
        answer=_make_answer(phase=phase, base=base),
        metrics=_make_metrics(metric_value),
        final_score=FinalScore(final),
        determinism_regime=regime,
        critical_failure_flag=flag,
        critical_failure_note=note,
    )


# ---------------------------------------------------------------------------
# Question
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_question_valid() -> None:
    q = _make_question()
    assert q.question_id == "q01"
    assert q.text == "O que é RAG?"
    assert q.ground_truth == "Retrieval-Augmented Generation."


@pytest.mark.unit
def test_question_is_frozen() -> None:
    q = _make_question()
    with pytest.raises(dataclasses.FrozenInstanceError):
        q.text = "outro"  # type: ignore[misc]


@pytest.mark.unit
@pytest.mark.parametrize(
    "kwargs",
    [
        {"question_id": ""},
        {"text": ""},
        {"ground_truth": ""},
    ],
)
def test_question_empty_field_raises(kwargs: dict[str, str]) -> None:
    with pytest.raises(InteligenciomicaEvalError):
        _make_question(**kwargs)


# ---------------------------------------------------------------------------
# GeneratedAnswer
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_generated_answer_valid_phase_a() -> None:
    ga = _make_answer(phase="A")
    assert ga.phase == "A"
    assert ga.base.value == "IDx_400k"


@pytest.mark.unit
def test_generated_answer_valid_phase_b_with_fixed_base() -> None:
    ga = _make_answer(phase="B", base="fixed")
    assert ga.phase == "B"
    assert ga.base.value == "fixed"


@pytest.mark.unit
@pytest.mark.parametrize("invalid_phase", ["C", "", "a", "b", "AB", "1"])
def test_generated_answer_invalid_phase_raises(invalid_phase: str) -> None:
    with pytest.raises(InvalidPhaseError) as exc_info:
        _make_answer(phase=invalid_phase)
    assert exc_info.value.phase == invalid_phase


@pytest.mark.unit
def test_generated_answer_phase_b_non_fixed_base_raises() -> None:
    with pytest.raises(InteligenciomicaEvalError, match="fixed"):
        _make_answer(phase="B", base="IDx_400k")


@pytest.mark.unit
def test_generated_answer_retrieval_tuples_length_mismatch_ids_vs_text() -> None:
    with pytest.raises(RetrievalTupleLengthMismatchError) as exc_info:
        _make_answer(
            chunk_ids=("c1", "c2"),
            chunks_text=("t1",),
            scores=(0.9, 0.8),
        )
    err = exc_info.value
    assert err.chunk_ids_len == 2
    assert err.chunks_text_len == 1
    assert err.scores_len == 2


@pytest.mark.unit
def test_generated_answer_retrieval_tuples_length_mismatch_ids_vs_scores() -> None:
    with pytest.raises(RetrievalTupleLengthMismatchError) as exc_info:
        _make_answer(
            chunk_ids=("c1",),
            chunks_text=("t1",),
            scores=(0.9, 0.8),
        )
    assert exc_info.value.chunk_ids_len == 1
    assert exc_info.value.scores_len == 2


@pytest.mark.unit
def test_generated_answer_all_tuples_length_mismatch() -> None:
    with pytest.raises(RetrievalTupleLengthMismatchError):
        _make_answer(
            chunk_ids=("c1", "c2", "c3"),
            chunks_text=("t1",),
            scores=(0.9, 0.8),
        )


@pytest.mark.unit
def test_generated_answer_empty_retrieval_tuples_valid() -> None:
    ga = _make_answer(chunk_ids=(), chunks_text=(), scores=())
    assert ga.retrieved_chunk_ids == ()
    assert ga.retrieved_chunks_text == ()
    assert ga.retrieval_scores == ()


@pytest.mark.unit
def test_generated_answer_is_frozen() -> None:
    ga = _make_answer()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ga.phase = "B"  # type: ignore[misc]


@pytest.mark.unit
def test_generated_answer_identity_by_row_id() -> None:
    ga1 = _make_answer()
    ga2 = _make_answer()
    assert ga1.row_id == ga2.row_id
    assert ga1 == ga2


# ---------------------------------------------------------------------------
# EvaluationResult — construção e invariantes
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_evaluation_result_valid() -> None:
    er = _make_eval()
    assert er.final_score.value == pytest.approx(0.8)
    assert er.determinism_regime == DeterminismRegime.JUDGE
    assert er.critical_failure_flag is None


@pytest.mark.unit
def test_evaluation_result_with_flag_zero() -> None:
    er = _make_eval(flag=0)
    assert er.critical_failure_flag == 0


@pytest.mark.unit
def test_evaluation_result_with_flag_one() -> None:
    er = _make_eval(flag=1, note="Resposta perigosa detectada.")
    assert er.critical_failure_flag == 1
    assert er.critical_failure_note == "Resposta perigosa detectada."


@pytest.mark.unit
@pytest.mark.parametrize("bad_flag", [-1, 2, 99, -99])
def test_evaluation_result_invalid_flag_raises(bad_flag: int) -> None:
    with pytest.raises(InvalidCriticalFailureFlagError) as exc_info:
        _make_eval(flag=bad_flag)
    assert exc_info.value.flag == bad_flag


@pytest.mark.unit
def test_evaluation_result_invalid_regime_type_raises() -> None:
    with pytest.raises(InteligenciomicaEvalError, match="DeterminismRegime"):
        EvaluationResult(
            answer=_make_answer(),
            metrics=_make_metrics(),
            final_score=FinalScore(0.8),
            determinism_regime="judge",  # type: ignore[arg-type]
            critical_failure_flag=None,
            critical_failure_note=None,
        )


@pytest.mark.unit
def test_evaluation_result_is_frozen() -> None:
    er = _make_eval()
    with pytest.raises(dataclasses.FrozenInstanceError):
        er.critical_failure_flag = 1  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EvaluationResult — is_failure
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("score", "threshold", "expected"),
    [
        (0.5, 0.6, True),  # abaixo do limiar
        (0.6, 0.6, False),  # igual ao limiar → não é falha (< estrito)
        (0.7, 0.6, False),  # acima do limiar
        (0.0, 0.6, True),  # score mínimo
        (1.0, 0.6, False),  # score máximo
    ],
)
def test_is_failure(score: float, threshold: float, expected: bool) -> None:
    er = _make_eval(final=score)
    assert er.is_failure(threshold) is expected


@pytest.mark.unit
def test_is_failure_nan_score_returns_false() -> None:
    er = EvaluationResult(
        answer=_make_answer(),
        metrics=_make_metrics(_NAN),
        final_score=FinalScore(_NAN),
        determinism_regime=DeterminismRegime.GENERATOR,
        critical_failure_flag=None,
        critical_failure_note=None,
    )
    assert er.is_failure(0.6) is False


@pytest.mark.unit
def test_is_failure_threshold_zero() -> None:
    er = _make_eval(final=0.0)
    assert er.is_failure(0.0) is False  # 0.0 < 0.0 é False


# ---------------------------------------------------------------------------
# EvaluationResult — is_critical_failure
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_is_critical_failure_none_flag() -> None:
    assert _make_eval(flag=None).is_critical_failure() is False


@pytest.mark.unit
def test_is_critical_failure_flag_zero() -> None:
    assert _make_eval(flag=0).is_critical_failure() is False


@pytest.mark.unit
def test_is_critical_failure_flag_one() -> None:
    assert _make_eval(flag=1).is_critical_failure() is True


# ---------------------------------------------------------------------------
# EvaluationResult — with_metrics (imutabilidade)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_with_metrics_returns_new_instance() -> None:
    original = _make_eval(
        metric_value=0.5, final=0.5, regime=DeterminismRegime.GENERATOR
    )
    new_metrics = _make_metrics(0.9)
    new_score = FinalScore(0.9)
    updated = original.with_metrics(new_metrics, new_score, DeterminismRegime.JUDGE)

    assert updated is not original
    assert updated.metrics is new_metrics
    assert updated.final_score.value == pytest.approx(0.9)
    assert updated.determinism_regime == DeterminismRegime.JUDGE


@pytest.mark.unit
def test_with_metrics_does_not_mutate_original() -> None:
    original = _make_eval(
        metric_value=0.5, final=0.5, regime=DeterminismRegime.GENERATOR
    )
    original.with_metrics(_make_metrics(0.9), FinalScore(0.9), DeterminismRegime.JUDGE)

    assert original.final_score.value == pytest.approx(0.5)
    assert original.determinism_regime == DeterminismRegime.GENERATOR


@pytest.mark.unit
def test_with_metrics_preserves_other_fields() -> None:
    original = _make_eval(flag=1, note="nota original")
    updated = original.with_metrics(
        _make_metrics(0.9), FinalScore(0.9), DeterminismRegime.JUDGE
    )

    assert updated.critical_failure_flag == 1
    assert updated.critical_failure_note == "nota original"
    assert updated.answer is original.answer


# ---------------------------------------------------------------------------
# EvaluationResult — with_human_annotation (imutabilidade)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_with_human_annotation_returns_new_instance() -> None:
    original = _make_eval(flag=None, note=None)
    annotated = original.with_human_annotation(flag=1, note="Resposta errada.")

    assert annotated is not original
    assert annotated.critical_failure_flag == 1
    assert annotated.critical_failure_note == "Resposta errada."


@pytest.mark.unit
def test_with_human_annotation_does_not_mutate_original() -> None:
    original = _make_eval(flag=None, note=None)
    original.with_human_annotation(flag=1, note="anotação")

    assert original.critical_failure_flag is None
    assert original.critical_failure_note is None


@pytest.mark.unit
def test_with_human_annotation_flag_zero() -> None:
    er = _make_eval().with_human_annotation(flag=0, note=None)
    assert er.critical_failure_flag == 0
    assert er.critical_failure_note is None


@pytest.mark.unit
def test_with_human_annotation_invalid_flag_raises() -> None:
    original = _make_eval()
    with pytest.raises(InvalidCriticalFailureFlagError):
        original.with_human_annotation(flag=2, note=None)


@pytest.mark.unit
def test_with_human_annotation_preserves_metrics() -> None:
    metrics = _make_metrics(0.75)
    original = EvaluationResult(
        answer=_make_answer(),
        metrics=metrics,
        final_score=FinalScore(0.75),
        determinism_regime=DeterminismRegime.JUDGE,
        critical_failure_flag=None,
        critical_failure_note=None,
    )
    annotated = original.with_human_annotation(flag=0, note="ok")

    assert annotated.metrics is metrics
    assert annotated.final_score.value == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# EvaluationResult — combinação de mutations
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_chained_mutations_produce_independent_instances() -> None:
    base = _make_eval(final=0.5, flag=None)
    with_m = base.with_metrics(
        _make_metrics(0.9), FinalScore(0.9), DeterminismRegime.JUDGE
    )
    annotated = with_m.with_human_annotation(flag=1, note="crítico")

    # base e with_m não foram alterados
    assert base.final_score.value == pytest.approx(0.5)
    assert base.critical_failure_flag is None
    assert with_m.critical_failure_flag is None
    assert annotated.final_score.value == pytest.approx(0.9)
    assert annotated.critical_failure_flag == 1


@pytest.mark.unit
def test_evaluation_result_nan_final_score_valid() -> None:
    er = EvaluationResult(
        answer=_make_answer(),
        metrics=_make_metrics(_NAN),
        final_score=FinalScore(_NAN),
        determinism_regime=DeterminismRegime.GENERATOR,
        critical_failure_flag=None,
        critical_failure_note=None,
    )
    assert math.isnan(er.final_score.value)
    assert er.is_failure(0.6) is False
    assert er.is_critical_failure() is False
