from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest
import yaml

from inteligenciomica_eval.domain.errors import (
    ConfigValidationError,
    ModelNotInRegistryError,
)
from inteligenciomica_eval.domain.value_objects import LLMId, ModelWaveSpec
from inteligenciomica_eval.infrastructure.config.model_registry import (
    GPUSlot,
    ModelEntry,
    ModelRegistryConfig,
    get_model,
    load_model_registry,
)

# Path to the versioned registry shipped with the repo (TAREFA-301 deliverable c).
# tests/unit/config/test_model_registry.py -> parents[3] == repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REGISTRY_YAML = _REPO_ROOT / "config" / "model_registry.yaml"


def _generator(
    name: str, *, gpu_index: int = 0, vram_awq: float = 6.0
) -> dict[str, Any]:
    """A valid generator entry as a plain dict (for YAML round-trips)."""
    return {
        "name": name,
        "hf_repo": name,
        "vram_gb_fp16": 16.0,
        "vram_gb_awq": vram_awq,
        "quantization": "awq",
        "tensor_parallel_size": 1,
        "gpu_index": gpu_index,
        "is_judge": False,
        "batch_invariant": False,
        "extra_args": {},
    }


def _judge(name: str = "judge", *, gpu_index: int = 3) -> dict[str, Any]:
    """A valid judge entry as a plain dict."""
    return {
        "name": name,
        "hf_repo": name,
        "vram_gb_fp16": 15.0,
        "vram_gb_awq": 15.0,
        "quantization": "bfloat16",
        "tensor_parallel_size": 1,
        "gpu_index": gpu_index,
        "is_judge": True,
        "batch_invariant": True,
        "extra_args": {"VLLM_BATCH_INVARIANT": "1"},
    }


def _slots(*indices: int, vram_gb: float = 96.0) -> list[dict[str, Any]]:
    return [{"gpu_index": i, "vram_gb": vram_gb, "reserved_gb": 8.0} for i in indices]


def _registry_dict(
    models: list[dict[str, Any]], slots: list[dict[str, Any]]
) -> dict[str, Any]:
    return {"models": models, "gpu_slots": slots}


def _dump_and_load(path: Path, payload: dict[str, Any]) -> ModelRegistryConfig:
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return load_model_registry(path)


# ---------------------------------------------------------------------------
# GPUSlot
# ---------------------------------------------------------------------------


def test_gpu_slot_available_gb_is_vram_minus_reserved() -> None:
    slot = GPUSlot(gpu_index=0, vram_gb=96.0, reserved_gb=8.0)
    assert slot.available_gb == pytest.approx(88.0)


def test_gpu_slot_default_reserved_is_eight() -> None:
    slot = GPUSlot(gpu_index=1, vram_gb=141.0)
    assert slot.reserved_gb == pytest.approx(8.0)
    assert slot.available_gb == pytest.approx(133.0)


# ---------------------------------------------------------------------------
# ModelEntry cross-field validation (ADR-003)
# ---------------------------------------------------------------------------


def test_valid_registry_loads(tmp_path: Path) -> None:
    payload = _registry_dict(
        [_generator("gen-a", gpu_index=0), _judge(gpu_index=3)],
        _slots(0, 3),
    )
    registry = _dump_and_load(tmp_path / "r.yaml", payload)
    assert {m.name for m in registry.models} == {"gen-a", "judge"}


def test_judge_without_batch_invariant_fails_citing_adr003(tmp_path: Path) -> None:
    bad_judge = _judge(gpu_index=3)
    bad_judge["batch_invariant"] = False
    payload = _registry_dict([_generator("gen-a"), bad_judge], _slots(0, 3))
    with pytest.raises(ConfigValidationError) as exc:
        _dump_and_load(tmp_path / "r.yaml", payload)
    assert "ADR-003" in str(exc.value)


def test_judge_with_tensor_parallel_two_fails_citing_adr003(tmp_path: Path) -> None:
    bad_judge = _judge(gpu_index=3)
    bad_judge["tensor_parallel_size"] = 2
    payload = _registry_dict([_generator("gen-a"), bad_judge], _slots(0, 3))
    with pytest.raises(ConfigValidationError) as exc:
        _dump_and_load(tmp_path / "r.yaml", payload)
    assert "ADR-003" in str(exc.value)


def test_generator_with_batch_invariant_true_fails_citing_adr003(
    tmp_path: Path,
) -> None:
    bad_gen = _generator("gen-a")
    bad_gen["batch_invariant"] = True
    payload = _registry_dict([bad_gen, _judge(gpu_index=3)], _slots(0, 3))
    with pytest.raises(ConfigValidationError) as exc:
        _dump_and_load(tmp_path / "r.yaml", payload)
    assert "ADR-003" in str(exc.value)


# ---------------------------------------------------------------------------
# ModelRegistryConfig set-level validation
# ---------------------------------------------------------------------------


def test_zero_judges_fails(tmp_path: Path) -> None:
    payload = _registry_dict(
        [_generator("gen-a", gpu_index=0), _generator("gen-b", gpu_index=1)],
        _slots(0, 1),
    )
    with pytest.raises(ConfigValidationError):
        _dump_and_load(tmp_path / "r.yaml", payload)


def test_two_judges_fails(tmp_path: Path) -> None:
    judge_two = _judge("judge-2", gpu_index=2)
    payload = _registry_dict(
        [_generator("gen-a"), _judge("judge-1", gpu_index=3), judge_two],
        _slots(0, 2, 3),
    )
    with pytest.raises(ConfigValidationError):
        _dump_and_load(tmp_path / "r.yaml", payload)


def test_duplicate_model_names_fails(tmp_path: Path) -> None:
    payload = _registry_dict(
        [_generator("dup", gpu_index=0), _generator("dup", gpu_index=1), _judge()],
        _slots(0, 1, 3),
    )
    with pytest.raises(ConfigValidationError):
        _dump_and_load(tmp_path / "r.yaml", payload)


def test_vram_exceeding_available_fails(tmp_path: Path) -> None:
    # available = 96 - 8 = 88; demand 90 > 88 -> fail.
    heavy = _generator("heavy", gpu_index=0, vram_awq=90.0)
    payload = _registry_dict([heavy, _judge()], _slots(0, 3))
    with pytest.raises(ConfigValidationError) as exc:
        _dump_and_load(tmp_path / "r.yaml", payload)
    assert "heavy" in str(exc.value)


def test_vram_check_uses_target_slot_not_max(tmp_path: Path) -> None:
    # gpu 0 available=88 (demand 90 -> fail) even though gpu 1 has 141 available.
    heavy = _generator("heavy", gpu_index=0, vram_awq=90.0)
    payload = _registry_dict(
        [heavy, _judge()],
        [
            {"gpu_index": 0, "vram_gb": 96.0, "reserved_gb": 8.0},
            {"gpu_index": 1, "vram_gb": 149.0, "reserved_gb": 8.0},
            {"gpu_index": 3, "vram_gb": 96.0, "reserved_gb": 8.0},
        ],
    )
    with pytest.raises(ConfigValidationError):
        _dump_and_load(tmp_path / "r.yaml", payload)


def test_model_targeting_missing_slot_fails(tmp_path: Path) -> None:
    payload = _registry_dict(
        [_generator("gen-a", gpu_index=7), _judge()],
        _slots(0, 3),
    )
    with pytest.raises(ConfigValidationError):
        _dump_and_load(tmp_path / "r.yaml", payload)


def test_root_not_mapping_fails(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigValidationError):
        load_model_registry(path)


# ---------------------------------------------------------------------------
# get_model
# ---------------------------------------------------------------------------


def test_get_model_returns_entry(tmp_path: Path) -> None:
    payload = _registry_dict([_generator("gen-a"), _judge()], _slots(0, 3))
    registry = _dump_and_load(tmp_path / "r.yaml", payload)
    entry = get_model(registry, LLMId("gen-a"))
    assert isinstance(entry, ModelEntry)
    assert entry.name == "gen-a"


def test_get_model_unknown_raises_model_not_in_registry(tmp_path: Path) -> None:
    payload = _registry_dict([_generator("gen-a"), _judge()], _slots(0, 3))
    registry = _dump_and_load(tmp_path / "r.yaml", payload)
    with pytest.raises(ModelNotInRegistryError):
        get_model(registry, LLMId("does-not-exist"))


# ---------------------------------------------------------------------------
# Shipped config/model_registry.yaml
# ---------------------------------------------------------------------------


def test_shipped_registry_loads_with_six_models() -> None:
    registry = load_model_registry(_REGISTRY_YAML)
    assert len(registry.models) == 6
    judges = [m for m in registry.models if m.is_judge]
    assert len(judges) == 1
    assert len(registry.models) - len(judges) == 5  # 5 generators


def test_shipped_registry_judge_is_deterministic() -> None:
    registry = load_model_registry(_REGISTRY_YAML)
    judge = next(m for m in registry.models if m.is_judge)
    assert judge.batch_invariant is True
    assert judge.tensor_parallel_size == 1
    assert judge.gpu_index == 3  # ADR-012


def test_shipped_registry_generators_are_non_invariant() -> None:
    registry = load_model_registry(_REGISTRY_YAML)
    for model in registry.models:
        if not model.is_judge:
            assert model.batch_invariant is False
            assert model.gpu_index in {0, 1, 2}  # ADR-012


# ---------------------------------------------------------------------------
# ModelWaveSpec (domain VO — TAREFA-301 deliverable b)
# ---------------------------------------------------------------------------


def test_model_wave_spec_is_frozen_dataclass() -> None:
    spec = ModelWaveSpec(
        name="gen-a",
        vram_gb_awq=6.0,
        is_judge=False,
        tensor_parallel_size=1,
        quantization="awq",
        gpu_index=0,
        extra_args={},
    )
    assert dataclasses.is_dataclass(spec)
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.name = "other"  # type: ignore[misc]


def test_model_wave_spec_has_expected_fields() -> None:
    field_names = {f.name for f in dataclasses.fields(ModelWaveSpec)}
    assert field_names == {
        "name",
        "vram_gb_awq",
        "is_judge",
        "tensor_parallel_size",
        "quantization",
        "gpu_index",
        "extra_args",
    }
