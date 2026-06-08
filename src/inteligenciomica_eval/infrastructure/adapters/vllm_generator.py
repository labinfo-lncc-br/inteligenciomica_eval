from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from typing import Any

import httpx
import openai
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from inteligenciomica_eval.domain.errors import GenerationError
from inteligenciomica_eval.domain.ports import Chunk, GenerationOutput
from inteligenciomica_eval.domain.value_objects import LLMId

_log = structlog.get_logger(__name__)

_RETRYABLE = (openai.APIConnectionError, openai.RateLimitError)

# Strip <think>…</think> blocks emitted by reasoning-capable models (DOTALL so
# multi-line think blocks are removed in one pass — matches production behaviour).
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _default_render_fn(question: str, contexts: Sequence[Chunk]) -> tuple[str, str]:
    """Default render using PromptRegistry with the v1_production bundle (ADR-015)."""
    from inteligenciomica_eval.infrastructure.prompts.registry import (
        get_default_registry,
    )

    return get_default_registry().render_rag_generation(
        version="v1_production",
        question=question,
        contexts=contexts,
    )


class VLLMGeneratorAdapter:
    """Generates text via a vLLM server using the OpenAI-compatible chat API.

    Uses ``openai.AsyncOpenAI`` with ``api_key="EMPTY"`` (vLLM does not enforce
    key auth).  The ``seed`` is forwarded via ``extra_body`` so that vLLM passes
    it to ``SamplingParams`` (§9.3).  ``batch_invariant`` is always ``False``
    for this adapter (§9.2.4).

    The prompt is composed of two messages (system + user) produced by
    ``render_fn`` (ADR-015, TAREFA-316).  When ``render_fn`` is ``None``, the
    default uses :func:`PromptRegistry.render_rag_generation` with the
    ``v1_production`` bundle, which replicates the production prompt verbatim.

    The raw output is stripped of ``<think>…</think>`` blocks before being
    stored in :class:`~inteligenciomica_eval.domain.ports.GenerationOutput`.

    Retries on :class:`openai.APIConnectionError` and :class:`openai.RateLimitError`
    with exponential backoff (multiplier=1, min=1 s, max=8 s, max 3 attempts).
    All other :class:`openai.OpenAIError` subclasses are wrapped immediately in
    :class:`~inteligenciomica_eval.domain.errors.GenerationError`.

    Args:
        url: OpenAI-compatible base URL of the vLLM server, including the ``/v1`` suffix
            (e.g. ``"http://localhost:8000/v1"``).  The URL is passed verbatim to
            ``openai.AsyncOpenAI(base_url=url)``.
        model: model identifier served by vLLM (must match the loaded model name).
        render_fn: ``(question, contexts) -> (system_content, user_content)``; if
            ``None`` the default uses the ``v1_production`` bundle from
            :class:`~inteligenciomica_eval.infrastructure.prompts.registry.PromptRegistry`
            (ADR-015).  Inject a custom callable for tests or alternative bundles.
        http_client: optional ``httpx.AsyncClient`` for testing / transport injection.
        _retry_stop: tenacity stop condition override (for testing — default is
            ``stop_after_attempt(3)``).
        _retry_wait: tenacity wait strategy override (for testing — default is
            ``wait_exponential(multiplier=1, min=1, max=8)``).
    """

    def __init__(
        self,
        url: str,
        model: str,
        *,
        render_fn: (Callable[[str, Sequence[Chunk]], tuple[str, str]] | None) = None,
        http_client: httpx.AsyncClient | None = None,
        _retry_stop: Any = None,
        _retry_wait: Any = None,
    ) -> None:
        self._model = model
        self._render_fn: Callable[[str, Sequence[Chunk]], tuple[str, str]] = (
            render_fn if render_fn is not None else _default_render_fn
        )
        self._client = openai.AsyncOpenAI(
            base_url=url,
            api_key="EMPTY",
            http_client=http_client,
            max_retries=0,  # tenacity owns all retry logic
        )
        self._retry_stop = (
            _retry_stop if _retry_stop is not None else stop_after_attempt(3)
        )
        self._retry_wait = (
            _retry_wait
            if _retry_wait is not None
            else wait_exponential(multiplier=1, min=1, max=8)
        )

    # ------------------------------------------------------------------
    # GeneratorPort interface
    # ------------------------------------------------------------------

    async def generate(
        self,
        *,
        llm: LLMId,
        question: str,
        contexts: Sequence[Chunk],
        seed: int,
        temperature: float,
    ) -> GenerationOutput:
        """Generate a response for *question* given *contexts*.

        Args:
            llm: model identifier used for logging.
            question: question text.
            contexts: sequence of retrieved chunks used as context.
            seed: reproducibility seed forwarded to vLLM via ``extra_body``.
            temperature: sampling temperature forwarded to the API.

        Returns:
            :class:`~inteligenciomica_eval.domain.ports.GenerationOutput` with
            ``batch_invariant=False`` (constant for this adapter, §9.2.4).
            The ``text`` field has ``<think>…</think>`` blocks stripped.

        Raises:
            GenerationError: on any generation failure (including retries exhausted).
        """
        system, user = self._render_fn(question, contexts)
        t0 = time.monotonic()
        response: openai.types.chat.ChatCompletion | None = None

        try:
            async for attempt in AsyncRetrying(
                stop=self._retry_stop,
                wait=self._retry_wait,
                retry=retry_if_exception_type(_RETRYABLE),
                reraise=True,
            ):
                with attempt:
                    response = await self._client.chat.completions.create(
                        model=self._model,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        temperature=temperature,
                        extra_body={"seed": seed},
                    )
        except openai.OpenAIError as exc:
            raise GenerationError(str(exc)) from exc

        latency_ms = int((time.monotonic() - t0) * 1000)

        assert response is not None  # guaranteed: exception raised otherwise
        choice = response.choices[0]
        usage = response.usage

        raw_text = choice.message.content or ""
        text = _THINK_RE.sub("", raw_text).strip()

        output = GenerationOutput(
            text=text,
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
            batch_invariant=False,
        )

        _log.info(
            "vllm_generation_completed",
            llm=llm.value,
            seed=seed,
            tokens_in=output.tokens_in,
            tokens_out=output.tokens_out,
            latency_ms=output.latency_ms,
            batch_invariant=output.batch_invariant,
            system_len=len(system),
            user_len=len(user),
            num_chunks=len(contexts),
        )

        return output

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying httpx transport held by ``AsyncOpenAI``."""
        await self._client.close()
