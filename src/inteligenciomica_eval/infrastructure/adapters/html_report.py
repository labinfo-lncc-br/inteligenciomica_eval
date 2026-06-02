"""HTMLReportAdapter — relatório executivo HTML autocontido (TAREFA-408, §11.4).

Implementa ``ReportPort.generate_html`` produzindo um arquivo HTML único,
sem URLs externas, com plots SVG embutidos como base64 (Nota M4 item 5).
Template separado em ``infrastructure/prompts/report_template.html.j2``.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import jinja2

from inteligenciomica_eval.domain.ports import ResultFrame
from inteligenciomica_eval.domain.services.aggregation import ConfigAggregate
from inteligenciomica_eval.domain.value_objects import (
    FigurePath,
    ReportPath,
    StatsReport,
)


class HTMLReportAdapter:
    """Gera relatório HTML autocontido via template Jinja2 (TAREFA-408).

    Implementa :class:`~inteligenciomica_eval.domain.ports.ReportPort`.
    O template reside em ``infrastructure/prompts/report_template.html.j2``
    e é carregado via ``PackageLoader`` para garantir compatibilidade com
    instalação via wheel.

    Args:
        _env: instância Jinja2 opcional (injetável para testes).
    """

    def __init__(self, _env: jinja2.Environment | None = None) -> None:
        if _env is not None:
            self._env = _env
        else:
            loader = jinja2.PackageLoader(
                "inteligenciomica_eval",
                package_path="infrastructure/prompts",
            )
            self._env = jinja2.Environment(
                loader=loader,
                autoescape=True,
                undefined=jinja2.Undefined,
            )

    # ------------------------------------------------------------------
    # ReportPort implementation
    # ------------------------------------------------------------------

    def generate_html(
        self,
        *,
        run_id: str,
        aggregates: Sequence[ConfigAggregate],
        results: ResultFrame,
        stats_report: StatsReport,
        figure_paths: Sequence[FigurePath],
        output_path: Path,
    ) -> ReportPath:
        """Gera relatório HTML autocontido.

        Pipeline (ordem obrigatória):
        1. Embute SVGs como ``data:image/svg+xml;base64,...`` (arquivo ausente → placeholder).
        2. Monta contexto Jinja2 com aggregates, stats_summary e figures.
        3. Renderiza ``report_template.html.j2``.
        4. Escreve HTML em ``output_path`` (cria dir pai se necessário).
        5. Retorna :class:`ReportPath`.

        Args:
            run_id: identificador do run de avaliação.
            aggregates: sequência de agregados de configuração (já ordenada pelo caller).
            results: frame com todos os resultados individuais da rodada.
            stats_report: relatório estatístico consolidado.
            figure_paths: sequência de caminhos das figuras a embutir.
            output_path: caminho de saída para o arquivo HTML gerado.

        Returns:
            :class:`ReportPath` com caminho, formato ``"html"`` e run_id.
        """
        figures = self._embed_figures(figure_paths)
        aggregates_table = self._build_aggregates_table(aggregates)
        stats_summary = self._build_stats_summary(stats_report)

        n_questions = len({r.answer.question.question_id for r in results.results})

        context: dict[str, object] = {
            "run_id": run_id,
            "generation_ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "n_configs": len(aggregates),
            "n_questions": n_questions,
            "aggregates_table": aggregates_table,
            "stats_summary": stats_summary,
            "figures": figures,
        }

        template = self._env.get_template("report_template.html.j2")
        html_content = template.render(**context)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html_content, encoding="utf-8")

        return ReportPath(path=output_path, format="html", run_id=run_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _embed_figures(
        self, figure_paths: Sequence[FigurePath]
    ) -> list[dict[str, object]]:
        """Codifica SVGs em base64; arquivo ausente gera placeholder."""
        figures: list[dict[str, object]] = []
        for fp in figure_paths:
            if fp.format == "svg" and fp.path.exists():
                raw = fp.path.read_bytes()
                b64 = base64.b64encode(raw).decode("utf-8")
                src = f"data:image/svg+xml;base64,{b64}"
                figures.append(
                    {"plot_type": fp.plot_type, "src": src, "available": True}
                )
            else:
                figures.append(
                    {"plot_type": fp.plot_type, "src": "", "available": False}
                )
        return figures

    def _build_aggregates_table(
        self, aggregates: Sequence[ConfigAggregate]
    ) -> list[dict[str, object]]:
        """Ordena agregados por rank_score desc e formata campos."""
        sorted_aggs = sorted(aggregates, key=lambda a: a.rank_score.value, reverse=True)
        rows: list[dict[str, object]] = []
        for agg in sorted_aggs:
            rows.append(
                {
                    "config": f"{agg.base.value}/{agg.llm.value}",
                    "rank_score": f"{agg.rank_score.value:.3f}",
                    "median_score": f"{agg.median_score:.3f}",
                    "failure_rate": f"{agg.failure_rate:.3f}",
                    "win_rate": f"{agg.win_rate:.3f}",
                    "critical_failure_rate": f"{agg.critical_failure_rate:.3f}",
                }
            )
        return rows

    def _build_stats_summary(self, stats_report: StatsReport) -> dict[str, object]:
        """Extrai campos do StatsReport; campo ausente → 'N/A'."""

        def _safe(val: object) -> str:
            if val is None:
                return "N/A"
            return str(val)

        wilcoxon_sig = any(wr.significant for wr in stats_report.wilcoxon_reports)
        friedman_sig = any(fr.significant for fr in stats_report.friedman_reports)

        return {
            "run_id": _safe(stats_report.run_id),
            "round_id": _safe(stats_report.round_id),
            "correction_method": _safe(stats_report.correction_method),
            "alpha": _safe(stats_report.alpha),
            "base_difference_significant": _safe(
                stats_report.base_difference_significant
            ),
            "llm_difference_significant": _safe(
                stats_report.llm_difference_significant
            ),
            "interaction_significant": _safe(stats_report.interaction_significant),
            "top_llm_by_friedman": _safe(stats_report.top_llm_by_friedman),
            "wilcoxon_significant": _safe(wilcoxon_sig),
            "friedman_significant": _safe(friedman_sig),
            "n_wilcoxon_tests": _safe(len(stats_report.wilcoxon_reports)),
            "n_friedman_tests": _safe(len(stats_report.friedman_reports)),
            "n_mlm_tests": _safe(len(stats_report.mlm_reports)),
        }
