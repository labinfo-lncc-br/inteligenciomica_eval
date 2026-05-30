"""Testes do VLLMServerManagerAdapter (TAREFA-302).

Local canônico da spec (``tests/integration/adapters/``). É **mock-based** — NÃO inicia
vLLM real nem exige Docker, por isso NÃO leva ``pytest.mark.integration`` (roda no job
``unit``/gate de cobertura, não no job de containers). Estratégia (Nota M3 item 2):
``asyncio.create_subprocess_exec`` mockado via pytest-mock + ``respx`` para ``/health``;
``os.kill`` mockado; relógios (``_clock``/``_now``) e intervalos injetados tornam
polling/timeout determinísticos e instantâneos.
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

from inteligenciomica_eval.domain.errors import (
    ModelSwitchError,
    ServerStartTimeoutError,
)
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
    """ModelSpec do juiz: batch_invariant=True, GPU 3 (ADR-003/ADR-012)."""
    return ModelSpec(
        model="prometheus-8x7b",
        port=port,
        quantization="awq",
        tensor_parallel_size=1,
        max_model_len=4096,
        gpu_index=3,
        batch_invariant=True,
        extra_args={},
    )


def _generator_spec(
    port: int = 8000,
    quantization: str | None = None,
    gpu_index: int = 0,
    extra_args: dict[str, str] | None = None,
) -> ModelSpec:
    """ModelSpec do gerador: batch_invariant=False (§9.2.4), GPUs 0/1/2."""
    return ModelSpec(
        model="llama3-8b",
        port=port,
        quantization=quantization,
        tensor_parallel_size=2,
        max_model_len=8192,
        gpu_index=gpu_index,
        batch_invariant=False,
        extra_args=extra_args if extra_args is not None else {},
    )


# ---------------------------------------------------------------------------
# Mocks de subprocess / streams
# ---------------------------------------------------------------------------


class _FakeStream:
    """``asyncio.StreamReader`` mínimo: emite ``lines`` e depois EOF (``b""``)."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = [line.encode() for line in lines]

    async def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        return b""


class _SlowThenFast:
    """``process.wait()``: bloqueia na 1ª chamada (cancelada por ``wait_for`` → timeout)
    e retorna imediatamente nas seguintes (simula SIGKILL surtindo efeito)."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self) -> int:
        self.calls += 1
        if self.calls == 1:
            await asyncio.sleep(3600)
        return 0


def _fake_process(
    pid: int = 4321,
    *,
    wait: Any = None,
    returncode: int | None = None,
    stderr_lines: list[str] | None = None,
    stdout_lines: list[str] | None = None,
) -> MagicMock:
    proc = MagicMock()
    proc.pid = pid
    proc.returncode = returncode  # None => vivo (NÃO deixar como MagicMock!)
    proc.wait = wait if wait is not None else AsyncMock(return_value=0)
    proc.stderr = _FakeStream(stderr_lines) if stderr_lines is not None else None
    proc.stdout = _FakeStream(stdout_lines) if stdout_lines is not None else None
    return proc


def _patch_subprocess(
    mocker: Any, proc: MagicMock | None = None
) -> tuple[Any, MagicMock]:
    """Mocka ``create_subprocess_exec`` e neutraliza o bind real de ``_port_in_use``."""
    proc = proc or _fake_process()
    create = mocker.patch(
        "asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=proc),
    )
    mocker.patch.object(VLLMServerManagerAdapter, "_port_in_use", return_value=False)
    return create, proc


def _counting_clock(step: float = 5.0) -> Any:
    """Relógio falso que avança ``step`` a cada chamada (deadline determinístico)."""
    counter = itertools.count(0.0, step)
    return lambda: next(counter)


def _untracked_handle(pid: int = 9999, port: int = 8000) -> ServerHandle:
    return ServerHandle(
        pid=pid,
        url=f"http://localhost:{port}/v1",
        model="ghost",
        batch_invariant=False,
        port=port,
        gpu_index=0,
        started_at=0.0,
    )


# ---------------------------------------------------------------------------
# Conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_satisfies_port(self) -> None:
        assert isinstance(VLLMServerManagerAdapter(), VLLMServerManagerPort)

    def test_no_public_is_healthy_method(self) -> None:
        """O port define wait_healthy(); is_healthy é PRIVADO (_is_healthy)."""
        assert not hasattr(VLLMServerManagerAdapter, "is_healthy")
        assert hasattr(VLLMServerManagerAdapter, "_is_healthy")


# ---------------------------------------------------------------------------
# start() — comando, ambiente, regime, GPU pinning
# ---------------------------------------------------------------------------


class TestStart:
    async def test_judge_handle_batch_invariant_true(self, mocker: Any) -> None:
        _patch_subprocess(mocker, _fake_process(pid=5))
        handle = await VLLMServerManagerAdapter().start(_judge_spec())
        assert handle.batch_invariant is True

    async def test_generator_handle_batch_invariant_false(self, mocker: Any) -> None:
        _patch_subprocess(mocker, _fake_process(pid=6))
        handle = await VLLMServerManagerAdapter().start(_generator_spec())
        assert handle.batch_invariant is False

    async def test_command_built_without_shell(self, mocker: Any) -> None:
        create, _ = _patch_subprocess(mocker, _fake_process(pid=111))
        await VLLMServerManagerAdapter().start(
            _generator_spec(port=8000, quantization="awq")
        )
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
        await VLLMServerManagerAdapter().start(_generator_spec(quantization=None))
        assert "--quantization" not in create.call_args.args

    async def test_extra_args_appended_as_cli_flags(self, mocker: Any) -> None:
        """extra_args = flags de CLI (decisão TAREFA-302), apendadas como --nome valor."""
        create, _ = _patch_subprocess(mocker)
        spec = _generator_spec(
            extra_args={"gpu-memory-utilization": "0.9", "enforce-eager": "true"}
        )
        await VLLMServerManagerAdapter().start(spec)
        args = list(create.call_args.args)
        assert "--gpu-memory-utilization" in args
        assert args[args.index("--gpu-memory-utilization") + 1] == "0.9"
        assert "--enforce-eager" in args

    async def test_cuda_visible_devices_injected_for_judge(self, mocker: Any) -> None:
        create, _ = _patch_subprocess(mocker)
        await VLLMServerManagerAdapter().start(_judge_spec(port=8001))
        env = create.call_args.kwargs["env"]
        assert env["CUDA_VISIBLE_DEVICES"] == "3"  # ADR-012: juiz na GPU 3

    async def test_cuda_visible_devices_injected_for_generator(
        self, mocker: Any
    ) -> None:
        create, _ = _patch_subprocess(mocker)
        await VLLMServerManagerAdapter().start(_generator_spec(port=8000, gpu_index=2))
        env = create.call_args.kwargs["env"]
        assert env["CUDA_VISIBLE_DEVICES"] == "2"  # ADR-012: gerador na GPU 0/1/2

    async def test_judge_env_has_regime_vars_injected(self, mocker: Any) -> None:
        """ADR-003: o adapter INJETA o regime a partir da flag batch_invariant=True."""
        create, _ = _patch_subprocess(mocker)
        await VLLMServerManagerAdapter().start(_judge_spec(port=8001))
        env = create.call_args.kwargs["env"]
        assert env["VLLM_BATCH_INVARIANT"] == "1"
        assert env["VLLM_ENABLE_V1_MULTIPROCESSING"] == "0"

    async def test_generator_env_has_no_regime_vars(self, mocker: Any) -> None:
        """ADR-003: gerador (batch_invariant=False) fica provadamente sem regime."""
        create, _ = _patch_subprocess(mocker)
        await VLLMServerManagerAdapter().start(_generator_spec(port=8000))
        env = create.call_args.kwargs["env"]
        assert "VLLM_BATCH_INVARIANT" not in env
        assert "VLLM_ENABLE_V1_MULTIPROCESSING" not in env

    async def test_generator_does_not_inherit_regime_from_parent_env(
        self, mocker: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regressão 019-B: regime no ambiente do orquestrador NÃO contamina o gerador."""
        monkeypatch.setenv("VLLM_BATCH_INVARIANT", "1")
        monkeypatch.setenv("VLLM_ENABLE_V1_MULTIPROCESSING", "0")
        monkeypatch.setenv("SENTINEL_VAR", "keep-me")
        create, _ = _patch_subprocess(mocker)
        handle = await VLLMServerManagerAdapter().start(_generator_spec(port=8000))
        env = create.call_args.kwargs["env"]
        assert "VLLM_BATCH_INVARIANT" not in env
        assert "VLLM_ENABLE_V1_MULTIPROCESSING" not in env
        assert env["SENTINEL_VAR"] == "keep-me"  # não-regime preservado
        assert handle.batch_invariant is False

    async def test_judge_overrides_parent_regime_env(
        self, mocker: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """O juiz fixa o regime via flag, sobrepondo valor 'errado' do ambiente pai."""
        monkeypatch.setenv("VLLM_BATCH_INVARIANT", "0")
        create, _ = _patch_subprocess(mocker)
        handle = await VLLMServerManagerAdapter().start(_judge_spec(port=8001))
        env = create.call_args.kwargs["env"]
        assert env["VLLM_BATCH_INVARIANT"] == "1"
        assert handle.batch_invariant is True

    async def test_handle_fields_and_log(self, mocker: Any) -> None:
        _patch_subprocess(mocker, _fake_process(pid=777))
        adapter = VLLMServerManagerAdapter(_now=_counting_clock(step=1.0))
        with structlog.testing.capture_logs() as logs:
            handle = await adapter.start(_generator_spec(port=8000, gpu_index=1))
        assert handle.pid == 777
        assert handle.url == "http://localhost:8000/v1"
        assert handle.model == "llama3-8b"
        assert handle.port == 8000
        assert handle.gpu_index == 1
        assert handle.started_at == pytest.approx(0.0)
        started = [e for e in logs if e["event"] == "vllm_server_started"]
        assert started
        assert started[0]["batch_invariant"] is False
        assert started[0]["pid"] == 777
        assert started[0]["port"] == 8000
        assert started[0]["gpu_index"] == 1

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
# start() — porta ocupada → ModelSwitchError
# ---------------------------------------------------------------------------


class TestPortCollision:
    async def test_second_start_same_port_raises_model_switch(
        self, mocker: Any
    ) -> None:
        _patch_subprocess(mocker, _fake_process(pid=1))
        adapter = VLLMServerManagerAdapter()
        await adapter.start(_generator_spec(port=8000))
        with pytest.raises(ModelSwitchError) as exc:
            await adapter.start(_judge_spec(port=8000))
        assert "8000" in str(exc.value)

    async def test_externally_bound_port_raises_model_switch(self, mocker: Any) -> None:
        mocker.patch.object(VLLMServerManagerAdapter, "_port_in_use", return_value=True)
        # subprocess NÃO deve ser alcançado (a recusa ocorre antes do spawn).
        create = mocker.patch("asyncio.create_subprocess_exec", new=AsyncMock())
        with pytest.raises(ModelSwitchError):
            await VLLMServerManagerAdapter().start(_generator_spec(port=8000))
        assert create.call_count == 0

    async def test_stale_handle_does_not_block_port_reuse(self, mocker: Any) -> None:
        """Handle stale (processo morto) NÃO bloqueia reinício na mesma porta (302-B)."""
        _patch_subprocess(mocker, _fake_process(pid=1, returncode=1))  # morre logo
        adapter = VLLMServerManagerAdapter()
        await adapter.start(_generator_spec(port=8000))
        # 2º start na MESMA porta, processo vivo: permitido (handle stale é liberado).
        _patch_subprocess(mocker, _fake_process(pid=2, returncode=None))
        handle2 = await adapter.start(_generator_spec(port=8000))
        assert handle2.pid == 2
        assert 1 not in adapter._handles  # stale esquecido

    def test_port_in_use_true_when_bind_fails(self, mocker: Any) -> None:
        """_port_in_use=True quando o bind falha. Hermético: ``socket`` mockado (o
        sandbox do auditor proíbe sockets AF_INET reais — PermissionError)."""
        ctx = mocker.patch("socket.socket").return_value.__enter__.return_value
        ctx.bind.side_effect = OSError("address already in use")
        assert VLLMServerManagerAdapter()._port_in_use(9999) is True

    def test_port_in_use_false_when_bind_succeeds(self, mocker: Any) -> None:
        """_port_in_use=False quando o bind tem sucesso (porta livre). Socket mockado."""
        ctx = mocker.patch("socket.socket").return_value.__enter__.return_value
        ctx.bind.return_value = None
        assert VLLMServerManagerAdapter()._port_in_use(9999) is False


# ---------------------------------------------------------------------------
# wait_healthy()
# ---------------------------------------------------------------------------


class TestWaitHealthy:
    async def test_returns_on_200(self, mocker: Any) -> None:
        _patch_subprocess(mocker, _fake_process(pid=4321))
        adapter = VLLMServerManagerAdapter(_poll_initial_s=0.0)
        handle = await adapter.start(_generator_spec(port=8000))
        with respx.mock:
            route = respx.get("http://localhost:8000/health").mock(
                return_value=httpx.Response(200)
            )
            await adapter.wait_healthy(handle, timeout_s=10)
            assert route.called

    async def test_polls_until_healthy_with_backoff(self, mocker: Any) -> None:
        _patch_subprocess(mocker, _fake_process(pid=4321))
        adapter = VLLMServerManagerAdapter(_poll_initial_s=0.0, _poll_max_s=0.0)
        handle = await adapter.start(_generator_spec(port=8000))
        with respx.mock:
            respx.get("http://localhost:8000/health").mock(
                side_effect=[httpx.Response(503), httpx.Response(200)]
            )
            await adapter.wait_healthy(handle, timeout_s=10)

    async def test_recovers_from_connection_error(self, mocker: Any) -> None:
        """Erro de rede transitório (servidor subindo) é tratado como 'não saudável'."""
        _patch_subprocess(mocker, _fake_process(pid=4321))
        adapter = VLLMServerManagerAdapter(_poll_initial_s=0.0)
        handle = await adapter.start(_generator_spec(port=8000))
        with respx.mock:
            respx.get("http://localhost:8000/health").mock(
                side_effect=[httpx.ConnectError("refused"), httpx.Response(200)]
            )
            await adapter.wait_healthy(handle, timeout_s=10)

    async def test_timeout_raises_kills_and_logs_stderr_tail(self, mocker: Any) -> None:
        kill = mocker.patch("os.kill")
        proc = _fake_process(
            pid=4321, stderr_lines=["boot...", "CUDA OOM: fatal error"]
        )
        _patch_subprocess(mocker, proc)
        adapter = VLLMServerManagerAdapter(
            _poll_initial_s=0.0, _clock=_counting_clock(step=5.0)
        )
        handle = await adapter.start(_generator_spec(port=8000))
        with respx.mock:
            respx.get("http://localhost:8000/health").mock(
                return_value=httpx.Response(503)
            )
            with (
                structlog.testing.capture_logs() as logs,
                pytest.raises(ServerStartTimeoutError) as exc_info,
            ):
                await adapter.wait_healthy(handle, timeout_s=10)
        assert (4321, signal.SIGKILL) in [c.args for c in kill.call_args_list]
        # contexto carregado NA exceção (auditoria 302-B), não só no log
        err = exc_info.value
        assert err.reason == "timeout"
        assert err.pid == 4321
        assert "CUDA OOM" in (err.stderr_tail or "")
        failed = [e for e in logs if e["event"] == "vllm_server_start_failed"]
        assert failed and failed[0]["reason"] == "timeout"
        assert "CUDA OOM" in failed[0]["stderr_tail"]

    async def test_process_death_raises_immediately_with_stderr(
        self, mocker: Any
    ) -> None:
        """Processo morre antes do timeout ⇒ ServerStartTimeoutError imediata + stderr."""
        kill = mocker.patch("os.kill")
        proc = _fake_process(
            pid=4321, returncode=1, stderr_lines=["fatal: model not found"]
        )
        _patch_subprocess(mocker, proc)
        adapter = VLLMServerManagerAdapter(_poll_initial_s=0.0)
        handle = await adapter.start(_generator_spec(port=8000))
        with respx.mock:
            respx.get("http://localhost:8000/health").mock(
                return_value=httpx.Response(503)
            )
            with (
                structlog.testing.capture_logs() as logs,
                pytest.raises(ServerStartTimeoutError) as exc_info,
            ):
                await adapter.wait_healthy(handle, timeout_s=600)
        err = exc_info.value
        assert err.reason == "process_exited"
        assert err.pid == 4321
        assert "model not found" in (err.stderr_tail or "")
        failed = [e for e in logs if e["event"] == "vllm_server_start_failed"]
        assert failed and failed[0]["reason"] == "process_exited"
        assert "model not found" in failed[0]["stderr_tail"]
        assert kill.called  # SIGKILL de limpeza

    async def test_timeout_on_untracked_handle(self, mocker: Any) -> None:
        """Timeout em handle não rastreado (process None) levanta sem explodir."""
        mocker.patch("os.kill")
        adapter = VLLMServerManagerAdapter(
            _poll_initial_s=0.0, _clock=_counting_clock(step=5.0)
        )
        handle = _untracked_handle(pid=9999, port=8000)
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
        assert stopped[0]["gpu_index"] == 0

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
        sigs = [c.args for c in kill.call_args_list]
        assert (444, signal.SIGTERM) in sigs
        assert (444, signal.SIGKILL) not in sigs
        stopped = [e for e in logs if e["event"] == "vllm_server_stopped"]
        assert stopped and stopped[0]["forced"] is False

    async def test_stop_untracked_handle(self, mocker: Any) -> None:
        """stop em handle não rastreado: SIGTERM best-effort, process None → forced False."""
        kill = mocker.patch("os.kill")
        adapter = VLLMServerManagerAdapter()
        handle = _untracked_handle(pid=8888, port=8000)
        await adapter.stop(handle)
        sigs = [c.args for c in kill.call_args_list]
        assert (8888, signal.SIGTERM) in sigs


# ---------------------------------------------------------------------------
# Drenagem de pipes (stdout/stderr) + cancelamento
# ---------------------------------------------------------------------------


class TestDrains:
    async def test_stdout_and_stderr_drained_and_cancelled_on_stop(
        self, mocker: Any
    ) -> None:
        """stdout/stderr são drenados em tasks de fundo; stop cancela/limpa o estado."""
        kill = mocker.patch("os.kill")
        proc = _fake_process(
            pid=555,
            stderr_lines=["warmup line"],
            stdout_lines=["serving on 8000"],
        )
        _patch_subprocess(mocker, proc)
        adapter = VLLMServerManagerAdapter()
        handle = await adapter.start(_generator_spec(port=8000))
        # Estado de drenagem registrado para o pid.
        assert handle.pid in adapter._drain_tasks
        await adapter.stop(handle)
        assert kill.called
        # Após stop, todo o estado interno do pid foi esquecido.
        assert handle.pid not in adapter._drain_tasks
        assert handle.pid not in adapter._stderr_tails


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
        await VLLMServerManagerAdapter().close()
        assert kill.call_count == 0
