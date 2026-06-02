"""Integration tests for ParquetStorage.update_annotation / current_annotation_flag.

Roundtrip: append EvaluationResult → update_annotation → load → verify field.
"""

from __future__ import annotations

from pathlib import Path

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
    ParquetStorage,
)

_NAN = float("nan")

# ---------------------------------------------------------------------------
# Builders
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


def _make_result(row_id: RowId, *, flag: int | None = None) -> EvaluationResult:
    metrics = MetricVector(
        answer_correctness=0.8,
        answer_similarity=0.8,
        faithfulness=0.8,
        context_precision=0.8,
        context_recall=0.8,
        answer_relevancy=0.8,
        bertscore_f1=0.8,
        rubric_biomed_score=0.8,
    )
    answer = GeneratedAnswer(
        row_id=row_id,
        question=Question(
            question_id="q01",
            text="O que é RAG?",
            ground_truth="Retrieval-Augmented Generation.",
        ),
        base=BaseId("IDx_400k"),
        llm=LLMId("llama3"),
        seed=Seed(42),
        phase="A",
        generated_answer="Resposta gerada.",
        retrieved_chunk_ids=("c1",),
        retrieved_chunks_text=("Texto do chunk.",),
        retrieval_scores=(0.9,),
    )
    return EvaluationResult(
        answer=answer,
        metrics=metrics,
        final_score=FinalScore(0.75),
        determinism_regime=DeterminismRegime.JUDGE,
        critical_failure_flag=flag,
        critical_failure_note=None,
    )


def _make_storage(tmp_path: Path, *, run_id: str = "run-001") -> ParquetStorage:
    return ParquetStorage(
        base_dir=tmp_path,
        run_id=run_id,
        round_id="round_1",
        judge_model="judge-v1",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_update_annotation_roundtrip(tmp_path: Path) -> None:
    """append → update_annotation → load → critical_failure_flag correto."""
    storage = _make_storage(tmp_path)
    row_id = _make_row_id()
    result = _make_result(row_id)
    storage.append(result)

    # Antes de anotar: flag deve ser None
    assert storage.current_annotation_flag(row_id) is None

    storage.update_annotation(
        row_id, critical_failure_flag=1, critical_failure_note="Erro crítico"
    )

    # Verificar via current_annotation_flag
    assert storage.current_annotation_flag(row_id) == 1

    # Verificar via load → EvaluationResult
    frame = storage.load(round_id="round_1", phase="A", run_id="run-001")
    assert len(frame.results) == 1
    loaded = frame.results[0]
    assert loaded.critical_failure_flag == 1
    assert loaded.critical_failure_note == "Erro crítico"


def test_update_annotation_flag_zero(tmp_path: Path) -> None:
    """flag=0 deve ser persistido corretamente (não confundir com None/falsy)."""
    storage = _make_storage(tmp_path)
    row_id = _make_row_id()
    storage.append(_make_result(row_id))

    storage.update_annotation(row_id, critical_failure_flag=0)

    assert storage.current_annotation_flag(row_id) == 0

    frame = storage.load(round_id="round_1", phase="A", run_id="run-001")
    assert frame.results[0].critical_failure_flag == 0


def test_update_annotation_does_not_touch_other_columns(tmp_path: Path) -> None:
    """update_annotation não deve alterar métricas ou resposta gerada."""
    storage = _make_storage(tmp_path)
    row_id = _make_row_id()
    result = _make_result(row_id)
    storage.append(result)

    storage.update_annotation(row_id, critical_failure_flag=1)

    frame = storage.load(round_id="round_1", phase="A", run_id="run-001")
    loaded = frame.results[0]
    assert loaded.answer.generated_answer == "Resposta gerada."
    assert loaded.metrics.answer_correctness == pytest.approx(0.8, abs=1e-4)


def test_current_annotation_flag_returns_none_when_row_absent(tmp_path: Path) -> None:
    """current_annotation_flag devolve None para row_id inexistente."""
    storage = _make_storage(tmp_path)
    row_id = _make_row_id(question_id="q99")
    assert storage.current_annotation_flag(row_id) is None


def test_update_annotation_raises_storage_error_when_row_absent(tmp_path: Path) -> None:
    """update_annotation deve levantar StorageError se a linha não existe."""
    from inteligenciomica_eval.domain.errors import StorageError

    storage = _make_storage(tmp_path)
    row_id = _make_row_id(question_id="q99")

    with pytest.raises(StorageError):
        storage.update_annotation(row_id, critical_failure_flag=1)


def test_overwrite_annotation(tmp_path: Path) -> None:
    """Segunda chamada a update_annotation sobrescreve a primeira (last-write-wins)."""
    storage = _make_storage(tmp_path)
    row_id = _make_row_id()
    storage.append(_make_result(row_id))

    storage.update_annotation(
        row_id, critical_failure_flag=0, critical_failure_note="Inicial"
    )
    storage.update_annotation(
        row_id, critical_failure_flag=1, critical_failure_note="Corrigido"
    )

    assert storage.current_annotation_flag(row_id) == 1

    frame = storage.load(round_id="round_1", phase="A", run_id="run-001")
    loaded = frame.results[0]
    assert loaded.critical_failure_flag == 1
    assert loaded.critical_failure_note == "Corrigido"
