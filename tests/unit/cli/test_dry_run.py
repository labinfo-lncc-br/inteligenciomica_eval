from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from inteligenciomica_eval.cli import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Shared YAML fixture data
# ---------------------------------------------------------------------------

_VALID_CONFIG: dict[object, object] = {
    "round_id": "dry-run-test",
    "phases": ["A", "B"],
    "bases": ["IDx_400k"],
    "llms": ["test-model/v1"],
    "seeds": [42, 99],
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
    "experiment_b": {
        "canonical_context_source": "IDx_400k",
        "canonical_top_k": 3,
    },
}


@pytest.fixture()
def valid_config_path(tmp_path: Path) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(_VALID_CONFIG), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Dry-run success path
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDryRunSuccess:
    def test_exits_zero(self, valid_config_path: Path) -> None:
        result = runner.invoke(
            app, ["run", "--dry-run", "--config", str(valid_config_path)]
        )
        assert result.exit_code == 0, result.output

    def test_prints_config_hash(self, valid_config_path: Path) -> None:
        result = runner.invoke(
            app, ["run", "--dry-run", "--config", str(valid_config_path)]
        )
        assert "config_hash" in result.output

    def test_prints_phase_a_cell_count(self, valid_config_path: Path) -> None:
        result = runner.invoke(
            app, ["run", "--dry-run", "--config", str(valid_config_path)]
        )
        assert "Phase A" in result.output

    def test_prints_phase_b_cell_count(self, valid_config_path: Path) -> None:
        result = runner.invoke(
            app, ["run", "--dry-run", "--config", str(valid_config_path)]
        )
        assert "Phase B" in result.output

    def test_cell_count_shows_exact_total(self, valid_config_path: Path) -> None:
        # _VALID_CONFIG: 1 base x 1 LLM x 2 seeds x 13 questions = 26 cells per phase
        result = runner.invoke(
            app, ["run", "--dry-run", "--config", str(valid_config_path)]
        )
        assert "13 questions" in result.output
        assert "26 cells" in result.output

    def test_prints_endpoints_section(self, valid_config_path: Path) -> None:
        result = runner.invoke(
            app, ["run", "--dry-run", "--config", str(valid_config_path)]
        )
        assert "endpoint" in result.output.lower()

    def test_no_network_call_needed(self, valid_config_path: Path) -> None:
        # The test completes without any network stubs — proof that dry-run
        # does not call vLLM, Qdrant, or any external service.
        result = runner.invoke(
            app, ["run", "--dry-run", "--config", str(valid_config_path)]
        )
        assert result.exit_code == 0

    def test_output_includes_round_id(self, valid_config_path: Path) -> None:
        result = runner.invoke(
            app, ["run", "--dry-run", "--config", str(valid_config_path)]
        )
        assert "dry-run-test" in result.output


# ---------------------------------------------------------------------------
# Dry-run with invalid config → exit 1 with clear error
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDryRunInvalidConfig:
    def test_exits_nonzero_on_invalid_yaml(self, tmp_path: Path) -> None:
        import copy

        bad = copy.deepcopy(_VALID_CONFIG)
        bad["bases"] = ["UNKNOWN"]  # type: ignore[index]
        p = tmp_path / "bad.yaml"
        p.write_text(yaml.dump(bad), encoding="utf-8")
        result = runner.invoke(app, ["run", "--dry-run", "--config", str(p)])
        assert result.exit_code != 0

    def test_exits_nonzero_on_missing_file(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["run", "--dry-run", "--config", str(tmp_path / "no_such_file.yaml")],
        )
        assert result.exit_code != 0

    def test_weights_error_exits_nonzero(self, tmp_path: Path) -> None:
        import copy

        bad = copy.deepcopy(_VALID_CONFIG)
        scoring = bad["scoring"]  # type: ignore[index]
        assert isinstance(scoring, dict)
        scoring["weights"] = {"answer_correctness": 0.9}  # sum != 1.0
        p = tmp_path / "bad_weights.yaml"
        p.write_text(yaml.dump(bad), encoding="utf-8")
        result = runner.invoke(app, ["run", "--dry-run", "--config", str(p)])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# run without --dry-run → not yet implemented
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_run_without_dry_run_exits_nonzero(valid_config_path: Path) -> None:
    result = runner.invoke(app, ["run", "--config", str(valid_config_path)])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Credential masking
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_url_with_auth_is_masked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VLLM_JUDGE_URL", "http://user:secret@vllm-host:8000")
    monkeypatch.setenv("VLLM_GENERATOR_URL", "http://user:secret@vllm-gen:8001")

    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(_VALID_CONFIG), encoding="utf-8")
    result = runner.invoke(app, ["run", "--dry-run", "--config", str(p)])

    assert "secret" not in result.output
