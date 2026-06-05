"""Testes unitários do CLI run em server_mode='external' (TAREFA-311, ADR-014)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from inteligenciomica_eval.cli import app

_runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixture de config YAML com server_mode=external
# ---------------------------------------------------------------------------

_EXTERNAL_CONFIG: dict[str, Any] = {
    "round_id": "cli-ext-test",
    "phases": ["A"],
    "bases": ["IDx_400k"],
    "llms": ["stub-gen"],
    "seeds": [42],
    "temperature": 0.0,
    "retrieval": {
        "top_k": 3,
        "embedding_model": "em",
        "chunk_strategy": "sentence",
    },
    "judge": {
        "model": "stub-judge",
        "endpoint_env": "VLLM_JUDGE_URL",
        "batch_invariant": True,
        "temperature": 0.0,
    },
    "scoring": {
        "weights": {"answer_correctness": 0.6, "faithfulness": 0.4},
        "failure_threshold": 0.3,
    },
    "server_mode": "external",
}


@pytest.fixture()
def external_config_path(tmp_path: Path) -> Path:
    p = tmp_path / "ext_config.yaml"
    p.write_text(yaml.dump(_EXTERNAL_CONFIG), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Testes da flag --require-verified-determinism na CLI
# ---------------------------------------------------------------------------


def test_run_external_require_determinism_exits_1_when_probe_fails(
    external_config_path: Path,
) -> None:
    """--require-verified-determinism com probe False → exit 1."""
    with (
        patch(
            "inteligenciomica_eval.cli.build_container",
            return_value=MagicMock(benchmark_loader=lambda: []),
        ),
        patch(
            "inteligenciomica_eval.cli._run_external_probes",
            side_effect=SystemExit(1),
        ),
    ):
        result = _runner.invoke(
            app,
            [
                "run",
                "--config",
                str(external_config_path),
                "--run-id",
                "test-run",
                "--require-verified-determinism",
            ],
        )

    assert result.exit_code == 1


def test_run_external_no_require_determinism_continues(
    external_config_path: Path,
    tmp_path: Path,
) -> None:
    """--no-require-verified-determinism não falha mesmo com probe False."""
    # Mocka build_container + experiment_uc.execute para simular run completo
    mock_report = MagicMock()
    mock_report.n_generated = 0
    mock_report.n_evaluated = 0
    mock_report.n_judged = 0
    mock_report.n_cells_total = 0
    mock_report.duration_s = 0.0
    mock_report.run_id = "test-run"
    mock_report.aggregates = ()
    mock_report.rank_scores = ()
    mock_report.failed_waves = ()

    mock_container = MagicMock()
    mock_container.benchmark_loader = lambda: []
    mock_container.experiment_uc.execute = AsyncMock(return_value=mock_report)

    with (
        patch(
            "inteligenciomica_eval.cli.build_container",
            return_value=mock_container,
        ),
        patch(
            "inteligenciomica_eval.cli._run_external_probes",
        ),
        patch.dict(
            os.environ,
            {
                "VLLM_GENERATOR_URL": "http://localhost:8000/v1",
                "VLLM_JUDGE_URL": "http://localhost:8003/v1",
                "QDRANT_URL": "http://localhost:6333",
            },
        ),
    ):
        result = _runner.invoke(
            app,
            [
                "run",
                "--config",
                str(external_config_path),
                "--run-id",
                "test-run",
                "--no-require-verified-determinism",
            ],
        )

    # Sem --require-verified-determinism, não deve falhar por probe
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Testes de _run_external_probes diretamente
# ---------------------------------------------------------------------------


def _make_asyncio_run_mock(return_value: Any) -> Any:
    """Cria side_effect para asyncio.run que fecha a coroutine antes de retornar.

    Quando asyncio.run é mockado com return_value, a coroutine criada internamente
    nunca é fechada → RuntimeWarning. Usar side_effect que fecha explicitamente.
    """
    import inspect

    def _side_effect(coro: Any) -> Any:
        if inspect.iscoroutine(coro):
            coro.close()
        return return_value

    return _side_effect


def test_run_external_probes_exits_1_when_require_determinism_and_probe_false(
    external_config_path: Path,
) -> None:
    """_run_external_probes levanta typer.Exit(1) quando determinismo não verificado."""
    import typer

    from inteligenciomica_eval.cli import _run_external_probes
    from inteligenciomica_eval.infrastructure.config.schema import load_round_config
    from inteligenciomica_eval.infrastructure.config.settings import RuntimeSettings

    cfg = load_round_config(external_config_path)
    settings = RuntimeSettings()

    with patch("inteligenciomica_eval.cli.asyncio.run") as mock_run:
        mock_run.side_effect = _make_asyncio_run_mock(
            ({}, None, False)  # (model_ids, judge_version, judge_deterministic)
        )

        with pytest.raises((typer.Exit, SystemExit)) as exc_info:
            _run_external_probes(
                cfg=cfg,
                settings=settings,
                require_verified_determinism=True,
            )

    # Verifica que saiu com código 1
    exc = exc_info.value
    if isinstance(exc, typer.Exit):
        assert exc.exit_code == 1
    else:
        assert exc.code == 1


def test_run_external_probes_does_not_exit_when_probe_true(
    external_config_path: Path,
) -> None:
    """_run_external_probes não levanta Exit quando judge_deterministic=True."""
    from inteligenciomica_eval.cli import _run_external_probes
    from inteligenciomica_eval.infrastructure.config.schema import load_round_config
    from inteligenciomica_eval.infrastructure.config.settings import RuntimeSettings

    cfg = load_round_config(external_config_path)
    settings = RuntimeSettings()

    with patch("inteligenciomica_eval.cli.asyncio.run") as mock_run:
        mock_run.side_effect = _make_asyncio_run_mock(
            ({"stub-gen": "gen-model-id"}, "0.4.3", True)  # judge_deterministic=True
        )
        # Não deve levantar exceção
        _run_external_probes(
            cfg=cfg,
            settings=settings,
            require_verified_determinism=True,
        )


def test_run_external_probes_no_require_does_not_exit_even_if_probe_false(
    external_config_path: Path,
) -> None:
    """Com require_verified_determinism=False, não sai mesmo com probe False."""
    from inteligenciomica_eval.cli import _run_external_probes
    from inteligenciomica_eval.infrastructure.config.schema import load_round_config
    from inteligenciomica_eval.infrastructure.config.settings import RuntimeSettings

    cfg = load_round_config(external_config_path)
    settings = RuntimeSettings()

    with patch("inteligenciomica_eval.cli.asyncio.run") as mock_run:
        mock_run.side_effect = _make_asyncio_run_mock(({}, None, False))
        # Não deve levantar exceção com require_verified_determinism=False
        _run_external_probes(
            cfg=cfg,
            settings=settings,
            require_verified_determinism=False,
        )
