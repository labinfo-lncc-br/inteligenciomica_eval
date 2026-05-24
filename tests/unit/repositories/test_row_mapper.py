from __future__ import annotations

import math

import pytest

from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
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
from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
    RowProvenance,
    _nan_to_none,
    _none_to_nan,
    _safe_msg,
    from_row,
    to_row,
)

_NAN = float("nan")

# ---------------------------------------------------------------------------
# Shared factories
# ---------------------------------------------------------------------------


def _make_row_id(
    *,
    run_id: str = "run-001",
    phase: str = "A",
    base: str = "IDx_400k",
    llm: str = "llama3",
    seed: int = 42,
    question_id: str = "q01",
) -> RowId:
    return RowId.from_cell(
        run_id=run_id,
        phase=phase,
        base=base,
        llm=llm,
        seed=seed,
        question_id=question_id,
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


def _make_nan_metrics() -> MetricVector:
    return MetricVector(
        answer_correctness=_NAN,
        answer_similarity=_NAN,
        faithfulness=_NAN,
        context_precision=_NAN,
        context_recall=_NAN,
        answer_relevancy=_NAN,
        bertscore_f1=_NAN,
        rubric_biomed_score=_NAN,
    )


def _make_answer(
    phase: str = "A",
    base: str = "IDx_400k",
) -> GeneratedAnswer:
    row_id = _make_row_id(phase=phase, base=base)
    return GeneratedAnswer(
        row_id=row_id,
        question=Question(
            question_id="q01",
            text="O que é RAG?",
            ground_truth="Retrieval-Augmented Generation.",
        ),
        base=BaseId(base),
        llm=LLMId("llama3"),
        seed=Seed(42),
        phase=phase,
        generated_answer="Resposta gerada.",
        retrieved_chunk_ids=("c1", "c2"),
        retrieved_chunks_text=("texto1", "texto2"),
        retrieval_scores=(0.9, 0.8),
    )


def _make_result(
    phase: str = "A",
    base: str = "IDx_400k",
    metrics: MetricVector | None = None,
    final: float = 0.75,
    regime: DeterminismRegime = DeterminismRegime.JUDGE,
    flag: int | None = None,
    note: str | None = None,
) -> EvaluationResult:
    return EvaluationResult(
        answer=_make_answer(phase=phase, base=base),
        metrics=metrics or _make_metrics(),
        final_score=FinalScore(final),
        determinism_regime=regime,
        critical_failure_flag=flag,
        critical_failure_note=note,
    )


# ---------------------------------------------------------------------------
# _nan_to_none / _none_to_nan
# ---------------------------------------------------------------------------


class TestNanNoneBridge:
    def test_nan_to_none_returns_none_for_nan(self) -> None:
        assert _nan_to_none(_NAN) is None

    def test_nan_to_none_passes_finite_float(self) -> None:
        assert _nan_to_none(0.5) == pytest.approx(0.5)

    def test_nan_to_none_passes_zero(self) -> None:
        assert _nan_to_none(0.0) == 0.0

    def test_none_to_nan_returns_nan_for_none(self) -> None:
        assert math.isnan(_none_to_nan(None))

    def test_none_to_nan_passes_finite_float(self) -> None:
        assert _none_to_nan(0.5) == pytest.approx(0.5)

    def test_roundtrip_nan(self) -> None:
        assert math.isnan(_none_to_nan(_nan_to_none(_NAN)))  # type: ignore[arg-type]

    def test_roundtrip_finite(self) -> None:
        assert _none_to_nan(_nan_to_none(0.42)) == pytest.approx(0.42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# to_row
# ---------------------------------------------------------------------------


class TestToRow:
    def test_core_identity_fields(self) -> None:
        result = _make_result()
        row = to_row(result)

        assert row["row_id"] == result.answer.row_id.value
        assert row["experiment_phase"] == "A"
        assert row["base"] == "IDx_400k"
        assert row["llm"] == "llama3"
        assert row["seed"] == 42
        assert row["question_id"] == "q01"
        assert row["question"] == "O que é RAG?"
        assert row["ground_truth"] == "Retrieval-Augmented Generation."
        assert row["generated_answer"] == "Resposta gerada."

    def test_retrieval_tuples_become_lists(self) -> None:
        result = _make_result()
        row = to_row(result)

        assert row["retrieved_chunk_ids"] == ["c1", "c2"]
        assert row["retrieved_chunks_text"] == ["texto1", "texto2"]
        assert row["retrieval_scores"] == pytest.approx([0.9, 0.8])

    def test_valid_metrics_stored_as_float(self) -> None:
        result = _make_result(metrics=_make_metrics(0.8))
        row = to_row(result)

        for field in (
            "answer_correctness",
            "answer_similarity",
            "faithfulness",
            "context_precision",
            "context_recall",
            "answer_relevancy",
            "bertscore_f1",
            "rubric_biomed_score",
        ):
            assert row[field] == pytest.approx(0.8), f"{field} should be 0.8"

    def test_nan_metrics_become_none(self) -> None:
        result = _make_result(metrics=_make_nan_metrics())
        row = to_row(result)

        for field in (
            "answer_correctness",
            "answer_similarity",
            "faithfulness",
            "context_precision",
            "context_recall",
            "answer_relevancy",
            "bertscore_f1",
            "rubric_biomed_score",
        ):
            assert row[field] is None, f"{field} should be None (NaN→NULL)"

    def test_nan_final_score_becomes_none(self) -> None:
        result = _make_result(final=_NAN)
        row = to_row(result)
        assert row["final_score"] is None

    def test_valid_final_score_stored(self) -> None:
        result = _make_result(final=0.65)
        row = to_row(result)
        assert row["final_score"] == pytest.approx(0.65)

    def test_critical_failure_flag_none_stored_as_none(self) -> None:
        result = _make_result(flag=None)
        row = to_row(result)
        # int8 NULL — not the same column type as float NULL
        assert row["critical_failure_flag"] is None

    def test_critical_failure_flag_int_stored(self) -> None:
        for flag_val in (0, 1):
            result = _make_result(flag=flag_val)
            row = to_row(result)
            assert row["critical_failure_flag"] == flag_val

    def test_judge_regime_maps_to_batch_invariant_true(self) -> None:
        result = _make_result(regime=DeterminismRegime.JUDGE)
        row = to_row(result)
        assert row["batch_invariant"] is True

    def test_generator_regime_maps_to_batch_invariant_false(self) -> None:
        result = _make_result(regime=DeterminismRegime.GENERATOR)
        row = to_row(result)
        assert row["batch_invariant"] is False

    def test_metric_nan_fields_populated(self) -> None:
        partial = MetricVector(
            answer_correctness=_NAN,
            answer_similarity=0.9,
            faithfulness=_NAN,
            context_precision=0.8,
            context_recall=0.7,
            answer_relevancy=0.6,
            bertscore_f1=0.5,
            rubric_biomed_score=0.4,
        )
        result = _make_result(metrics=partial)
        row = to_row(result)
        assert set(row["metric_nan_fields"]) == {"answer_correctness", "faithfulness"}

    def test_provenance_fields_from_rowprovenance(self) -> None:
        prov = RowProvenance(
            run_id="run-xyz",
            round_id="round_1",
            judge_model="prometheus-8x7b",
            embedding_model="bge-m3",
            chunk_strategy="fixed_512",
            reranker="colbert",
            top_k=5,
            prompt_version="v2",
            temperature=0.1,
            vllm_version="0.4.0",
            ragas_version="0.1.0",
            config_hash="abc123",
        )
        result = _make_result()
        row = to_row(result, prov)

        assert row["run_id"] == "run-xyz"
        assert row["round_id"] == "round_1"
        assert row["judge_model"] == "prometheus-8x7b"
        assert row["embedding_model"] == "bge-m3"
        assert row["top_k"] == 5
        assert row["vllm_version"] == "0.4.0"
        assert row["config_hash"] == "abc123"

    def test_default_provenance_when_none(self) -> None:
        row = to_row(_make_result(), None)
        assert row["run_id"] == ""
        assert row["round_id"] == ""
        assert row["vllm_version"] == "unknown"

    def test_schema_keys_complete(self) -> None:
        from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
            EVAL_SCHEMA,
        )

        row = to_row(_make_result())
        expected_keys = {field.name for field in EVAL_SCHEMA}
        assert set(row.keys()) == expected_keys


# ---------------------------------------------------------------------------
# from_row
# ---------------------------------------------------------------------------


class TestFromRow:
    def _base_row(self) -> dict[str, object]:
        result = _make_result()
        return to_row(result)

    def test_question_fields_reconstructed(self) -> None:
        row = self._base_row()
        result = from_row(row)  # type: ignore[arg-type]

        assert result.answer.question.question_id == "q01"
        assert result.answer.question.text == "O que é RAG?"
        assert result.answer.question.ground_truth == "Retrieval-Augmented Generation."

    def test_row_id_reconstructed(self) -> None:
        original = _make_result()
        row = to_row(original)
        restored = from_row(row)  # type: ignore[arg-type]
        assert restored.answer.row_id.value == original.answer.row_id.value

    def test_base_llm_seed_reconstructed(self) -> None:
        row = self._base_row()
        result = from_row(row)  # type: ignore[arg-type]
        assert result.answer.base.value == "IDx_400k"
        assert result.answer.llm.value == "llama3"
        assert result.answer.seed.value == 42

    def test_retrieval_tuples_reconstructed(self) -> None:
        row = self._base_row()
        result = from_row(row)  # type: ignore[arg-type]
        assert result.answer.retrieved_chunk_ids == ("c1", "c2")
        assert result.answer.retrieved_chunks_text == ("texto1", "texto2")

    def test_none_metrics_become_nan(self) -> None:
        row = self._base_row()
        for field in (
            "answer_correctness",
            "answer_similarity",
            "faithfulness",
            "context_precision",
            "context_recall",
            "answer_relevancy",
            "bertscore_f1",
            "rubric_biomed_score",
        ):
            row[field] = None
        result = from_row(row)  # type: ignore[arg-type]
        assert math.isnan(result.metrics.answer_correctness)
        assert math.isnan(result.metrics.rubric_biomed_score)

    def test_none_final_score_becomes_nan(self) -> None:
        row = self._base_row()
        row["final_score"] = None
        result = from_row(row)  # type: ignore[arg-type]
        assert math.isnan(result.final_score.value)

    def test_none_critical_failure_flag_stays_none(self) -> None:
        row = self._base_row()
        row["critical_failure_flag"] = None
        result = from_row(row)  # type: ignore[arg-type]
        assert result.critical_failure_flag is None

    def test_int_critical_failure_flag_restored(self) -> None:
        for flag_val in (0, 1):
            row = self._base_row()
            row["critical_failure_flag"] = flag_val
            result = from_row(row)  # type: ignore[arg-type]
            assert result.critical_failure_flag == flag_val

    def test_batch_invariant_true_gives_judge_regime(self) -> None:
        row = self._base_row()
        row["batch_invariant"] = True
        result = from_row(row)  # type: ignore[arg-type]
        assert result.determinism_regime == DeterminismRegime.JUDGE

    def test_batch_invariant_false_gives_generator_regime(self) -> None:
        row = self._base_row()
        row["batch_invariant"] = False
        result = from_row(row)  # type: ignore[arg-type]
        assert result.determinism_regime == DeterminismRegime.GENERATOR


# ---------------------------------------------------------------------------
# Roundtrip — to_row -> from_row
# ---------------------------------------------------------------------------


class TestRoundtrip:
    def _roundtrip(self, result: EvaluationResult) -> EvaluationResult:
        return from_row(to_row(result))  # type: ignore[arg-type]

    def test_all_valid_metrics(self) -> None:
        original = _make_result(metrics=_make_metrics(0.75))
        restored = self._roundtrip(original)

        assert restored.metrics.answer_correctness == pytest.approx(0.75, abs=1e-4)
        assert restored.metrics.faithfulness == pytest.approx(0.75, abs=1e-4)
        assert restored.final_score.value == pytest.approx(0.75, abs=1e-4)

    def test_all_nan_metrics_roundtrip(self) -> None:
        original = _make_result(metrics=_make_nan_metrics(), final=_NAN)
        restored = self._roundtrip(original)

        for field in _make_nan_metrics().__dataclass_fields__:
            assert math.isnan(getattr(restored.metrics, field)), field
        assert math.isnan(restored.final_score.value)

    def test_partial_nan_metrics_roundtrip(self) -> None:
        partial = MetricVector(
            answer_correctness=0.9,
            answer_similarity=_NAN,
            faithfulness=0.8,
            context_precision=_NAN,
            context_recall=0.7,
            answer_relevancy=0.6,
            bertscore_f1=_NAN,
            rubric_biomed_score=0.5,
        )
        original = _make_result(metrics=partial)
        restored = self._roundtrip(original)

        assert restored.metrics.answer_correctness == pytest.approx(0.9, abs=1e-4)
        assert math.isnan(restored.metrics.answer_similarity)
        assert restored.metrics.faithfulness == pytest.approx(0.8, abs=1e-4)
        assert math.isnan(restored.metrics.context_precision)

    def test_critical_failure_flag_none_roundtrip(self) -> None:
        original = _make_result(flag=None)
        restored = self._roundtrip(original)
        assert restored.critical_failure_flag is None

    def test_critical_failure_flag_one_roundtrip(self) -> None:
        original = _make_result(flag=1, note="hallucination detected")
        restored = self._roundtrip(original)
        assert restored.critical_failure_flag == 1
        assert restored.critical_failure_note == "hallucination detected"

    def test_judge_regime_roundtrip(self) -> None:
        original = _make_result(regime=DeterminismRegime.JUDGE)
        restored = self._roundtrip(original)
        assert restored.determinism_regime == DeterminismRegime.JUDGE

    def test_generator_regime_roundtrip(self) -> None:
        original = _make_result(regime=DeterminismRegime.GENERATOR)
        restored = self._roundtrip(original)
        assert restored.determinism_regime == DeterminismRegime.GENERATOR

    def test_row_id_identity_preserved(self) -> None:
        original = _make_result()
        restored = self._roundtrip(original)
        assert restored.answer.row_id.value == original.answer.row_id.value

    def test_phase_b_roundtrip(self) -> None:
        original = _make_result(phase="B", base="fixed")
        restored = self._roundtrip(original)
        assert restored.answer.phase == "B"
        assert restored.answer.base.value == "fixed"

    def test_nan_vs_none_semantic_distinction(self) -> None:
        """NaN metric and None flag must remain semantically distinct after roundtrip."""
        original = _make_result(metrics=_make_nan_metrics(), flag=None)
        row = to_row(original)

        # Both are stored as None in the dict, but column types differ in Parquet
        assert row["answer_correctness"] is None  # float NULL (NaN→NULL)
        assert row["critical_failure_flag"] is None  # int8 NULL (not annotated)

        restored = self._roundtrip(original)
        # float NULL → NaN (float)
        assert math.isnan(restored.metrics.answer_correctness)
        # int8 NULL → None (Python None)
        assert restored.critical_failure_flag is None
        # Confirm types differ
        assert isinstance(restored.metrics.answer_correctness, float)
        assert restored.critical_failure_flag is None


# ---------------------------------------------------------------------------
# _safe_msg — path redaction
# ---------------------------------------------------------------------------


class TestSafeMsg:
    def test_absolute_unix_path_redacted(self) -> None:
        msg = "failed to read /home/user/data/secret.parquet"
        result = _safe_msg(Exception(msg))
        assert "/home" not in result
        assert "<path>" in result

    def test_nested_hive_path_redacted(self) -> None:
        msg = "IOError: /var/data/eval/round_id=round_1/experiment_phase=A/file.parquet not found"
        result = _safe_msg(Exception(msg))
        assert "/var" not in result
        assert "<path>" in result

    def test_message_without_paths_unchanged(self) -> None:
        msg = "Row abc123 not found — run append first"
        result = _safe_msg(Exception(msg))
        assert result == msg

    def test_multiple_paths_all_redacted(self) -> None:
        msg = "cannot merge /tmp/a.parquet and /tmp/b.parquet"
        result = _safe_msg(Exception(msg))
        assert "/tmp" not in result
        assert result.count("<path>") == 2
