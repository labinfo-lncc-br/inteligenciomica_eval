from __future__ import annotations

import json
from pathlib import Path

from factories.factories import (
    make_evaluation_result,
    make_generated_answer,
    make_row_id,
)
from fakes.storage import InMemoryResultStore, InMemoryResultWriter

from inteligenciomica_eval.application.use_cases.ingest_annotation import (
    IngestAnnotationInput,
    IngestAnnotationOutput,
    IngestHumanAnnotationUseCase,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_writer(
    *, round_id: str = "round_1", run_id: str = "run-001"
) -> tuple[InMemoryResultWriter, InMemoryResultStore]:
    store = InMemoryResultStore()
    writer = InMemoryResultWriter(store, round_id=round_id, run_id=run_id)
    return writer, store


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records),
        encoding="utf-8",
    )


def _make_record(row_id: str, flag: object, note: str = "") -> dict[str, object]:
    return {
        "row_id": row_id,
        "question_id": "q01",
        "question": "Q?",
        "generated_answer": "A.",
        "ground_truth": "GT.",
        "final_score": 0.5,
        "rubric_biomed_score": 0.6,
        "rubric_feedback": "",
        "critical_failure_flag": flag,
        "critical_failure_note": note,
    }


# ---------------------------------------------------------------------------
# a) Ingestão normal: 3 linhas com flag 0/1 → n_ingested=3
# ---------------------------------------------------------------------------


def test_normal_ingest_three_rows(tmp_path: Path) -> None:
    writer, _ = _make_writer()
    row_ids = [make_row_id(question_id=f"q0{i}") for i in range(1, 4)]
    for rid in row_ids:
        writer.append(make_evaluation_result(answer=make_generated_answer(row_id=rid)))

    records = [
        _make_record(row_ids[0].value, 0),
        _make_record(row_ids[1].value, 1, note="Erro grave"),
        _make_record(row_ids[2].value, 0),
    ]
    jsonl = tmp_path / "annotations.jsonl"
    _write_jsonl(jsonl, records)

    uc = IngestHumanAnnotationUseCase(writer=writer)
    out = uc.execute(IngestAnnotationInput(annotations_path=jsonl, run_id="run-001"))

    assert out == IngestAnnotationOutput(
        n_ingested=3, n_skipped=0, n_invalid=0, n_missing_row_id=0
    )


# ---------------------------------------------------------------------------
# b) Flag inválido (2): n_invalid=1, não aborta, demais ingeridas
# ---------------------------------------------------------------------------


def test_invalid_flag_does_not_abort(tmp_path: Path) -> None:
    writer, _ = _make_writer()
    row_id_ok = make_row_id(question_id="q01")
    row_id_ok2 = make_row_id(question_id="q02")
    writer.append(
        make_evaluation_result(answer=make_generated_answer(row_id=row_id_ok))
    )
    writer.append(
        make_evaluation_result(answer=make_generated_answer(row_id=row_id_ok2))
    )

    records = [
        _make_record(row_id_ok.value, 0),
        _make_record(row_id_ok.value, 2),  # flag inválido
        _make_record(row_id_ok2.value, 1),
    ]
    jsonl = tmp_path / "ann.jsonl"
    _write_jsonl(jsonl, records)

    uc = IngestHumanAnnotationUseCase(writer=writer)
    out = uc.execute(IngestAnnotationInput(annotations_path=jsonl, run_id="run-001"))

    assert out.n_invalid == 1
    assert out.n_ingested == 2
    assert out.n_skipped == 0
    assert out.n_missing_row_id == 0


# ---------------------------------------------------------------------------
# c) flag=null: linha pulada silenciosamente, não conta em inválido
# ---------------------------------------------------------------------------


def test_null_flag_skipped_silently(tmp_path: Path) -> None:
    writer, _ = _make_writer()
    row_id = make_row_id(question_id="q01")
    writer.append(make_evaluation_result(answer=make_generated_answer(row_id=row_id)))

    records = [_make_record(row_id.value, None)]
    jsonl = tmp_path / "ann.jsonl"
    _write_jsonl(jsonl, records)

    uc = IngestHumanAnnotationUseCase(writer=writer)
    out = uc.execute(IngestAnnotationInput(annotations_path=jsonl, run_id="run-001"))

    assert out == IngestAnnotationOutput(
        n_ingested=0, n_skipped=0, n_invalid=0, n_missing_row_id=0
    )


# ---------------------------------------------------------------------------
# d) force=False, linha já anotada: n_skipped=1
# ---------------------------------------------------------------------------


def test_idempotency_force_false_skips(tmp_path: Path) -> None:
    writer, _ = _make_writer()
    row_id = make_row_id(question_id="q01")
    writer.append(make_evaluation_result(answer=make_generated_answer(row_id=row_id)))
    # Pre-annotate
    writer.update_annotation(row_id, critical_failure_flag=0)

    records = [_make_record(row_id.value, 1, note="Reedit")]
    jsonl = tmp_path / "ann.jsonl"
    _write_jsonl(jsonl, records)

    uc = IngestHumanAnnotationUseCase(writer=writer)
    out = uc.execute(
        IngestAnnotationInput(annotations_path=jsonl, run_id="run-001", force=False)
    )

    assert out == IngestAnnotationOutput(
        n_ingested=0, n_skipped=1, n_invalid=0, n_missing_row_id=0
    )
    # Flag deve permanecer 0 (não sobrescrito)
    assert writer.current_annotation_flag(row_id) == 0


# ---------------------------------------------------------------------------
# e) force=True, linha já anotada: n_ingested=1 (sobrescreve)
# ---------------------------------------------------------------------------


def test_idempotency_force_true_overwrites(tmp_path: Path) -> None:
    writer, _ = _make_writer()
    row_id = make_row_id(question_id="q01")
    writer.append(make_evaluation_result(answer=make_generated_answer(row_id=row_id)))
    writer.update_annotation(row_id, critical_failure_flag=0)

    records = [_make_record(row_id.value, 1, note="Correção")]
    jsonl = tmp_path / "ann.jsonl"
    _write_jsonl(jsonl, records)

    uc = IngestHumanAnnotationUseCase(writer=writer)
    out = uc.execute(
        IngestAnnotationInput(annotations_path=jsonl, run_id="run-001", force=True)
    )

    assert out == IngestAnnotationOutput(
        n_ingested=1, n_skipped=0, n_invalid=0, n_missing_row_id=0
    )
    assert writer.current_annotation_flag(row_id) == 1


# ---------------------------------------------------------------------------
# f) row_id inexistente: n_missing_row_id=1, sem exceção
# ---------------------------------------------------------------------------


def test_missing_row_id_does_not_raise(tmp_path: Path) -> None:
    writer, _ = _make_writer()
    fake_row_id = make_row_id(question_id="q99")  # não appendado

    records = [_make_record(fake_row_id.value, 1)]
    jsonl = tmp_path / "ann.jsonl"
    _write_jsonl(jsonl, records)

    uc = IngestHumanAnnotationUseCase(writer=writer)
    out = uc.execute(IngestAnnotationInput(annotations_path=jsonl, run_id="run-001"))

    assert out == IngestAnnotationOutput(
        n_ingested=0, n_skipped=0, n_invalid=0, n_missing_row_id=1
    )


# ---------------------------------------------------------------------------
# Extra: boolean flag (true/false em JSON) é tratado como inválido
# ---------------------------------------------------------------------------


def test_boolean_flag_treated_as_invalid(tmp_path: Path) -> None:
    """JSON boolean true/false não são aceitos como 0/1 inteiros (tipo errado)."""
    writer, _ = _make_writer()
    row_id = make_row_id(question_id="q01")
    writer.append(make_evaluation_result(answer=make_generated_answer(row_id=row_id)))

    # json.dumps converte True → true
    record = _make_record(row_id.value, None)
    record["critical_failure_flag"] = True  # bool Python → true JSON
    jsonl = tmp_path / "ann.jsonl"
    _write_jsonl(jsonl, [record])

    uc = IngestHumanAnnotationUseCase(writer=writer)
    out = uc.execute(IngestAnnotationInput(annotations_path=jsonl, run_id="run-001"))

    assert out.n_invalid == 1
    assert out.n_ingested == 0


# ---------------------------------------------------------------------------
# Extra: linha JSON malformada conta como inválida
# ---------------------------------------------------------------------------


def test_malformed_json_line_counted_as_invalid(tmp_path: Path) -> None:
    jsonl = tmp_path / "ann.jsonl"
    jsonl.write_text("{invalid json}\n", encoding="utf-8")

    writer, _ = _make_writer()
    uc = IngestHumanAnnotationUseCase(writer=writer)
    out = uc.execute(IngestAnnotationInput(annotations_path=jsonl, run_id="run-001"))

    assert out.n_invalid == 1
