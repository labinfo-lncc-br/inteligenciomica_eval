"""Testes unitários de AnnotationWorkflowUseCase (TAREFA-308, Camada 3)."""

from __future__ import annotations

import math

import pytest
from factories import (
    make_evaluation_result,
    make_generated_answer,
    make_metric_vector,
    make_row_id,
)
from fakes.storage import (
    InMemoryResultReader,
    InMemoryResultStore,
    InMemoryResultWriter,
)

from inteligenciomica_eval.application.use_cases.annotation_workflow import (
    AnnotationConfig,
    AnnotationWorkflowUseCase,
)
from inteligenciomica_eval.domain.errors import ScoreOutOfRangeError, StorageError
from inteligenciomica_eval.domain.value_objects import DeterminismRegime

_NAN = float("nan")
_ROUND_ID = "round_308"
_RUN_ID = "run_308"
_SCORE_THRESHOLD = 0.6
_RUBRIC_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_uc(
    store: InMemoryResultStore | None = None,
    *,
    score_threshold: float = _SCORE_THRESHOLD,
    rubric_threshold: float = _RUBRIC_THRESHOLD,
    max_to_review: int | None = None,
) -> tuple[AnnotationWorkflowUseCase, InMemoryResultWriter, InMemoryResultStore]:
    s = store or InMemoryResultStore()
    writer = InMemoryResultWriter(s, round_id=_ROUND_ID)
    reader = InMemoryResultReader(s)
    cfg = AnnotationConfig(
        round_id=_ROUND_ID,
        score_threshold=score_threshold,
        rubric_threshold=rubric_threshold,
        max_to_review=max_to_review,
    )
    uc = AnnotationWorkflowUseCase(reader=reader, writer=writer, config=cfg)
    return uc, writer, s


def _make_result(
    *,
    question_id: str = "q01",
    final_score: float = 0.8,
    rubric_biomed_score: float = 0.9,
    critical_failure_flag: int | None = None,
) -> object:
    """Helper para criar EvaluationResult com final_score e rubric controlados."""
    metrics = make_metric_vector(rubric_biomed_score=rubric_biomed_score)
    return make_evaluation_result(
        answer=make_generated_answer(question_id=question_id),
        metrics=metrics,
        final_score=final_score,
        determinism_regime=DeterminismRegime.JUDGE,
        critical_failure_flag=critical_failure_flag,
    )


# ---------------------------------------------------------------------------
# TestGetReviewQueue
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetReviewQueue:
    def test_excludes_already_annotated_flag_zero(self) -> None:
        """Resultados com critical_failure_flag=0 já revisados são excluídos."""
        uc, writer, _store = _make_uc()
        r = _make_result(final_score=0.1, critical_failure_flag=0)
        writer.append(r)  # type: ignore[arg-type]
        queue = uc.get_review_queue(run_id=_RUN_ID)
        assert queue == ()

    def test_excludes_already_annotated_flag_one(self) -> None:
        """Resultados com critical_failure_flag=1 já revisados são excluídos."""
        uc, writer, _store = _make_uc()
        r = _make_result(final_score=0.1, critical_failure_flag=1)
        writer.append(r)  # type: ignore[arg-type]
        queue = uc.get_review_queue(run_id=_RUN_ID)
        assert queue == ()

    def test_includes_low_final_score(self) -> None:
        """Resultado com final_score abaixo do threshold entra na fila."""
        uc, writer, _store = _make_uc()
        r = _make_result(final_score=0.3, rubric_biomed_score=0.9)
        writer.append(r)  # type: ignore[arg-type]
        queue = uc.get_review_queue(run_id=_RUN_ID)
        assert len(queue) == 1

    def test_includes_low_rubric_score(self) -> None:
        """Resultado com rubric_biomed_score abaixo do threshold entra na fila."""
        uc, writer, _store = _make_uc()
        r = _make_result(final_score=0.9, rubric_biomed_score=0.2)
        writer.append(r)  # type: ignore[arg-type]
        queue = uc.get_review_queue(run_id=_RUN_ID)
        assert len(queue) == 1

    def test_excludes_above_thresholds(self) -> None:
        """Resultado acima de ambos os thresholds NÃO entra na fila."""
        uc, writer, _store = _make_uc()
        r = _make_result(final_score=0.9, rubric_biomed_score=0.9)
        writer.append(r)  # type: ignore[arg-type]
        queue = uc.get_review_queue(run_id=_RUN_ID)
        assert queue == ()

    def test_sorted_by_final_score_asc(self) -> None:
        """Fila ordenada por final_score ASC (piores primeiro)."""
        uc, writer, _store = _make_uc()
        for i, score in enumerate([0.5, 0.2, 0.4], start=1):
            r = _make_result(
                question_id=f"q0{i}", final_score=score, rubric_biomed_score=0.1
            )
            writer.append(r)  # type: ignore[arg-type]
        queue = uc.get_review_queue(run_id=_RUN_ID)
        scores = [r.final_score.value for r in queue]
        assert scores == sorted(scores), f"Queue not sorted ASC: {scores}"

    def test_max_to_review_respected(self) -> None:
        """max_to_review limita o tamanho da fila."""
        uc, writer, _store = _make_uc(max_to_review=2)
        for i in range(5):
            r = _make_result(
                question_id=f"q{i:02d}", final_score=0.1 * i, rubric_biomed_score=0.1
            )
            writer.append(r)  # type: ignore[arg-type]
        queue = uc.get_review_queue(run_id=_RUN_ID)
        assert len(queue) <= 2

    def test_nan_final_score_sorted_first(self) -> None:
        """Resultado com final_score=NaN aparece antes dos valores finitos."""
        uc, writer, _store = _make_uc()
        # NaN result — enters via rubric_biomed_score below threshold
        r_nan = _make_result(
            question_id="q_nan", final_score=_NAN, rubric_biomed_score=0.1
        )
        r_low = _make_result(
            question_id="q_low", final_score=0.3, rubric_biomed_score=0.9
        )
        writer.append(r_nan)  # type: ignore[arg-type]
        writer.append(r_low)  # type: ignore[arg-type]
        queue = uc.get_review_queue(run_id=_RUN_ID)
        assert len(queue) == 2
        # NaN vai primeiro (pior / mais incerto)
        assert math.isnan(queue[0].final_score.value)

    def test_empty_store_returns_empty_queue(self) -> None:
        """Store vazio → fila vazia."""
        uc, _, _ = _make_uc()
        assert uc.get_review_queue(run_id=_RUN_ID) == ()

    def test_mixed_annotated_and_pending(self) -> None:
        """Apenas resultados sem anotação entram na fila."""
        uc, writer, _store = _make_uc()
        r_annotated = _make_result(
            question_id="q_done", final_score=0.1, critical_failure_flag=0
        )
        r_pending = _make_result(
            question_id="q_pend", final_score=0.1, critical_failure_flag=None
        )
        writer.append(r_annotated)  # type: ignore[arg-type]
        writer.append(r_pending)  # type: ignore[arg-type]
        queue = uc.get_review_queue(run_id=_RUN_ID)
        assert len(queue) == 1
        assert queue[0].answer.question.question_id == "q_pend"


# ---------------------------------------------------------------------------
# TestAnnotate
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnnotate:
    def test_flag_0_persists(self) -> None:
        """Anotação com flag=0 persiste via update_metrics."""
        uc, writer, store = _make_uc()
        r = _make_result(final_score=0.1)
        writer.append(r)  # type: ignore[arg-type]
        row_id = r.answer.row_id  # type: ignore[union-attr]

        uc.annotate(row_id=row_id, flag=0, note="")

        from fakes.storage import InMemoryResultReader

        reader = InMemoryResultReader(store)
        frame = reader.load(round_id=_ROUND_ID)
        updated = next(r for r in frame.results if r.answer.row_id == row_id)
        assert updated.critical_failure_flag == 0

    def test_flag_1_persists(self) -> None:
        """Anotação com flag=1 e nota persiste via update_metrics."""
        uc, writer, store = _make_uc()
        r = _make_result(final_score=0.1)
        writer.append(r)  # type: ignore[arg-type]
        row_id = r.answer.row_id  # type: ignore[union-attr]

        uc.annotate(row_id=row_id, flag=1, note="Diagnóstico incorreto.")

        from fakes.storage import InMemoryResultReader

        reader = InMemoryResultReader(store)
        frame = reader.load(round_id=_ROUND_ID)
        updated = next(r for r in frame.results if r.answer.row_id == row_id)
        assert updated.critical_failure_flag == 1
        assert updated.critical_failure_note == "Diagnóstico incorreto."

    def test_invalid_flag_raises_score_out_of_range(self) -> None:
        """flag fora de {0, 1} levanta ScoreOutOfRangeError."""
        uc, writer, _store = _make_uc()
        r = _make_result(final_score=0.1)
        writer.append(r)  # type: ignore[arg-type]
        row_id = r.answer.row_id  # type: ignore[union-attr]

        with pytest.raises(ScoreOutOfRangeError):
            uc.annotate(row_id=row_id, flag=2, note="")

    def test_invalid_flag_minus_one_raises(self) -> None:
        """flag negativo levanta ScoreOutOfRangeError."""
        uc, writer, _store = _make_uc()
        r = _make_result(final_score=0.1)
        writer.append(r)  # type: ignore[arg-type]
        row_id = r.answer.row_id  # type: ignore[union-attr]

        with pytest.raises(ScoreOutOfRangeError):
            uc.annotate(row_id=row_id, flag=-1, note="")

    def test_row_not_found_raises_storage_error(self) -> None:
        """row_id inexistente levanta StorageError."""
        uc, _writer, _store = _make_uc()
        phantom_id = make_row_id(question_id="q_phantom")

        with pytest.raises(StorageError, match="not found"):
            uc.annotate(row_id=phantom_id, flag=0, note="")

    def test_calls_with_human_annotation_entity_pattern(self) -> None:
        """annotate usa with_human_annotation — padrão de imutabilidade ADR-010."""
        uc, writer, store = _make_uc()
        r = _make_result(final_score=0.1)
        writer.append(r)  # type: ignore[arg-type]
        row_id = r.answer.row_id  # type: ignore[union-attr]

        # Anotamos flag=1 com nota
        uc.annotate(row_id=row_id, flag=1, note="Nota de diagnóstico")

        # Verifica que o flag e a nota foram persistidos (confirmando ADR-010)
        from fakes.storage import InMemoryResultReader

        reader = InMemoryResultReader(store)
        frame = reader.load(round_id=_ROUND_ID)
        updated = next(r for r in frame.results if r.answer.row_id == row_id)
        assert updated.critical_failure_flag == 1
        assert updated.critical_failure_note == "Nota de diagnóstico"
        assert updated.is_critical_failure()

    def test_empty_note_stored_as_none(self) -> None:
        """Nota vazia é armazenada como None (não como string vazia)."""
        uc, writer, store = _make_uc()
        r = _make_result(final_score=0.1)
        writer.append(r)  # type: ignore[arg-type]
        row_id = r.answer.row_id  # type: ignore[union-attr]

        uc.annotate(row_id=row_id, flag=0, note="")

        from fakes.storage import InMemoryResultReader

        reader = InMemoryResultReader(store)
        frame = reader.load(round_id=_ROUND_ID)
        updated = next(r for r in frame.results if r.answer.row_id == row_id)
        assert updated.critical_failure_note is None


# ---------------------------------------------------------------------------
# TestBatchAnnotateFromCSV
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBatchAnnotateFromCSV:
    def _make_csv(self, rows: list[dict[str, str]]) -> str:
        import csv
        import io

        buf = io.StringIO()
        writer_csv = csv.DictWriter(buf, fieldnames=["row_id", "flag", "note"])
        writer_csv.writeheader()
        writer_csv.writerows(rows)
        return buf.getvalue()

    def test_batch_annotates_multiple_rows(self) -> None:
        """batch_annotate_from_csv anota múltiplas linhas em lote."""
        uc, writer, _store = _make_uc()
        results = [
            _make_result(question_id=f"q{i:02d}", final_score=0.1) for i in range(3)
        ]
        for r in results:
            writer.append(r)  # type: ignore[arg-type]

        csv_rows = [
            {"row_id": r.answer.row_id.value, "flag": "0", "note": ""}  # type: ignore[union-attr]
            for r in results
        ]
        summary = uc.batch_annotate_from_csv(self._make_csv(csv_rows))

        assert summary.n_annotated == 3

    def test_batch_with_flag_1_and_note(self) -> None:
        """batch_annotate_from_csv persiste flag=1 + nota."""
        uc, writer, store = _make_uc()
        r = _make_result(question_id="q01", final_score=0.1)
        writer.append(r)  # type: ignore[arg-type]
        row_id = r.answer.row_id  # type: ignore[union-attr]

        csv_content = self._make_csv(
            [{"row_id": row_id.value, "flag": "1", "note": "Erro detectado"}]
        )
        summary = uc.batch_annotate_from_csv(csv_content)
        assert summary.n_annotated == 1

        from fakes.storage import InMemoryResultReader

        reader = InMemoryResultReader(store)
        frame = reader.load(round_id=_ROUND_ID)
        updated = next(x for x in frame.results if x.answer.row_id == row_id)
        assert updated.critical_failure_flag == 1
        assert updated.critical_failure_note == "Erro detectado"

    def test_invalid_flag_in_csv_counted_as_error(self) -> None:
        """flag inválido no CSV é logado como erro (não aborta o lote)."""
        uc, writer, _store = _make_uc()
        r = _make_result(question_id="q01", final_score=0.1)
        writer.append(r)  # type: ignore[arg-type]
        row_id = r.answer.row_id  # type: ignore[union-attr]

        csv_content = self._make_csv(
            [{"row_id": row_id.value, "flag": "9", "note": ""}]
        )
        summary = uc.batch_annotate_from_csv(csv_content)
        # flag 9 → ScoreOutOfRangeError → contado como erro, não anotado
        assert summary.n_annotated == 0
        assert summary.n_errors == 1

    def test_summary_n_errors_reflects_all_failures(self) -> None:
        """n_errors em AnnotationSummary contabiliza todas as linhas que falharam."""
        uc, writer, _store = _make_uc()
        r = _make_result(question_id="q01", final_score=0.1)
        writer.append(r)  # type: ignore[arg-type]
        row_id = r.answer.row_id  # type: ignore[union-attr]

        # 1 linha válida + 2 linhas com flag inválido
        csv_content = self._make_csv(
            [
                {"row_id": row_id.value, "flag": "0", "note": ""},
                {"row_id": row_id.value, "flag": "7", "note": ""},  # inválido
                {"row_id": "0" * 64, "flag": "0", "note": ""},  # row_id inexistente
            ]
        )
        summary = uc.batch_annotate_from_csv(csv_content)
        assert summary.n_annotated == 1
        assert summary.n_errors == 2

    def test_missing_columns_raises_storage_error(self) -> None:
        """CSV sem coluna row_id ou flag levanta StorageError na abertura."""
        uc, _, _ = _make_uc()
        bad_csv = "row_id\n" + "abc123\n"  # sem coluna flag
        with pytest.raises(StorageError, match="row_id, flag"):
            uc.batch_annotate_from_csv(bad_csv)

    def test_empty_csv_returns_zero_annotated(self) -> None:
        """CSV com header mas sem linhas retorna n_annotated=0."""
        uc, _, _ = _make_uc()
        csv_content = self._make_csv([])
        summary = uc.batch_annotate_from_csv(csv_content)
        assert summary.n_annotated == 0
