"""Sondas de proveniência de endpoint para modo external (TAREFA-311, ADR-014).

Três sondas assíncronas independentes:
- :func:`probe_served_model`: identifica o modelo servido via ``GET /v1/models``.
- :func:`probe_vllm_version`: obtém a versão do vLLM via ``GET /version``.
- :func:`probe_judge_determinism`: verifica se o juiz é determinístico enviando
  a mesma prompt duas vezes e comparando as respostas byte a byte.

Todas as sondas retornam valores sentinela (``None`` / ``False``) em caso de erro,
sem propagar exceções — falha em sonda nunca deve interromper a execução (ADR-014).
"""

from __future__ import annotations

import httpx
import structlog

from inteligenciomica_eval.infrastructure.masking import mask_url

_log = structlog.get_logger(__name__)

_TIMEOUT_S: float = 10.0
_PROBE_PROMPT = "Responda com a palavra DETERMINISMO."


async def probe_served_model(url: str) -> str:
    """Identifica o primeiro modelo servido via ``GET /v1/models``.

    Chama ``{url}/v1/models`` (sem sufixo duplicado se ``url`` já termina em ``/v1``).

    Args:
        url: URL base do servidor (com ou sem ``/v1``).

    Returns:
        ID do primeiro modelo listado, ou ``""`` em caso de falha.
    """
    base = url.rstrip("/")
    # Evita duplo /v1 se o url já o inclui.
    models_url = f"{base}/models" if base.endswith("/v1") else f"{base}/v1/models"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.get(models_url)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", [])
            if models:
                model_id: str = str(models[0].get("id", ""))
                _log.info(
                    "probe_served_model_ok", url=mask_url(models_url), model_id=model_id
                )
                return model_id
            _log.warning("probe_served_model_empty", url=mask_url(models_url))
            return ""
    except Exception as exc:
        _log.warning(
            "probe_served_model_failed", url=mask_url(models_url), error=str(exc)
        )
        return ""


async def probe_vllm_version(url: str) -> str | None:
    """Tenta obter a versão do vLLM via múltiplas fontes, em ordem de preferência.

    Fontes tentadas na ordem:
    1. ``GET /version`` → campo ``"version"`` no JSON.
    2. Header ``x-vllm-version`` de qualquer resposta bem-sucedida.
    3. Campo ``"created"`` / ``"meta"`` de ``GET /v1/models`` (metadata).

    Args:
        url: URL base do servidor.

    Returns:
        String de versão (ex.: ``"0.4.3"``), ou ``None`` se nenhuma fonte a fornecer.
    """
    base = url.rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    version_url = f"{base}/version"
    models_url = f"{base}/v1/models"

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            # Fonte 1: GET /version
            try:
                resp = await client.get(version_url)
                if resp.status_code < 300:
                    data = resp.json()
                    ver: str = str(data.get("version", ""))
                    if ver:
                        _log.info(
                            "probe_vllm_version_ok", source="/version", version=ver
                        )
                        return ver
                    # Fonte 2: header na resposta de /version
                    header_ver: str = str(resp.headers.get("x-vllm-version", ""))
                    if header_ver:
                        _log.info(
                            "probe_vllm_version_ok", source="header", version=header_ver
                        )
                        return header_ver
            except Exception:
                pass

            # Fonte 3: metadata de /v1/models
            try:
                resp2 = await client.get(models_url)
                if resp2.status_code < 300:
                    # Header em resposta de /v1/models
                    header_ver2: str = str(resp2.headers.get("x-vllm-version", ""))
                    if header_ver2:
                        _log.info(
                            "probe_vllm_version_ok",
                            source="models_header",
                            version=header_ver2,
                        )
                        return header_ver2
            except Exception:
                pass

        _log.warning("probe_vllm_version_unavailable", url=mask_url(version_url))
        return None
    except Exception as exc:
        _log.warning(
            "probe_vllm_version_failed", url=mask_url(version_url), error=str(exc)
        )
        return None


async def probe_judge_determinism(url: str) -> bool:
    """Verifica se o juiz é determinístico enviando a mesma prompt duas vezes.

    Usa ``POST /v1/chat/completions`` com ``temperature=0.0`` e ``seed=42``
    duas vezes com o mesmo prompt e compara as respostas byte a byte.

    Args:
        url: URL base do servidor (com ou sem ``/v1``).

    Returns:
        ``True`` se ambas as respostas são idênticas; ``False`` se divergem ou
        se a sonda falhou por qualquer razão.
    """
    base = url.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    completions_url = f"{base}/chat/completions"

    payload = {
        "model": "",  # Aceito por qualquer modelo; vLLM ignora se houver apenas 1
        "messages": [{"role": "user", "content": _PROBE_PROMPT}],
        "temperature": 0.0,
        "max_tokens": 32,
        "seed": 42,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp1 = await client.post(completions_url, json=payload)
            resp1.raise_for_status()
            resp2 = await client.post(completions_url, json=payload)
            resp2.raise_for_status()

        text1: str = resp1.json()["choices"][0]["message"]["content"]
        text2: str = resp2.json()["choices"][0]["message"]["content"]
        deterministic = text1 == text2
        _log.info(
            "probe_judge_determinism_ok",
            url=mask_url(completions_url),
            deterministic=deterministic,
        )
        return deterministic
    except Exception as exc:
        _log.warning(
            "probe_judge_determinism_failed",
            url=mask_url(completions_url),
            error=str(exc),
        )
        return False
