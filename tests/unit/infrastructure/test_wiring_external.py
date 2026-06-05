"""Testes unitários do wiring em server_mode='external' (TAREFA-311, ADR-014)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from inteligenciomica_eval.domain.errors import ConfigValidationError
from inteligenciomica_eval.infrastructure.config.schema import load_round_config
from inteligenciomica_eval.infrastructure.config.settings import RuntimeSettings
from inteligenciomica_eval.infrastructure.wiring import (
    _build_external_server_manager,
    build_container,
)

# ---------------------------------------------------------------------------
# Helpers de fixture
# ---------------------------------------------------------------------------

_BASE_CONFIG: dict[str, Any] = {
    "round_id": "ext-wiring-test",
    "phases": ["A"],
    "bases": ["IDx_400k"],
    "llms": ["stub-gen"],
    "seeds": [42],
    "temperature": 0.0,
    "retrieval": {
        "top_k": 3,
        "reranker": None,
        "embedding_model": "embed-v1",
        "chunk_strategy": "sliding",
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

_REGISTRY_YAML: dict[str, Any] = {
    "models": [
        {
            "name": "stub-gen",
            "hf_repo": "org/stub-gen",
            "vram_gb_fp16": 16.0,
            "vram_gb_awq": 8.0,
            "quantization": "awq",
            "tensor_parallel_size": 1,
            "gpu_index": 0,
            "is_judge": False,
            "batch_invariant": False,
            "endpoint_env": "STUB_GEN_URL",
        },
        {
            "name": "stub-judge",
            "hf_repo": "org/stub-judge",
            "vram_gb_fp16": 14.0,
            "vram_gb_awq": 7.0,
            "quantization": "awq",
            "tensor_parallel_size": 1,
            "gpu_index": 1,
            "is_judge": True,
            "batch_invariant": True,
            "endpoint_env": "STUB_JUDGE_URL",
        },
    ],
    "gpu_slots": [
        {"gpu_index": 0, "vram_gb": 40.0, "reserved_gb": 4.0},
        {"gpu_index": 1, "vram_gb": 40.0, "reserved_gb": 4.0},
    ],
}


@pytest.fixture()
def cfg_with_registry(tmp_path: Path) -> tuple[Any, Path]:
    """Cria round config YAML e registry YAML para testes de wiring external."""
    registry_path = tmp_path / "model_registry.yaml"
    registry_path.write_text(yaml.dump(_REGISTRY_YAML), encoding="utf-8")

    config_data = dict(_BASE_CONFIG)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config_data), encoding="utf-8")

    cfg = load_round_config(config_path)
    return cfg, tmp_path


@pytest.fixture(autouse=True)
def _patch_hf_embeddings() -> Any:
    """Evita carregamento real de HuggingFace em testes de wiring (offline-safe)."""
    with patch(
        "inteligenciomica_eval.infrastructure.adapters.ragas_metrics._build_embeddings",
        return_value=(MagicMock(), "hf_local"),
    ):
        yield


# ---------------------------------------------------------------------------
# Testes de _build_external_server_manager
# ---------------------------------------------------------------------------


def test_build_external_server_manager_ok_with_env_vars(
    cfg_with_registry: tuple[Any, Path],
) -> None:
    """Constrói ExternalVLLMServerManager quando todas as env vars estão presentes."""
    from inteligenciomica_eval.infrastructure.adapters.external_vllm_server_manager import (
        ExternalVLLMServerManager,
    )
    from inteligenciomica_eval.infrastructure.config.model_registry import (
        load_model_registry,
    )

    cfg, tmp_path = cfg_with_registry
    registry = load_model_registry(tmp_path / "model_registry.yaml")

    env_patch = {
        "STUB_GEN_URL": "http://host-gen:8000/v1",
        "STUB_JUDGE_URL": "http://host-judge:8003/v1",
    }
    with patch.dict(os.environ, env_patch):
        manager = _build_external_server_manager(
            cfg, list(registry.models), ExternalVLLMServerManager
        )

    assert isinstance(manager, ExternalVLLMServerManager)
    assert manager._endpoint_map["stub-gen"] == "http://host-gen:8000/v1"
    assert manager._endpoint_map["stub-judge"] == "http://host-judge:8003/v1"


def test_build_external_server_manager_missing_endpoint_env_raises(
    tmp_path: Path,
) -> None:
    """Levanta ConfigValidationError se endpoint_env for None em algum modelo."""
    from inteligenciomica_eval.infrastructure.adapters.external_vllm_server_manager import (
        ExternalVLLMServerManager,
    )

    # Cria um ModelEntry fake sem endpoint_env
    class _FakeEntry:
        name = "no-env-model"
        endpoint_env: str | None = None

    cfg = object()
    with pytest.raises(ConfigValidationError) as exc_info:
        _build_external_server_manager(cfg, [_FakeEntry()], ExternalVLLMServerManager)

    assert "no-env-model" in str(exc_info.value)
    assert "endpoint_env" in str(exc_info.value)


def test_build_external_server_manager_missing_env_var_raises(
    tmp_path: Path,
) -> None:
    """Levanta ConfigValidationError se a env var não estiver no ambiente."""
    from inteligenciomica_eval.infrastructure.adapters.external_vllm_server_manager import (
        ExternalVLLMServerManager,
    )

    class _FakeEntry:
        name = "my-model"
        endpoint_env: str | None = "MY_MODEL_NONEXISTENT_URL_XYZ"

    cfg = object()
    # Garante que a env var não existe
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("MY_MODEL_NONEXISTENT_URL_XYZ", None)
        with pytest.raises(ConfigValidationError) as exc_info:
            _build_external_server_manager(
                cfg, [_FakeEntry()], ExternalVLLMServerManager
            )

    assert "MY_MODEL_NONEXISTENT_URL_XYZ" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Testes de build_container em external mode
# ---------------------------------------------------------------------------


def test_build_container_external_mode_uses_external_manager(
    cfg_with_registry: tuple[Any, Path],
) -> None:
    """build_container com server_mode='external' instancia ExternalVLLMServerManager."""
    from inteligenciomica_eval.domain.ports import VLLMServerManagerPort
    from inteligenciomica_eval.infrastructure.adapters.external_vllm_server_manager import (
        ExternalVLLMServerManager,
    )

    cfg, tmp_path = cfg_with_registry

    # Settings com env vars mínimas para produção (QDRANT_URL ainda necessário)
    env_patch = {
        "STUB_GEN_URL": "http://host-gen:8000/v1",
        "STUB_JUDGE_URL": "http://host-judge:8003/v1",
        "VLLM_GENERATOR_URL": "http://host-gen:8000/v1",
        "VLLM_JUDGE_URL": "http://host-judge:8003/v1",
        "QDRANT_URL": "http://localhost:6333",
    }
    with patch.dict(os.environ, env_patch):
        settings = RuntimeSettings()
        container = build_container(cfg, settings, config_dir=tmp_path)

    assert isinstance(container.server_manager, ExternalVLLMServerManager)
    assert isinstance(container.server_manager, VLLMServerManagerPort)


def test_build_container_managed_mode_skips_external_manager(
    tmp_path: Path,
) -> None:
    """build_container com server_mode='managed' usa VLLMServerManagerAdapter."""
    from inteligenciomica_eval.infrastructure.adapters.external_vllm_server_manager import (
        ExternalVLLMServerManager,
    )

    # Config sem server_mode (default managed)
    config_data: dict[str, Any] = {
        "round_id": "managed-test",
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
            "weights": {"answer_correctness": 1.0},
            "failure_threshold": 0.3,
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config_data), encoding="utf-8")
    cfg = load_round_config(config_path)

    env_patch = {
        "VLLM_GENERATOR_URL": "http://localhost:8000/v1",
        "VLLM_JUDGE_URL": "http://localhost:8003/v1",
        "QDRANT_URL": "http://localhost:6333",
    }
    with patch.dict(os.environ, env_patch):
        settings = RuntimeSettings()
        container = build_container(cfg, settings, config_dir=tmp_path)

    # Não deve ser ExternalVLLMServerManager em modo managed
    assert not isinstance(container.server_manager, ExternalVLLMServerManager)


def test_build_container_external_missing_env_var_raises(
    cfg_with_registry: tuple[Any, Path],
) -> None:
    """build_container external levanta ConfigValidationError se env var ausente."""
    cfg, tmp_path = cfg_with_registry

    # Não define STUB_GEN_URL nem STUB_JUDGE_URL
    env_vars = {
        "VLLM_GENERATOR_URL": "http://localhost:8000/v1",
        "VLLM_JUDGE_URL": "http://localhost:8003/v1",
        "QDRANT_URL": "http://localhost:6333",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        os.environ.pop("STUB_GEN_URL", None)
        os.environ.pop("STUB_JUDGE_URL", None)
        settings = RuntimeSettings()

        with pytest.raises(ConfigValidationError) as exc_info:
            build_container(cfg, settings, config_dir=tmp_path)

    assert "endpoint_env" in str(exc_info.value).lower() or "URL" in str(exc_info.value)


# ---------------------------------------------------------------------------
# server_mode no RoundConfig
# ---------------------------------------------------------------------------


def test_round_config_default_server_mode_is_managed(tmp_path: Path) -> None:
    """RoundConfig sem server_mode usa default 'managed'."""
    config_data: dict[str, Any] = {
        "round_id": "default-mode-test",
        "phases": ["A"],
        "bases": ["IDx_400k"],
        "llms": ["m"],
        "seeds": [0],
        "temperature": 0.0,
        "retrieval": {
            "top_k": 1,
            "embedding_model": "em",
            "chunk_strategy": "s",
        },
        "judge": {
            "model": "j",
            "endpoint_env": "VLLM_JUDGE_URL",
            "batch_invariant": True,
            "temperature": 0.0,
        },
        "scoring": {
            "weights": {"answer_correctness": 1.0},
            "failure_threshold": 0.3,
        },
    }
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text(yaml.dump(config_data), encoding="utf-8")
    cfg = load_round_config(cfg_path)
    assert cfg.server_mode == "managed"


def test_round_config_explicit_external_mode(tmp_path: Path) -> None:
    """RoundConfig com server_mode='external' é aceito."""
    config_data: dict[str, Any] = {
        "round_id": "ext-test",
        "phases": ["A"],
        "bases": ["IDx_400k"],
        "llms": ["m"],
        "seeds": [0],
        "temperature": 0.0,
        "retrieval": {
            "top_k": 1,
            "embedding_model": "em",
            "chunk_strategy": "s",
        },
        "judge": {
            "model": "j",
            "endpoint_env": "VLLM_JUDGE_URL",
            "batch_invariant": True,
            "temperature": 0.0,
        },
        "scoring": {
            "weights": {"answer_correctness": 1.0},
            "failure_threshold": 0.3,
        },
        "server_mode": "external",
    }
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text(yaml.dump(config_data), encoding="utf-8")
    cfg = load_round_config(cfg_path)
    assert cfg.server_mode == "external"


def test_round_config_invalid_server_mode_raises(tmp_path: Path) -> None:
    """server_mode inválido levanta ConfigValidationError."""
    config_data: dict[str, Any] = {
        "round_id": "bad-mode",
        "phases": ["A"],
        "bases": ["IDx_400k"],
        "llms": ["m"],
        "seeds": [0],
        "temperature": 0.0,
        "retrieval": {
            "top_k": 1,
            "embedding_model": "em",
            "chunk_strategy": "s",
        },
        "judge": {
            "model": "j",
            "endpoint_env": "VLLM_JUDGE_URL",
            "batch_invariant": True,
            "temperature": 0.0,
        },
        "scoring": {
            "weights": {"answer_correctness": 1.0},
            "failure_threshold": 0.3,
        },
        "server_mode": "kubernetes",  # inválido
    }
    cfg_path = tmp_path / "c.yaml"
    cfg_path.write_text(yaml.dump(config_data), encoding="utf-8")

    with pytest.raises(ConfigValidationError):
        load_round_config(cfg_path)
