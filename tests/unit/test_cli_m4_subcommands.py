"""Testes unitários dos subcomandos analyze, report, status, show-config (TAREFA-408)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from inteligenciomica_eval.cli import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixtures de configuração YAML mínimos
# ---------------------------------------------------------------------------

_ROUND_ID = "round_408"
_RUN_ID = "run-408-test"

_VALID_CONFIG: dict[object, object] = {
    "round_id": _ROUND_ID,
    "phases": ["A"],
    "bases": ["IDx_400k"],
    "llms": ["llama3-8b"],
    "seeds": [42],
    "temperature": 0.0,
    "retrieval": {
        "top_k": 3,
        "reranker": None,
        "embedding_model": "text-embedding-ada-002",
        "chunk_strategy": "fixed_512",
    },
    "judge": {
        "model": "prometheus-eval/prometheus-8x7b-v2.0",
        "endpoint_env": "VLLM_JUDGE_URL",
        "batch_invariant": True,
        "temperature": 0.0,
        "seed": 42,
    },
    "scoring": {
        "failure_threshold": 0.5,
        "weights": {
            "answer_correctness": 0.2,
            "answer_similarity": 0.1,
            "faithfulness": 0.15,
            "context_precision": 0.1,
            "context_recall": 0.1,
            "answer_relevancy": 0.1,
            "bertscore_f1": 0.1,
            "rubric_biomed_score": 0.15,
        },
    },
    "model_registry_path": "model_registry.yaml",
}

_INVALID_CONFIG: dict[object, object] = {
    "round_id": "",  # vazio → ConfigValidationError
}


def _write_config(tmp_path: Path, content: dict[object, object]) -> Path:
    p = tmp_path / "round_config.yaml"
    p.write_text(yaml.dump(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# (a) --help de cada subcomando: exit_code=0
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHelpExitsZero:
    """Todos os 4 subcomandos devem responder --help com exit_code=0."""

    def test_analyze_help(self) -> None:
        result = runner.invoke(app, ["analyze", "--help"])
        assert result.exit_code == 0

    def test_report_help(self) -> None:
        result = runner.invoke(app, ["report", "--help"])
        assert result.exit_code == 0

    def test_status_help(self) -> None:
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0

    def test_show_config_help(self) -> None:
        result = runner.invoke(app, ["show-config", "--help"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# (b) status --run-id inexistente: exit_code=0, sem traceback
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStatusRunIdInexistente:
    """status com run_id inexistente deve sair com exit_code=0 sem traceback."""

    def test_missing_run_id_exits_zero(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, _VALID_CONFIG)
        result = runner.invoke(
            app,
            [
                "status",
                "--run-id",
                "run-nao-existe-99999",
                "--config",
                str(config_path),
            ],
        )
        assert result.exit_code == 0, (
            f"Esperado exit_code=0, obtido {result.exit_code}.\nOutput:\n{result.output}"
        )
        # Garante que não há traceback (stack trace Python)
        assert "Traceback" not in (result.output or ""), (
            "Saída contém traceback Python — não permitido para run_id inexistente"
        )

    def test_missing_config_exits_zero(self, tmp_path: Path) -> None:
        """Config ausente também deve sair com 0 (mensagem amigável)."""
        result = runner.invoke(
            app,
            [
                "status",
                "--run-id",
                "qualquer",
                "--config",
                str(tmp_path / "nao_existe.yaml"),
            ],
        )
        assert result.exit_code == 0
        assert "Traceback" not in (result.output or "")


# ---------------------------------------------------------------------------
# (c) show-config --config valid.yaml: exit_code=0
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestShowConfigValid:
    """show-config com YAML válido deve sair com exit_code=0."""

    def test_valid_config_exits_zero(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, _VALID_CONFIG)
        result = runner.invoke(
            app,
            ["show-config", "--config", str(config_path)],
        )
        assert result.exit_code == 0, (
            f"Esperado exit_code=0, obtido {result.exit_code}.\nOutput:\n{result.output}"
        )

    def test_valid_config_prints_content(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, _VALID_CONFIG)
        result = runner.invoke(
            app,
            ["show-config", "--config", str(config_path)],
        )
        # A saída deve conter o round_id
        assert _ROUND_ID in result.output


# ---------------------------------------------------------------------------
# (d) show-config --config invalid.yaml: exit_code=1, mensagem amigável
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestShowConfigInvalid:
    """show-config com YAML inválido deve sair com exit_code=1 e mensagem amigável."""

    def test_invalid_config_exits_one(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, _INVALID_CONFIG)
        result = runner.invoke(
            app,
            ["show-config", "--config", str(config_path)],
        )
        assert result.exit_code == 1, (
            f"Esperado exit_code=1, obtido {result.exit_code}.\nOutput:\n{result.output}"
        )

    def test_invalid_config_no_traceback(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, _INVALID_CONFIG)
        result = runner.invoke(
            app,
            ["show-config", "--config", str(config_path)],
        )
        assert "Traceback" not in (result.output or ""), (
            "Saída contém traceback — deve exibir mensagem amigável"
        )

    def test_missing_config_file_exits_one(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["show-config", "--config", str(tmp_path / "nao_existe.yaml")],
        )
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# (e) report --format pdf: exit_code=0, mensagem informativa (sem crash)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReportFormatPdf:
    """report --format pdf deve retornar exit_code=0 com mensagem de 'versão futura'."""

    def test_pdf_format_exits_zero(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, _VALID_CONFIG)
        result = runner.invoke(
            app,
            [
                "report",
                "--run-id",
                _RUN_ID,
                "--config",
                str(config_path),
                "--format",
                "pdf",
                "--output-dir",
                str(tmp_path / "out"),
            ],
        )
        assert result.exit_code == 0, (
            f"Esperado exit_code=0 para --format pdf, obtido {result.exit_code}.\n"
            f"Output:\n{result.output}"
        )

    def test_pdf_format_prints_friendly_message(self, tmp_path: Path) -> None:
        config_path = _write_config(tmp_path, _VALID_CONFIG)
        result = runner.invoke(
            app,
            [
                "report",
                "--run-id",
                _RUN_ID,
                "--config",
                str(config_path),
                "--format",
                "pdf",
                "--output-dir",
                str(tmp_path / "out"),
            ],
        )
        # Deve mencionar "futura" ou similar
        assert "futur" in result.output.lower(), (
            f"Mensagem amigável sobre PDF não encontrada. Output:\n{result.output}"
        )
        assert "Traceback" not in (result.output or "")
