from __future__ import annotations

import copy

import pytest

from inteligenciomica_eval.infrastructure.config.provenance import (
    ProvenanceInfo,
    collect_provenance,
    config_hash,
)
from inteligenciomica_eval.infrastructure.config.schema import RoundConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_BASE_DATA: dict[object, object] = {
    "round_id": "hash-test",
    "phases": ["A"],
    "bases": ["IDx_400k"],
    "llms": ["model-a"],
    "seeds": [42],
    "temperature": 0.0,
    "retrieval": {
        "top_k": 3,
        "reranker": None,
        "embedding_model": "test-emb",
        "chunk_strategy": "sliding",
    },
    "judge": {
        "model": "judge-model",
        "endpoint_env": "VLLM_JUDGE_URL",
        "batch_invariant": True,
        "temperature": 0.0,
    },
    "scoring": {
        "weights": {"answer_correctness": 1.0},
        "failure_threshold": 0.5,
    },
}


@pytest.fixture()
def base_config() -> RoundConfig:
    return RoundConfig.model_validate(copy.deepcopy(_BASE_DATA))


# ---------------------------------------------------------------------------
# Stability: same config → same hash
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigHashStability:
    def test_same_config_yields_same_hash(self, base_config: RoundConfig) -> None:
        h1 = config_hash(base_config)
        h2 = config_hash(base_config)
        assert h1 == h2

    def test_same_data_different_instances_yield_same_hash(self) -> None:
        cfg1 = RoundConfig.model_validate(copy.deepcopy(_BASE_DATA))
        cfg2 = RoundConfig.model_validate(copy.deepcopy(_BASE_DATA))
        assert config_hash(cfg1) == config_hash(cfg2)

    def test_hash_is_64_hex_chars(self, base_config: RoundConfig) -> None:
        h = config_hash(base_config)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# Sensitivity: one change → different hash
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigHashSensitivity:
    def test_different_round_id_yields_different_hash(self) -> None:
        cfg1 = RoundConfig.model_validate(copy.deepcopy(_BASE_DATA))
        data2 = copy.deepcopy(_BASE_DATA)
        data2["round_id"] = "different-id"  # type: ignore[index]
        cfg2 = RoundConfig.model_validate(data2)
        assert config_hash(cfg1) != config_hash(cfg2)

    def test_different_temperature_yields_different_hash(self) -> None:
        cfg1 = RoundConfig.model_validate(copy.deepcopy(_BASE_DATA))
        data2 = copy.deepcopy(_BASE_DATA)
        data2["temperature"] = 0.5  # type: ignore[index]
        cfg2 = RoundConfig.model_validate(data2)
        assert config_hash(cfg1) != config_hash(cfg2)

    def test_different_seed_yields_different_hash(self) -> None:
        cfg1 = RoundConfig.model_validate(copy.deepcopy(_BASE_DATA))
        data2 = copy.deepcopy(_BASE_DATA)
        data2["seeds"] = [99]  # type: ignore[index]
        cfg2 = RoundConfig.model_validate(data2)
        assert config_hash(cfg1) != config_hash(cfg2)

    def test_extra_llm_yields_different_hash(self) -> None:
        cfg1 = RoundConfig.model_validate(copy.deepcopy(_BASE_DATA))
        data2 = copy.deepcopy(_BASE_DATA)
        data2["llms"] = ["model-a", "model-b"]  # type: ignore[index]
        cfg2 = RoundConfig.model_validate(data2)
        assert config_hash(cfg1) != config_hash(cfg2)

    def test_weight_change_yields_different_hash(self) -> None:
        cfg1 = RoundConfig.model_validate(copy.deepcopy(_BASE_DATA))
        data2 = copy.deepcopy(_BASE_DATA)
        scoring = data2["scoring"]  # type: ignore[index]
        assert isinstance(scoring, dict)
        scoring["weights"] = {"answer_correctness": 0.6, "faithfulness": 0.4}
        cfg2 = RoundConfig.model_validate(data2)
        assert config_hash(cfg1) != config_hash(cfg2)

    def test_batch_invariant_is_included_in_hash_payload(self) -> None:
        """batch_invariant is always True in valid round configs.

        We cannot produce two valid configs with different batch_invariant values
        (the schema rejects False). Instead we verify that the field IS present in
        the canonical JSON payload — so any hypothetical future change to the field
        would propagate to a different hash.
        """
        import json

        cfg = RoundConfig.model_validate(copy.deepcopy(_BASE_DATA))
        payload = json.dumps(
            cfg.model_dump(mode="json"),
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        assert '"batch_invariant":true' in payload


# ---------------------------------------------------------------------------
# Key-order independence: dict key insertion order must not affect hash
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_hash_independent_of_dict_key_order() -> None:
    """Hash must be the same regardless of key insertion order in weights."""
    data_ab = copy.deepcopy(_BASE_DATA)
    scoring_ab = data_ab["scoring"]  # type: ignore[index]
    assert isinstance(scoring_ab, dict)
    scoring_ab["weights"] = {"alpha": 0.6, "beta": 0.4}

    data_ba = copy.deepcopy(_BASE_DATA)
    scoring_ba = data_ba["scoring"]  # type: ignore[index]
    assert isinstance(scoring_ba, dict)
    scoring_ba["weights"] = {"beta": 0.4, "alpha": 0.6}

    cfg_ab = RoundConfig.model_validate(data_ab)
    cfg_ba = RoundConfig.model_validate(data_ba)
    assert config_hash(cfg_ab) == config_hash(cfg_ba)


# ---------------------------------------------------------------------------
# ProvenanceInfo
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCollectProvenance:
    def test_collect_provenance_returns_provenance_info(
        self, base_config: RoundConfig
    ) -> None:
        prov = collect_provenance(base_config)
        assert isinstance(prov, ProvenanceInfo)

    def test_provenance_config_hash_matches(self, base_config: RoundConfig) -> None:
        prov = collect_provenance(base_config)
        assert prov.config_hash == config_hash(base_config)

    def test_provenance_versions_are_strings(self, base_config: RoundConfig) -> None:
        prov = collect_provenance(base_config)
        assert isinstance(prov.vllm_version, str)
        assert isinstance(prov.ragas_version, str)

    def test_provenance_collected_at_is_iso8601(self, base_config: RoundConfig) -> None:
        from datetime import datetime

        prov = collect_provenance(base_config)
        # Should parse without error
        dt = datetime.fromisoformat(prov.collected_at)
        assert dt.tzinfo is not None  # UTC-aware
