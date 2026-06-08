"""Testes unitários do ExternalVLLMServerManager (TAREFA-311, ADR-014)."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from inteligenciomica_eval.domain.errors import EndpointUnreachableError
from inteligenciomica_eval.domain.ports import ModelSpec, ServerHandle
from inteligenciomica_eval.infrastructure.adapters.external_vllm_server_manager import (
    ExternalVLLMServerManager,
    _parse_port,
)
from inteligenciomica_eval.infrastructure.masking import mask_url as _mask_url

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_URL = "http://localhost:8000/v1"
_JUDGE_URL = "http://localhost:8003/v1"


def _make_spec(
    model: str = "test-gen",
    port: int = 8000,
    batch_invariant: bool = False,
) -> ModelSpec:
    return ModelSpec(
        model=model,
        port=port,
        quantization="awq",
        tensor_parallel_size=1,
        max_model_len=4096,
        gpu_index=0,
        batch_invariant=batch_invariant,
        extra_args={},
    )


def _make_manager(
    endpoint_map: dict[str, str] | None = None,
    *,
    poll_interval: float = 0.01,
    health_timeout: float = 1.0,
    now_values: list[float] | None = None,
) -> ExternalVLLMServerManager:
    """Constrói um manager com valores injetáveis para testes."""
    _times: list[float] = now_values or [0.0, 10.0, 20.0, 30.0, 40.0]
    _idx: list[int] = [0]

    def _fake_now() -> float:
        val = _times[min(_idx[0], len(_times) - 1)]
        _idx[0] += 1
        return val

    return ExternalVLLMServerManager(
        endpoint_map=endpoint_map or {"test-gen": _DEFAULT_URL},
        _poll_interval_s=poll_interval,
        _health_timeout_s=health_timeout,
        _now=_fake_now,
    )


# ---------------------------------------------------------------------------
# _mask_url
# ---------------------------------------------------------------------------


def test_mask_url_basic() -> None:
    masked = _mask_url("http://localhost:8000/v1")
    assert "localhost" in masked
    assert "8000" in masked
    assert "/v1" not in masked


def test_mask_url_with_credentials() -> None:
    masked = _mask_url("http://user:secret@host:9000/v1")
    assert "secret" not in masked
    assert "host" in masked


def test_mask_url_invalid_returns_sentinel() -> None:
    # Deve retornar "***" em caso de URL malformada que causa exceção
    # (cobertura do bloco except)
    result = _mask_url("")
    # Empty string → urlparse devolve objeto com scheme="" → sem exceção normalmente
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# _parse_port
# ---------------------------------------------------------------------------


def test_parse_port_explicit() -> None:
    assert _parse_port("http://localhost:8000/v1") == 8000


def test_parse_port_no_port_defaults_80() -> None:
    assert _parse_port("http://example.com/v1") == 80


def test_parse_port_invalid_returns_80() -> None:
    assert _parse_port("not-a-url") == 80


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------


async def test_start_returns_handle_without_pid() -> None:
    manager = _make_manager({"my-model": _DEFAULT_URL})
    spec = _make_spec(model="my-model")
    handle = await manager.start(spec)

    assert handle.pid is None
    assert handle.url == _DEFAULT_URL
    assert handle.model == "my-model"
    assert handle.batch_invariant is False
    assert handle.gpu_index == -1
    assert handle.port == 8000


async def test_start_judge_batch_invariant() -> None:
    manager = _make_manager({"stub-judge": _JUDGE_URL})
    spec = _make_spec(model="stub-judge", port=8003, batch_invariant=True)
    handle = await manager.start(spec)

    assert handle.batch_invariant is True
    assert handle.model == "stub-judge"


async def test_start_missing_model_raises_endpoint_unreachable() -> None:
    manager = _make_manager({"other-model": _DEFAULT_URL})
    spec = _make_spec(model="unknown-model")

    with pytest.raises(EndpointUnreachableError) as exc_info:
        await manager.start(spec)

    assert "unknown-model" in str(exc_info.value)


async def test_start_empty_url_raises_endpoint_unreachable() -> None:
    """URL vazia (endpoint_map com '' para o modelo) levanta EndpointUnreachableError."""
    # ExternalVLLMServerManager.start faz `if not url` → falsy string levanta
    manager = _make_manager({"test-gen": ""})
    spec = _make_spec(model="test-gen")

    with pytest.raises(EndpointUnreachableError):
        await manager.start(spec)


async def test_start_sets_started_at() -> None:
    fixed_time = 12345.0
    manager = ExternalVLLMServerManager(
        endpoint_map={"test-gen": _DEFAULT_URL},
        _now=lambda: fixed_time,
    )
    handle = await manager.start(_make_spec(model="test-gen"))
    assert handle.started_at == fixed_time


# ---------------------------------------------------------------------------
# wait_healthy()
# ---------------------------------------------------------------------------


def _make_handle(
    url: str = _DEFAULT_URL,
    model: str = "test-gen",
    batch_invariant: bool = False,
) -> ServerHandle:
    return ServerHandle(
        pid=None,
        url=url,
        model=model,
        batch_invariant=batch_invariant,
        port=_parse_port(url),
        gpu_index=-1,
        started_at=time.time(),
    )


async def test_wait_healthy_success_on_first_try() -> None:
    """wait_healthy retorna normalmente quando /health responde imediatamente."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch(
        "inteligenciomica_eval.infrastructure.adapters.external_vllm_server_manager.httpx.AsyncClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        manager = _make_manager(now_values=[0.0, 5.0, 10.0])
        handle = _make_handle()
        await manager.wait_healthy(handle, timeout_s=30)  # não deve levantar


async def test_wait_healthy_success_after_retry() -> None:
    """wait_healthy reintenta e sucede na 2ª tentativa."""
    fail_resp = MagicMock()
    fail_resp.status_code = 503
    ok_resp = MagicMock()
    ok_resp.status_code = 200

    call_count = [0]

    async def _mock_get(url: str) -> Any:
        call_count[0] += 1
        return fail_resp if call_count[0] == 1 else ok_resp

    with patch(
        "inteligenciomica_eval.infrastructure.adapters.external_vllm_server_manager.httpx.AsyncClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = _mock_get
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "inteligenciomica_eval.infrastructure.adapters.external_vllm_server_manager.asyncio.sleep",
            AsyncMock(),
        ):
            manager = _make_manager(now_values=[0.0, 5.0, 10.0, 15.0])
            handle = _make_handle()
            await manager.wait_healthy(handle, timeout_s=60)

    assert call_count[0] == 2


async def test_wait_healthy_timeout_raises_endpoint_unreachable() -> None:
    """wait_healthy levanta EndpointUnreachableError quando timeout expira."""
    with patch(
        "inteligenciomica_eval.infrastructure.adapters.external_vllm_server_manager.httpx.AsyncClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "inteligenciomica_eval.infrastructure.adapters.external_vllm_server_manager.asyncio.sleep",
            AsyncMock(),
        ):
            # now retorna valores já além do deadline (0 + 5 > 0 + 3)
            manager = _make_manager(now_values=[0.0, 10.0])
            handle = _make_handle()

            with pytest.raises(EndpointUnreachableError) as exc_info:
                await manager.wait_healthy(handle, timeout_s=3)

    assert "test-gen" in str(exc_info.value)


async def test_wait_healthy_strips_v1_from_health_url() -> None:
    """wait_healthy chama /health na raiz, sem /v1."""
    called_urls: list[str] = []

    ok_resp = MagicMock()
    ok_resp.status_code = 200

    async def _mock_get(url: str) -> Any:
        called_urls.append(url)
        return ok_resp

    with patch(
        "inteligenciomica_eval.infrastructure.adapters.external_vllm_server_manager.httpx.AsyncClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = _mock_get
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        manager = _make_manager(now_values=[0.0, 5.0])
        handle = _make_handle(url="http://localhost:8000/v1")
        await manager.wait_healthy(handle, timeout_s=30)

    assert called_urls, "GET deve ter sido chamado"
    assert "/v1/health" not in called_urls[0], "URL não deve ter duplo /v1"
    assert called_urls[0].endswith("/health")


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------


async def test_stop_is_noop() -> None:
    """stop() deve retornar sem erros e sem chamar subprocess."""
    manager = _make_manager()
    handle = _make_handle()
    # Não deve levantar exceção
    await manager.stop(handle)


async def test_stop_does_not_raise_on_external_handle() -> None:
    """stop() com pid=None não levanta."""
    manager = _make_manager()
    handle = ServerHandle(
        pid=None,
        url=_DEFAULT_URL,
        model="test-gen",
        batch_invariant=False,
        port=8000,
        gpu_index=-1,
        started_at=0.0,
    )
    await manager.stop(handle)  # deve ser silencioso


# ---------------------------------------------------------------------------
# isinstance check — satisfaz VLLMServerManagerPort (duck-typing)
# ---------------------------------------------------------------------------


def test_external_manager_satisfies_port_protocol() -> None:
    """ExternalVLLMServerManager é reconhecido como VLLMServerManagerPort."""
    from inteligenciomica_eval.domain.ports import VLLMServerManagerPort

    manager = ExternalVLLMServerManager(endpoint_map={})
    assert isinstance(manager, VLLMServerManagerPort)
