"""MatplotlibVisualizationAdapter — 6 plots canônicos §11.4 (TAREFA-407).

Nota de operacionalização M4 item 3: todos os 6 plots em um único adapter.
Nota de operacionalização M4 item 4: matplotlib.use("Agg") ANTES de qualquer
import gráfico — linha 1 do bloco de imports gráficos.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # BLOQUEADOR: deve preceder qualquer import de pyplot/seaborn

# isort: split
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns

from inteligenciomica_eval.domain.errors import ConfigValidationError
from inteligenciomica_eval.domain.ports import ResultFrame
from inteligenciomica_eval.domain.services.aggregation import ConfigAggregate
from inteligenciomica_eval.domain.value_objects import FigurePath
from inteligenciomica_eval.infrastructure.config.adapter_configs import (
    VisualizationAdapterConfig,
)

_VALID_METRICS = frozenset(
    {
        "rank_score",
        "median_score",
        "failure_rate",
        "win_rate",
        "critical_failure_rate",
    }
)

_RADAR_AXES = [
    "median_score",
    "failure_rate",
    "critical_failure_rate",
    "win_rate",
    "mean_score",
    "min_score",
]
"""Eixos do radar chart.

Nota: ``ConfigAggregate`` (M0) armazena agregados de ``FinalScore``, não métricas
individuais RAGAS/BERTScore. Os 6 eixos usam os campos disponíveis do VO. Os eixos
originalmente desejados (``answer_correctness``, ``faithfulness``, etc.) requerem
extensão do ``ConfigAggregate`` em M5+.
"""


def _metric_value(agg: ConfigAggregate, metric: str) -> float:
    """Retorna o valor numérico de *metric* em *agg*."""
    if metric == "rank_score":
        return agg.rank_score.value
    return float(getattr(agg, metric))


def _config_label(agg: ConfigAggregate) -> str:
    return f"{agg.base.value}\n{agg.llm.value}"


def _save(
    fig: Any,  # matplotlib.figure.Figure — sem stubs mypy para matplotlib
    path: Path,
    config: VisualizationAdapterConfig,
    plot_type: str,
) -> FigurePath:
    """Salva a figura e fecha-a. Retorna FigurePath primário (SVG)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="svg", bbox_inches="tight")
    if "png" in config.formats:
        png_path = path.with_suffix(".png")
        fig.savefig(png_path, format="png", dpi=config.dpi, bbox_inches="tight")
    plt.close(fig)
    return FigurePath(path=path, format="svg", plot_type=plot_type)


class MatplotlibVisualizationAdapter:
    """Implementa :class:`VisualizationPort` com Matplotlib/Seaborn (TAREFA-407, §11.4).

    Todos os métodos são síncronos (CPU-bound). O backend ``Agg`` é configurado
    no topo do módulo — obrigatório para CI sem display (Nota M4 item 4).

    Args:
        config: configuração de visualização; usa defaults se omitido.
    """

    def __init__(
        self,
        config: VisualizationAdapterConfig | None = None,
    ) -> None:
        self._config = config or VisualizationAdapterConfig()
        sns.set_theme(style="whitegrid", palette="colorblind")

    # ------------------------------------------------------------------
    # (1) Heatmap de RankScore
    # ------------------------------------------------------------------

    def plot_rankscore_heatmap(
        self,
        aggregates: Sequence[ConfigAggregate],
        *,
        output_dir: Path,
        metric_name: str = "rank_score",
    ) -> FigurePath:
        """Heatmap pivot {base x LLM} para a metrica solicitada.

        Args:
            aggregates: sequência de ConfigAggregate.
            output_dir: diretório de saída.
            metric_name: uma de ``"rank_score"``, ``"median_score"``,
                ``"failure_rate"``, ``"win_rate"``, ``"critical_failure_rate"``.

        Returns:
            :class:`FigurePath` com caminho do SVG gerado.

        Raises:
            :class:`ConfigValidationError`: se *metric_name* for inválido.
        """
        if metric_name not in _VALID_METRICS:
            raise ConfigValidationError(
                "metric_name",
                f"{metric_name!r} não é uma métrica válida; "
                f"válidas: {sorted(_VALID_METRICS)}",
            )

        bases = sorted({a.base.value for a in aggregates})
        llms = sorted({a.llm.value for a in aggregates})

        matrix: list[list[float]] = []
        for base in bases:
            row = []
            for llm in llms:
                matches = [
                    a for a in aggregates if a.base.value == base and a.llm.value == llm
                ]
                val = (
                    _metric_value(matches[0], metric_name) if matches else float("nan")
                )
                row.append(val)
            matrix.append(row)

        import pandas as pd

        data = pd.DataFrame(matrix, index=bases, columns=llms)

        fig, ax = plt.subplots(
            figsize=(self._config.figure_width, self._config.figure_height)
        )
        sns.heatmap(
            data,
            annot=True,
            fmt=".3f",
            cmap="RdYlGn",
            vmin=0,
            vmax=1,
            ax=ax,
            linewidths=0.5,
        )
        ax.set_title(f"{metric_name} — heatmap")

        # Borda preta na célula com valor máximo (ignora NaN)
        flat = [
            (r, c, matrix[r][c]) for r in range(len(bases)) for c in range(len(llms))
        ]
        valid = [(r, c, v) for r, c, v in flat if not math.isnan(v)]
        if valid:
            max_r, max_c, _ = max(valid, key=lambda t: t[2])
            ax.add_patch(
                mpatches.Rectangle(
                    (max_c, max_r),
                    1,
                    1,
                    fill=False,
                    edgecolor="black",
                    lw=2,
                )
            )

        path = output_dir / f"{metric_name}_heatmap.svg"
        return _save(fig, path, self._config, "rankscore_heatmap")

    # ------------------------------------------------------------------
    # (2) Boxplots de FinalScore
    # ------------------------------------------------------------------

    def plot_finalscore_boxplots(
        self,
        aggregates: Sequence[ConfigAggregate],
        *,
        output_dir: Path,
        results: ResultFrame | None = None,
    ) -> FigurePath:
        """Boxplots de FinalScore por configuração, ordenados por rank_score descendente.

        Quando *results* não é fornecido, usa aproximação por ``median_score`` e
        ``iqr`` do ``ConfigAggregate`` (documentado como aproximação no docstring).

        Args:
            aggregates: sequência de ConfigAggregate.
            output_dir: diretório de saída.
            results: frame com resultados individuais; ``None`` usa apenas agregados.

        Returns:
            :class:`FigurePath` com caminho do SVG gerado.
        """
        sorted_aggs = sorted(aggregates, key=lambda a: a.rank_score.value, reverse=True)
        labels = [_config_label(a) for a in sorted_aggs]

        fig, ax = plt.subplots(
            figsize=(self._config.figure_width, self._config.figure_height)
        )

        if results is not None:
            # Boxplot real a partir dos EvaluationResult
            import pandas as pd

            rows = []
            for er in results.results:
                config_label = f"{er.answer.base.value}\n{er.answer.llm.value}"
                rows.append(
                    {"config": config_label, "final_score": er.final_score.value}
                )
            df = pd.DataFrame(rows)
            # Preservar ordem de sorted_aggs
            order = [lb for lb in labels if lb in df["config"].values]
            import seaborn as _sns

            _sns.boxplot(data=df, x="config", y="final_score", order=order, ax=ax)
        else:
            # Aproximação: médiana central, iqr como spread
            box_data = []
            for agg in sorted_aggs:
                med = agg.median_score
                half_iqr = agg.iqr / 2.0 if not math.isnan(agg.iqr) else 0.0
                q1 = med - half_iqr
                q3 = med + half_iqr
                # Simular 5 pontos: min, Q1, med, Q3, max (para boxplot aproximado)
                whisker_lo = max(0.0, agg.min_score)
                whisker_hi = min(1.0, q3 + half_iqr)
                box_data.append(
                    {
                        "med": med,
                        "q1": q1,
                        "q3": q3,
                        "whislo": whisker_lo,
                        "whishi": whisker_hi,
                        "fliers": [],
                    }
                )
            ax.bxp(box_data, showfliers=False)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, rotation=30, ha="right")

        ax.set_title("FinalScore — boxplot por configuração")
        ax.set_ylabel("FinalScore")
        ax.set_xlabel("Configuração")

        path = output_dir / "finalscore_boxplot.svg"
        return _save(fig, path, self._config, "finalscore_boxplot")

    # ------------------------------------------------------------------
    # (3) Interaction plot
    # ------------------------------------------------------------------

    def plot_interaction(
        self,
        aggregates: Sequence[ConfigAggregate],
        *,
        output_dir: Path,
    ) -> FigurePath:
        """Interaction plot: x=base, y=median_score, linha por LLM.

        Args:
            aggregates: sequência de ConfigAggregate.
            output_dir: diretório de saída.

        Returns:
            :class:`FigurePath` com caminho do SVG gerado.
        """
        llms = sorted({a.llm.value for a in aggregates})
        bases = sorted({a.base.value for a in aggregates})

        fig, ax = plt.subplots(
            figsize=(self._config.figure_width, self._config.figure_height)
        )

        for llm in llms:
            xs: list[int] = []
            ys: list[float] = []
            for i, base in enumerate(bases):
                matches = [
                    a for a in aggregates if a.base.value == base and a.llm.value == llm
                ]
                if matches:
                    xs.append(i)
                    ys.append(matches[0].median_score)
            ax.plot(xs, ys, marker="o", label=llm)

        ax.set_xticks(range(len(bases)))
        ax.set_xticklabels(bases)
        ax.set_xlabel("Base")
        ax.set_ylabel("median_score")
        ax.set_title("Interaction plot — base x LLM")
        ax.legend(title="LLM", bbox_to_anchor=(1.05, 1), loc="upper left")

        path = output_dir / "interaction_plot.svg"
        return _save(fig, path, self._config, "interaction")

    # ------------------------------------------------------------------
    # (4) Radar chart
    # ------------------------------------------------------------------

    def plot_radar(
        self,
        aggregates: Sequence[ConfigAggregate],
        *,
        output_dir: Path,
        top_n: int = 5,
    ) -> FigurePath:
        """Radar (spider) chart das top-N configurações por rank_score.

        Eixos utilizados: ``median_score``, ``failure_rate``, ``critical_failure_rate``,
        ``win_rate``, ``mean_score``, ``min_score`` — campos disponíveis no
        ``ConfigAggregate`` (M0). Os eixos RAGAS individuais (``answer_correctness``,
        ``faithfulness``, etc.) requerem extensão do VO em M5+.

        Args:
            aggregates: sequência de ConfigAggregate.
            output_dir: diretório de saída.
            top_n: número de configurações a incluir.

        Returns:
            :class:`FigurePath` com caminho do SVG gerado.
        """
        top = sorted(aggregates, key=lambda a: a.rank_score.value, reverse=True)[:top_n]

        axes = _RADAR_AXES
        n_axes = len(axes)
        angles = [2 * math.pi * i / n_axes for i in range(n_axes)]
        angles_closed = [*angles, angles[0]]

        fig, polar_ax_raw = plt.subplots(
            figsize=(self._config.figure_width, self._config.figure_height),
            subplot_kw={"projection": "polar"},
        )
        polar_ax: Any = polar_ax_raw  # PolarAxes — sem stubs mypy

        palette = sns.color_palette("colorblind", len(top))

        for i, agg in enumerate(top):
            values = []
            for metric in axes:
                v = _metric_value(agg, metric)
                values.append(0.0 if math.isnan(v) else v)
            values_closed = [*values, values[0]]
            color = palette[i]
            polar_ax.plot(angles_closed, values_closed, color=color, linewidth=1.5)
            polar_ax.fill(angles_closed, values_closed, color=color, alpha=0.15)

        polar_ax.set_thetagrids(
            [math.degrees(a) for a in angles],
            labels=axes,
        )
        polar_ax.set_title(f"Radar — top {top_n} por rank_score", pad=20)
        handles = [
            mpatches.Patch(color=palette[i], label=_config_label(top[i]))
            for i in range(len(top))
        ]
        polar_ax.legend(
            handles=handles,
            loc="upper right",
            bbox_to_anchor=(1.3, 1.1),
        )

        path = output_dir / f"radar_top{top_n}.svg"
        return _save(fig, path, self._config, "radar")

    # ------------------------------------------------------------------
    # (5) Per-question ranking heatmap
    # ------------------------------------------------------------------

    def plot_per_question_ranking(
        self,
        results: ResultFrame,
        *,
        output_dir: Path,
    ) -> FigurePath:
        """Heatmap question x config com FinalScore por celula.

        Args:
            results: frame com resultados individuais por pergunta.
            output_dir: diretório de saída.

        Returns:
            :class:`FigurePath` com caminho do SVG gerado.
        """
        import pandas as pd

        rows = []
        for er in results.results:
            config_label = f"{er.answer.base.value}\n{er.answer.llm.value}"
            rows.append(
                {
                    "question": er.answer.question.question_id,
                    "config": config_label,
                    "final_score": er.final_score.value,
                }
            )
        df = pd.DataFrame(rows)

        if df.empty:
            matrix = pd.DataFrame()
        else:
            matrix = df.pivot_table(
                index="question", columns="config", values="final_score", aggfunc="mean"
            )

        fig, ax = plt.subplots(
            figsize=(self._config.figure_width, self._config.figure_height)
        )
        if not matrix.empty:
            sns.heatmap(
                matrix,
                annot=True,
                fmt=".2f",
                cmap="YlOrRd",
                ax=ax,
                linewidths=0.3,
            )
        ax.set_title("FinalScore por questao x configuracao")

        path = output_dir / "per_question_ranking.svg"
        return _save(fig, path, self._config, "per_question_ranking")

    # ------------------------------------------------------------------
    # (6) Failure breakdown stacked bar
    # ------------------------------------------------------------------

    def plot_failure_breakdown(
        self,
        aggregates: Sequence[ConfigAggregate],
        *,
        output_dir: Path,
    ) -> FigurePath:
        """Stacked bar de failure_rate + critical_failure_rate por configuração.

        Quando nenhuma configuração supera ``config.failure_threshold``, gera figura
        com mensagem "Sem falhas acima do threshold" (sem exceção).

        Args:
            aggregates: sequência de ConfigAggregate.
            output_dir: diretório de saída.

        Returns:
            :class:`FigurePath` com caminho do SVG gerado.
        """
        threshold = self._config.failure_threshold
        above = [
            a
            for a in aggregates
            if not math.isnan(a.failure_rate) and a.failure_rate > threshold
        ]

        fig, ax = plt.subplots(
            figsize=(self._config.figure_width, self._config.figure_height)
        )

        if not above:
            ax.text(
                0.5,
                0.5,
                "Sem falhas acima do threshold",
                ha="center",
                va="center",
                transform=ax.transAxes,
                fontsize=14,
            )
            ax.set_axis_off()
        else:
            sorted_above = sorted(above, key=lambda a: a.failure_rate, reverse=True)
            labels = [_config_label(a) for a in sorted_above]
            xs = np.arange(len(sorted_above))
            failure_rates = [
                a.failure_rate if not math.isnan(a.failure_rate) else 0.0
                for a in sorted_above
            ]
            crit_rates = [
                a.critical_failure_rate
                if not math.isnan(a.critical_failure_rate)
                else 0.0
                for a in sorted_above
            ]

            ax.bar(xs, failure_rates, label="failure_rate", color="#f4d03f")
            ax.bar(
                xs,
                crit_rates,
                bottom=failure_rates,
                label="critical_failure_rate",
                color="#e74c3c",
            )
            ax.set_xticks(xs)
            ax.set_xticklabels(labels, rotation=30, ha="right")
            ax.set_ylabel("Taxa")
            ax.set_title("Breakdown de falhas por configuração")
            ax.legend()

        path = output_dir / "failure_breakdown.svg"
        return _save(fig, path, self._config, "failure_breakdown")
