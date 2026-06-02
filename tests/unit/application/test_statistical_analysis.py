"""Testes unitários do StatisticalAnalysisUseCase (TAREFA-405).

Cobre:
  a) Correção BH: p-values [0.04, 0.03, 0.02] → corrigidos calculados
     manualmente e conferem.
  b) tests=("wilcoxon",): apenas Wilcoxon chamado; Friedman/MLM NÃO chamados.
  c) base_difference_significant=True quando pelo menos 1 Wilcoxon corrigido < alpha.
  d) top_llm_by_friedman: LLM com mais vitórias no Nemenyi identificado.
  e) Persistência JSON: arquivo criado com campos de síntese presentes.
  f) interaction_significant derivado corretamente dos MLMReports.
  g) tests=("all",): todos os três adapters chamados.
  h) Correção Holm: método alternativo funcional.
  i) Caso sem p-values disponíveis (todos NaN): relatório não falha.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from inteligenciomica_eval.application.statistical_analysis import (
    StatisticalAnalysisUseCase,
    StatisticsInput,
    _apply_multiple_correction,
    _derive_top_llm_by_friedman,
)
from inteligenciomica_eval.domain.ports import (
    FriedmanReport,
    MLMReport,
    NemenyiPair,
    ResultFrame,
    WilcoxonReport,
)
from inteligenciomica_eval.domain.value_objects import StatsReport

# ---------------------------------------------------------------------------
# Constantes e helpers
# ---------------------------------------------------------------------------

_RUN_ID = "run-001"
_ROUND_ID = "round_1"
_ALPHA = 0.05


def _make_wilcoxon(
    p: float,
    metric: str = "final_score",
    significant: bool = False,
) -> WilcoxonReport:
    return WilcoxonReport(
        metric=metric,
        base_a="IDx_400k",
        base_b="ID_230K",
        statistic=10.0,
        p_value=p,
        p_value_corrected=None,
        significant=significant,
        n_pairs=10,
        effect_size_r=0.3,
    )


def _make_friedman(
    p: float,
    metric: str = "final_score",
    nemenyi_pairs: tuple[NemenyiPair, ...] = (),
    significant: bool = False,
) -> FriedmanReport:
    return FriedmanReport(
        metric=metric,
        chi2_statistic=8.5,
        p_value=p,
        p_value_corrected=None,
        significant=significant,
        n_groups=3,
        n_blocks=5,
        nemenyi_pairs=nemenyi_pairs,
    )


def _make_mlm(
    interaction_p: float = 0.3,
    base_effect_p: float = 0.1,
    interaction_significant: bool = False,
) -> MLMReport:
    return MLMReport(
        formula="final_score ~ base * llm + (1 | question_id)",
        base_effect_coef=0.05,
        base_effect_p_value=base_effect_p,
        llm_effect_p_values={"llm[T.llama3-70b]": 0.02},
        interaction_p_value=interaction_p,
        interaction_significant=interaction_significant,
        aic=120.5,
        n_observations=60,
        convergence_warning=False,
    )


def _make_use_case(
    wilcoxon_returns: list[WilcoxonReport] | None = None,
    friedman_returns: list[FriedmanReport] | None = None,
    mlm_returns: list[MLMReport] | None = None,
    data_dir: Path | None = None,
) -> tuple[StatisticalAnalysisUseCase, MagicMock, MagicMock, MagicMock, MagicMock]:
    reader = MagicMock()
    reader.load.return_value = ResultFrame(results=())

    w_adapter = MagicMock()
    if wilcoxon_returns is not None:
        w_adapter.wilcoxon_paired.side_effect = wilcoxon_returns
    else:
        w_adapter.wilcoxon_paired.return_value = _make_wilcoxon(0.1)

    f_adapter = MagicMock()
    if friedman_returns is not None:
        f_adapter.friedman_nemenyi.side_effect = friedman_returns
    else:
        f_adapter.friedman_nemenyi.return_value = _make_friedman(0.2)

    m_adapter = MagicMock()
    if mlm_returns is not None:
        m_adapter.mixed_linear_model.side_effect = mlm_returns
    else:
        m_adapter.mixed_linear_model.return_value = _make_mlm()

    uc = StatisticalAnalysisUseCase(
        reader=reader,
        wilcoxon_adapter=w_adapter,
        friedman_adapter=f_adapter,
        mlm_adapter=m_adapter,
        data_dir=data_dir or Path("/tmp"),
    )
    return uc, reader, w_adapter, f_adapter, m_adapter


# ---------------------------------------------------------------------------
# a) Correção BH: p-values [0.04, 0.03, 0.02] → todos corrigidos para 0.04
# ---------------------------------------------------------------------------


class TestBHCorrection:
    """Correção Benjamini-Hochberg com três p-values conhecidos."""

    def test_bh_corrected_values_match_manual_calculation(self) -> None:
        """Para p-values [0.04, 0.03, 0.02] com n=3 e BH:

        Ordenados: [0.02 @rank1, 0.03 @rank2, 0.04 @rank3]
        Ajustados: [0.02*3/1, 0.03*3/2, 0.04*3/3] = [0.06, 0.045, 0.04]
        Após cummin da direita: todos = 0.04
        """
        w_reports = [_make_wilcoxon(0.04), _make_wilcoxon(0.03)]
        f_reports = [_make_friedman(0.02)]

        new_w, new_f = _apply_multiple_correction(
            w_reports, f_reports, "benjamini-hochberg", _ALPHA
        )

        assert new_w[0].p_value_corrected == pytest.approx(0.04, abs=1e-8)
        assert new_w[1].p_value_corrected == pytest.approx(0.04, abs=1e-8)
        assert new_f[0].p_value_corrected == pytest.approx(0.04, abs=1e-8)

    def test_bh_all_significant_at_alpha_005(self) -> None:
        """p_corrected=0.04 < alpha=0.05 → todos significant=True."""
        w_reports = [_make_wilcoxon(0.04), _make_wilcoxon(0.03)]
        f_reports = [_make_friedman(0.02)]

        new_w, new_f = _apply_multiple_correction(
            w_reports, f_reports, "benjamini-hochberg", _ALPHA
        )

        assert all(r.significant for r in new_w)
        assert all(r.significant for r in new_f)

    def test_bh_via_use_case_corrects_reports(self, tmp_path: Path) -> None:
        """Use case aplica correção BH e popula p_value_corrected."""
        # 2 métricas → 2 chamadas para cada adapter
        uc, _, _, _, _ = _make_use_case(
            wilcoxon_returns=[_make_wilcoxon(0.04), _make_wilcoxon(0.03)],
            friedman_returns=[_make_friedman(0.02), _make_friedman(0.15)],
            mlm_returns=[_make_mlm(), _make_mlm()],
            data_dir=tmp_path,
        )
        inp = StatisticsInput(
            run_id=_RUN_ID,
            round_id=_ROUND_ID,
            metrics=("final_score", "bertscore_f1"),
            tests=("all",),
        )
        report = uc.execute(inp)

        for r in report.wilcoxon_reports:
            assert r.p_value_corrected is not None
        for r in report.friedman_reports:
            assert r.p_value_corrected is not None


# ---------------------------------------------------------------------------
# b) tests=("wilcoxon",) — Friedman/MLM NÃO chamados
# ---------------------------------------------------------------------------


class TestTestsSelection:
    """Seleção de subconjunto de testes."""

    def test_wilcoxon_only_calls_only_wilcoxon(self, tmp_path: Path) -> None:
        uc, _, w, f, m = _make_use_case(data_dir=tmp_path)
        uc.execute(
            StatisticsInput(
                run_id=_RUN_ID,
                round_id=_ROUND_ID,
                tests=("wilcoxon",),
            )
        )
        w.wilcoxon_paired.assert_called_once()
        f.friedman_nemenyi.assert_not_called()
        m.mixed_linear_model.assert_not_called()

    def test_friedman_only_calls_only_friedman(self, tmp_path: Path) -> None:
        uc, _, w, f, m = _make_use_case(data_dir=tmp_path)
        uc.execute(
            StatisticsInput(
                run_id=_RUN_ID,
                round_id=_ROUND_ID,
                tests=("friedman",),
            )
        )
        w.wilcoxon_paired.assert_not_called()
        f.friedman_nemenyi.assert_called_once()
        m.mixed_linear_model.assert_not_called()

    def test_mlm_only_calls_only_mlm(self, tmp_path: Path) -> None:
        uc, _, w, f, m = _make_use_case(data_dir=tmp_path)
        uc.execute(
            StatisticsInput(
                run_id=_RUN_ID,
                round_id=_ROUND_ID,
                tests=("mlm",),
            )
        )
        w.wilcoxon_paired.assert_not_called()
        f.friedman_nemenyi.assert_not_called()
        m.mixed_linear_model.assert_called_once()

    def test_all_calls_all_three_adapters(self, tmp_path: Path) -> None:
        uc, _, w, f, m = _make_use_case(data_dir=tmp_path)
        uc.execute(
            StatisticsInput(
                run_id=_RUN_ID,
                round_id=_ROUND_ID,
                tests=("all",),
            )
        )
        w.wilcoxon_paired.assert_called_once()
        f.friedman_nemenyi.assert_called_once()
        m.mixed_linear_model.assert_called_once()

    def test_multiple_metrics_calls_adapters_per_metric(self, tmp_path: Path) -> None:
        uc, _, w, _f, _m = _make_use_case(
            wilcoxon_returns=[_make_wilcoxon(0.1), _make_wilcoxon(0.2)],
            data_dir=tmp_path,
        )
        uc.execute(
            StatisticsInput(
                run_id=_RUN_ID,
                round_id=_ROUND_ID,
                metrics=("final_score", "bertscore_f1"),
                tests=("wilcoxon",),
            )
        )
        assert w.wilcoxon_paired.call_count == 2


# ---------------------------------------------------------------------------
# c) base_difference_significant=True quando Wilcoxon corrigido < alpha
# ---------------------------------------------------------------------------


class TestBaseDifferenceSignificant:
    """Campo base_difference_significant derivado corretamente."""

    def test_significant_true_when_corrected_p_below_alpha(
        self, tmp_path: Path
    ) -> None:
        # p=0.01 com n=1 → corrigido = 0.01 < 0.05 → significant=True
        uc, _, _, _, _ = _make_use_case(
            wilcoxon_returns=[_make_wilcoxon(0.01)],
            friedman_returns=[_make_friedman(0.5)],
            mlm_returns=[_make_mlm()],
            data_dir=tmp_path,
        )
        report = uc.execute(
            StatisticsInput(run_id=_RUN_ID, round_id=_ROUND_ID, tests=("all",))
        )
        assert report.base_difference_significant is True

    def test_significant_false_when_all_corrected_p_above_alpha(
        self, tmp_path: Path
    ) -> None:
        # p=0.5 → corrigido = 0.5 > 0.05 → significant=False
        uc, _, _, _, _ = _make_use_case(
            wilcoxon_returns=[_make_wilcoxon(0.5)],
            friedman_returns=[_make_friedman(0.5)],
            mlm_returns=[_make_mlm()],
            data_dir=tmp_path,
        )
        report = uc.execute(
            StatisticsInput(run_id=_RUN_ID, round_id=_ROUND_ID, tests=("all",))
        )
        assert report.base_difference_significant is False

    def test_no_wilcoxon_tests_gives_false(self, tmp_path: Path) -> None:
        uc, _, _, _, _ = _make_use_case(data_dir=tmp_path)
        report = uc.execute(
            StatisticsInput(
                run_id=_RUN_ID, round_id=_ROUND_ID, tests=("friedman", "mlm")
            )
        )
        assert report.base_difference_significant is False


# ---------------------------------------------------------------------------
# d) top_llm_by_friedman: LLM com mais vitórias no Nemenyi
# ---------------------------------------------------------------------------


class TestTopLLMByFriedman:
    """Campo top_llm_by_friedman derivado corretamente."""

    def test_no_significant_pairs_returns_none(self) -> None:
        reports = [
            _make_friedman(
                0.3,
                nemenyi_pairs=(
                    NemenyiPair("llm_A", "llm_B", 0.2, False, winner=None),
                    NemenyiPair("llm_A", "llm_C", 0.3, False, winner=None),
                ),
            )
        ]
        assert _derive_top_llm_by_friedman(reports) is None

    def test_top_llm_by_winner_field(self) -> None:
        # llm_B vence 2 pares; llm_A vence 0; llm_C vence 0
        nemenyi = (
            NemenyiPair("llm_A", "llm_B", 0.01, True, winner="llm_B"),
            NemenyiPair("llm_B", "llm_C", 0.02, True, winner="llm_B"),
            NemenyiPair("llm_A", "llm_C", 0.3, False, winner=None),
        )
        reports = [_make_friedman(0.01, nemenyi_pairs=nemenyi)]
        assert _derive_top_llm_by_friedman(reports) == "llm_B"

    def test_tie_resolved_alphabetically(self) -> None:
        # llm_A vence 1, llm_B vence 1 → empate → alfabético → "llm_A"
        nemenyi = (
            NemenyiPair("llm_C", "llm_A", 0.01, True, winner="llm_A"),
            NemenyiPair("llm_D", "llm_B", 0.02, True, winner="llm_B"),
        )
        reports = [_make_friedman(0.01, nemenyi_pairs=nemenyi)]
        result = _derive_top_llm_by_friedman(reports)
        assert result == "llm_A"

    def test_winner_none_not_counted(self) -> None:
        # Pares significativos sem winner (não contribuem para contagem)
        nemenyi = (NemenyiPair("llm_A", "llm_B", 0.01, True, winner=None),)
        reports = [_make_friedman(0.01, nemenyi_pairs=nemenyi)]
        assert _derive_top_llm_by_friedman(reports) is None

    def test_correct_identification_via_use_case(self, tmp_path: Path) -> None:
        # llm_X vence 2 pares → top
        nemenyi = (
            NemenyiPair("llm_X", "llm_Y", 0.01, True, winner="llm_X"),
            NemenyiPair("llm_X", "llm_Z", 0.02, True, winner="llm_X"),
            NemenyiPair("llm_Y", "llm_Z", 0.3, False, winner=None),
        )
        uc, _, _, _, _ = _make_use_case(
            wilcoxon_returns=[_make_wilcoxon(0.5)],
            friedman_returns=[_make_friedman(0.01, nemenyi_pairs=nemenyi)],
            mlm_returns=[_make_mlm()],
            data_dir=tmp_path,
        )
        report = uc.execute(
            StatisticsInput(run_id=_RUN_ID, round_id=_ROUND_ID, tests=("all",))
        )
        assert report.top_llm_by_friedman == "llm_X"


# ---------------------------------------------------------------------------
# e) Persistência JSON — arquivo criado com campos de síntese presentes
# ---------------------------------------------------------------------------


class TestJSONPersistence:
    """StatsReport é persistido em JSON parseable com campos de síntese."""

    def test_json_file_created(self, tmp_path: Path) -> None:
        uc, _, _, _, _ = _make_use_case(data_dir=tmp_path)
        uc.execute(StatisticsInput(run_id=_RUN_ID, round_id=_ROUND_ID, tests=("all",)))
        expected_path = tmp_path / f"{_RUN_ID}_{_ROUND_ID}_stats.json"
        assert expected_path.exists()

    def test_json_is_valid_and_parseable(self, tmp_path: Path) -> None:
        uc, _, _, _, _ = _make_use_case(data_dir=tmp_path)
        uc.execute(StatisticsInput(run_id=_RUN_ID, round_id=_ROUND_ID, tests=("all",)))
        path = tmp_path / f"{_RUN_ID}_{_ROUND_ID}_stats.json"
        data = json.loads(path.read_text())
        assert isinstance(data, dict)

    def test_json_contains_synthesis_fields(self, tmp_path: Path) -> None:
        uc, _, _, _, _ = _make_use_case(data_dir=tmp_path)
        uc.execute(StatisticsInput(run_id=_RUN_ID, round_id=_ROUND_ID, tests=("all",)))
        path = tmp_path / f"{_RUN_ID}_{_ROUND_ID}_stats.json"
        data = json.loads(path.read_text())

        required = {
            "run_id",
            "round_id",
            "wilcoxon_reports",
            "friedman_reports",
            "mlm_reports",
            "correction_method",
            "alpha",
            "base_difference_significant",
            "llm_difference_significant",
            "interaction_significant",
            "top_llm_by_friedman",
        }
        assert required.issubset(data.keys())

    def test_json_nan_serialized_as_null(self, tmp_path: Path) -> None:
        """NaN em p_value_corrected deve aparecer como null no JSON."""
        nan_w = WilcoxonReport(
            metric="final_score",
            base_a="IDx_400k",
            base_b="ID_230K",
            statistic=float("nan"),
            p_value=float("nan"),
            p_value_corrected=None,
            significant=False,
            n_pairs=0,
            effect_size_r=None,
        )
        uc, _, w, _f, _m = _make_use_case(data_dir=tmp_path)
        w.wilcoxon_paired.return_value = nan_w
        uc.execute(StatisticsInput(run_id=_RUN_ID, round_id=_ROUND_ID, tests=("all",)))
        path = tmp_path / f"{_RUN_ID}_{_ROUND_ID}_stats.json"
        raw = path.read_text()
        assert "NaN" not in raw  # JSON RFC 8259 não admite NaN literal

    def test_json_contains_correct_run_and_round(self, tmp_path: Path) -> None:
        uc, _, _, _, _ = _make_use_case(data_dir=tmp_path)
        uc.execute(StatisticsInput(run_id="my-run", round_id="round_2", tests=("all",)))
        path = tmp_path / "my-run_round_2_stats.json"
        data = json.loads(path.read_text())
        assert data["run_id"] == "my-run"
        assert data["round_id"] == "round_2"


# ---------------------------------------------------------------------------
# f) interaction_significant derivado dos MLMReports
# ---------------------------------------------------------------------------


class TestInteractionSignificant:
    """Campo interaction_significant derivado de MLMReport.interaction_p_value."""

    def test_significant_when_interaction_p_below_alpha(self, tmp_path: Path) -> None:
        uc, _, _, _, _ = _make_use_case(
            wilcoxon_returns=[_make_wilcoxon(0.5)],
            friedman_returns=[_make_friedman(0.5)],
            mlm_returns=[_make_mlm(interaction_p=0.02)],
            data_dir=tmp_path,
        )
        report = uc.execute(
            StatisticsInput(run_id=_RUN_ID, round_id=_ROUND_ID, tests=("all",))
        )
        assert report.interaction_significant is True

    def test_not_significant_when_interaction_p_above_alpha(
        self, tmp_path: Path
    ) -> None:
        uc, _, _, _, _ = _make_use_case(
            wilcoxon_returns=[_make_wilcoxon(0.5)],
            friedman_returns=[_make_friedman(0.5)],
            mlm_returns=[_make_mlm(interaction_p=0.3)],
            data_dir=tmp_path,
        )
        report = uc.execute(
            StatisticsInput(run_id=_RUN_ID, round_id=_ROUND_ID, tests=("all",))
        )
        assert report.interaction_significant is False

    def test_nan_interaction_p_yields_false(self, tmp_path: Path) -> None:
        uc, _, _, _, _ = _make_use_case(
            wilcoxon_returns=[_make_wilcoxon(0.5)],
            friedman_returns=[_make_friedman(0.5)],
            mlm_returns=[_make_mlm(interaction_p=float("nan"))],
            data_dir=tmp_path,
        )
        report = uc.execute(
            StatisticsInput(run_id=_RUN_ID, round_id=_ROUND_ID, tests=("all",))
        )
        assert report.interaction_significant is False


# ---------------------------------------------------------------------------
# h) Correção Holm funcional
# ---------------------------------------------------------------------------


class TestHolmCorrection:
    def test_holm_correction_applied(self, tmp_path: Path) -> None:
        uc, _, _, _, _ = _make_use_case(
            wilcoxon_returns=[_make_wilcoxon(0.01)],
            friedman_returns=[_make_friedman(0.5)],
            mlm_returns=[_make_mlm()],
            data_dir=tmp_path,
        )
        report = uc.execute(
            StatisticsInput(
                run_id=_RUN_ID,
                round_id=_ROUND_ID,
                tests=("all",),
                correction_method="holm",
            )
        )
        # Com n=2 p-values [0.01, 0.5] e Holm:
        # sorted: [0.01@rank0, 0.5@rank1]
        # adjusted: [0.01*(2-0)=0.02, 0.5*(2-1)=0.5]
        # After cummax: [0.02, 0.5]
        # p_corrected do wilcoxon = 0.02 < 0.05 → significant
        assert report.wilcoxon_reports[0].p_value_corrected == pytest.approx(
            0.02, abs=1e-8
        )
        assert report.wilcoxon_reports[0].significant is True


# ---------------------------------------------------------------------------
# i) Todos p-values NaN — não falha, relatorio vazio
# ---------------------------------------------------------------------------


class TestAllNaNPValues:
    def test_all_nan_p_values_no_correction_needed(self, tmp_path: Path) -> None:
        nan_w = WilcoxonReport(
            metric="final_score",
            base_a="IDx_400k",
            base_b="ID_230K",
            statistic=0.0,
            p_value=float("nan"),
            p_value_corrected=None,
            significant=False,
            n_pairs=0,
            effect_size_r=None,
        )
        uc, _, w, _f, _m = _make_use_case(data_dir=tmp_path)
        w.wilcoxon_paired.return_value = nan_w
        # Should not raise
        report = uc.execute(
            StatisticsInput(run_id=_RUN_ID, round_id=_ROUND_ID, tests=("wilcoxon",))
        )
        assert report.base_difference_significant is False


# ---------------------------------------------------------------------------
# j) Reader chamado com parâmetros corretos (fase "A" e run_id)
# ---------------------------------------------------------------------------


class TestReaderCalled:
    def test_reader_called_with_phase_a_and_run_id(self, tmp_path: Path) -> None:
        uc, reader, _, _, _ = _make_use_case(data_dir=tmp_path)
        uc.execute(
            StatisticsInput(
                run_id="specific-run",
                round_id="round_1",
                tests=("wilcoxon",),
            )
        )
        reader.load.assert_called_once_with(
            round_id="round_1",
            phase="A",
            run_id="specific-run",
        )

    def test_mlm_formula_contains_metric_name(self, tmp_path: Path) -> None:
        uc, _, _, _, m = _make_use_case(data_dir=tmp_path)
        uc.execute(
            StatisticsInput(
                run_id=_RUN_ID,
                round_id=_ROUND_ID,
                metrics=("bertscore_f1",),
                tests=("mlm",),
            )
        )
        formula_used = m.mixed_linear_model.call_args[0][1]
        assert formula_used == "bertscore_f1 ~ base * llm + (1 | question_id)"


# ---------------------------------------------------------------------------
# k) StatsReport é um VO imutável (frozen)
# ---------------------------------------------------------------------------


class TestStatsReportImmutable:
    def test_stats_report_is_frozen(self, tmp_path: Path) -> None:
        uc, _, _, _, _ = _make_use_case(data_dir=tmp_path)
        report = uc.execute(
            StatisticsInput(run_id=_RUN_ID, round_id=_ROUND_ID, tests=("all",))
        )
        assert isinstance(report, StatsReport)
        with pytest.raises((AttributeError, TypeError)):
            report.run_id = "modified"  # type: ignore[misc]
