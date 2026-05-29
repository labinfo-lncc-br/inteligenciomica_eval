"""Testes unitários do VLLMServerManagerAdapter (TAREFA-019).

Estratégia (Nota M1 item 7): subprocess mockado via pytest-mock (``asyncio.
create_subprocess_exec``) + ``respx`` para ``/health``. Nenhum vLLM real é iniciado.
``os.kill`` é mockado para não enviar sinais ao SO. ``_poll_interval_s``/``_clock``/
``_sigterm_timeout_s`` injetados tornam polling e timeout determinísticos e instantâneos.
"""

from __future__ import annotations

import asyncio
import itertools
import signal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
import structlog

from inteligenciomica_eval.domain.errors import ServerStartTimeoutError
from inteligenciomica_eval.domain.ports import (
    ModelSpec,
    ServerHandle,
    VLLMServerManagerPort,
)
from inteligenciomica_eval.infrastructure.adapters.vllm_server_manager import (
    VLLMServerManagerAdapter,
)

# ---------------------------------------------------------------------------
# Builders de ModelSpec
# ---------------------------------------------------------------------------


def _judge_spec(port: int = 8001) -> ModelSpec:
    """ModelSpec do juiz: BATCH_INVARIANT presente no extra_env (§9.2)."""
    return ModelSpec(
        model="prometheus-8x7b",
        port=port,
        quantization=None,
        tensor_parallel_size=1,
        max_model_len=4096,
        extra_env={
            "VLLM_BATCH_INVARIANT": "1",
            "VLLM_ENABLE_V1_MULTIPROCESSING": "0",
        },
    )


def _generator_spec(port: int = 8000, quantization: str | None = None) -> ModelSpec:
    """ModelSpec do gerador: sem BATCH_INVARIANT (§9.2.4)."""
    return ModelSpec(
        model="llama3-8b",
        port=port,
        quantization=quantization,
        tensor_parallel_size=2,
        max_model_len=8192,
        extra_env={},
    )


# ---------------------------------------------------------------------------
# Mocks de subprocess
# ---------------------------------------------------------------------------


class _SlowThenFast:
    """``process.wait()``: bloqueia na 1ª chamada (cancelada por ``wait_for`` → timeout),
    e retorna imediatamente nas seguintes (simula SIGKILL surtindo efeito)."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> int:
        self.calls += 1
        if self.calls == 1:
            await asyncio.sleep(3600)
        return 0


def _fake_process(pid: int = 4321, wait: Any = None) -> MagicMock:
    proc = MagicMock()
    proc.pid = pid
    proc.wait = wait if wait is not None else AsyncMock(return_value=0)
    return proc


def _patch_subprocess(
    mocker: Any, proc: MagicMock | None = None
) -> tuple[Any, MagicMock]:
    proc = proc or _fake_process()
    create = mocker.patch(
        "asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=proc),
    )
    return create, proc


def _counting_clock(step: float = 5.0) -> Any:
    """Relógio monotônico falso que avança ``step`` a cada chamada (deadline determinístico)."""
    counter = itertools.count(0.0, step)
    return lambda: next(counter)


# ---------------------------------------------------------------------------
# Conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_port(self) -> None:
        assert isinstance(VLLMServerManagerAdapter(), VLLMServerManagerPort)

    def test_no_is_healthy_method(self) -> None:
        """O port define wait_healthy(), NÃO is_healthy() — não deve existir no adapter."""
        assert not hasattr(VLLMServerManagerAdapter, "is_healthy")


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------


class TestStart:
    async def test_judge_handle_batch_invariant_true(self, mocker: Any) -> None:
        _patch_subprocess(mocker, _fake_process(pid=5))
        adapter = VLLMServerManagerAdapter()
        handle = await adapter.start(_judge_spec())
        assert handle.batch_invariant is True

    async def test_generator_handle_batch_invariant_false(self, mocker: Any) -> None:
        _patch_subprocess(mocker, _fake_process(pid=6))
        adapter = VLLMServerManagerAdapter()
        handle = await adapter.start(_generator_spec())
        assert handle.batch_invariant is False

    async def test_command_built_without_shell(self, mocker: Any) -> None:
        create, _ = _patch_subprocess(mocker, _fake_process(pid=111))
        adapter = VLLMServerManagerAdapter()
        await adapter.start(_generator_spec(port=8000, quantization="awq"))
        # create_subprocess_exec é a API sem shell; nenhum shell=True é passado.
        assert "shell" not in create.call_args.kwargs
        args = create.call_args.args
        assert "vllm.entrypoints.openai.api_server" in args
        assert "--model" in args and "llama3-8b" in args
        assert "--port" in args and "8000" in args
        assert "--tensor-parallel-size" in args and "2" in args
        assert "--max-model-len" in args and "8192" in args
        assert "--quantization" in args and "awq" in args

    async def test_command_omits_quantization_when_none(self, mocker: Any) -> None:
        create, _ = _patch_subprocess(mocker)
        adapter = VLLMServerManagerAdapter()
        await adapter.start(_generator_spec(port=8000, quantization=None))
        assert "--quantization" not in create.call_args.args

    async def test_env_extends_os_environ_with_extra_env(
        self, mocker: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SENTINEL_VAR", "xyz")
        create, _ = _patch_subprocess(mocker)
        adapter = VLLMServerManagerAdapter()
        await adapter.start(_judge_spec(port=8001))
        env = create.call_args.kwargs["env"]
        # os.environ preservado (não substituído)
        assert env["SENTINEL_VAR"] == "xyz"
        # extra_env do juiz mesclado — só aparece porque está no ModelSpec
        assert env["VLLM_BATCH_INVARIANT"] == "1"
        assert env["VLLM_ENABLE_V1_MULTIPROCESSING"] == "0"

    async def test_generator_env_has_no_batch_invariant(self, mocker: Any) -> None:
        create, _ = _patch_subprocess(mocker)
        adapter = VLLMServerManagerAdapter()
        await adapter.start(_generator_spec(port=8000))
        env = create.call_args.kwargs["env"]
        assert "VLLM_BATCH_INVARIANT" not in env

    async def test_generator_does_not_inherit_regime_from_parent_env(
        self, mocker: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regressão 019-B: orquestrador com regime no ambiente NÃO contamina o gerador.

        O regime juiz/gerador deve ser decidido exclusivamente por ModelSpec.extra_env —
        as chaves de regime são saneadas do os.environ herdado.
        """
        monkeypatch.setenv("VLLM_BATCH_INVARIANT", "1")
        monkeypatch.setenv("VLLM_ENABLE_V1_MULTIPROCESSING", "0")
        monkeypatch.setenv("SENTINEL_VAR", "keep-me")
        create, _ = _patch_subprocess(mocker)
        adapter = VLLMServerManagerAdapter()
        handle = await adapter.start(_generator_spec(port=8000))  # extra_env={}
        env = create.call_args.kwargs["env"]
        # chaves de regime saneadas do ambiente herdado
        assert "VLLM_BATCH_INVARIANT" not in env
        assert "VLLM_ENABLE_V1_MULTIPROCESSING" not in env
        # variáveis não-regime do ambiente pai continuam preservadas
        assert env["SENTINEL_VAR"] == "keep-me"
        # handle coerente com o ambiente real do processo
        assert handle.batch_invariant is False

    async def test_judge_overrides_parent_regime_env(
        self, mocker: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """O juiz fixa o regime via extra_env, independentemente do ambiente pai."""
        monkeypatch.setenv("VLLM_BATCH_INVARIANT", "0")  # valor "errado" no pai
        create, _ = _patch_subprocess(mocker)
        adapter = VLLMServerManagerAdapter()
        handle = await adapter.start(_judge_spec(port=8001))
        env = create.call_args.kwargs["env"]
        assert env["VLLM_BATCH_INVARIANT"] == "1"  # vem do extra_env, não do pai
        assert handle.batch_invariant is True

    async def test_handle_fields_and_log(self, mocker: Any) -> None:
        _patch_subprocess(mocker, _fake_process(pid=777))
        adapter = VLLMServerManagerAdapter()
        with structlog.testing.capture_logs() as logs:
            handle = await adapter.start(_generator_spec(port=8000))
        assert handle.pid == 777
        assert handle.url == "http://localhost:8000/v1"
        assert handle.model == "llama3-8b"
        started = [e for e in logs if e["event"] == "vllm_server_started"]
        assert started
        assert started[0]["batch_invariant"] is False
        assert started[0]["pid"] == 777
        assert started[0]["port"] == 8000

    async def test_start_does_not_poll_health(self, mocker: Any) -> None:
        """O polling de /health é responsabilidade de wait_healthy, não de start()."""
        _patch_subprocess(mocker, _fake_process(pid=9))
        adapter = VLLMServerManagerAdapter()
        with respx.mock(assert_all_called=False) as router:
            route = router.get("http://localhost:8000/health").mock(
                return_value=httpx.Response(200)
            )
            await adapter.start(_generator_spec(port=8000))
            assert not route.called


# ---------------------------------------------------------------------------
# wait_healthy()
# ---------------------------------------------------------------------------


class TestWaitHealthy:
    async def test_returns_on_200(self, mocker: Any) -> None:
        _patch_subprocess(mocker, _fake_process(pid=4321))
        adapter = VLLMServerManagerAdapter(_poll_interval_s=0.0)
        handle = await adapter.start(_generator_spec(port=8000))
        with respx.mock:
            route = respx.get("http://localhost:8000/health").mock(
                return_value=httpx.Response(200)
            )
            await adapter.wait_healthy(handle, timeout_s=10)
            assert route.called

    async def test_polls_until_healthy(self, mocker: Any) -> None:
        _patch_subprocess(mocker, _fake_process(pid=4321))
        adapter = VLLMServerManagerAdapter(_poll_interval_s=0.0)
        handle = await adapter.start(_generator_spec(port=8000))
        with respx.mock:
            respx.get("http://localhost:8000/health").mock(
                side_effect=[httpx.Response(503), httpx.Response(200)]
            )
            await adapter.wait_healthy(handle, timeout_s=10)

    async def test_recovers_from_connection_error(self, mocker: Any) -> None:
        """Erro de rede transitório (servidor ainda subindo) é tratado como 'não saudável'."""
        _patch_subprocess(mocker, _fake_process(pid=4321))
        adapter = VLLMServerManagerAdapter(_poll_interval_s=0.0)
        handle = await adapter.start(_generator_spec(port=8000))
        with respx.mock:
            respx.get("http://localhost:8000/health").mock(
                side_effect=[httpx.ConnectError("refused"), httpx.Response(200)]
            )
            await adapter.wait_healthy(handle, timeout_s=10)

    async def test_timeout_raises_and_kills_process(self, mocker: Any) -> None:
        kill = mocker.patch("os.kill")
        _patch_subprocess(mocker, _fake_process(pid=4321))
        adapter = VLLMServerManagerAdapter(
            _poll_interval_s=0.0, _clock=_counting_clock(step=5.0)
        )
        handle = await adapter.start(_generator_spec(port=8000))
        with respx.mock:
            respx.get("http://localhost:8000/health").mock(
                return_value=httpx.Response(503)
            )
            with pytest.raises(ServerStartTimeoutError):
                await adapter.wait_healthy(handle, timeout_s=10)
        sigs = [c.args for c in kill.call_args_list]
        assert (4321, signal.SIGKILL) in sigs

    async def test_timeout_on_untracked_handle(self, mocker: Any) -> None:
        """Timeout em handle não rastreado (process None) ainda levanta sem explodir."""
        mocker.patch("os.kill")
        adapter = VLLMServerManagerAdapter(
            _poll_interval_s=0.0, _clock=_counting_clock(step=5.0)
        )
        handle = ServerHandle(
            pid=9999,
            url="http://localhost:8000/v1",
            model="ghost",
            batch_invariant=False,
        )
        with respx.mock:
            respx.get("http://localhost:8000/health").mock(
                return_value=httpx.Response(503)
            )
            with pytest.raises(ServerStartTimeoutError):
                await adapter.wait_healthy(handle, timeout_s=10)


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------


class TestStop:
    async def test_sigterm_then_clean_exit(self, mocker: Any) -> None:
        kill = mocker.patch("os.kill")
        _patch_subprocess(
            mocker, _fake_process(pid=222, wait=AsyncMock(return_value=0))
        )
        adapter = VLLMServerManagerAdapter()
        handle = await adapter.start(_generator_spec(port=8000))
        with structlog.testing.capture_logs() as logs:
            await adapter.stop(handle)
        sigs = [c.args for c in kill.call_args_list]
        assert (222, signal.SIGTERM) in sigs
        assert (222, signal.SIGKILL) not in sigs
        stopped = [e for e in logs if e["event"] == "vllm_server_stopped"]
        assert stopped and stopped[0]["forced"] is False

    async def test_escalates_to_sigkill_on_timeout(self, mocker: Any) -> None:
        kill = mocker.patch("os.kill")
        _patch_subprocess(mocker, _fake_process(pid=333, wait=_SlowThenFast()))
        adapter = VLLMServerManagerAdapter(_sigterm_timeout_s=0.01)
        handle = await adapter.start(_generator_spec(port=8000))
        with structlog.testing.capture_logs() as logs:
            await adapter.stop(handle)
        sigs = [c.args for c in kill.call_args_list]
        assert (333, signal.SIGTERM) in sigs
        assert (333, signal.SIGKILL) in sigs
        stopped = [e for e in logs if e["event"] == "vllm_server_stopped"]
        assert stopped and stopped[0]["forced"] is True

    async def test_already_dead_process_is_noop(self, mocker: Any) -> None:
        """SIGTERM em processo inexistente (ProcessLookupError) não escala nem explode."""
        kill = mocker.patch("os.kill", side_effect=ProcessLookupError)
        _patch_subprocess(mocker, _fake_process(pid=444))
        adapter = VLLMServerManagerAdapter()
        handle = await adapter.start(_generator_spec(port=8000))
        with structlog.testing.capture_logs() as logs:
            await adapter.stop(handle)
        # Apenas SIGTERM tentado; sem SIGKILL pois o processo já não existe.
        sigs = [c.args for c in kill.call_args_list]
        assert (444, signal.SIGTERM) in sigs
        assert (444, signal.SIGKILL) not in sigs
        stopped = [e for e in logs if e["event"] == "vllm_server_stopped"]
        assert stopped and stopped[0]["forced"] is False

    async def test_stop_untracked_handle(self, mocker: Any) -> None:
        """stop em handle não rastreado: SIGTERM best-effort, process None → forced False."""
        kill = mocker.patch("os.kill")
        adapter = VLLMServerManagerAdapter()
        handle = ServerHandle(
            pid=8888,
            url="http://localhost:8000/v1",
            model="ghost",
            batch_invariant=False,
        )
        await adapter.stop(handle)
        sigs = [c.args for c in kill.call_args_list]
        assert (8888, signal.SIGTERM) in sigs


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


class TestClose:
    async def test_stops_all_live_handles(self, mocker: Any) -> None:
        kill = mocker.patch("os.kill")
        _patch_subprocess(mocker, _fake_process(pid=10))
        adapter = VLLMServerManagerAdapter()
        await adapter.start(_generator_spec(port=8000))
        _patch_subprocess(mocker, _fake_process(pid=11))
        await adapter.start(_generator_spec(port=8002))

        await adapter.close()

        killed = [c.args[0] for c in kill.call_args_list]
        assert 10 in killed
        assert 11 in killed
        # Idempotente: segunda chamada não tem handles a parar.
        kill.reset_mock()
        await adapter.close()
        assert kill.call_count == 0

    async def test_close_on_fresh_adapter_is_noop(self, mocker: Any) -> None:
        kill = mocker.patch("os.kill")
        adapter = VLLMServerManagerAdapter()
        await adapter.close()
        assert kill.call_count == 0
