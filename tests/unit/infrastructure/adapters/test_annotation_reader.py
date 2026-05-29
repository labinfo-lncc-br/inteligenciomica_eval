"""Testes unitários do AnnotationReaderAdapter (TAREFA-020).

Estratégia (Nota M1 item 7): lê o JSONL de fixture em ``tests/fixtures/annotations.jsonl``;
casos de erro (malformado, flag inválida, row_id inválido) escrevem arquivos temporários
via ``tmp_path``. Sem I/O de rede, sem container.
"""

from __future__ import annotations

import inspect
import pathlib

import pytest
import structlog

from inteligenciomica_eval.domain.errors import StorageError
from inteligenciomica_eval.domain.ports import AnnotationReaderPort, CriticalAnnotation
from inteligenciomica_eval.domain.value_objects import RowId
from inteligenciomica_eval.infrastructure.adapters.annotation_reader import (
    AnnotationReaderAdapter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIXTURES_DIR = pathlib.Path(__file__).parents[3] / "fixtures"
_VALID_HEX = "1da62a9e0159ecdddd6fc7538fc2130e613a2796a295388bdff60cda8be438f3"


@pytest.fixture
def annotation_file() -> pathlib.Path:
    return _FIXTURES_DIR / "annotations.jsonl"


@pytest.fixture
def reader(annotation_file: pathlib.Path) -> AnnotationReaderAdapter:
    return AnnotationReaderAdapter(annotation_file)


def _write(path: pathlib.Path, *lines: str) -> pathlib.Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_port(self, reader: AnnotationReaderAdapter) -> None:
        assert isinstance(reader, AnnotationReaderPort)


# ---------------------------------------------------------------------------
# read() — happy path
# ---------------------------------------------------------------------------


class TestRead:
    def test_returns_annotations_for_run(self, reader: AnnotationReaderAdapter) -> None:
        annotations = reader.read("round_1")
        assert len(annotations) == 2
        assert all(isinstance(a, CriticalAnnotation) for a in annotations)
        flags = {a.flag for a in annotations}
        assert flags == {0, 1}

    def test_row_id_converted_to_domain_type(
        self, reader: AnnotationReaderAdapter
    ) -> None:
        annotations = reader.read("round_1")
        row_ids = [a.row_id for a in annotations]
        assert all(isinstance(rid, RowId) for rid in row_ids)
        assert _VALID_HEX in {rid.value for rid in row_ids}

    def test_optional_note_may_be_none(self, reader: AnnotationReaderAdapter) -> None:
        notes = [a.note for a in reader.read("round_1")]
        assert None in notes
        assert any(n is not None for n in notes)

    def test_second_run(self, reader: AnnotationReaderAdapter) -> None:
        annotations = reader.read("round_2")
        assert len(annotations) == 1
        assert annotations[0].flag == 1

    def test_unknown_run_returns_empty_list(
        self, reader: AnnotationReaderAdapter
    ) -> None:
        result = reader.read("nonexistent_run")
        assert result == []
        assert result is not None

    def test_read_returns_fresh_copy(self, reader: AnnotationReaderAdapter) -> None:
        first = reader.read("round_1")
        first.clear()
        assert len(reader.read("round_1")) == 2  # estado interno intacto


# ---------------------------------------------------------------------------
# Arquivo ausente — Camada 3 desabilitada
# ---------------------------------------------------------------------------


class TestMissingFile:
    def test_missing_file_reads_empty_without_error(
        self, tmp_path: pathlib.Path
    ) -> None:
        missing = tmp_path / "does_not_exist.jsonl"
        with structlog.testing.capture_logs() as logs:
            adapter = AnnotationReaderAdapter(missing)
        assert adapter.read("any_run") == []
        events = [e["event"] for e in logs]
        assert any("not found" in e for e in events)


# ---------------------------------------------------------------------------
# Arquivo malformado / inválido — StorageError NA CONSTRUÇÃO
# ---------------------------------------------------------------------------


class TestMalformed:
    def test_invalid_json_raises_on_construction(self, tmp_path: pathlib.Path) -> None:
        path = _write(tmp_path / "bad.jsonl", "{not valid json")
        with pytest.raises(StorageError):
            AnnotationReaderAdapter(path)

    def test_missing_required_field_raises(self, tmp_path: pathlib.Path) -> None:
        # falta "row_id"
        path = _write(tmp_path / "missing.jsonl", '{"run_id": "r1", "flag": 0}')
        with pytest.raises(StorageError):
            AnnotationReaderAdapter(path)

    def test_flag_out_of_domain_raises_on_construction(
        self, tmp_path: pathlib.Path
    ) -> None:
        path = _write(
            tmp_path / "flag.jsonl",
            f'{{"run_id": "r1", "row_id": "{_VALID_HEX}", "flag": 2}}',
        )
        with pytest.raises(StorageError):
            AnnotationReaderAdapter(path)

    def test_invalid_row_id_raises_on_construction(
        self, tmp_path: pathlib.Path
    ) -> None:
        path = _write(
            tmp_path / "rowid.jsonl",
            '{"run_id": "r1", "row_id": "not-a-sha256", "flag": 1}',
        )
        with pytest.raises(StorageError):
            AnnotationReaderAdapter(path)

    def test_blank_lines_are_skipped(self, tmp_path: pathlib.Path) -> None:
        path = tmp_path / "blanks.jsonl"
        path.write_text(
            f'\n{{"run_id": "r1", "row_id": "{_VALID_HEX}", "flag": 1}}\n\n',
            encoding="utf-8",
        )
        adapter = AnnotationReaderAdapter(path)
        assert len(adapter.read("r1")) == 1


# ---------------------------------------------------------------------------
# reload()
# ---------------------------------------------------------------------------


class TestReload:
    def test_reload_returns_total_count(self, reader: AnnotationReaderAdapter) -> None:
        assert reader.reload() == 3  # 2 (round_1) + 1 (round_2)

    def test_reload_switches_file(
        self, reader: AnnotationReaderAdapter, tmp_path: pathlib.Path
    ) -> None:
        smaller = _write(
            tmp_path / "small.jsonl",
            f'{{"run_id": "rX", "row_id": "{_VALID_HEX}", "flag": 0}}',
        )
        total = reader.reload(smaller)
        assert total == 1
        assert reader.read("rX")[0].flag == 0
        assert reader.read("round_1") == []  # arquivo antigo não está mais carregado

    def test_reload_picks_up_new_annotations(self, tmp_path: pathlib.Path) -> None:
        path = _write(
            tmp_path / "growing.jsonl",
            f'{{"run_id": "r1", "row_id": "{_VALID_HEX}", "flag": 1}}',
        )
        adapter = AnnotationReaderAdapter(path)
        assert adapter.reload() == 1
        _write(
            path,
            f'{{"run_id": "r1", "row_id": "{_VALID_HEX}", "flag": 1}}',
            f'{{"run_id": "r2", "row_id": "{_VALID_HEX}", "flag": 0}}',
        )
        assert adapter.reload() == 2


# ---------------------------------------------------------------------------
# Sincronicidade
# ---------------------------------------------------------------------------


class TestSynchronous:
    def test_read_is_not_async(self) -> None:
        assert not inspect.iscoroutinefunction(AnnotationReaderAdapter.read)

    def test_reload_is_not_async(self) -> None:
        assert not inspect.iscoroutinefunction(AnnotationReaderAdapter.reload)
