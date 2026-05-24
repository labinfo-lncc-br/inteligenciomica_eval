from __future__ import annotations

import pathlib

import pytest

from inteligenciomica_eval.domain.errors import StorageError
from inteligenciomica_eval.infrastructure.adapters.qdrant_retriever import (
    GoldChunkReaderAdapter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FIXTURES_DIR = pathlib.Path(__file__).parents[3] / "fixtures"


@pytest.fixture()
def gold_file() -> pathlib.Path:
    return _FIXTURES_DIR / "gold_chunks.jsonl"


@pytest.fixture()
def reader(gold_file: pathlib.Path) -> GoldChunkReaderAdapter:
    return GoldChunkReaderAdapter(gold_file=gold_file)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_gold_for_returns_correct_ids_q01(reader: GoldChunkReaderAdapter) -> None:
    result = reader.gold_for("q01")
    assert result == ["chunk_abc", "chunk_def", "chunk_ghi"]


@pytest.mark.unit
def test_gold_for_returns_correct_ids_q02(reader: GoldChunkReaderAdapter) -> None:
    result = reader.gold_for("q02")
    assert result == ["chunk_xyz"]


@pytest.mark.unit
def test_gold_for_returns_new_list_each_call(reader: GoldChunkReaderAdapter) -> None:
    """Mutations to the returned list must not affect subsequent calls."""
    first = reader.gold_for("q01")
    first.append("MUTATED")
    second = reader.gold_for("q01")
    assert "MUTATED" not in second


@pytest.mark.unit
def test_gold_for_lazy_loading_is_idempotent(reader: GoldChunkReaderAdapter) -> None:
    r1 = reader.gold_for("q01")
    r2 = reader.gold_for("q01")
    assert r1 == r2


# ---------------------------------------------------------------------------
# GoldChunkReaderPort structural conformance
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_adapter_satisfies_gold_chunk_reader_port(
    reader: GoldChunkReaderAdapter,
) -> None:
    from inteligenciomica_eval.domain.ports import GoldChunkReaderPort

    assert isinstance(reader, GoldChunkReaderPort)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_gold_for_raises_storage_error_for_unknown_question_id(
    reader: GoldChunkReaderAdapter,
) -> None:
    with pytest.raises(StorageError, match="q99"):
        reader.gold_for("q99")


@pytest.mark.unit
def test_gold_for_raises_storage_error_when_file_absent(tmp_path: pathlib.Path) -> None:
    missing = tmp_path / "nonexistent.jsonl"
    adapter = GoldChunkReaderAdapter(gold_file=missing)
    with pytest.raises(StorageError, match="not found"):
        adapter.gold_for("q01")


@pytest.mark.unit
def test_gold_for_raises_storage_error_on_malformed_jsonl(
    tmp_path: pathlib.Path,
) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{bad json\n", encoding="utf-8")
    adapter = GoldChunkReaderAdapter(gold_file=bad)
    with pytest.raises(StorageError, match="Invalid JSONL"):
        adapter.gold_for("q01")


@pytest.mark.unit
def test_gold_for_raises_storage_error_on_missing_key(
    tmp_path: pathlib.Path,
) -> None:
    bad = tmp_path / "nokey.jsonl"
    bad.write_text(
        '{"question_id": "q01"}\n', encoding="utf-8"
    )  # missing gold_chunk_ids
    adapter = GoldChunkReaderAdapter(gold_file=bad)
    with pytest.raises(StorageError, match="Invalid JSONL"):
        adapter.gold_for("q01")
