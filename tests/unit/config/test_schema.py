from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from inteligenciomica_eval.domain.errors import ConfigValidationError
from inteligenciomica_eval.infrastructure.config.schema import (
    RoundConfig,
    load_round_config,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_DICT: dict[object, object] = {
    "round_id": "test-round",
    "phases": ["A", "B"],
    "bases": ["IDx_400k"],
    "llms": ["some-model/v1"],
    "seeds": [42],
    "temperature": 0.0,
    "retrieval": {
        "top_k": 5,
        "reranker": None,
        "embedding_model": "test-embed",
        "chunk_strategy": "fixed",
    },
    "judge": {
        "model": "some-judge",
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
        "canonical_top_k": 5,
    },
}


def _cfg(**overrides: object) -> dict[object, object]:
    """Return a copy of the base dict with deep overrides applied."""
    import copy

    data = copy.deepcopy(_BASE_DICT)
    for key, value in overrides.items():
        if "." in key:
            # Support "scoring.weights" style keys
            parts = key.split(".", 1)
            nested = data.setdefault(parts[0], {})
            assert isinstance(nested, dict)
            nested[parts[1]] = value
        else:
            data[key] = value
    return data


def _write_yaml(tmp_path: Path, data: dict[object, object]) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Valid config
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidConfig:
    def test_valid_config_loads(self, tmp_path: Path) -> None:
        cfg = load_round_config(_write_yaml(tmp_path, _BASE_DICT))
        assert cfg.round_id == "test-round"
        assert cfg.bases == ["IDx_400k"]
        assert cfg.seeds == [42]

    def test_valid_config_via_model_validate(self) -> None:
        import copy

        cfg = RoundConfig.model_validate(copy.deepcopy(_BASE_DICT))
        assert cfg.temperature == 0.0
        assert cfg.judge.batch_invariant is True

    def test_experiment_b_optional_when_no_phase_b(self, tmp_path: Path) -> None:
        data = _cfg(phases=["A"])
        del data["experiment_b"]  # type: ignore[arg-type]
        cfg = load_round_config(_write_yaml(tmp_path, data))
        assert cfg.experiment_b is None

    def test_phase_a_only(self, tmp_path: Path) -> None:
        data = _cfg(phases=["A"])
        del data["experiment_b"]  # type: ignore[arg-type]
        cfg = load_round_config(_write_yaml(tmp_path, data))
        assert "A" in cfg.phases
        assert "B" not in cfg.phases

    def test_multiple_bases_and_seeds(self, tmp_path: Path) -> None:
        data = _cfg(bases=["IDx_400k", "ID_230K"], seeds=[1, 2, 3])
        cfg = load_round_config(_write_yaml(tmp_path, data))
        assert len(cfg.bases) == 2
        assert len(cfg.seeds) == 3


# ---------------------------------------------------------------------------
# bases validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBasesValidation:
    def test_unknown_base_raises(self, tmp_path: Path) -> None:
        data = _cfg(bases=["IDx_400k", "UNKNOWN_BASE"])
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert exc_info.value.field == "bases"

    def test_fixed_base_not_allowed_in_round_config(self, tmp_path: Path) -> None:
        # "fixed" is reserved for Experiment B internal use, not round-level bases
        data = _cfg(bases=["fixed"])
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert exc_info.value.field == "bases"

    def test_empty_bases_raises(self, tmp_path: Path) -> None:
        data = _cfg(bases=[])
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert exc_info.value.field == "bases"


# ---------------------------------------------------------------------------
# llms validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLLMsValidation:
    def test_empty_llms_raises(self, tmp_path: Path) -> None:
        data = _cfg(llms=[])
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert exc_info.value.field == "llms"

    def test_llm_with_space_raises(self, tmp_path: Path) -> None:
        data = _cfg(llms=["valid-model", "bad model"])
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert exc_info.value.field == "llms"


# ---------------------------------------------------------------------------
# seeds validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSeedsValidation:
    def test_empty_seeds_raises(self, tmp_path: Path) -> None:
        data = _cfg(seeds=[])
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert exc_info.value.field == "seeds"

    def test_negative_seed_raises(self, tmp_path: Path) -> None:
        data = _cfg(seeds=[42, -1])
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert exc_info.value.field == "seeds"

    def test_zero_seed_is_valid(self, tmp_path: Path) -> None:
        data = _cfg(seeds=[0, 42])
        cfg = load_round_config(_write_yaml(tmp_path, data))
        assert 0 in cfg.seeds


# ---------------------------------------------------------------------------
# temperature validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTemperatureValidation:
    def test_negative_temperature_raises(self, tmp_path: Path) -> None:
        data = _cfg(temperature=-0.1)
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert "temperature" in exc_info.value.field


# ---------------------------------------------------------------------------
# retrieval validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRetrievalValidation:
    def test_top_k_zero_raises(self, tmp_path: Path) -> None:
        data = _cfg(**{"retrieval.top_k": 0})  # type: ignore[arg-type]
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert "top_k" in exc_info.value.field

    def test_top_k_negative_raises(self, tmp_path: Path) -> None:
        data = _cfg(**{"retrieval.top_k": -1})  # type: ignore[arg-type]
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert "top_k" in exc_info.value.field


# ---------------------------------------------------------------------------
# judge validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestJudgeValidation:
    def test_batch_invariant_false_raises(self, tmp_path: Path) -> None:
        data = _cfg(**{"judge.batch_invariant": False})  # type: ignore[arg-type]
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert "batch_invariant" in exc_info.value.field

    def test_judge_negative_temperature_raises(self, tmp_path: Path) -> None:
        data = _cfg(**{"judge.temperature": -1.0})  # type: ignore[arg-type]
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert "temperature" in exc_info.value.field

    def test_endpoint_env_lowercase_raises(self, tmp_path: Path) -> None:
        data = _cfg(**{"judge.endpoint_env": "vllm_judge_url"})  # type: ignore[arg-type]
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert "endpoint_env" in exc_info.value.field

    def test_endpoint_env_literal_url_raises(self, tmp_path: Path) -> None:
        data = _cfg(**{"judge.endpoint_env": "http://judge:8000"})  # type: ignore[arg-type]
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert "endpoint_env" in exc_info.value.field

    def test_endpoint_env_valid_name_accepted(self, tmp_path: Path) -> None:
        data = _cfg(**{"judge.endpoint_env": "VLLM_JUDGE_URL"})  # type: ignore[arg-type]
        cfg = load_round_config(_write_yaml(tmp_path, data))
        assert cfg.judge.endpoint_env == "VLLM_JUDGE_URL"


# ---------------------------------------------------------------------------
# scoring validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScoringValidation:
    def test_weights_not_summing_to_one_raises(self, tmp_path: Path) -> None:
        data = _cfg(
            **{"scoring.weights": {"answer_correctness": 0.6, "faithfulness": 0.5}}  # type: ignore[arg-type]
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert "weights" in exc_info.value.field

    def test_failure_threshold_above_one_raises(self, tmp_path: Path) -> None:
        data = _cfg(**{"scoring.failure_threshold": 1.1})  # type: ignore[arg-type]
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert "failure_threshold" in exc_info.value.field

    def test_failure_threshold_below_zero_raises(self, tmp_path: Path) -> None:
        data = _cfg(**{"scoring.failure_threshold": -0.1})  # type: ignore[arg-type]
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert "failure_threshold" in exc_info.value.field

    def test_weights_summing_to_one_with_precision(self, tmp_path: Path) -> None:
        # Weights that sum to 1.0 within floating-point error should be accepted
        weights = {
            "a": 1 / 3,
            "b": 1 / 3,
            "c": 1 / 3,
        }
        # 1/3 + 1/3 + 1/3 = 0.9999... in float; verify tolerance handles it
        # (only passes if tolerance > machine epsilon; our tolerance is 1e-9)
        total = sum(weights.values())
        if abs(total - 1.0) <= 1e-9:
            data = _cfg(**{"scoring.weights": weights})  # type: ignore[arg-type]
            cfg = load_round_config(_write_yaml(tmp_path, data))
            assert cfg.scoring.weights == weights


# ---------------------------------------------------------------------------
# phases validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExperimentBValidation:
    def test_invalid_canonical_source_raises(self, tmp_path: Path) -> None:
        data = _cfg(
            **{"experiment_b.canonical_context_source": "UNKNOWN_SOURCE"}  # type: ignore[arg-type]
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert "canonical_context_source" in exc_info.value.field

    def test_expert_curated_is_valid(self, tmp_path: Path) -> None:
        data = _cfg(
            **{"experiment_b.canonical_context_source": "expert_curated"}  # type: ignore[arg-type]
        )
        cfg = load_round_config(_write_yaml(tmp_path, data))
        assert cfg.experiment_b is not None
        assert cfg.experiment_b.canonical_context_source == "expert_curated"

    def test_idx_400k_is_valid(self, tmp_path: Path) -> None:
        data = _cfg(
            **{"experiment_b.canonical_context_source": "IDx_400k"}  # type: ignore[arg-type]
        )
        cfg = load_round_config(_write_yaml(tmp_path, data))
        assert cfg.experiment_b is not None
        assert cfg.experiment_b.canonical_context_source == "IDx_400k"


# ---------------------------------------------------------------------------
# phases validation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPhasesValidation:
    def test_invalid_phase_raises(self, tmp_path: Path) -> None:
        data = _cfg(phases=["A", "C"])
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(_write_yaml(tmp_path, data))
        assert "phases" in exc_info.value.field

    def test_phase_b_without_experiment_b_raises(self, tmp_path: Path) -> None:
        data = _cfg(phases=["B"])
        data.pop("experiment_b", None)  # type: ignore[attr-defined]
        with pytest.raises(ConfigValidationError):
            load_round_config(_write_yaml(tmp_path, data))


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestYAMLLoading:
    def test_nonexistent_file_raises_file_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_round_config(tmp_path / "does_not_exist.yaml")

    def test_non_mapping_yaml_raises_config_validation_error(
        self, tmp_path: Path
    ) -> None:
        p = tmp_path / "bad.yaml"
        p.write_text("- just a list\n", encoding="utf-8")
        with pytest.raises(ConfigValidationError) as exc_info:
            load_round_config(p)
        assert exc_info.value.field == "(root)"
