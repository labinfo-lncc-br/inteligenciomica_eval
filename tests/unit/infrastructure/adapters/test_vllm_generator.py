"""Unit tests for VLLMGeneratorAdapter (TAREFA-014).

Mocks ``openai.AsyncOpenAI.chat.completions.create`` via ``AsyncMock`` — an
environment-independent approach that intercepts at the SDK layer without relying on
HTTP-transport internals (``httpx.MockTransport``, ``respx``) that can silently fail in
sandboxed environments where the event-loop or transport policy differs.

The mock is injected via direct attribute assignment after the adapter is built:
    adapter._client.chat.completions.create = AsyncMock(...)
This is possible because ``openai.AsyncCompletions.create`` is a regular instance method
and Python does not prevent replacing it on the object level.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest
from tenacity import stop_after_attempt, wait_none

from inteligenciomica_eval.domain.errors import GenerationError
from inteligenciomica_eval.domain.ports import Chunk, GenerationOutput, GeneratorPort
from inteligenciomica_eval.domain.value_objects import LLMId
from inteligenciomica_eval.infrastructure.adapters.vllm_generator import (
    VLLMGeneratorAdapter,
    _default_prompt_fn,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE_URL = "http://localhost:8000/v1"
_MODEL = "test-model"
_ENDPOINT = f"{_BASE_URL}/chat/completions"

# Values matching tests/fixtures/vllm_generator_response.json
_FIXTURE_TEXT = "DNA replication is the process by which a DNA molecule is copied."
_FIXTURE_TOKENS_IN = 128
_FIXTURE_TOKENS_OUT = 16

# Minimal httpx objects needed to instantiate openai SDK error types.
# These never reach the network — they exist only to satisfy constructor signatures.
_DUMMY_REQUEST = httpx.Request("POST", _ENDPOINT)
_DUMMY_RESP_429 = httpx.Response(429, request=_DUMMY_REQUEST)
_DUMMY_RESP_422 = httpx.Response(422, request=_DUMMY_REQUEST)
_DUMMY_RESP_400 = httpx.Response(400, request=_DUMMY_REQUEST)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_completion(
    text: str = _FIXTURE_TEXT,
    tokens_in: int = _FIXTURE_TOKENS_IN,
    tokens_out: int = _FIXTURE_TOKENS_OUT,
) -> MagicMock:
    """Create a minimal ChatCompletion mock matching vllm_generator_response.json."""
    comp = MagicMock()
    comp.choices = [MagicMock()]
    comp.choices[0].message.content = text
    comp.usage = MagicMock()
    comp.usage.prompt_tokens = tokens_in
    comp.usage.completion_tokens = tokens_out
    return comp


def _make_adapter(create_mock: AsyncMock | None = None) -> VLLMGeneratorAdapter:
    """Return a VLLMGeneratorAdapter with ``create()`` intercepted by *create_mock*.

    Mocks at the SDK layer so that no I/O occurs, regardless of transport or
    event-loop policy.  When *create_mock* is ``None`` the adapter is returned
    without any mock (useful for lifecycle / protocol tests).
    """
    adapter = VLLMGeneratorAdapter(
        url=_BASE_URL,
        model=_MODEL,
        _retry_stop=stop_after_attempt(3),
        _retry_wait=wait_none(),
    )
    if create_mock is not None:
        adapter._client.chat.completions.create = create_mock  # type: ignore[method-assign]
    return adapter


_CHUNK = Chunk(id="c1", text="DNA replication occurs in the cell nucleus.", score=0.95)
_LLM = LLMId("test-model")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_returns_text_from_fixture() -> None:
    mock_create = AsyncMock(return_value=_mock_completion())
    adapter = _make_adapter(mock_create)

    result = await adapter.generate(
        llm=_LLM,
        question="What is DNA replication?",
        contexts=[_CHUNK],
        seed=42,
        temperature=0.1,
    )

    assert result.text == _FIXTURE_TEXT


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_seed_appears_in_request_body() -> None:
    mock_create = AsyncMock(return_value=_mock_completion())
    adapter = _make_adapter(mock_create)

    await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=99, temperature=0.1
    )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["extra_body"]["seed"] == 99


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_batch_invariant_always_false() -> None:
    mock_create = AsyncMock(return_value=_mock_completion())
    adapter = _make_adapter(mock_create)

    result = await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.1
    )

    assert result.batch_invariant is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_returns_generation_output_type() -> None:
    mock_create = AsyncMock(return_value=_mock_completion())
    adapter = _make_adapter(mock_create)

    result = await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=1, temperature=0.1
    )

    assert isinstance(result, GenerationOutput)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_token_counts_from_fixture() -> None:
    mock_create = AsyncMock(return_value=_mock_completion())
    adapter = _make_adapter(mock_create)

    result = await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.1
    )

    assert result.tokens_in == _FIXTURE_TOKENS_IN
    assert result.tokens_out == _FIXTURE_TOKENS_OUT


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_latency_ms_is_non_negative() -> None:
    mock_create = AsyncMock(return_value=_mock_completion())
    adapter = _make_adapter(mock_create)

    result = await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=5, temperature=0.1
    )

    assert result.latency_ms >= 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_temperature_in_request_body() -> None:
    mock_create = AsyncMock(return_value=_mock_completion())
    adapter = _make_adapter(mock_create)

    await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.25
    )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["temperature"] == pytest.approx(0.25)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_prompt_fn_includes_question_and_context() -> None:
    chunk = Chunk(id="c1", text="relevant context", score=0.9)
    prompt = _default_prompt_fn("What is genomics?", [chunk])

    assert "What is genomics?" in prompt
    assert "relevant context" in prompt


@pytest.mark.unit
def test_default_prompt_fn_lists_multiple_contexts() -> None:
    chunks = [
        Chunk(id="c1", text="context A", score=0.9),
        Chunk(id="c2", text="context B", score=0.8),
    ]
    prompt = _default_prompt_fn("Q?", chunks)
    assert "context A" in prompt
    assert "context B" in prompt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_custom_prompt_fn_is_used() -> None:
    mock_create = AsyncMock(return_value=_mock_completion())
    adapter = VLLMGeneratorAdapter(
        url=_BASE_URL,
        model=_MODEL,
        prompt_fn=lambda q, _ctx: f"CUSTOM: {q}",
        _retry_wait=wait_none(),
    )
    adapter._client.chat.completions.create = mock_create  # type: ignore[method-assign]

    await adapter.generate(
        llm=_LLM, question="my question", contexts=[_CHUNK], seed=0, temperature=0.1
    )

    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["messages"][0]["content"] == "CUSTOM: my question"


# ---------------------------------------------------------------------------
# Error handling — non-retryable
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_non_retryable_error_raises_generation_error() -> None:
    """HTTP 422 (UnprocessableEntity) is non-retryable; must raise GenerationError."""
    exc = openai.UnprocessableEntityError(
        "invalid request", response=_DUMMY_RESP_422, body=None
    )
    mock_create = AsyncMock(side_effect=exc)
    adapter = _make_adapter(mock_create)

    with pytest.raises(GenerationError):
        await adapter.generate(
            llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.1
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_non_retryable_error_not_retried() -> None:
    """A 400 bad-request must not be retried — exactly one SDK call."""
    exc = openai.BadRequestError("bad request", response=_DUMMY_RESP_400, body=None)
    mock_create = AsyncMock(side_effect=exc)
    adapter = _make_adapter(mock_create)

    with pytest.raises(GenerationError):
        await adapter.generate(
            llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.1
        )

    assert mock_create.call_count == 1


# ---------------------------------------------------------------------------
# Retry behavior — APIConnectionError
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retries_three_times_on_connection_error() -> None:
    """APIConnectionError triggers up to 3 attempts via tenacity."""
    exc = openai.APIConnectionError(
        message="connection refused", request=_DUMMY_REQUEST
    )
    mock_create = AsyncMock(side_effect=exc)
    adapter = _make_adapter(mock_create)

    with pytest.raises(GenerationError):
        await adapter.generate(
            llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.1
        )

    assert mock_create.call_count == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_succeeds_after_transient_connection_error() -> None:
    """Adapter succeeds on the 3rd attempt after 2 connection failures."""
    call_count = 0

    def _side_effect(**kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise openai.APIConnectionError(
                message="transient failure", request=_DUMMY_REQUEST
            )
        return _mock_completion()

    mock_create = AsyncMock(side_effect=_side_effect)
    adapter = _make_adapter(mock_create)

    result = await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=42, temperature=0.1
    )

    assert call_count == 3
    assert result.batch_invariant is False


# ---------------------------------------------------------------------------
# Retry behavior — RateLimitError
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retries_three_times_on_rate_limit_error() -> None:
    """RateLimitError triggers up to 3 attempts, same as APIConnectionError."""
    exc = openai.RateLimitError(
        "rate limit exceeded", response=_DUMMY_RESP_429, body=None
    )
    mock_create = AsyncMock(side_effect=exc)
    adapter = _make_adapter(mock_create)

    with pytest.raises(GenerationError):
        await adapter.generate(
            llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.1
        )

    assert mock_create.call_count == 3


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_adapter_satisfies_generator_port() -> None:
    adapter = _make_adapter()
    assert isinstance(adapter, GeneratorPort)


@pytest.mark.unit
async def test_adapter_close_shuts_down_client() -> None:
    """await adapter.close() must not raise and must close the underlying client."""
    adapter = _make_adapter()
    await adapter.close()  # must complete without exception
