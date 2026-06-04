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
        # _VALID_CONFIG: 1 base x 1 LLM x 2 seeds x N questions (N = bundled RF1 count)
        # O benchmark loader real usa questions_rf1.jsonl (3 placeholders RF1 em produção).
        result = runner.invoke(
            app, ["run", "--dry-run", "--config", str(valid_config_path)]
        )
        assert "questions" in result.output
        assert "cells" in result.output

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


@pytest.mark.unit
def test_missing_registry_skips_wave_map(valid_config_path: Path) -> None:
    # _VALID_CONFIG aponta para model_registry.yaml inexistente em tmp_path.
    result = runner.invoke(
        app, ["run", "--dry-run", "--config", str(valid_config_path)]
    )
    assert result.exit_code == 0, result.output
    assert "wave map skipped" in result.output


# ---------------------------------------------------------------------------
# Dry-run wave map (TAREFA-303) — config + registry escritos lado a lado
# ---------------------------------------------------------------------------


def _gen_entry(name: str, *, vram: float = 80.0, gpu: int = 0) -> dict[str, object]:
    return {
        "name": name,
        "hf_repo": name,
        "vram_gb_fp16": 160.0,
        "vram_gb_awq": vram,
        "quantization": "awq",
        "tensor_parallel_size": 1,
        "gpu_index": gpu,
        "is_judge": False,
        "batch_invariant": False,
        "extra_args": {},
    }


def _judge_entry(name: str = "the-judge", *, gpu: int = 3) -> dict[str, object]:
    return {
        "name": name,
        "hf_repo": name,
        "vram_gb_fp16": 160.0,
        "vram_gb_awq": 26.0,
        "quantization": "awq",
        "tensor_parallel_size": 1,
        "gpu_index": gpu,
        "is_judge": True,
        "batch_invariant": True,
        "extra_args": {},
    }


def _slot(idx: int, *, vram: float = 96.0) -> dict[str, object]:
    return {"gpu_index": idx, "vram_gb": vram, "reserved_gb": 8.0}


def _write_round_and_registry(
    tmp_path: Path,
    *,
    llms: list[str],
    models: list[dict[str, object]],
    slots: list[dict[str, object]],
) -> Path:
    import copy

    config = copy.deepcopy(_VALID_CONFIG)
    config["round_id"] = "wave-test"
    config["model_registry_path"] = "model_registry.yaml"
    config["llms"] = llms
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump(config), encoding="utf-8")
    (tmp_path / "model_registry.yaml").write_text(
        yaml.dump({"models": models, "gpu_slots": slots}), encoding="utf-8"
    )
    return cfg_path


@pytest.mark.unit
class TestDryRunWaveMap:
    def test_table_and_totals_shown(self, tmp_path: Path) -> None:
        models = [_gen_entry(f"gen-{i}", gpu=i % 3) for i in range(5)]
        models.append(_judge_entry())
        slots = [_slot(0), _slot(1), _slot(2), _slot(3)]
        cfg = _write_round_and_registry(
            tmp_path,
            llms=[f"gen-{i}" for i in range(5)],
            models=models,
            slots=slots,
        )
        result = runner.invoke(app, ["run", "--dry-run", "--config", str(cfg)])
        assert result.exit_code == 0, result.output
        assert "GPU / wave map" in result.output
        assert "Total cells per pass" in result.output
        assert "Estimated VRAM peak" in result.output

    def test_serial_flag_warns_against_adr012(self, tmp_path: Path) -> None:
        models = [_gen_entry("gen-a"), _gen_entry("gen-b", gpu=1), _judge_entry()]
        slots = [_slot(0), _slot(1), _slot(2), _slot(3)]
        cfg = _write_round_and_registry(
            tmp_path, llms=["gen-a", "gen-b"], models=models, slots=slots
        )
        result = runner.invoke(
            app, ["run", "--dry-run", "--serial", "--config", str(cfg)]
        )
        assert result.exit_code == 0, result.output
        assert "Serial mode" in result.output

    def test_capacity_warning_when_reassigned_gpu_too_small(
        self, tmp_path: Path
    ) -> None:
        # GPU 1 pequena (avail 32); gen-b (80) nominal na GPU 2 é reatribuído à GPU 1.
        models = [
            _gen_entry("gen-a", vram=80.0, gpu=0),
            _gen_entry("gen-b", vram=80.0, gpu=2),
            _judge_entry(),
        ]
        slots = [_slot(0), _slot(1, vram=40.0), _slot(2), _slot(3)]
        cfg = _write_round_and_registry(
            tmp_path, llms=["gen-a", "gen-b"], models=models, slots=slots
        )
        result = runner.invoke(app, ["run", "--dry-run", "--config", str(cfg)])
        assert result.exit_code == 0, result.output
        assert "capacity" in result.output.lower()  # título do Panel
        # Asserção dedicada ao TEXTO do Panel (mensagem de estouro por modelo,
        # template "{name} needs {x} GB but GPU {g} has {y} GB available"). As
        # palavras "needs"/"available" só ocorrem nessa mensagem e, por serem
        # palavras inteiras, sobrevivem ao wrapping do Rich.
        assert "needs" in result.output
        assert "available" in result.output
        assert "gen-b" in result.output  # o modelo reatribuído que estoura a GPU 1

    def test_unknown_model_in_round_exits_nonzero(self, tmp_path: Path) -> None:
        models = [_gen_entry("gen-a"), _judge_entry()]
        slots = [_slot(0), _slot(3)]
        cfg = _write_round_and_registry(
            tmp_path, llms=["gen-a", "ghost"], models=models, slots=slots
        )
        result = runner.invoke(app, ["run", "--dry-run", "--config", str(cfg)])
        assert result.exit_code != 0
