"""VLLMServerManagerAdapter — ciclo de vida de servidores vLLM locais (§9.3).

Implementa ``VLLMServerManagerPort`` orquestrando processos vLLM locais via
``asyncio.create_subprocess_exec`` (Nota M1 item 9 — **não** usa Docker SDK, que fica
reservado para M3/produção). Em M1 o adapter é exercitado apenas com subprocess
mockado; nunca inicia um vLLM real em CI.

Notas de design:

- **Async-first** (Nota M1 item 1): ``start``/``wait_healthy``/``stop`` são ``async`` —
  ``start`` lança o processo, ``wait_healthy`` faz polling de ``/health`` via
  ``httpx.AsyncClient``, ``stop`` encerra com ``SIGTERM`` → ``SIGKILL``.
- **``close()`` é extensão de ciclo de vida** — encerra todos os handles ainda vivos;
  NÃO pertence ao port (análogo a ``QdrantRetrieverAdapter.close``).
- **Juiz vs. gerador (§9.2)**: o regime BATCH_INVARIANT (ADR-003) é decidido pelo
  ``extra_env`` do :class:`~inteligenciomica_eval.domain.ports.ModelSpec`, nunca
  *hardcoded* aqui — ``ServerHandle.batch_invariant`` deriva de
  ``"VLLM_BATCH_INVARIANT" in model.extra_env``. As chaves de regime são **saneadas** do
  ``os.environ`` herdado antes de aplicar ``extra_env`` (ver ``_build_env``), de modo que
  um gerador (``extra_env={}``) nunca herde o regime do juiz de um orquestrador que por
  acaso já tenha essas variáveis no ambiente (correção auditoria 019-B).
- **Segurança**: ``shell=False`` sempre (lista de args, nunca string de shell) — sem
  risco de injeção (DoD §14.2).
- **Testabilidade**: ``_poll_interval_s``, ``_sigterm_timeout_s`` e ``_clock`` são
  injetáveis (convenção ``_`` do projeto) para tornar o polling/timeout determinístico
  nos testes, sem espera de relógio real.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import time
from collections.abc import Callable

import httpx
import structlog

from inteligenciomica_eval.domain.errors import ServerStartTimeoutError
from inteligenciomica_eval.domain.ports import ModelSpec, ServerHandle

_log = structlog.get_logger(__name__)

_VLLM_ENTRYPOINT = "vllm.entrypoints.openai.api_server"
_BATCH_INVARIANT_ENV = "VLLM_BATCH_INVARIANT"
# Chaves de ambiente que decidem o regime de determinismo (§9.2/ADR-003). São
# removidas do os.environ herdado antes de aplicar model.extra_env, de modo que o
# regime juiz/gerador seja decidido EXCLUSIVAMENTE por model.extra_env — nunca herdado
# do ambiente do processo orquestrador (correção auditoria 019-B).
_RESERVED_REGIME_ENV = frozenset(
    {
        _BATCH_INVARIANT_ENV,
        "VLLM_ENABLE_V1_MULTIPROCESSING",
    }
)
_DEFAULT_HOST = "localhost"
_DEFAULT_POLL_INTERVAL_S = 2.0
_DEFAULT_SIGTERM_TIMEOUT_S = 30.0
_HEALTH_REQUEST_TIMEOUT_S = 5.0


class VLLMServerManagerAdapter:
    """Gerencia processos vLLM locais via ``asyncio`` subprocess (Nota M1 item 9).

    Args:
        host: host onde o vLLM expõe a API (padrão ``"localhost"``); compõe a
            ``ServerHandle.url`` junto com ``model.port``.
        _poll_interval_s: intervalo entre polls de ``/health`` em ``wait_healthy``
            (padrão ``2.0`` s — §spec). Injetável para testes.
        _sigterm_timeout_s: prazo de espera após ``SIGTERM`` antes do ``SIGKILL`` em
            ``stop`` (padrão ``30.0`` s). Injetável para testes.
        _clock: relógio monotônico usado para o deadline de ``wait_healthy`` (padrão
            :func:`time.monotonic`). Injetável para testes determinísticos.
    """

    def __init__(
        self,
        *,
        host: str = _DEFAULT_HOST,
        _poll_interval_s: float = _DEFAULT_POLL_INTERVAL_S,
        _sigterm_timeout_s: float = _DEFAULT_SIGTERM_TIMEOUT_S,
        _clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._host = host
        self._poll_interval_s = _poll_interval_s
        self._sigterm_timeout_s = _sigterm_timeout_s
        self._clock = _clock
        self._processes: dict[int, asyncio.subprocess.Process] = {}
        self._handles: dict[int, ServerHandle] = {}

    # ------------------------------------------------------------------
    # VLLMServerManagerPort interface
    # ------------------------------------------------------------------

    async def start(self, model: ModelSpec) -> ServerHandle:
        """Lança um servidor vLLM para ``model`` e devolve seu :class:`ServerHandle`.

        O comando é montado como lista de args (``shell=False``) e o processo recebe
        o ambiente de :meth:`_build_env` — ``os.environ`` estendido por ``model.extra_env``,
        mas com as chaves de regime (:data:`_RESERVED_REGIME_ENV`) saneadas do ambiente
        herdado para que juiz/gerador seja decidido só por ``extra_env``.

        Args:
            model: especificação do modelo (inclui ``port`` e ``extra_env``).

        Returns:
            :class:`ServerHandle` com ``pid``, ``url`` (sufixo ``/v1``), ``model`` e
            ``batch_invariant`` derivado de ``"VLLM_BATCH_INVARIANT" in model.extra_env``.
        """
        command = self._build_command(model)
        process = await asyncio.create_subprocess_exec(
            *command,
            env=self._build_env(model),
        )
        batch_invariant = _BATCH_INVARIANT_ENV in model.extra_env
        handle = ServerHandle(
            pid=process.pid,
            url=f"http://{self._host}:{model.port}/v1",
            model=model.model,
            batch_invariant=batch_invariant,
        )
        self._processes[handle.pid] = process
        self._handles[handle.pid] = handle
        _log.info(
            "vllm_server_started",
            model=model.model,
            port=model.port,
            batch_invariant=batch_invariant,
            pid=handle.pid,
        )
        return handle

    async def wait_healthy(self, handle: ServerHandle, timeout_s: int) -> None:
        """Faz polling de ``GET {base}/health`` a cada ``_poll_interval_s`` até ``200``.

        Args:
            handle: handle do servidor a aguardar.
            timeout_s: prazo máximo, em segundos.

        Raises:
            ServerStartTimeoutError: se ``/health`` não responder ``200`` dentro do
                prazo. O processo é encerrado (``SIGKILL``) antes de levantar.
        """
        health_url = handle.url.replace("/v1", "") + "/health"
        deadline = self._clock() + timeout_s
        async with httpx.AsyncClient() as client:
            while self._clock() < deadline:
                if await self._health_ok(client, health_url):
                    _log.info(
                        "vllm_server_healthy",
                        model=handle.model,
                        pid=handle.pid,
                        url=health_url,
                    )
                    return
                await asyncio.sleep(self._poll_interval_s)

        await self._force_kill(handle)
        _log.error(
            "vllm_server_start_timeout",
            model=handle.model,
            pid=handle.pid,
            timeout_s=timeout_s,
        )
        raise ServerStartTimeoutError(handle.model, float(timeout_s))

    async def stop(self, handle: ServerHandle) -> None:
        """Encerra o servidor com ``SIGTERM`` e escala para ``SIGKILL`` em timeout.

        Args:
            handle: handle do servidor a parar.
        """
        process = self._processes.get(handle.pid)
        sent = self._signal(handle.pid, signal.SIGTERM)
        forced = await self._await_exit(process, handle.pid) if sent else False
        self._forget(handle.pid)
        _log.info(
            "vllm_server_stopped",
            model=handle.model,
            pid=handle.pid,
            forced=forced,
        )

    async def close(self) -> None:
        """Encerra todos os servidores ainda vivos rastreados pelo adapter."""
        for handle in list(self._handles.values()):
            await self.stop(handle)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_command(self, model: ModelSpec) -> list[str]:
        """Monta a lista de args do ``api_server`` vLLM a partir de ``model`` (sem shell)."""
        command = [
            sys.executable,
            "-m",
            _VLLM_ENTRYPOINT,
            "--model",
            model.model,
            "--port",
            str(model.port),
            "--tensor-parallel-size",
            str(model.tensor_parallel_size),
            "--max-model-len",
            str(model.max_model_len),
        ]
        if model.quantization is not None:
            command += ["--quantization", model.quantization]
        return command

    @staticmethod
    def _build_env(model: ModelSpec) -> dict[str, str]:
        """Monta o ambiente do subprocess: ``os.environ`` saneado + ``model.extra_env``.

        As chaves de regime (:data:`_RESERVED_REGIME_ENV`) são **removidas** do
        ``os.environ`` herdado antes de aplicar ``model.extra_env``. Assim o regime de
        determinismo (juiz vs. gerador, §9.2/ADR-003) é decidido **exclusivamente** por
        ``model.extra_env`` — um gerador com ``extra_env={}`` nunca herda
        ``VLLM_BATCH_INVARIANT``/``VLLM_ENABLE_V1_MULTIPROCESSING`` de um orquestrador que
        por acaso as tenha definido (correção auditoria 019-B).
        """
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in _RESERVED_REGIME_ENV
        }
        env.update(model.extra_env)
        return env

    async def _health_ok(self, client: httpx.AsyncClient, health_url: str) -> bool:
        """``True`` se ``/health`` responde ``200``; ``False`` em erro de rede ou status."""
        try:
            response = await client.get(health_url, timeout=_HEALTH_REQUEST_TIMEOUT_S)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    @staticmethod
    def _signal(pid: int, sig: signal.Signals) -> bool:
        """Envia ``sig`` ao ``pid``; ``False`` se o processo já não existe."""
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return False
        return True

    async def _await_exit(
        self, process: asyncio.subprocess.Process | None, pid: int
    ) -> bool:
        """Aguarda a saída do processo; em timeout envia ``SIGKILL``. ``True`` se forçou."""
        if process is None:
            return False
        try:
            await asyncio.wait_for(process.wait(), timeout=self._sigterm_timeout_s)
            return False
        except TimeoutError:
            self._signal(pid, signal.SIGKILL)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=self._sigterm_timeout_s)
            return True

    async def _force_kill(self, handle: ServerHandle) -> None:
        """Mata o processo com ``SIGKILL`` (startup falho) e o esquece."""
        process = self._processes.get(handle.pid)
        self._signal(handle.pid, signal.SIGKILL)
        if process is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=self._sigterm_timeout_s)
        self._forget(handle.pid)

    def _forget(self, pid: int) -> None:
        """Remove o processo/handle do rastreamento interno."""
        self._processes.pop(pid, None)
        self._handles.pop(pid, None)
