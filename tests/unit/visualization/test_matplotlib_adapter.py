"""Testes unitários do MatplotlibVisualizationAdapter (TAREFA-407)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from factories.factories import (
    make_config_aggregate,
    make_evaluation_result,
    make_generated_answer,
)

from inteligenciomica_eval.domain.errors import ConfigValidationError
from inteligenciomica_eval.domain.ports import ResultFrame
from inteligenciomica_eval.infrastructure.config.adapter_configs import (
    VisualizationAdapterConfig,
)
from inteligenciomica_eval.visualization.matplotlib_adapter import (
    MatplotlibVisualizationAdapter,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def adapter() -> MatplotlibVisualizationAdapter:
    return MatplotlibVisualizationAdapter()


@pytest.fixture()
def two_aggregates() -> list:
    """Dois ConfigAggregate com bases e LLMs distintos."""
    return [
        make_config_aggregate(base="IDx_400k", llm="llama3-8b", rank_score=0.80),
        make_config_aggregate(base="ID_230K", llm="llama3-8b", rank_score=0.70),
    ]


@pytest.fixture()
def multi_aggregates() -> list:
    """4 ConfigAggregate cobrindo 2 bases x 2 LLMs."""
    return [
        make_config_aggregate(
            base="IDx_400k", llm="llama3-8b", rank_score=0.80, failure_rate=0.30
        ),
        make_config_aggregate(
            base="IDx_400k", llm="llama3-70b", rank_score=0.75, failure_rate=0.10
        ),
        make_config_aggregate(
            base="ID_230K", llm="llama3-8b", rank_score=0.70, failure_rate=0.25
        ),
        make_config_aggregate(
            base="ID_230K", llm="llama3-70b", rank_score=0.65, failure_rate=0.05
        ),
    ]


@pytest.fixture()
def small_result_frame() -> ResultFrame:
    """ResultFrame com 2 EvaluationResult para testes de boxplot e per-question."""
    r1 = make_evaluation_result(
        answer=make_generated_answer(
            base="IDx_400k", llm="llama3-8b", question_id="q01"
        ),
        final_score=0.80,
    )
    r2 = make_evaluation_result(
        answer=make_generated_answer(
            base="ID_230K", llm="llama3-8b", question_id="q02"
        ),
        final_score=0.70,
    )
    return ResultFrame(results=(r1, r2))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_svg_created(path: Path) -> None:
    assert path.exists(), f"SVG não encontrado: {path}"
    assert path.stat().st_size > 0, f"SVG vazio: {path}"


# ---------------------------------------------------------------------------
# (1) plot_rankscore_heatmap
# ---------------------------------------------------------------------------


class TestPlotRankscoreHeatmap:
    def test_svg_criado(
        self,
        adapter: MatplotlibVisualizationAdapter,
        multi_aggregates: list,
        tmp_path: Path,
    ) -> None:
        with patch("matplotlib.pyplot.close") as mock_close:
            fp = adapter.plot_rankscore_heatmap(multi_aggregates, output_dir=tmp_path)
        _assert_svg_created(fp.path)
        assert fp.format == "svg"
        assert fp.plot_type == "rankscore_heatmap"
        assert mock_close.call_count >= 1

    def test_metric_name_invalido(
        self,
        adapter: MatplotlibVisualizationAdapter,
        multi_aggregates: list,
        tmp_path: Path,
    ) -> None:
        with pytest.raises(ConfigValidationError):
            adapter.plot_rankscore_heatmap(
                multi_aggregates, output_dir=tmp_path, metric_name="invalid_metric"
            )

    def test_metricas_validas(
        self,
        adapter: MatplotlibVisualizationAdapter,
        multi_aggregates: list,
        tmp_path: Path,
    ) -> None:
        for metric in [
            "median_score",
            "failure_rate",
            "win_rate",
            "critical_failure_rate",
        ]:
            with patch("matplotlib.pyplot.close"):
                fp = adapter.plot_rankscore_heatmap(
                    multi_aggregates, output_dir=tmp_path, metric_name=metric
                )
            _assert_svg_created(fp.path)

    def test_plt_close_chamado(
        self,
        adapter: MatplotlibVisualizationAdapter,
        multi_aggregates: list,
        tmp_path: Path,
    ) -> None:
        with patch("matplotlib.pyplot.close") as mock_close:
            adapter.plot_rankscore_heatmap(multi_aggregates, output_dir=tmp_path)
        assert mock_close.call_count >= 1


# ---------------------------------------------------------------------------
# (2) plot_finalscore_boxplots
# ---------------------------------------------------------------------------


class TestPlotFinalscoreBoxplots:
    def test_svg_criado_sem_results(
        self,
        adapter: MatplotlibVisualizationAdapter,
        multi_aggregates: list,
        tmp_path: Path,
    ) -> None:
        with patch("matplotlib.pyplot.close") as mock_close:
            fp = adapter.plot_finalscore_boxplots(multi_aggregates, output_dir=tmp_path)
        _assert_svg_created(fp.path)
        assert fp.format == "svg"
        assert fp.plot_type == "finalscore_boxplot"
        assert mock_close.call_count >= 1

    def test_svg_criado_com_results(
        self,
        adapter: MatplotlibVisualizationAdapter,
        multi_aggregates: list,
        small_result_frame: ResultFrame,
        tmp_path: Path,
    ) -> None:
        with patch("matplotlib.pyplot.close") as mock_close:
            fp = adapter.plot_finalscore_boxplots(
                multi_aggregates, output_dir=tmp_path, results=small_result_frame
            )
        _assert_svg_created(fp.path)
        assert mock_close.call_count >= 1

    def test_plt_close_chamado(
        self,
        adapter: MatplotlibVisualizationAdapter,
        multi_aggregates: list,
        tmp_path: Path,
    ) -> None:
        with patch("matplotlib.pyplot.close") as mock_close:
            adapter.plot_finalscore_boxplots(multi_aggregates, output_dir=tmp_path)
        assert mock_close.call_count >= 1


# ---------------------------------------------------------------------------
# (3) plot_interaction
# ---------------------------------------------------------------------------


class TestPlotInteraction:
    def test_svg_criado(
        self,
        adapter: MatplotlibVisualizationAdapter,
        multi_aggregates: list,
        tmp_path: Path,
    ) -> None:
        with patch("matplotlib.pyplot.close") as mock_close:
            fp = adapter.plot_interaction(multi_aggregates, output_dir=tmp_path)
        _assert_svg_created(fp.path)
        assert fp.format == "svg"
        assert fp.plot_type == "interaction"
        assert mock_close.call_count >= 1

    def test_plt_close_chamado(
        self,
        adapter: MatplotlibVisualizationAdapter,
        multi_aggregates: list,
        tmp_path: Path,
    ) -> None:
        with patch("matplotlib.pyplot.close") as mock_close:
            adapter.plot_interaction(multi_aggregates, output_dir=tmp_path)
        assert mock_close.call_count >= 1


# ---------------------------------------------------------------------------
# (4) plot_radar
# ---------------------------------------------------------------------------


class TestPlotRadar:
    def test_svg_criado(
        self,
        adapter: MatplotlibVisualizationAdapter,
        multi_aggregates: list,
        tmp_path: Path,
    ) -> None:
        with patch("matplotlib.pyplot.close") as mock_close:
            fp = adapter.plot_radar(multi_aggregates, output_dir=tmp_path, top_n=2)
        _assert_svg_created(fp.path)
        assert fp.format == "svg"
        assert fp.plot_type == "radar"
        assert mock_close.call_count >= 1

    def test_nome_arquivo_top_n(
        self,
        adapter: MatplotlibVisualizationAdapter,
        multi_aggregates: list,
        tmp_path: Path,
    ) -> None:
        with patch("matplotlib.pyplot.close"):
            fp = adapter.plot_radar(multi_aggregates, output_dir=tmp_path, top_n=3)
        assert "radar_top3" in fp.path.name

    def test_plt_close_chamado(
        self,
        adapter: MatplotlibVisualizationAdapter,
        multi_aggregates: list,
        tmp_path: Path,
    ) -> None:
        with patch("matplotlib.pyplot.close") as mock_close:
            adapter.plot_radar(multi_aggregates, output_dir=tmp_path)
        assert mock_close.call_count >= 1


# ---------------------------------------------------------------------------
# (5) plot_per_question_ranking
# ---------------------------------------------------------------------------


class TestPlotPerQuestionRanking:
    def test_svg_criado(
        self,
        adapter: MatplotlibVisualizationAdapter,
        small_result_frame: ResultFrame,
        tmp_path: Path,
    ) -> None:
        with patch("matplotlib.pyplot.close") as mock_close:
            fp = adapter.plot_per_question_ranking(
                small_result_frame, output_dir=tmp_path
            )
        _assert_svg_created(fp.path)
        assert fp.format == "svg"
        assert fp.plot_type == "per_question_ranking"
        assert mock_close.call_count >= 1

    def test_resultado_vazio(
        self, adapter: MatplotlibVisualizationAdapter, tmp_path: Path
    ) -> None:
        empty = ResultFrame(results=())
        with patch("matplotlib.pyplot.close") as mock_close:
            fp = adapter.plot_per_question_ranking(empty, output_dir=tmp_path)
        _assert_svg_created(fp.path)
        assert mock_close.call_count >= 1

    def test_plt_close_chamado(
        self,
        adapter: MatplotlibVisualizationAdapter,
        small_result_frame: ResultFrame,
        tmp_path: Path,
    ) -> None:
        with patch("matplotlib.pyplot.close") as mock_close:
            adapter.plot_per_question_ranking(small_result_frame, output_dir=tmp_path)
        assert mock_close.call_count >= 1


# ---------------------------------------------------------------------------
# (6) plot_failure_breakdown
# ---------------------------------------------------------------------------


class TestPlotFailureBreakdown:
    def test_svg_criado_com_falhas(
        self,
        adapter: MatplotlibVisualizationAdapter,
        multi_aggregates: list,
        tmp_path: Path,
    ) -> None:
        with patch("matplotlib.pyplot.close") as mock_close:
            fp = adapter.plot_failure_breakdown(multi_aggregates, output_dir=tmp_path)
        _assert_svg_created(fp.path)
        assert fp.format == "svg"
        assert fp.plot_type == "failure_breakdown"
        assert mock_close.call_count >= 1

    def test_zero_falhas_arquivo_criado_sem_excecao(
        self, adapter: MatplotlibVisualizationAdapter, tmp_path: Path
    ) -> None:
        """Quando failure_rate=0 em todos, nenhuma exceção e arquivo criado."""
        aggs = [
            make_config_aggregate(base="IDx_400k", llm="llama3-8b", failure_rate=0.0),
            make_config_aggregate(base="ID_230K", llm="llama3-8b", failure_rate=0.05),
        ]
        with patch("matplotlib.pyplot.close") as mock_close:
            fp = adapter.plot_failure_breakdown(aggs, output_dir=tmp_path)
        _assert_svg_created(fp.path)
        assert mock_close.call_count >= 1

    def test_plt_close_chamado(
        self,
        adapter: MatplotlibVisualizationAdapter,
        multi_aggregates: list,
        tmp_path: Path,
    ) -> None:
        with patch("matplotlib.pyplot.close") as mock_close:
            adapter.plot_failure_breakdown(multi_aggregates, output_dir=tmp_path)
        assert mock_close.call_count >= 1


# ---------------------------------------------------------------------------
# VisualizationAdapterConfig
# ---------------------------------------------------------------------------


class TestVisualizationAdapterConfig:
    def test_defaults(self) -> None:
        cfg = VisualizationAdapterConfig()
        assert cfg.formats == ["svg"]
        assert cfg.dpi == 150
        assert cfg.figure_width == 10.0
        assert cfg.figure_height == 6.0
        assert cfg.failure_threshold == 0.20
        assert cfg.top_n_radar == 5

    def test_png_adicional(self, multi_aggregates: list, tmp_path: Path) -> None:
        cfg = VisualizationAdapterConfig(formats=["svg", "png"])
        adapter = MatplotlibVisualizationAdapter(config=cfg)
        with patch("matplotlib.pyplot.close"):
            fp = adapter.plot_rankscore_heatmap(multi_aggregates, output_dir=tmp_path)
        assert fp.path.exists()
        png_path = fp.path.with_suffix(".png")
        assert png_path.exists()
