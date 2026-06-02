"""Testes unitários do HTMLReportAdapter (TAREFA-408)."""

from __future__ import annotations

import base64
import html.parser
from pathlib import Path

import jinja2
import pytest

from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
)
from inteligenciomica_eval.domain.ports import ResultFrame
from inteligenciomica_eval.domain.services.aggregation import ConfigAggregate
from inteligenciomica_eval.domain.value_objects import (
    BaseId,
    DeterminismRegime,
    FigurePath,
    FinalScore,
    FriedmanReport,
    LLMId,
    MetricVector,
    MLMReport,
    NemenyiPair,
    RankScore,
    ReportPath,
    RowId,
    Seed,
    StatsReport,
    WilcoxonReport,
)
from inteligenciomica_eval.infrastructure.adapters.html_report import HTMLReportAdapter

# ---------------------------------------------------------------------------
# Helpers / factories de fixture
# ---------------------------------------------------------------------------

_NAN = float("nan")


def _metric_vector(val: float = 0.8) -> MetricVector:
    return MetricVector(
        answer_correctness=val,
        answer_similarity=val,
        faithfulness=val,
        context_precision=val,
        context_recall=val,
        answer_relevancy=val,
        bertscore_f1=val,
        rubric_biomed_score=val,
    )


def _question(qid: str = "q1") -> Question:
    return Question(
        question_id=qid,
        text="Qual o papel do BRCA1?",
        ground_truth="Proteína supressora de tumor.",
    )


def _row_id(hex_str: str | None = None) -> RowId:
    default = "a" * 64
    return RowId(hex_str or default)


def _generated_answer(
    qid: str = "q1",
    llm: str = "llm_a",
    base: str = "IDx_400k",
    seed: int = 42,
) -> GeneratedAnswer:
    return GeneratedAnswer(
        row_id=_row_id("a" * 64),
        question=_question(qid),
        base=BaseId(base),
        llm=LLMId(llm),
        seed=Seed(seed),
        phase="A",
        generated_answer="Resposta gerada.",
        retrieved_chunk_ids=("chunk-1",),
        retrieved_chunks_text=("Texto do chunk 1.",),
        retrieval_scores=(0.9,),
    )


def _eval_result(
    qid: str = "q1",
    llm: str = "llm_a",
    base: str = "IDx_400k",
    score: float = 0.8,
) -> EvaluationResult:
    return EvaluationResult(
        answer=_generated_answer(qid=qid, llm=llm, base=base),
        metrics=_metric_vector(score),
        final_score=FinalScore(score),
        determinism_regime=DeterminismRegime.JUDGE,
        critical_failure_flag=None,
        critical_failure_note=None,
    )


def _config_aggregate(
    base: str = "IDx_400k",
    llm: str = "llm_a",
    rank: float = 0.85,
    median: float = 0.80,
    fail: float = 0.10,
    win: float = 0.60,
    crit_fail: float = 0.05,
) -> ConfigAggregate:
    return ConfigAggregate(
        base=BaseId(base),
        llm=LLMId(llm),
        mean_score=median,
        median_score=median,
        min_score=0.5,
        iqr=0.1,
        failure_rate=fail,
        critical_failure_rate=crit_fail,
        win_rate=win,
        rank_score=RankScore(rank),
        n_observations=13,
        n_excluded_nan=0,
    )


def _stats_report(run_id: str = "run1") -> StatsReport:
    return StatsReport(
        run_id=run_id,
        round_id="round_1",
        wilcoxon_reports=(
            WilcoxonReport(
                metric="final_score",
                base_a="IDx_400k",
                base_b="ID_230K",
                statistic=12.0,
                p_value=0.03,
                p_value_corrected=0.04,
                significant=True,
                n_pairs=13,
                effect_size_r=0.45,
            ),
        ),
        friedman_reports=(
            FriedmanReport(
                metric="final_score",
                chi2_statistic=8.5,
                p_value=0.04,
                p_value_corrected=0.04,
                significant=True,
                n_groups=3,
                n_blocks=13,
                nemenyi_pairs=(
                    NemenyiPair(
                        llm_a="llm_a",
                        llm_b="llm_b",
                        p_value=0.02,
                        significant=True,
                        winner="llm_a",
                    ),
                ),
            ),
        ),
        mlm_reports=(
            MLMReport(
                formula="final_score ~ base * llm + (1 | question_id)",
                base_effect_coef=0.12,
                base_effect_p_value=0.03,
                llm_effect_p_values={"llm_b": 0.05},
                interaction_p_value=0.10,
                interaction_significant=False,
                aic=120.5,
                n_observations=78,
                convergence_warning=False,
            ),
        ),
        correction_method="benjamini-hochberg",
        alpha=0.05,
        base_difference_significant=True,
        llm_difference_significant=True,
        interaction_significant=False,
        top_llm_by_friedman="llm_a",
    )


def _result_frame(n: int = 2) -> ResultFrame:
    results = tuple(
        _eval_result(qid=f"q{i}", llm="llm_a", base="IDx_400k", score=0.8)
        for i in range(n)
    )
    return ResultFrame(results=results)


def _svg_bytes() -> bytes:
    return b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="100" height="100"/></svg>'


def _make_adapter() -> HTMLReportAdapter:
    """Cria HTMLReportAdapter usando o PackageLoader real (template do pacote)."""
    return HTMLReportAdapter()


def _make_adapter_with_template(template_str: str) -> HTMLReportAdapter:
    """Cria HTMLReportAdapter com template inline para testes isolados."""
    env = jinja2.Environment(
        loader=jinja2.DictLoader({"report_template.html.j2": template_str}),
        autoescape=True,
    )
    return HTMLReportAdapter(_env=env)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHTMLReportAdapterEmbedFigures:
    """(a) 6 figuras SVG → HTML com 6 data:image/svg+xml;base64,"""

    def test_six_svg_figures_embedded_as_base64(self, tmp_path: Path) -> None:
        plot_types = [
            "rankscore_heatmap",
            "finalscore_boxplot",
            "interaction",
            "radar",
            "per_question_ranking",
            "failure_breakdown",
        ]
        svg_data = _svg_bytes()
        figure_paths = []
        for pt in plot_types:
            p = tmp_path / f"{pt}.svg"
            p.write_bytes(svg_data)
            figure_paths.append(FigurePath(path=p, format="svg", plot_type=pt))

        adapter = _make_adapter()
        out = tmp_path / "report.html"
        result = adapter.generate_html(
            run_id="run1",
            aggregates=[_config_aggregate()],
            results=_result_frame(),
            stats_report=_stats_report(),
            figure_paths=figure_paths,
            output_path=out,
        )

        html_content = out.read_text(encoding="utf-8")
        expected_b64 = base64.b64encode(svg_data).decode("utf-8")
        count = html_content.count(f"data:image/svg+xml;base64,{expected_b64}")
        assert count == 6, f"Esperado 6 figuras embutidas, encontrado {count}"
        assert isinstance(result, ReportPath)
        assert result.format == "html"
        assert result.run_id == "run1"

    def test_returns_report_path_pointing_to_output(self, tmp_path: Path) -> None:
        svg_p = tmp_path / "plot.svg"
        svg_p.write_bytes(_svg_bytes())
        fp = FigurePath(path=svg_p, format="svg", plot_type="rankscore_heatmap")

        adapter = _make_adapter()
        out = tmp_path / "sub" / "report.html"
        result = adapter.generate_html(
            run_id="r2",
            aggregates=[_config_aggregate()],
            results=_result_frame(),
            stats_report=_stats_report(),
            figure_paths=[fp],
            output_path=out,
        )
        assert result.path == out
        assert out.exists()


@pytest.mark.unit
class TestHTMLReportAdapterMissingFigure:
    """(b) Figura ausente → placeholder sem exceção."""

    def test_missing_svg_produces_placeholder(self, tmp_path: Path) -> None:
        fp = FigurePath(
            path=tmp_path / "nao_existe.svg",
            format="svg",
            plot_type="rankscore_heatmap",
        )
        adapter = _make_adapter()
        out = tmp_path / "report.html"
        # não deve lançar exceção
        adapter.generate_html(
            run_id="r3",
            aggregates=[_config_aggregate()],
            results=_result_frame(),
            stats_report=_stats_report(),
            figure_paths=[fp],
            output_path=out,
        )
        html_content = out.read_text(encoding="utf-8")
        assert "indispon" in html_content.lower() or "rankscore_heatmap" in html_content

    def test_empty_figure_paths_no_exception(self, tmp_path: Path) -> None:
        adapter = _make_adapter()
        out = tmp_path / "report.html"
        # figure_paths vazio não deve lançar
        adapter.generate_html(
            run_id="r4",
            aggregates=[_config_aggregate()],
            results=_result_frame(),
            stats_report=_stats_report(),
            figure_paths=[],
            output_path=out,
        )
        assert out.exists()


@pytest.mark.unit
class TestHTMLReportAdapterMissingStatsField:
    """(c) Campo ausente em StatsReport → 'N/A' no HTML, sem exceção."""

    def test_none_top_llm_renders_na(self, tmp_path: Path) -> None:
        sr = StatsReport(
            run_id="r5",
            round_id="round_1",
            wilcoxon_reports=(),
            friedman_reports=(),
            mlm_reports=(),
            correction_method="benjamini-hochberg",
            alpha=0.05,
            base_difference_significant=False,
            llm_difference_significant=False,
            interaction_significant=False,
            top_llm_by_friedman=None,  # ausente
        )
        adapter = _make_adapter()
        out = tmp_path / "report.html"
        adapter.generate_html(
            run_id="r5",
            aggregates=[_config_aggregate()],
            results=_result_frame(),
            stats_report=sr,
            figure_paths=[],
            output_path=out,
        )
        html_content = out.read_text(encoding="utf-8")
        assert "N/A" in html_content


@pytest.mark.unit
class TestHTMLReportAdapterRankingTable:
    """(d) Tabela ordenada: melhor config na linha 1 com class="best-config"."""

    def test_best_config_is_first_row(self, tmp_path: Path) -> None:
        # Agrega desordenados propositalmente: llm_b tem rank alto, llm_a baixo
        agg_high = _config_aggregate(llm="llm_b", rank=0.95, median=0.92)
        agg_low = _config_aggregate(llm="llm_a", rank=0.60, median=0.55)
        aggregates = [agg_low, agg_high]  # ordem proposital: baixo primeiro

        adapter = _make_adapter()
        out = tmp_path / "report.html"
        adapter.generate_html(
            run_id="r6",
            aggregates=aggregates,
            results=_result_frame(),
            stats_report=_stats_report(),
            figure_paths=[],
            output_path=out,
        )
        html_content = out.read_text(encoding="utf-8")
        # best-config deve aparecer antes do llm_a
        pos_best = html_content.find("best-config")
        pos_llm_b = html_content.find("IDx_400k/llm_b")
        pos_llm_a = html_content.find("IDx_400k/llm_a")
        assert pos_best != -1, "class='best-config' não encontrada"
        assert pos_llm_b < pos_llm_a, "llm_b (rank maior) deve aparecer antes de llm_a"

    def test_best_config_class_present(self, tmp_path: Path) -> None:
        agg1 = _config_aggregate(llm="llm_a", rank=0.90)
        agg2 = _config_aggregate(llm="llm_b", rank=0.70)
        adapter = _make_adapter()
        out = tmp_path / "report.html"
        adapter.generate_html(
            run_id="r7",
            aggregates=[agg1, agg2],
            results=_result_frame(),
            stats_report=_stats_report(),
            figure_paths=[],
            output_path=out,
        )
        html_content = out.read_text(encoding="utf-8")
        assert "best-config" in html_content


@pytest.mark.unit
class TestHTMLReportAdapterNoExternalURLs:
    """(e) assert 'http' not in html_content.lower()."""

    def test_no_http_references(self, tmp_path: Path) -> None:
        adapter = _make_adapter()
        out = tmp_path / "report.html"
        adapter.generate_html(
            run_id="r8",
            aggregates=[_config_aggregate()],
            results=_result_frame(),
            stats_report=_stats_report(),
            figure_paths=[],
            output_path=out,
        )
        html_content = out.read_text(encoding="utf-8")
        assert "http" not in html_content.lower(), (
            "HTML contém referência(s) a URL externa com 'http'"
        )

    def test_template_has_no_http_references(self) -> None:
        """Verifica que o template em disco não contém http."""
        from importlib.resources import files

        template_path = (
            files("inteligenciomica_eval")
            / "infrastructure"
            / "prompts"
            / "report_template.html.j2"
        )
        content = template_path.read_text(encoding="utf-8")
        assert "http" not in content.lower(), (
            "report_template.html.j2 contém referência 'http' — BLOQUEADOR Nota M4 item 5"
        )


@pytest.mark.unit
class TestHTMLReportAdapterParseable:
    """(f) HTML parseable via html.parser."""

    def test_html_is_parseable(self, tmp_path: Path) -> None:
        adapter = _make_adapter()
        out = tmp_path / "report.html"
        adapter.generate_html(
            run_id="r9",
            aggregates=[_config_aggregate()],
            results=_result_frame(),
            stats_report=_stats_report(),
            figure_paths=[],
            output_path=out,
        )
        html_content = out.read_text(encoding="utf-8")
        errors: list[str] = []

        class _StrictParser(html.parser.HTMLParser):
            def handle_starttag(
                self, tag: str, attrs: list[tuple[str, str | None]]
            ) -> None:
                pass

            def handle_endtag(self, tag: str) -> None:
                pass

            def handle_data(self, data: str) -> None:
                pass

        parser = _StrictParser()
        try:
            parser.feed(html_content)
        except html.parser.HTMLParseError as exc:
            errors.append(str(exc))

        assert not errors, f"HTML inválido: {errors}"

    def test_five_section_ids_present(self, tmp_path: Path) -> None:
        """Verifica os 5 section IDs obrigatórios."""
        required_ids = [
            'id="cabecalho"',
            'id="ranking-executivo"',
            'id="visualizacoes"',
            'id="resultados-estatisticos"',
            'id="nota-metodologica"',
        ]
        adapter = _make_adapter()
        out = tmp_path / "report.html"
        adapter.generate_html(
            run_id="r10",
            aggregates=[_config_aggregate()],
            results=_result_frame(),
            stats_report=_stats_report(),
            figure_paths=[],
            output_path=out,
        )
        html_content = out.read_text(encoding="utf-8")
        for section_id in required_ids:
            assert section_id in html_content, (
                f"Section ID obrigatório ausente no HTML: {section_id}"
            )
