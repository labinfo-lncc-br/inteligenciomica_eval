"""Testes unitários das sondas de proveniência (TAREFA-311, ADR-014).

Inclui testes de mascaramento de URL nos eventos de log (TAREFA-314 — B1).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import structlog.testing

from inteligenciomica_eval.infrastructure.provenance.endpoint_probe import (
    probe_judge_determinism,
    probe_served_model,
    probe_vllm_version,
)

_BASE_URL = "http://localhost:8000"
_V1_URL = "http://localhost:8000/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(
    status: int = 200,
    json_body: Any = None,
    *,
    x_vllm_version: str = "",
) -> MagicMock:
    """Cria um MagicMock de httpx.Response."""
    resp = MagicMock()
    resp.status_code = status
    resp.json = MagicMock(return_value=json_body or {})
    resp.raise_for_status = MagicMock(
        side_effect=(
            None
            if status < 400
            else httpx.HTTPStatusError("error", request=MagicMock(), response=resp)
        )
    )
    # Simula httpx.Headers.get() retornando vazio por padrão (sem header de versão)
    resp.headers = MagicMock()
    resp.headers.get = MagicMock(return_value=x_vllm_version)
    return resp


def _patch_async_client(
    get_side_effect: Any = None, post_side_effect: Any = None
) -> Any:
    """Context manager que mocka httpx.AsyncClient."""
    mock_client = AsyncMock()
    if get_side_effect is not None:
        mock_client.get = AsyncMock(side_effect=get_side_effect)
    if post_side_effect is not None:
        mock_client.post = AsyncMock(side_effect=post_side_effect)

    patcher = patch(
        "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
    )
    return patcher, mock_client


# ---------------------------------------------------------------------------
# probe_served_model
# ---------------------------------------------------------------------------


async def test_probe_served_model_returns_id() -> None:
    """probe_served_model retorna o id do primeiro modelo."""
    resp = _mock_response(200, {"data": [{"id": "prometheus-2"}]})

    with patch(
        "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await probe_served_model(_V1_URL)

    assert result == "prometheus-2"


async def test_probe_served_model_empty_data_returns_empty() -> None:
    """probe_served_model retorna '' quando data é vazia."""
    resp = _mock_response(200, {"data": []})

    with patch(
        "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await probe_served_model(_BASE_URL)

    assert result == ""


async def test_probe_served_model_network_error_returns_empty() -> None:
    """probe_served_model retorna '' em erro de rede (sem propagar)."""
    with patch(
        "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await probe_served_model(_V1_URL)

    assert result == ""


async def test_probe_served_model_url_with_v1_no_double_v1() -> None:
    """probe_served_model não duplica /v1 quando a URL já termina com /v1."""
    called_urls: list[str] = []
    resp = _mock_response(200, {"data": [{"id": "model-x"}]})

    async def _get(url: str) -> Any:
        called_urls.append(url)
        return resp

    with patch(
        "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = _get
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        await probe_served_model("http://host:8000/v1")

    assert called_urls, "GET deve ter sido chamado"
    assert "/v1/v1/" not in called_urls[0], "URL não deve ter /v1/v1"


# ---------------------------------------------------------------------------
# probe_vllm_version
# ---------------------------------------------------------------------------


async def test_probe_vllm_version_returns_version() -> None:
    resp = _mock_response(200, {"version": "0.4.3"})

    with patch(
        "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await probe_vllm_version(_V1_URL)

    assert result == "0.4.3"


async def test_probe_vllm_version_not_found_returns_none() -> None:
    with patch(
        "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock()
            )
        )
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await probe_vllm_version(_V1_URL)

    assert result is None


async def test_probe_vllm_version_empty_string_returns_none() -> None:
    resp = _mock_response(200, {"version": ""})

    with patch(
        "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=resp)
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await probe_vllm_version(_V1_URL)

    assert result is None


async def test_probe_vllm_version_strips_v1() -> None:
    """probe_vllm_version chama /version na raiz, sem /v1."""
    called_urls: list[str] = []
    resp = _mock_response(200, {"version": "0.5.0"})

    async def _get(url: str) -> Any:
        called_urls.append(url)
        return resp

    with patch(
        "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.get = _get
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        await probe_vllm_version("http://host:8000/v1")

    assert called_urls
    assert "/v1/version" not in called_urls[0]
    assert called_urls[0].endswith("/version")


# ---------------------------------------------------------------------------
# probe_judge_determinism
# ---------------------------------------------------------------------------


async def test_probe_judge_determinism_true_when_same_response() -> None:
    """Retorna True quando ambas as respostas são idênticas."""
    identical_resp = {"choices": [{"message": {"content": "DETERMINISMO"}}]}
    resp1 = _mock_response(200, identical_resp)
    resp2 = _mock_response(200, identical_resp)

    with patch(
        "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[resp1, resp2])
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await probe_judge_determinism(_V1_URL)

    assert result is True


async def test_probe_judge_determinism_false_when_different_response() -> None:
    """Retorna False quando as respostas diferem."""
    resp1 = _mock_response(200, {"choices": [{"message": {"content": "RESP1"}}]})
    resp2 = _mock_response(200, {"choices": [{"message": {"content": "RESP2"}}]})

    with patch(
        "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=[resp1, resp2])
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await probe_judge_determinism(_V1_URL)

    assert result is False


async def test_probe_judge_determinism_false_on_network_error() -> None:
    """Retorna False em erro de rede sem propagar exceção."""
    with patch(
        "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await probe_judge_determinism(_V1_URL)

    assert result is False


async def test_probe_judge_determinism_adds_v1_when_missing() -> None:
    """probe_judge_determinism adiciona /v1 à URL base sem o sufixo."""
    called_urls: list[str] = []
    identical = {"choices": [{"message": {"content": "same"}}]}
    resp = _mock_response(200, identical)

    async def _post(url: str, **kwargs: object) -> Any:
        called_urls.append(url)
        return resp

    with patch(
        "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
    ) as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = _post
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        await probe_judge_determinism("http://host:8000")

    assert called_urls
    assert "/v1/chat/completions" in called_urls[0]


# ---------------------------------------------------------------------------
# Testes de mascaramento de URL nos logs (TAREFA-314 — B1)
# ---------------------------------------------------------------------------

# URL com credenciais e path — o que NÃO deve aparecer nos logs
_CRED_URL = "http://user:secret@probehost:9876/v1"
# Verificações: host+path (indicam URL crua) e credencial
_RAW_HOST_MODELS = "probehost:9876/v1/models"
_RAW_HOST_VERSION = "probehost:9876/version"
_RAW_HOST_COMPLETIONS = "probehost:9876/v1/chat/completions"
_CREDENTIAL_FRAGMENT = "secret"


def _all_log_values(logs: list[dict[str, Any]]) -> list[str]:
    """Coleta todos os valores de log como strings para inspeção."""
    values: list[str] = []
    for ev in logs:
        for v in ev.values():
            values.append(str(v))
    return values


class TestProbesMaskingUrls:
    """Garante que nenhum probe loga URL crua (com path ou credenciais) — TAREFA-314."""

    async def test_probe_served_model_no_raw_url_in_logs(self) -> None:
        """probe_served_model não deve logar path (/v1/models) nem credenciais."""
        resp = _mock_response(200, {"data": [{"id": "modelo"}]})

        with patch(
            "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            with structlog.testing.capture_logs() as logs:
                await probe_served_model(_CRED_URL)

        values = _all_log_values(logs)
        assert logs, "Deve haver ao menos um evento de log"
        for v in values:
            assert _CREDENTIAL_FRAGMENT not in v, f"Credencial vazou no log: {v!r}"
            assert _RAW_HOST_MODELS not in v, f"URL raw (host+path) vazou no log: {v!r}"

    async def test_probe_served_model_error_no_raw_url_in_logs(self) -> None:
        """probe_served_model em falha não deve logar URL crua."""
        with patch(
            "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            with structlog.testing.capture_logs() as logs:
                await probe_served_model(_CRED_URL)

        values = _all_log_values(logs)
        assert logs, "Deve haver evento de falha no log"
        for v in values:
            assert _CREDENTIAL_FRAGMENT not in v, (
                f"Credencial vazou no log de erro: {v!r}"
            )
            assert _RAW_HOST_MODELS not in v, (
                f"URL raw (host+path) vazou no log de erro: {v!r}"
            )

    async def test_probe_vllm_version_no_raw_url_in_logs(self) -> None:
        """probe_vllm_version não deve logar path (/version) nem credenciais."""
        resp = _mock_response(200, {"version": "0.4.3"})

        with patch(
            "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            with structlog.testing.capture_logs() as logs:
                await probe_vllm_version(_CRED_URL)

        values = _all_log_values(logs)
        assert logs, "Deve haver ao menos um evento de log"
        for v in values:
            assert _CREDENTIAL_FRAGMENT not in v, f"Credencial vazou no log: {v!r}"
            # _RAW_HOST_VERSION = "probehost:9876/version" (host+path), não só "/version"
            # porque o probe usa source="/version" como identificador (sem host) — legítimo.
            assert _RAW_HOST_VERSION not in v, (
                f"URL raw (host+path) vazou no log: {v!r}"
            )

    async def test_probe_judge_determinism_no_raw_url_in_logs(self) -> None:
        """probe_judge_determinism não deve logar path (/v1/chat/completions) nem credenciais."""
        identical = {"choices": [{"message": {"content": "DETERMINISMO"}}]}
        resp1 = _mock_response(200, identical)
        resp2 = _mock_response(200, identical)

        with patch(
            "inteligenciomica_eval.infrastructure.provenance.endpoint_probe.httpx.AsyncClient"
        ) as mock_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[resp1, resp2])
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            with structlog.testing.capture_logs() as logs:
                await probe_judge_determinism(_CRED_URL)

        values = _all_log_values(logs)
        assert logs, "Deve haver ao menos um evento de log"
        for v in values:
            assert _CREDENTIAL_FRAGMENT not in v, f"Credencial vazou no log: {v!r}"
            assert _RAW_HOST_COMPLETIONS not in v, (
                f"URL raw (host+path) vazou no log: {v!r}"
            )
