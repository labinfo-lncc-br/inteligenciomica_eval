from __future__ import annotations

import asyncio
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


def _default_prompt_fn(question: str, contexts: Sequence[Chunk]) -> str:
    """Build a minimal generation prompt from question and context chunks."""
    context_block = "\n".join(f"- {c.text}" for c in contexts)
    return f"Contexts:\n{context_block}\n\nQuestion: {question}\n\nAnswer:"


class VLLMGeneratorAdapter:
    """Generates text via a vLLM server using the OpenAI-compatible chat API.

    Uses ``openai.AsyncOpenAI`` with ``api_key="EMPTY"`` (vLLM does not enforce
    key auth).  The ``seed`` is forwarded via ``extra_body`` so that vLLM passes
    it to ``SamplingParams`` (§9.3).  ``batch_invariant`` is always ``False``
    for this adapter (§9.2.4).

    Retries on :class:`openai.APIConnectionError` and :class:`openai.RateLimitError`
    with exponential backoff (multiplier=1, min=1 s, max=8 s, max 3 attempts).
    All other :class:`openai.OpenAIError` subclasses are wrapped immediately in
    :class:`~inteligenciomica_eval.domain.errors.GenerationError`.

    Args:
        url: OpenAI-compatible base URL of the vLLM server, including the ``/v1`` suffix
            (e.g. ``"http://localhost:8000/v1"``).  The URL is passed verbatim to
            ``openai.AsyncOpenAI(base_url=url)``.
        model: model identifier served by vLLM (must match the loaded model name).
        prompt_fn: ``(question, contexts) -> prompt_str``; if ``None`` a minimal
            default is used (will be replaced by ``PromptRegistry`` in TAREFA-015).
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
        prompt_fn: Callable[[str, Sequence[Chunk]], str] | None = None,
        http_client: httpx.AsyncClient | None = None,
        _retry_stop: Any = None,
        _retry_wait: Any = None,
    ) -> None:
        self._model = model
        self._prompt_fn: Callable[[str, Sequence[Chunk]], str] = (
            prompt_fn or _default_prompt_fn
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

    def generate(
        self,
        *,
        llm: LLMId,
        question: str,
        contexts: Sequence[Chunk],
        seed: int,
        temperature: float,
    ) -> GenerationOutput:
        """Generate a response for *question* given *contexts*.

        Synchronous wrapper around the async implementation.  Must NOT be
        called from within a running event loop; use ``_generate_async``
        directly from async contexts.

        Args:
            llm: model identifier used for logging.
            question: question text.
            contexts: sequence of retrieved chunks used as context.
            seed: reproducibility seed forwarded to vLLM via ``extra_body``.
            temperature: sampling temperature forwarded to the API.

        Returns:
            :class:`~inteligenciomica_eval.domain.ports.GenerationOutput` with
            ``batch_invariant=False`` (constant for this adapter, §9.2.4).

        Raises:
            GenerationError: on any generation failure (including retries exhausted).
        """
        return asyncio.run(
            self._generate_async(
                llm=llm,
                question=question,
                contexts=contexts,
                seed=seed,
                temperature=temperature,
            )
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying httpx transport held by ``AsyncOpenAI``."""
        await self._client.close()

    # ------------------------------------------------------------------
    # Internal async implementation
    # ------------------------------------------------------------------

    async def _generate_async(
        self,
        *,
        llm: LLMId,
        question: str,
        contexts: Sequence[Chunk],
        seed: int,
        temperature: float,
    ) -> GenerationOutput:
        """Async implementation: calls vLLM with tenacity retry on transient errors.

        Args:
            llm: model identifier used for logging.
            question: question text.
            contexts: sequence of retrieved chunks.
            seed: reproducibility seed passed in ``extra_body`` (§9.3, ADR-003).
            temperature: sampling temperature.

        Returns:
            :class:`~inteligenciomica_eval.domain.ports.GenerationOutput`.

        Raises:
            GenerationError: on non-retryable API errors or retries exhausted.
        """
        prompt = self._prompt_fn(question, contexts)
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
                        messages=[{"role": "user", "content": prompt}],
                        temperature=temperature,
                        extra_body={"seed": seed},
                    )
        except openai.OpenAIError as exc:
            raise GenerationError(str(exc)) from exc

        latency_ms = int((time.monotonic() - t0) * 1000)

        assert response is not None  # guaranteed: exception raised otherwise
        choice = response.choices[0]
        usage = response.usage

        output = GenerationOutput(
            text=choice.message.content or "",
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
        )

        return output
