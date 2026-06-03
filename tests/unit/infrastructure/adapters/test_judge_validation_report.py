"""Testes unitários de JudgeValidationReportAdapter (TAREFA-602)."""

from __future__ import annotations

from pathlib import Path

import pytest

from inteligenciomica_eval.application.judge_validation import JudgeValidationResult
from inteligenciomica_eval.infrastructure.adapters.judge_validation_report_adapter import (
    JudgeValidationReportAdapter,
)


def _make_result(
    *,
    kappa: float = 0.5,
    interpretation: str = "moderada",
    n_total: int = 20,
    n_annotated: int = 20,
    n_valid: int = 20,
    n_excluded_nan: int = 0,
    threshold: float = 0.50,
    judge_model: str = "prometheus-v2",
    batch_invariant_confirmed: bool = True,
    discordances: list | None = None,
) -> JudgeValidationResult:
    return JudgeValidationResult(
        n_total=n_total,
        n_annotated=n_annotated,
        n_valid=n_valid,
        n_excluded_nan=n_excluded_nan,
        cohen_kappa=kappa,
        kappa_interpretation=interpretation,  # type: ignore[arg-type]
        confusion_matrix={"TP": 8, "TN": 7, "FP": 3, "FN": 2},
        binarization_threshold=threshold,
        judge_model=judge_model,
        batch_invariant_confirmed=batch_invariant_confirmed,
        discordances=discordances or [],
    )


@pytest.fixture()
def adapter() -> JudgeValidationReportAdapter:
    return JudgeValidationReportAdapter()


class TestReportContent:
    def test_contains_kappa_value(
        self, adapter: JudgeValidationReportAdapter, tmp_path: Path
    ) -> None:
        result = _make_result(kappa=0.5)
        path = tmp_path / "report.md"
        adapter.generate_report(result, path, run_id="run-1", round_id="R1")
        content = path.read_text()
        assert "0.5" in content

    def test_contains_interpretation(
        self, adapter: JudgeValidationReportAdapter, tmp_path: Path
    ) -> None:
        result = _make_result(kappa=0.5, interpretation="moderada")
        path = tmp_path / "report.md"
        adapter.generate_report(result, path, run_id="run-1", round_id="R1")
        content = path.read_text()
        assert "moderada" in content

    def test_contains_threshold(
        self, adapter: JudgeValidationReportAdapter, tmp_path: Path
    ) -> None:
        result = _make_result(threshold=0.50)
        path = tmp_path / "report.md"
        adapter.generate_report(result, path, run_id="run-1", round_id="R1")
        content = path.read_text()
        assert "0.5" in content

    def test_contains_n_valid(
        self, adapter: JudgeValidationReportAdapter, tmp_path: Path
    ) -> None:
        result = _make_result(n_valid=18)
        path = tmp_path / "report.md"
        adapter.generate_report(result, path, run_id="run-1", round_id="R1")
        content = path.read_text()
        assert "18" in content

    def test_contains_n_excluded_nan(
        self, adapter: JudgeValidationReportAdapter, tmp_path: Path
    ) -> None:
        result = _make_result(n_excluded_nan=3)
        path = tmp_path / "report.md"
        adapter.generate_report(result, path, run_id="run-1", round_id="R1")
        content = path.read_text()
        assert "3" in content

    def test_is_markdown(
        self, adapter: JudgeValidationReportAdapter, tmp_path: Path
    ) -> None:
        result = _make_result()
        path = tmp_path / "report.md"
        adapter.generate_report(result, path, run_id="run-1", round_id="R1")
        content = path.read_text()
        assert content.startswith("#")
        assert "|" in content  # tabela Markdown

    def test_confusion_matrix_present(
        self, adapter: JudgeValidationReportAdapter, tmp_path: Path
    ) -> None:
        result = _make_result()
        path = tmp_path / "report.md"
        adapter.generate_report(result, path, run_id="run-1", round_id="R1")
        content = path.read_text()
        assert (
            "TP" in content and "TN" in content and "FP" in content and "FN" in content
        )


class TestAllInterpretationBranches:
    """Garante que os 5 ramos de interpretação de κ estão cobertos no template."""

    @pytest.mark.parametrize(
        "kappa,interpretation,expected_text",
        [
            (0.85, "quase-perfeita", "quase-perfeita"),
            (0.70, "substancial", "substancial"),
            (0.50, "moderada", "moderada"),
            (0.30, "razoável", "razoável"),
            (0.10, "fraca", "fraca"),
        ],
    )
    def test_branch(
        self,
        adapter: JudgeValidationReportAdapter,
        tmp_path: Path,
        kappa: float,
        interpretation: str,
        expected_text: str,
    ) -> None:
        result = _make_result(kappa=kappa, interpretation=interpretation)
        path = tmp_path / f"report_{interpretation}.md"
        adapter.generate_report(result, path, run_id="run-1", round_id="R1")
        content = path.read_text()
        assert expected_text in content


class TestDiscordancesTable:
    def test_discordances_shown(
        self, adapter: JudgeValidationReportAdapter, tmp_path: Path
    ) -> None:
        discordances = [
            {
                "row_id": "abc123",
                "rubric_biomed_score": 0.3,
                "judge_binary": 1,
                "critical_failure_flag": 0,
            },
        ]
        result = _make_result(discordances=discordances)
        path = tmp_path / "report.md"
        adapter.generate_report(result, path, run_id="run-1", round_id="R1")
        content = path.read_text()
        assert "abc123" in content

    def test_no_discordances_message(
        self, adapter: JudgeValidationReportAdapter, tmp_path: Path
    ) -> None:
        result = _make_result(discordances=[])
        path = tmp_path / "report.md"
        adapter.generate_report(result, path, run_id="run-1", round_id="R1")
        content = path.read_text()
        assert "Nenhuma discordância" in content
