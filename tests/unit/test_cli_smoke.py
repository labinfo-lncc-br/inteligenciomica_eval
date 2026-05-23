from __future__ import annotations

import pytest
from typer.testing import CliRunner

from inteligenciomica_eval.cli import app

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
