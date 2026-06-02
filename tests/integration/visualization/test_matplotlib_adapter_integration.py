"""Testes de integração do MatplotlibVisualizationAdapter (TAREFA-407).

Gera SVGs reais (sem mock) e valida que são XML bem-formado.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from factories.factories import (
    make_config_aggregate,
    make_evaluation_result,
    make_generated_answer,
)

from inteligenciomica_eval.domain.ports import ResultFrame
from inteligenciomica_eval.visualization.matplotlib_adapter import (
    MatplotlibVisualizationAdapter,
)


@pytest.fixture(scope="module")
def adapter() -> MatplotlibVisualizationAdapter:
    return MatplotlibVisualizationAdapter()


@pytest.fixture(scope="module")
def aggregates() -> list:
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


@pytest.fixture(scope="module")
def result_frame() -> ResultFrame:
    results = tuple(
        make_evaluation_result(
            answer=make_generated_answer(
                base="IDx_400k", llm="llama3-8b", question_id=f"q{i:02d}"
            ),
            final_score=0.7 + i * 0.05,
        )
        for i in range(3)
    )
    return ResultFrame(results=results)


def _assert_valid_svg(path: Path) -> None:
    assert path.exists(), f"SVG não encontrado: {path}"
    assert path.stat().st_size > 0, f"SVG vazio: {path}"
    content = path.read_text(encoding="utf-8")
    ET.fromstring(content)  # levanta ParseError se XML inválido


@pytest.mark.integration
def test_rankscore_heatmap_svg_valido(
    adapter: MatplotlibVisualizationAdapter, aggregates: list, tmp_path: Path
) -> None:
    fp = adapter.plot_rankscore_heatmap(aggregates, output_dir=tmp_path)
    _assert_valid_svg(fp.path)


@pytest.mark.integration
def test_finalscore_boxplots_svg_valido(
    adapter: MatplotlibVisualizationAdapter, aggregates: list, tmp_path: Path
) -> None:
    fp = adapter.plot_finalscore_boxplots(aggregates, output_dir=tmp_path)
    _assert_valid_svg(fp.path)


@pytest.mark.integration
def test_finalscore_boxplots_com_results_svg_valido(
    adapter: MatplotlibVisualizationAdapter,
    aggregates: list,
    result_frame: ResultFrame,
    tmp_path: Path,
) -> None:
    fp = adapter.plot_finalscore_boxplots(
        aggregates, output_dir=tmp_path, results=result_frame
    )
    _assert_valid_svg(fp.path)


@pytest.mark.integration
def test_interaction_svg_valido(
    adapter: MatplotlibVisualizationAdapter, aggregates: list, tmp_path: Path
) -> None:
    fp = adapter.plot_interaction(aggregates, output_dir=tmp_path)
    _assert_valid_svg(fp.path)


@pytest.mark.integration
def test_radar_svg_valido(
    adapter: MatplotlibVisualizationAdapter, aggregates: list, tmp_path: Path
) -> None:
    fp = adapter.plot_radar(aggregates, output_dir=tmp_path, top_n=3)
    _assert_valid_svg(fp.path)


@pytest.mark.integration
def test_per_question_ranking_svg_valido(
    adapter: MatplotlibVisualizationAdapter, result_frame: ResultFrame, tmp_path: Path
) -> None:
    fp = adapter.plot_per_question_ranking(result_frame, output_dir=tmp_path)
    _assert_valid_svg(fp.path)


@pytest.mark.integration
def test_failure_breakdown_svg_valido(
    adapter: MatplotlibVisualizationAdapter, aggregates: list, tmp_path: Path
) -> None:
    fp = adapter.plot_failure_breakdown(aggregates, output_dir=tmp_path)
    _assert_valid_svg(fp.path)


@pytest.mark.integration
def test_failure_breakdown_zero_falhas_svg_valido(
    adapter: MatplotlibVisualizationAdapter, tmp_path: Path
) -> None:
    """Sem falhas acima do threshold: arquivo criado, XML válido."""
    aggs = [
        make_config_aggregate(failure_rate=0.0),
        make_config_aggregate(base="ID_230K", failure_rate=0.05),
    ]
    fp = adapter.plot_failure_breakdown(aggs, output_dir=tmp_path)
    _assert_valid_svg(fp.path)
