from __future__ import annotations

import pytest
import yaml
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from inteligenciomica_eval.cli import app, main

runner = CliRunner()


@pytest.mark.unit
class TestCLISmoke:
    """Smoke tests for the CLI entry point."""

    def test_help_exits_zero(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    def test_help_output_mentions_package(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert "ielm-eval" in result.output or "InteligenciÔmica" in result.output

    def test_version_command_exits_zero(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0

    def test_version_output_contains_package_name(self) -> None:
        result = runner.invoke(app, ["version"])
        assert "inteligenciomica-eval" in result.output

    def test_keyboard_interrupt_exits_with_code_130(
        self, mocker: MockerFixture
    ) -> None:
        """KeyboardInterrupt during app execution exits with POSIX signal code 130."""
        mocker.patch("inteligenciomica_eval.cli.app", side_effect=KeyboardInterrupt)
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 130


# ---------------------------------------------------------------------------
# run --dry-run — validação de generation_prompt_version (TAREFA-316)
# ---------------------------------------------------------------------------

_BASE_RUN_CFG: dict[str, object] = {
    "round_id": "cli-test-round",
    "phases": ["A"],
    "bases": ["IDx_400k"],
    "llms": ["model-a"],
    "seeds": [42],
    "temperature": 0.0,
    "retrieval": {
        "top_k": 3,
        "reranker": None,
        "embedding_model": "e-v1",
        "chunk_strategy": "sliding",
    },
    "judge": {
        "model": "judge",
        "endpoint_env": "VLLM_JUDGE_URL",
        "batch_invariant": True,
        "temperature": 0.0,
    },
    "scoring": {
        "weights": {"answer_correctness": 0.6, "faithfulness": 0.4},
        "failure_threshold": 0.3,
    },
}


@pytest.mark.unit
class TestRunDryRunPromptVersion:
    """CLI run --dry-run deve rejeitar generation_prompt_version inválido."""

    def test_invalid_generation_prompt_version_exits_nonzero(
        self, tmp_path: object
    ) -> None:
        """Versão de prompt inexistente → exit 1 antes de qualquer I/O."""
        cfg = {**_BASE_RUN_CFG, "generation_prompt_version": "v99_does_not_exist"}
        p = tmp_path / "config.yaml"  # type: ignore[operator]
        p.write_text(yaml.dump(cfg), encoding="utf-8")

        result = runner.invoke(app, ["run", "--config", str(p), "--dry-run"])

        assert result.exit_code != 0

    def test_invalid_version_error_message_cites_version(
        self, tmp_path: object
    ) -> None:
        """A mensagem de erro deve citar a versão inválida (facilita diagnóstico)."""
        cfg = {**_BASE_RUN_CFG, "generation_prompt_version": "v99_does_not_exist"}
        p = tmp_path / "config.yaml"  # type: ignore[operator]
        p.write_text(yaml.dump(cfg), encoding="utf-8")

        result = runner.invoke(app, ["run", "--config", str(p), "--dry-run"])

        # CliRunner captura stdout+stderr em result.output
        assert (
            "v99_does_not_exist" in result.output
            or "generation_prompt_version" in result.output
        )

    def test_valid_generation_prompt_version_passes_dry_run(
        self, tmp_path: object
    ) -> None:
        """Versão v1_production (bundle real) não deve causar exit por validação."""
        cfg = {**_BASE_RUN_CFG, "generation_prompt_version": "v1_production"}
        p = tmp_path / "config.yaml"  # type: ignore[operator]
        p.write_text(yaml.dump(cfg), encoding="utf-8")

        result = runner.invoke(app, ["run", "--config", str(p), "--dry-run"])

        # Pode falhar por razões de wiring (fakes/registry ausentes) mas NÃO por
        # generation_prompt_version — a saída não deve mencionar esse campo como erro.
        if result.exit_code != 0:
            assert "generation_prompt_version" not in result.output
