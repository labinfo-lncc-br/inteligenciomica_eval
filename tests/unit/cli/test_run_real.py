"""Testes unitários para o comando `ielm-eval run` com execução real e dry-run (TAREFA-309)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from inteligenciomica_eval.cli import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Fixture de config YAML válido
# ---------------------------------------------------------------------------

_VALID_CONFIG: dict[object, object] = {
    "round_id": "run-real-test",
    "phases": ["A"],
    "bases": ["IDx_400k"],
    "llms": ["stub-gen-a"],
    "seeds": [42],
    "temperature": 0.0,
    "retrieval": {
        "top_k": 3,
        "reranker": None,
        "embedding_model": "embed-v1",
        "chunk_strategy": "sliding",
    },
    "judge": {
        "model": "judge-model",
        "endpoint_env": "VLLM_JUDGE_URL",
        "batch_invariant": True,
        "temperature": 0.0,
    },
    "scoring": {
        "weights": {"answer_correctness": 0.6, "faithfulness": 0.4},
        "failure_threshold": 0.3,
    },
}


@pytest.fixture()
def valid_config_path(tmp_path: Path) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(_VALID_CONFIG), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


class TestRunWithFakeContainerSucceeds:
    """Run real com build_container substituído por build_fake_container."""

    def test_run_succeeds_with_fake_container(self, valid_config_path: Path) -> None:
        from inteligenciomica_eval.application.services.wave_scheduler import WavePlan
        from inteligenciomica_eval.application.use_cases.run_experiment import (
            ExperimentReport,
        )

        fake_report = ExperimentReport(
            run_id="test-run",
            config_hash="abc12345",
            wave_plan=WavePlan(waves=(), total_cells=0, estimated_vram_peak_gb=0.0),
            n_generated=0,
            n_evaluated=0,
            n_judged=0,
            n_cells_total=0,
            aggregates=(),
            rank_scores=(),
            duration_s=0.1,
            failed_waves=(),
        )

        async def _fake_execute(**kwargs: object) -> ExperimentReport:
            return fake_report

        from inteligenciomica_eval.infrastructure.wiring import (
            build_fake_container as _bfc,
        )

        def _patched_build_container(
            cfg: object, settings: object, **kwargs: object
        ) -> object:
            container = _bfc(cfg)  # type: ignore[arg-type]
            # Substituir o experiment_uc por um mock determinístico
            mock_uc = MagicMock()
            mock_uc.execute = AsyncMock(return_value=fake_report)
            mock_uc._shutdown_requested = False
            import dataclasses

            return dataclasses.replace(container, experiment_uc=mock_uc)

        with patch(
            "inteligenciomica_eval.infrastructure.wiring.build_container",
            side_effect=_patched_build_container,
        ):
            result = runner.invoke(
                app,
                ["run", "--config", str(valid_config_path), "--run-id", "test-run"],
            )

        assert result.exit_code == 0, result.output + (result.stderr or "")


class TestRunMissingEnvVarExits1:
    """Env var ausente → exit code 1 sem stacktrace no stdout."""

    def test_missing_env_var_exits_1(self, valid_config_path: Path) -> None:
        from inteligenciomica_eval.domain.errors import ConfigValidationError

        def _raise_config_error(
            cfg: object, settings: object, **kwargs: object
        ) -> object:
            raise ConfigValidationError(
                "VLLM_GENERATOR_URL",
                "Variável de ambiente obrigatória não configurada: VLLM_GENERATOR_URL.",
            )

        with patch(
            "inteligenciomica_eval.infrastructure.wiring.build_container",
            side_effect=_raise_config_error,
        ):
            result = runner.invoke(
                app,
                ["run", "--config", str(valid_config_path), "--run-id", "test-run"],
            )

        assert result.exit_code == 1
        # Stacktrace NÃO deve aparecer no stdout
        assert "Traceback" not in result.output
        assert "Traceback" not in (result.stderr or "")

    def test_error_message_is_friendly(self, valid_config_path: Path) -> None:
        from inteligenciomica_eval.domain.errors import ConfigValidationError

        def _raise_config_error(
            cfg: object, settings: object, **kwargs: object
        ) -> object:
            raise ConfigValidationError(
                "VLLM_GENERATOR_URL",
                "Variável de ambiente obrigatória não configurada: VLLM_GENERATOR_URL.",
            )

        with patch(
            "inteligenciomica_eval.infrastructure.wiring.build_container",
            side_effect=_raise_config_error,
        ):
            result = runner.invoke(
                app,
                ["run", "--config", str(valid_config_path), "--run-id", "test-run"],
            )

        # Mensagem amigável deve estar presente
        combined = result.output + (result.stderr or "")
        assert "VLLM_GENERATOR_URL" in combined or "configuração" in combined.lower()


class TestRunKeyboardInterruptExits130:
    """KeyboardInterrupt → exit code 130 + mensagem amigável."""

    def test_keyboard_interrupt_exits_130(self, valid_config_path: Path) -> None:
        from inteligenciomica_eval.infrastructure.wiring import (
            build_fake_container as _bfc,
        )

        def _patched_build_container(
            cfg: object, settings: object, **kwargs: object
        ) -> object:
            container = _bfc(cfg)  # type: ignore[arg-type]
            mock_uc = MagicMock()
            mock_uc.execute = AsyncMock(side_effect=KeyboardInterrupt())
            mock_uc._shutdown_requested = False
            import dataclasses

            return dataclasses.replace(container, experiment_uc=mock_uc)

        with patch(
            "inteligenciomica_eval.infrastructure.wiring.build_container",
            side_effect=_patched_build_container,
        ):
            result = runner.invoke(
                app,
                ["run", "--config", str(valid_config_path), "--run-id", "test-run"],
            )

        assert result.exit_code == 130
        combined = result.output + (result.stderr or "")
        assert "Encerramento" in combined or "Interrupted" in combined


class TestDryRunShowsQuestionCount:
    """--dry-run exibe contagem de perguntas carregadas."""

    def test_dry_run_shows_question_count(self, valid_config_path: Path) -> None:
        result = runner.invoke(
            app,
            ["run", "--config", str(valid_config_path), "--dry-run"],
        )

        assert result.exit_code == 0, result.output + (result.stderr or "")
        assert "Perguntas carregadas:" in result.output

    def test_dry_run_no_run_id_required(self, valid_config_path: Path) -> None:
        # --dry-run não exige --run-id
        result = runner.invoke(
            app,
            ["run", "--config", str(valid_config_path), "--dry-run"],
        )
        assert result.exit_code == 0

    def test_run_without_run_id_exits_1(self, valid_config_path: Path) -> None:
        # Execução real sem --run-id → exit 1
        from inteligenciomica_eval.infrastructure.wiring import (
            build_fake_container as _bfc,
        )

        with patch(
            "inteligenciomica_eval.infrastructure.wiring.build_container",
            side_effect=lambda *a, **k: _bfc(a[0]),
        ):
            result = runner.invoke(
                app,
                ["run", "--config", str(valid_config_path)],
            )
        assert result.exit_code == 1
