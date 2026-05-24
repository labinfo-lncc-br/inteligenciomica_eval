from __future__ import annotations

import math
from pathlib import Path

import pytest

from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
)
from inteligenciomica_eval.domain.errors import StorageError
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
    ParquetStorage,
)

_NAN = float("nan")

# ---------------------------------------------------------------------------
# Factories
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


def _make_result(
    *,
    run_id: str = "run-001",
    phase: str = "A",
    base: str = "IDx_400k",
    llm: str = "llama3",
    seed: int = 42,
    question_id: str = "q01",
    metrics: MetricVector | None = None,
    final: float = 0.75,
    regime: DeterminismRegime = DeterminismRegime.JUDGE,
    flag: int | None = None,
    note: str | None = None,
    generated_answer: str = "Resposta gerada.",
    chunk_ids: tuple[str, ...] = ("c1", "c2"),
    chunks_text: tuple[str, ...] = ("texto1", "texto2"),
    scores: tuple[float, ...] = (0.9, 0.8),
) -> EvaluationResult:
    row_id = RowId.from_cell(
        run_id=run_id,
        phase=phase,
        base=base,
        llm=llm,
        seed=seed,
        question_id=question_id,
    )
    answer = GeneratedAnswer(
        row_id=row_id,
        question=Question(
            question_id=question_id,
            text="O que é RAG?",
            ground_truth="Retrieval-Augmented Generation.",
        ),
        base=BaseId(base),
        llm=LLMId(llm),
        seed=Seed(seed),
        phase=phase,
        generated_answer=generated_answer,
        retrieved_chunk_ids=chunk_ids,
        retrieved_chunks_text=chunks_text,
        retrieval_scores=scores,
    )
    return EvaluationResult(
        answer=answer,
        metrics=metrics or _make_metrics(),
        final_score=FinalScore(final),
        determinism_regime=regime,
        critical_failure_flag=flag,
        critical_failure_note=note,
    )


def _make_storage(tmp_path: Path, *, round_id: str = "round_1") -> ParquetStorage:
    return ParquetStorage(
        tmp_path,
        run_id="run-001",
        round_id=round_id,
        judge_model="prometheus-8x7b",
        embedding_model="bge-m3",
        chunk_strategy="fixed_512",
    )


# ---------------------------------------------------------------------------
# exists — before any write
# ---------------------------------------------------------------------------


class TestExistsEmpty:
    def test_nonexistent_base_dir_returns_false(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path / "nonexistent")
        row_id = _make_row_id()
        assert storage.exists(row_id) is False

    def test_empty_base_dir_returns_false(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        assert storage.exists(_make_row_id()) is False


# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------


class TestAppend:
    def test_append_creates_parquet_file(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        result = _make_result()
        storage.append(result)

        files = list(tmp_path.rglob("*.parquet"))
        assert len(files) == 1

    def test_append_file_in_correct_partition(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path, round_id="round_1")
        result = _make_result(phase="A", base="IDx_400k", llm="llama3")
        storage.append(result)

        partition_dir = (
            tmp_path
            / "round_id=round_1"
            / "experiment_phase=A"
            / "base=IDx_400k"
            / "llm=llama3"
        )
        assert partition_dir.is_dir()
        files = list(partition_dir.glob("*.parquet"))
        assert len(files) == 1

    def test_file_named_by_row_id(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        result = _make_result()
        storage.append(result)

        files = list(tmp_path.rglob("*.parquet"))
        assert files[0].stem == result.answer.row_id.value

    def test_exists_true_after_append(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        result = _make_result()
        storage.append(result)
        assert storage.exists(result.answer.row_id) is True

    def test_append_twice_no_duplicate(self, tmp_path: Path) -> None:
        # last-write-wins: second append overwrites, never creates a second file
        storage = _make_storage(tmp_path)
        result = _make_result()
        storage.append(result)
        storage.append(result)

        files = list(tmp_path.rglob("*.parquet"))
        assert len(files) == 1

    def test_append_last_write_wins_updates_data(self, tmp_path: Path) -> None:
        # last-write-wins: second append with different data is reflected on load
        storage = _make_storage(tmp_path)
        v1 = _make_result(metrics=_make_nan_metrics(), final=_NAN)
        storage.append(v1)

        v2 = _make_result(metrics=_make_metrics(0.9), final=0.9)
        storage.append(v2)  # overwrites v1

        frame = storage.load(round_id="round_1")
        assert len(frame.results) == 1
        assert frame.results[0].metrics.answer_correctness == pytest.approx(
            0.9, abs=1e-4
        )

    def test_append_different_rows_creates_separate_files(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        r1 = _make_result(question_id="q01")
        r2 = _make_result(question_id="q02")
        storage.append(r1)
        storage.append(r2)

        files = list(tmp_path.rglob("*.parquet"))
        assert len(files) == 2

    def test_append_with_nan_metrics(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        result = _make_result(metrics=_make_nan_metrics(), final=_NAN)
        storage.append(result)  # must not raise

        assert storage.exists(result.answer.row_id) is True

    def test_append_with_critical_failure_flag(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        result = _make_result(flag=1, note="hallucination")
        storage.append(result)
        assert storage.exists(result.answer.row_id) is True


# ---------------------------------------------------------------------------
# load — roundtrip
# ---------------------------------------------------------------------------


class TestLoad:
    def test_load_empty_round_returns_empty_frame(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        frame = storage.load(round_id="round_nonexistent")
        assert frame.results == ()

    def test_load_empty_phase_returns_empty_frame(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        result = _make_result(phase="A")
        storage.append(result)

        frame = storage.load(round_id="round_1", phase="B")
        assert frame.results == ()

    def test_load_round_returns_appended_result(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        result = _make_result()
        storage.append(result)

        frame = storage.load(round_id="round_1")
        assert len(frame.results) == 1

    def test_load_roundtrip_row_id(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        original = _make_result()
        storage.append(original)

        frame = storage.load(round_id="round_1")
        restored = frame.results[0]
        assert restored.answer.row_id.value == original.answer.row_id.value

    def test_load_roundtrip_valid_metrics(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        original = _make_result(metrics=_make_metrics(0.72))
        storage.append(original)

        frame = storage.load(round_id="round_1")
        restored = frame.results[0]
        assert restored.metrics.answer_correctness == pytest.approx(0.72, abs=1e-4)
        assert restored.metrics.faithfulness == pytest.approx(0.72, abs=1e-4)
        assert restored.final_score.value == pytest.approx(0.75, abs=1e-4)

    def test_load_roundtrip_nan_metrics(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        original = _make_result(metrics=_make_nan_metrics(), final=_NAN)
        storage.append(original)

        frame = storage.load(round_id="round_1")
        restored = frame.results[0]
        assert math.isnan(restored.metrics.answer_correctness)
        assert math.isnan(restored.final_score.value)

    def test_load_roundtrip_none_flag(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        original = _make_result(flag=None)
        storage.append(original)

        frame = storage.load(round_id="round_1")
        assert frame.results[0].critical_failure_flag is None

    def test_load_roundtrip_flag_and_note(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        original = _make_result(flag=1, note="alucinação")
        storage.append(original)

        frame = storage.load(round_id="round_1")
        restored = frame.results[0]
        assert restored.critical_failure_flag == 1
        assert restored.critical_failure_note == "alucinação"

    def test_load_phase_filter(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        storage.append(_make_result(phase="A", question_id="q01"))
        storage.append(_make_result(phase="B", base="fixed", question_id="q01"))

        frame_a = storage.load(round_id="round_1", phase="A")
        frame_b = storage.load(round_id="round_1", phase="B")
        assert len(frame_a.results) == 1
        assert len(frame_b.results) == 1
        assert frame_a.results[0].answer.phase == "A"
        assert frame_b.results[0].answer.phase == "B"

    def test_load_all_phases_when_none(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        storage.append(_make_result(phase="A", question_id="q01"))
        storage.append(_make_result(phase="B", base="fixed", question_id="q01"))

        frame = storage.load(round_id="round_1", phase=None)
        assert len(frame.results) == 2

    def test_load_multiple_questions(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        for qid in ("q01", "q02", "q03"):
            storage.append(_make_result(question_id=qid))

        frame = storage.load(round_id="round_1")
        assert len(frame.results) == 3

    def test_load_roundtrip_retrieval_data(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        original = _make_result(
            chunk_ids=("chunk_a", "chunk_b", "chunk_c"),
            chunks_text=("txt_a", "txt_b", "txt_c"),
            scores=(0.95, 0.85, 0.75),
        )
        storage.append(original)

        frame = storage.load(round_id="round_1")
        restored = frame.results[0]
        assert restored.answer.retrieved_chunk_ids == ("chunk_a", "chunk_b", "chunk_c")
        assert restored.answer.retrieved_chunks_text == ("txt_a", "txt_b", "txt_c")
        assert restored.answer.retrieval_scores == pytest.approx(
            (0.95, 0.85, 0.75), abs=1e-4
        )


# ---------------------------------------------------------------------------
# update_metrics
# ---------------------------------------------------------------------------


class TestUpdateMetrics:
    def test_update_overwrites_null_metrics(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        # Generation pass: append with NaN metrics
        original = _make_result(metrics=_make_nan_metrics(), final=_NAN)
        storage.append(original)

        # Judging pass: update with real metrics
        new_metrics = _make_metrics(0.9)
        storage.update_metrics(original.answer.row_id, new_metrics)

        frame = storage.load(round_id="round_1")
        restored = frame.results[0]
        assert restored.metrics.answer_correctness == pytest.approx(0.9, abs=1e-4)
        assert restored.metrics.bertscore_f1 == pytest.approx(0.9, abs=1e-4)

    def test_update_does_not_change_other_columns(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        original = _make_result(
            metrics=_make_nan_metrics(),
            final=_NAN,
            flag=None,
            note=None,
        )
        storage.append(original)

        storage.update_metrics(original.answer.row_id, _make_metrics(0.7))

        frame = storage.load(round_id="round_1")
        restored = frame.results[0]
        # final_score not changed by update_metrics
        assert math.isnan(restored.final_score.value)
        # critical_failure_flag not changed
        assert restored.critical_failure_flag is None
        # generated_answer not changed
        assert restored.answer.generated_answer == "Resposta gerada."

    def test_update_partial_nan_metrics(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        original = _make_result(metrics=_make_nan_metrics(), final=_NAN)
        storage.append(original)

        partial = MetricVector(
            answer_correctness=0.85,
            answer_similarity=_NAN,
            faithfulness=0.80,
            context_precision=_NAN,
            context_recall=0.75,
            answer_relevancy=0.70,
            bertscore_f1=_NAN,
            rubric_biomed_score=0.65,
        )
        storage.update_metrics(original.answer.row_id, partial)

        frame = storage.load(round_id="round_1")
        m = frame.results[0].metrics
        assert m.answer_correctness == pytest.approx(0.85, abs=1e-4)
        assert math.isnan(m.answer_similarity)
        assert m.faithfulness == pytest.approx(0.80, abs=1e-4)
        assert math.isnan(m.context_precision)

    def test_update_nonexistent_row_raises_storage_error(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        phantom_id = _make_row_id(question_id="q99")

        with pytest.raises(StorageError, match="update_metrics"):
            storage.update_metrics(phantom_id, _make_metrics())

    def test_update_metric_nan_fields_reflects_new_nans(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        original = _make_result(metrics=_make_nan_metrics(), final=_NAN)
        storage.append(original)

        partial = MetricVector(
            answer_correctness=0.9,
            answer_similarity=_NAN,
            faithfulness=0.8,
            context_precision=_NAN,
            context_recall=0.7,
            answer_relevancy=0.6,
            bertscore_f1=0.5,
            rubric_biomed_score=0.4,
        )
        storage.update_metrics(original.answer.row_id, partial)

        frame = storage.load(round_id="round_1")
        restored = frame.results[0]
        nan_fields = set(restored.metrics.nan_fields())
        assert nan_fields == {"answer_similarity", "context_precision"}


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_exists_on_unreadable_file_raises_storage_error(
        self, tmp_path: Path
    ) -> None:
        storage = _make_storage(tmp_path)
        result = _make_result()
        storage.append(result)

        # Corrupt the file
        files = list(tmp_path.rglob("*.parquet"))
        files[0].write_bytes(b"not a parquet file")

        with pytest.raises(StorageError, match="exists"):
            storage.exists(result.answer.row_id)

    def test_load_corrupted_file_raises_storage_error(self, tmp_path: Path) -> None:
        storage = _make_storage(tmp_path)
        result = _make_result()
        storage.append(result)

        files = list(tmp_path.rglob("*.parquet"))
        files[0].write_bytes(b"corrupted")

        with pytest.raises(StorageError, match="load"):
            storage.load(round_id="round_1")


# ---------------------------------------------------------------------------
# Port contract — isinstance checks
# ---------------------------------------------------------------------------


class TestPortContract:
    def test_implements_result_writer_port(self, tmp_path: Path) -> None:
        from inteligenciomica_eval.domain.ports import ResultWriterPort

        storage = _make_storage(tmp_path)
        assert isinstance(storage, ResultWriterPort)

    def test_implements_result_reader_port(self, tmp_path: Path) -> None:
        from inteligenciomica_eval.domain.ports import ResultReaderPort

        storage = _make_storage(tmp_path)
        assert isinstance(storage, ResultReaderPort)
