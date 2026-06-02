from __future__ import annotations

from pathlib import Path

from inteligenciomica_eval.domain.ports import ResultReaderPort, ResultWriterPort


def build_annotation_reader(config_path: Path) -> ResultReaderPort:
    """Build a ResultReaderPort for annotation export workflows (TAREFA-401, ADR-010).

    Loads the round config at *config_path* to derive the ``round_id``, then
    returns a :class:`ParquetStorage` reader rooted at
    ``config_path.parent / "data"`` — the conventional round-data directory.

    Args:
        config_path: path to the round config YAML file.

    Returns:
        :class:`ResultReaderPort` backed by :class:`ParquetStorage`.
    """
    from inteligenciomica_eval.infrastructure.config.schema import load_round_config
    from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
        ParquetStorage,
    )

    cfg = load_round_config(config_path)
    data_dir = config_path.parent / "data"
    return ParquetStorage(base_dir=data_dir, round_id=cfg.round_id)


def build_annotation_writer(config_path: Path, *, run_id: str = "") -> ResultWriterPort:
    """Build a ResultWriterPort for annotation ingest workflows (TAREFA-402, ADR-010).

    Loads the round config at *config_path* to derive the ``round_id``, then
    returns a :class:`ParquetStorage` writer rooted at
    ``config_path.parent / "data"`` — the conventional round-data directory.

    Args:
        config_path: path to the round config YAML file.
        run_id: optional run identifier propagated to the storage provenance.

    Returns:
        :class:`ResultWriterPort` backed by :class:`ParquetStorage`.
    """
    from inteligenciomica_eval.infrastructure.config.schema import load_round_config
    from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
        ParquetStorage,
    )

    cfg = load_round_config(config_path)
    data_dir = config_path.parent / "data"
    return ParquetStorage(base_dir=data_dir, run_id=run_id, round_id=cfg.round_id)
