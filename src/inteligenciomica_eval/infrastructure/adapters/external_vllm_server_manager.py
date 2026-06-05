"""ExternalVLLMServerManager — adapter para servidores vLLM pré-existentes (TAREFA-311, ADR-014).

Implementa ``VLLMServerManagerPort`` para o modo de implantação ``external``:
os servidores (geradores e juiz) já estão em execução e são acessados via
túnel (ex.: SSH tunnel, ngrok). Nenhum subprocess é criado nem encerrado.

Contratos:
- ``start()``: resolve a URL a partir do mapa ``endpoint_map``; não inicia processo.
- ``wait_healthy()``: realiza ``GET /health`` com backoff até ``timeout_s``; levanta
  ``EndpointUnreachableError`` se o servidor não responder.
- ``stop()``: no-op — não encerra servidores externos.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from urllib.parse import urlparse

import httpx
import structlog

from inteligenciomica_eval.domain.errors import EndpointUnreachableError
from inteligenciomica_eval.domain.ports import ModelSpec, ServerHandle

_log = structlog.get_logger(__name__)

_DEFAULT_POLL_INTERVAL_S: float = 2.0
_DEFAULT_HEALTH_TIMEOUT_S: float = 5.0


def _mask_url(url: str) -> str:
    """Mascara credenciais em URLs para logs (ADR-008).

    Remove ``user:password@`` se presentes; exibe apenas ``scheme://host:port/***``.

    Args:
        url: URL possivelmente contendo credenciais.

    Returns:
        URL anonimizada para exibição segura em logs.
    """
    try:
        p = urlparse(url)
        masked = f"{p.scheme}://{p.hostname}"
        if p.port:
            masked += f":{p.port}"
        masked += "/***"
        return masked
    except Exception:
        return "***"


def _parse_port(url: str) -> int:
    """Extrai a porta de uma URL; retorna 80 se não explícita.

    Args:
        url: URL do endpoint (ex.: ``"http://localhost:8000/v1"``).

    Returns:
        Porta TCP como inteiro.
    """
    try:
        parsed = urlparse(url)
        return parsed.port or 80
    except Exception:
        return 80


class ExternalVLLMServerManager:
    """Adapter VLLMServerManagerPort para servidores externos (ADR-014).

    Em vez de criar subprocessos, resolve URLs a partir de um mapeamento
    ``{model_name: url}`` injetado no construtor. O wiring (``build_container``)
    é responsável por resolver as env vars e montar esse mapa antes de
    instanciar este adapter.

    Args:
        endpoint_map: dicionário ``{model_name: url}`` com as URLs completas
            (incluindo ``/v1``) dos endpoints tunelados.
        _poll_interval_s: intervalo de polling em ``wait_healthy()`` (injetável
            para testes).
        _health_timeout_s: timeout de cada requisição ``GET /health`` (injetável
            para testes).
        _now: callable zero-args que retorna o tempo atual em epoch seconds
            (injetável para testes; default: ``time.time``).
    """

    def __init__(
        self,
        endpoint_map: dict[str, str],
        *,
        _poll_interval_s: float = _DEFAULT_POLL_INTERVAL_S,
        _health_timeout_s: float = _DEFAULT_HEALTH_TIMEOUT_S,
        _now: Callable[[], float] = time.time,
    ) -> None:
        self._endpoint_map = endpoint_map
        self._poll_interval_s = _poll_interval_s
        self._health_timeout_s = _health_timeout_s
        self._now = _now

    async def start(self, model: ModelSpec) -> ServerHandle:
        """Resolve a URL do endpoint externo e retorna um ServerHandle sem PID.

        Args:
            model: especificação do modelo a "iniciar" (sem subprocess).

        Returns:
            :class:`~inteligenciomica_eval.domain.ports.ServerHandle` com
            ``pid=None`` e ``gpu_index=-1`` (sem alocação local).

        Raises:
            EndpointUnreachableError: se o modelo não estiver no ``endpoint_map``.
        """
        url = self._endpoint_map.get(model.model)
        if not url:
            raise EndpointUnreachableError(
                model.model,
                f"model not found in endpoint_map; known: {sorted(self._endpoint_map)}",
            )
        port = _parse_port(url)
        handle = ServerHandle(
            pid=None,
            url=url,
            model=model.model,
            batch_invariant=model.batch_invariant,
            port=port,
            gpu_index=-1,
            started_at=self._now(),
        )
        _log.info(
            "external_server_start",
            model=model.model,
            url=_mask_url(url),
            batch_invariant=model.batch_invariant,
        )
        return handle

    async def wait_healthy(self, handle: ServerHandle, timeout_s: int) -> None:
        """Aguarda o endpoint responder a ``GET /health`` dentro do prazo.

        Realiza polling com intervalo ``_poll_interval_s`` até ``timeout_s``
        segundos. Usa ``httpx.AsyncClient`` diretamente (sem SDK OpenAI).

        Args:
            handle: handle do servidor externo.
            timeout_s: prazo máximo em segundos.

        Raises:
            EndpointUnreachableError: se o servidor não responder dentro do prazo.
        """
        base = handle.url.rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        health_url = f"{base}/health"

        deadline = self._now() + timeout_s
        last_error: str = "unknown"
        while self._now() < deadline:
            try:
                async with httpx.AsyncClient(timeout=self._health_timeout_s) as client:
                    resp = await client.get(health_url)
                    if resp.status_code < 300:
                        _log.info(
                            "external_server_healthy",
                            model=handle.model,
                            url=_mask_url(health_url),
                            status=resp.status_code,
                        )
                        return
                    last_error = f"HTTP {resp.status_code}"
            except httpx.HTTPError as exc:
                last_error = str(exc)
            await asyncio.sleep(self._poll_interval_s)

        raise EndpointUnreachableError(
            handle.model,
            f"did not respond to GET {_mask_url(health_url)} within {timeout_s}s; "
            f"last error: {last_error}",
        )

    async def stop(self, handle: ServerHandle) -> None:
        """No-op — não encerra servidores externos.

        Apenas loga o evento para auditoria de ciclo de vida (ADR-014).

        Args:
            handle: handle do servidor externo (não usado).
        """
        _log.info(
            "external_server_stop_noop",
            model=handle.model,
            url=_mask_url(handle.url),
        )
