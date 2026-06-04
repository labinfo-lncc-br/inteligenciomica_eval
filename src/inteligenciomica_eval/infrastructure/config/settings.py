from __future__ import annotations

import os
import re

from pydantic_settings import BaseSettings, SettingsConfigDict


class RuntimeSettings(BaseSettings):
    """Runtime secrets and endpoint URLs — sourced exclusively from environment variables.

    Never persisted in or read from the YAML round config (ADR-008). The YAML
    stores only the *name* of the env var (e.g. ``endpoint_env: VLLM_JUDGE_URL``);
    this class resolves the actual values at runtime.

    Attributes:
        VLLM_GENERATOR_URL: URL of the vLLM generator server.
        VLLM_JUDGE_URL: URL of the vLLM judge server.
        QDRANT_URL: URL of the Qdrant vector database.
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        case_sensitive=True,
    )

    VLLM_GENERATOR_URL: str = "<not set>"
    VLLM_JUDGE_URL: str = "<not set>"
    QDRANT_URL: str = "<not set>"

    BENCHMARK_QUESTIONS_PATH: str = ""
    """Caminho para um arquivo JSONL externo de perguntas do benchmark.

    String vazia (default) = usar o arquivo ``questions_rf1.jsonl`` empacotado
    no módulo via ``importlib.resources``. Path absoluto ou relativo = arquivo
    externo, útil para testes de integração e futuras rodadas.
    """

    VLLM_STARTUP_TIMEOUT_S: int = 300
    """Tempo máximo (segundos) para aguardar cada servidor vLLM ficar saudável."""

    VLLM_DEFAULT_MAX_MODEL_LEN: int = 4096
    """Comprimento máximo de contexto padrão (tokens) para modelos vLLM."""


def resolve_endpoint(env_var_name: str) -> str:
    """Resolve an endpoint URL from a named environment variable.

    Args:
        env_var_name: name of the environment variable to look up.

    Returns:
        The resolved value, or ``'<not set>'`` if the variable is absent.
    """
    return os.environ.get(env_var_name, "<not set>")


_URL_AUTH_RE: re.Pattern[str] = re.compile(r"(://)[^@]+@")


def mask_endpoint(value: str) -> str:
    """Mask credentials in endpoint URLs for safe display.

    Rules:
    - ``<not set>`` or empty strings pass through unchanged.
    - URLs containing ``://user:pass@host`` have the auth part replaced with ``****@``.
    - Non-URL values (no ``://``) are assumed to be opaque secrets: only the first
      8 characters are shown, followed by ``****``.

    Args:
        value: raw endpoint or secret value.

    Returns:
        A display-safe version of the value.
    """
    if value in ("<not set>", ""):
        return value
    if "://" in value:
        return _URL_AUTH_RE.sub(r"\1****@", value)
    # Non-URL: probably an API key or opaque token — show a minimal prefix only
    return (value[:8] + "****") if len(value) > 8 else "****"
