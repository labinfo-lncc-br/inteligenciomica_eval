from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from inteligenciomica_eval.domain.ports import ResultReaderPort, ResultWriterPort

if TYPE_CHECKING:
    from inteligenciomica_eval.application.statistical_analysis import (
        StatisticalAnalysisUseCase,
    )
    from inteligenciomica_eval.domain.ports import ReportPort
    from inteligenciomica_eval.visualization.matplotlib_adapter import (
        MatplotlibVisualizationAdapter,
    )


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


def build_analysis_from_config(config_path: Path) -> StatisticalAnalysisUseCase:
    """Build a StatisticalAnalysisUseCase from a round config (TAREFA-408).

    Loads round config to derive ``round_id`` and ``data_dir``, then wires
    :class:`ParquetStorage`, the three stats adapters and returns a ready-to-use
    :class:`StatisticalAnalysisUseCase`.

    Args:
        config_path: path to the round config YAML file.

    Returns:
        :class:`~inteligenciomica_eval.application.statistical_analysis.StatisticalAnalysisUseCase`
        wired with real adapters.
    """
    from inteligenciomica_eval.application.statistical_analysis import (
        StatisticalAnalysisUseCase,
    )
    from inteligenciomica_eval.infrastructure.adapters.stats_adapters import (
        FriedmanNemenyiAdapter,
        MixedLinearModelAdapter,
        WilcoxonAdapter,
    )
    from inteligenciomica_eval.infrastructure.config.schema import load_round_config
    from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
        ParquetStorage,
    )

    cfg = load_round_config(config_path)
    data_dir = config_path.parent / "data"
    reader = ParquetStorage(base_dir=data_dir, round_id=cfg.round_id)

    return StatisticalAnalysisUseCase(
        reader=reader,
        wilcoxon_adapter=WilcoxonAdapter(),
        friedman_adapter=FriedmanNemenyiAdapter(),
        mlm_adapter=MixedLinearModelAdapter(),
        data_dir=data_dir,
    )


def build_visualization_adapter(config_path: Path) -> MatplotlibVisualizationAdapter:
    """Build a MatplotlibVisualizationAdapter (TAREFA-408).

    Args:
        config_path: path to the round config YAML (reserved for future wiring).

    Returns:
        :class:`~inteligenciomica_eval.visualization.matplotlib_adapter.MatplotlibVisualizationAdapter`
        with default configuration.
    """
    from inteligenciomica_eval.infrastructure.config.adapter_configs import (
        VisualizationAdapterConfig,
    )
    from inteligenciomica_eval.visualization.matplotlib_adapter import (
        MatplotlibVisualizationAdapter,
    )

    return MatplotlibVisualizationAdapter(config=VisualizationAdapterConfig())


def build_report_adapter(config_path: Path) -> ReportPort:
    """Build an HTMLReportAdapter as a ReportPort (TAREFA-408).

    Returns the adapter typed as :class:`~inteligenciomica_eval.domain.ports.ReportPort`
    so that callers (e.g. ``cli.py``) do not need to import the concrete adapter
    class from ``infrastructure/adapters/``, respecting the architectural constraint
    that the CLI must not import adapters directly.

    Args:
        config_path: path to the round config YAML (reserved for future wiring).

    Returns:
        :class:`~inteligenciomica_eval.domain.ports.ReportPort` backed by
        :class:`~inteligenciomica_eval.infrastructure.adapters.html_report.HTMLReportAdapter`.
    """
    from inteligenciomica_eval.infrastructure.adapters.html_report import (
        HTMLReportAdapter,
    )

    return HTMLReportAdapter()
