"""VLLMServerManagerAdapter — ciclo de vida de servidores vLLM locais (§9.3, TAREFA-302).

Implementa ``VLLMServerManagerPort`` orquestrando processos vLLM locais via
``asyncio.create_subprocess_exec`` (Nota M3 item 2 — **não** usa Docker SDK, que fica
reservado para produção). O adapter é exercitado apenas com subprocess mockado; nunca
inicia um vLLM real em CI.

Notas de design:

- **Async-first** (Nota M1 item 1 / Nota M3 item 2): ``start``/``wait_healthy``/``stop``
  são ``async`` — o Port de domínio (``VLLMServerManagerPort``) é assíncrono. Onde a spec
  da TAREFA-302 menciona ``subprocess.Popen`` + *threads daemon* para drenar pipes, a
  implementação async-first usa o equivalente direto: ``asyncio.create_subprocess_exec``
  com ``stdout``/``stderr`` em ``PIPE`` drenados por **tasks de fundo** (mesma garantia de
  não-bloqueio/anti-deadlock que as threads daemon dariam, sem sair do modelo async).
- **Regime por FLAG (ADR-003, decisão TAREFA-302)**: o regime juiz vs. gerador é decidido
  por ``ModelSpec.batch_invariant`` — o adapter **injeta** ``VLLM_BATCH_INVARIANT=1`` e
  ``VLLM_ENABLE_V1_MULTIPROCESSING=0`` *sse* a flag for ``True``. As chaves de regime são
  saneadas do ``os.environ`` herdado antes da injeção, de modo que um gerador
  (``batch_invariant=False``) fique **provadamente** sem essas variáveis, mesmo que o
  orquestrador as tenha no ambiente. ``ServerHandle.batch_invariant`` reflete a flag.
- **GPU pinning (ADR-012)**: ``CUDA_VISIBLE_DEVICES=str(model.gpu_index)`` é injetado para
  TODOS os modelos (juiz=GPU 3; geradores=GPUs 0/1/2).
- **``extra_args`` são flags de CLI** (não env): apendadas ao comando como ``--nome valor``.
- **Porta ocupada → ``ModelSwitchError``**: ``start`` recusa uma porta já servida por outro
  handle vivo ou ligada por outro processo (tentativa de bind ao socket).
- **``close()`` é extensão de ciclo de vida** — encerra todos os handles ainda vivos; NÃO
  pertence ao port (análogo a ``QdrantRetrieverAdapter.close``).
- **Segurança**: ``shell=False`` sempre (lista de args, nunca string de shell).
- **Testabilidade**: ``_poll_initial_s``/``_poll_max_s``/``_sigterm_timeout_s``/``_clock``/
  ``_now`` são injetáveis (convenção ``_`` do projeto) para tornar polling/timeout/relógio
  determinísticos nos testes, sem espera real.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import socket
import sys
import time
from collections import deque
from collections.abc import Callable

import httpx
import structlog

from inteligenciomica_eval.domain.errors import (
    ModelSwitchError,
    ServerStartTimeoutError,
)
from inteligenciomica_eval.domain.ports import ModelSpec, ServerHandle

_log = structlog.get_logger(__name__)

_VLLM_ENTRYPOINT = "vllm.entrypoints.openai.api_server"
_CUDA_VISIBLE_DEVICES = "CUDA_VISIBLE_DEVICES"
_BATCH_INVARIANT_ENV = "VLLM_BATCH_INVARIANT"
_MULTIPROCESSING_ENV = "VLLM_ENABLE_V1_MULTIPROCESSING"
# Chaves de ambiente que decidem o regime de determinismo (§9.2/ADR-003). São removidas
# do os.environ herdado antes da injeção pelo adapter, de modo que o regime juiz/gerador
# seja decidido EXCLUSIVAMENTE pela flag ModelSpec.batch_invariant — nunca herdado do
# ambiente do processo orquestrador (correção auditoria 019-B, preservada na 302).
_RESERVED_REGIME_ENV = frozenset({_BATCH_INVARIANT_ENV, _MULTIPROCESSING_ENV})
_DEFAULT_HOST = "localhost"
_DEFAULT_POLL_INITIAL_S = 1.0
_DEFAULT_POLL_MAX_S = 15.0
_DEFAULT_SIGTERM_TIMEOUT_S = 30.0
_HEALTH_REQUEST_TIMEOUT_S = 2.0
_STDERR_TAIL_LINES = 20
_DRAIN_GRACE_S = 2.0


class VLLMServerManagerAdapter:
    """Gerencia processos vLLM locais via ``asyncio`` subprocess (Nota M3 item 2).

    Args:
        host: host onde o vLLM expõe a API (padrão ``"localhost"``); compõe a
            ``ServerHandle.url`` junto com ``model.port``.
        _poll_initial_s: intervalo inicial do backoff exponencial de ``wait_healthy``
            (padrão ``1.0`` s — §spec). Injetável para testes.
        _poll_max_s: teto do backoff exponencial de ``wait_healthy`` (padrão ``15.0`` s).
            Injetável para testes.
        _sigterm_timeout_s: prazo de espera após ``SIGTERM`` antes do ``SIGKILL`` em
            ``stop`` (padrão ``30.0`` s). Injetável para testes.
        _clock: relógio monotônico usado para o deadline de ``wait_healthy`` (padrão
            :func:`time.monotonic`). Injetável para testes determinísticos.
        _now: relógio de parede usado em ``ServerHandle.started_at`` (padrão
            :func:`time.time`). Injetável para testes.
    """

    def __init__(
        self,
        *,
        host: str = _DEFAULT_HOST,
        _poll_initial_s: float = _DEFAULT_POLL_INITIAL_S,
        _poll_max_s: float = _DEFAULT_POLL_MAX_S,
        _sigterm_timeout_s: float = _DEFAULT_SIGTERM_TIMEOUT_S,
        _clock: Callable[[], float] = time.monotonic,
        _now: Callable[[], float] = time.time,
    ) -> None:
        self._host = host
        self._poll_initial_s = _poll_initial_s
        self._poll_max_s = _poll_max_s
        self._sigterm_timeout_s = _sigterm_timeout_s
        self._clock = _clock
        self._now = _now
        self._processes: dict[int, asyncio.subprocess.Process] = {}
        self._handles: dict[int, ServerHandle] = {}
        self._stderr_tails: dict[int, deque[str]] = {}
        self._drain_tasks: dict[int, list[asyncio.Task[None]]] = {}

    # ------------------------------------------------------------------
    # VLLMServerManagerPort interface
    # ------------------------------------------------------------------

    async def start(self, model: ModelSpec) -> ServerHandle:
        """Lança um servidor vLLM para ``model`` e devolve seu :class:`ServerHandle`.

        O comando é montado como lista de args (``shell=False``) e o processo recebe o
        ambiente de :meth:`_build_env` — ``os.environ`` saneado das chaves de regime,
        ``CUDA_VISIBLE_DEVICES`` fixado em ``model.gpu_index`` (ADR-012) e, se
        ``model.batch_invariant``, as variáveis de regime injetadas (ADR-003). Recusa a
        porta com :class:`ModelSwitchError` se já estiver ocupada.

        Args:
            model: especificação do modelo (inclui ``port``, ``gpu_index``,
                ``batch_invariant`` e ``extra_args``).

        Returns:
            :class:`ServerHandle` com ``pid``, ``url`` (sufixo ``/v1``), ``model``,
            ``batch_invariant`` (= ``model.batch_invariant``), ``port``, ``gpu_index`` e
            ``started_at``.

        Raises:
            ModelSwitchError: se ``model.port`` já estiver servido por outro handle vivo
                ou ligada por outro processo.
        """
        self._assert_port_available(model)
        t0 = self._clock()
        command = self._build_command(model)
        process = await asyncio.create_subprocess_exec(
            *command,
            env=self._build_env(model),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        handle = ServerHandle(
            pid=process.pid,
            url=f"http://{self._host}:{model.port}/v1",
            model=model.model,
            batch_invariant=model.batch_invariant,
            port=model.port,
            gpu_index=model.gpu_index,
            started_at=self._now(),
        )
        # VLLMServerManagerAdapter sempre cria processos locais com PID inteiro;
        # pid=None é exclusivo do ExternalVLLMServerManager (ADR-014).
        assert handle.pid is not None, "managed adapter always has a real PID"
        self._processes[handle.pid] = process
        self._handles[handle.pid] = handle
        self._spawn_drains(handle.pid, process)
        _log.info(
            "vllm_server_started",
            model=model.model,
            port=model.port,
            gpu_index=model.gpu_index,
            batch_invariant=model.batch_invariant,
            pid=handle.pid,
            elapsed_ms=round((self._clock() - t0) * 1000.0, 3),
        )
        return handle

    async def wait_healthy(self, handle: ServerHandle, timeout_s: int) -> None:
        """Faz polling de ``GET {base}/health`` com backoff exponencial até ``200``.

        Args:
            handle: handle do servidor a aguardar.
            timeout_s: prazo máximo, em segundos.

        Raises:
            ServerStartTimeoutError: se o processo morrer antes de ficar saudável, ou se
                ``/health`` não responder ``200`` dentro do prazo. Em ambos os casos o
                ``tail`` das últimas 20 linhas de ``stderr`` é logado e o processo é
                encerrado (``SIGKILL``) antes de levantar.
        """
        deadline = self._clock() + timeout_s
        interval = self._poll_initial_s
        while self._clock() < deadline:
            if await self._is_healthy(handle):
                _log.info(
                    "vllm_server_healthy",
                    model=handle.model,
                    port=handle.port,
                    pid=handle.pid,
                    gpu_index=handle.gpu_index,
                    batch_invariant=handle.batch_invariant,
                    elapsed_ms=self._elapsed_ms(handle),
                )
                return
            if self._process_died(handle):
                await self._fail(handle, timeout_s, reason="process_exited")
            await asyncio.sleep(interval)
            interval = min(self._poll_max_s, interval * 2)

        await self._fail(handle, timeout_s, reason="timeout")

    async def stop(self, handle: ServerHandle) -> None:
        """Encerra o servidor com ``SIGTERM`` e escala para ``SIGKILL`` em timeout.

        Args:
            handle: handle do servidor a parar.
        """
        # VLLMServerManagerAdapter só recebe handles com pid inteiro (criados em start()).
        assert handle.pid is not None, "managed stop() called with external handle"
        process = self._processes.get(handle.pid)
        sent = self._signal(handle.pid, signal.SIGTERM)
        forced = await self._await_exit(process, handle.pid) if sent else False
        await self._cancel_drains(handle.pid)
        self._forget(handle.pid)
        _log.info(
            "vllm_server_stopped",
            model=handle.model,
            port=handle.port,
            pid=handle.pid,
            gpu_index=handle.gpu_index,
            batch_invariant=handle.batch_invariant,
            elapsed_ms=self._elapsed_ms(handle),
            forced=forced,
        )

    async def close(self) -> None:
        """Encerra todos os servidores ainda vivos rastreados pelo adapter."""
        for handle in list(self._handles.values()):
            await self.stop(handle)

    # ------------------------------------------------------------------
    # Internals — comando e ambiente
    # ------------------------------------------------------------------

    def _build_command(self, model: ModelSpec) -> list[str]:
        """Monta a lista de args do ``api_server`` vLLM a partir de ``model`` (sem shell).

        ``extra_args`` (flags de CLI adicionais) são apendadas como ``--nome valor``.
        """
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
        for key, value in model.extra_args.items():
            command += [f"--{key}", value]
        return command

    @staticmethod
    def _build_env(model: ModelSpec) -> dict[str, str]:
        """Monta o ambiente do subprocess (ADR-003/ADR-012).

        Parte de ``os.environ`` **saneado** das chaves de regime
        (:data:`_RESERVED_REGIME_ENV`), fixa ``CUDA_VISIBLE_DEVICES`` em
        ``model.gpu_index`` (ADR-012) e, **só se** ``model.batch_invariant``, injeta
        ``VLLM_BATCH_INVARIANT=1`` / ``VLLM_ENABLE_V1_MULTIPROCESSING=0`` (ADR-003). Assim
        um gerador (``batch_invariant=False``) fica provadamente sem essas variáveis,
        mesmo que o orquestrador as tenha definido no ambiente.
        """
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in _RESERVED_REGIME_ENV
        }
        env[_CUDA_VISIBLE_DEVICES] = str(model.gpu_index)
        if model.batch_invariant:
            env[_BATCH_INVARIANT_ENV] = "1"
            env[_MULTIPROCESSING_ENV] = "0"
        return env

    def _assert_port_available(self, model: ModelSpec) -> None:
        """Recusa ``model.port`` se já servida (handle **vivo**) ou ligada (bind ao socket).

        Handles *stale* (processo já morto) NÃO bloqueiam — são esquecidos e a porta é
        reavaliada via socket, permitindo reinício após uma morte inesperada (auditoria
        302-B): o bloqueio só ocorre enquanto o processo dono da porta está vivo.
        """
        for handle in list(self._handles.values()):
            if handle.port != model.port:
                continue
            if handle.pid is None:
                continue  # external handle — não gerenciado aqui
            process = self._processes.get(handle.pid)
            if process is not None and process.returncode is None:
                raise ModelSwitchError(
                    from_model=handle.model,
                    to_model=model.model,
                    reason=f"port {model.port} is already serving {handle.model!r}",
                )
            # Handle stale (processo morto/ausente): libera a porta e esquece o handle.
            self._forget(handle.pid)
        if self._port_in_use(model.port):
            raise ModelSwitchError(
                from_model="unknown",
                to_model=model.model,
                reason=f"port {model.port} is already bound by another process",
            )

    def _port_in_use(self, port: int) -> bool:
        """``True`` se o bind a ``(host, port)`` falha (porta já ocupada por outro processo)."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((self._host, port))
            except OSError:
                return True
        return False

    # ------------------------------------------------------------------
    # Internals — health check
    # ------------------------------------------------------------------

    async def _is_healthy(self, handle: ServerHandle) -> bool:
        """``True`` se ``GET {base}/health`` responde ``200`` em < 2 s; ``False`` se não.

        Auxiliar PRIVADO usado por :meth:`wait_healthy` (NÃO faz parte do Port §5.1).
        Erro de rede (servidor ainda subindo) ou status != 200 ⇒ ``False`` (sem exceção).
        """
        health_url = handle.url.replace("/v1", "") + "/health"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    health_url, timeout=_HEALTH_REQUEST_TIMEOUT_S
                )
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def _process_died(self, handle: ServerHandle) -> bool:
        """``True`` se o processo rastreado já terminou (``returncode`` definido)."""
        if handle.pid is None:
            return False  # external handle — sem processo local
        process = self._processes.get(handle.pid)
        return process is not None and process.returncode is not None

    async def _fail(self, handle: ServerHandle, timeout_s: int, *, reason: str) -> None:
        """Encerra o processo e levanta ``ServerStartTimeoutError`` com o contexto.

        O ``tail`` de stderr, ``pid`` e ``reason`` são logados **e** carregados na própria
        exceção (auditoria 302-B) — o orquestrador (TAREFA-307) acessa a causa-raiz sem
        reparsear logs.
        """
        assert handle.pid is not None  # managed adapter sempre tem pid
        await self._force_kill(handle)
        stderr_tail = await self._collect_stderr_tail(handle.pid)
        _log.error(
            "vllm_server_start_failed",
            model=handle.model,
            port=handle.port,
            pid=handle.pid,
            gpu_index=handle.gpu_index,
            reason=reason,
            elapsed_ms=self._elapsed_ms(handle),
            stderr_tail=stderr_tail,
        )
        await self._cancel_drains(handle.pid)
        self._forget(handle.pid)
        raise ServerStartTimeoutError(
            handle.model,
            float(timeout_s),
            pid=handle.pid,
            reason=reason,
            stderr_tail=stderr_tail or None,
        )

    # ------------------------------------------------------------------
    # Internals — sinais e ciclo de vida do processo
    # ------------------------------------------------------------------

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
        """Mata o processo com ``SIGKILL`` (startup falho) e aguarda sua saída."""
        assert handle.pid is not None  # managed adapter sempre tem pid
        process = self._processes.get(handle.pid)
        self._signal(handle.pid, signal.SIGKILL)
        if process is not None:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=self._sigterm_timeout_s)

    # ------------------------------------------------------------------
    # Internals — drenagem de pipes (anti-deadlock) + tail de stderr
    # ------------------------------------------------------------------

    def _spawn_drains(self, pid: int, process: asyncio.subprocess.Process) -> None:
        """Cria tasks de fundo que drenam stdout/stderr (anti-deadlock, §spec TAREFA-302).

        Equivalente async-first das *threads daemon* da spec: leem os pipes sem bloquear o
        fluxo principal. As linhas de stderr são retidas num anel de 20 (``tail``).
        """
        self._stderr_tails[pid] = deque(maxlen=_STDERR_TAIL_LINES)
        tasks: list[asyncio.Task[None]] = []
        if process.stderr is not None:
            tasks.append(
                asyncio.create_task(self._drain(process.stderr, pid, capture=True))
            )
        if process.stdout is not None:
            tasks.append(
                asyncio.create_task(self._drain(process.stdout, pid, capture=False))
            )
        self._drain_tasks[pid] = tasks

    async def _drain(
        self, reader: asyncio.StreamReader, pid: int, *, capture: bool
    ) -> None:
        """Lê linhas de ``reader`` até EOF; retém as de stderr no anel de ``tail``."""
        while True:
            line = await reader.readline()
            if not line:
                break
            text = line.decode(errors="replace").rstrip()
            if capture:
                self._stderr_tails[pid].append(text)

    async def _collect_stderr_tail(self, pid: int) -> str:
        """Aguarda (com folga) os drains terminarem e devolve o ``tail`` de stderr."""
        tasks = self._drain_tasks.get(pid, [])
        if tasks:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=_DRAIN_GRACE_S,
                )
        lines = self._stderr_tails.get(pid)
        return "\n".join(lines) if lines else ""

    async def _cancel_drains(self, pid: int) -> None:
        """Cancela as tasks de drenagem ainda vivas do ``pid``."""
        for task in self._drain_tasks.pop(pid, []):
            if not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    def _elapsed_ms(self, handle: ServerHandle) -> float:
        """Milissegundos decorridos desde ``handle.started_at`` (auditoria/logs)."""
        return round((self._now() - handle.started_at) * 1000.0, 3)

    def _forget(self, pid: int) -> None:
        """Remove o processo/handle/buffers do rastreamento interno."""
        self._processes.pop(pid, None)
        self._handles.pop(pid, None)
        self._stderr_tails.pop(pid, None)
        self._drain_tasks.pop(pid, None)
