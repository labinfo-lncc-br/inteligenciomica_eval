"""Unit tests for VLLMGeneratorAdapter (TAREFA-014 + TAREFA-316).

Mocks ``openai.AsyncOpenAI.chat.completions.create`` via ``AsyncMock`` — an
environment-independent approach that intercepts at the SDK layer without relying on
HTTP-transport internals (``httpx.MockTransport``, ``respx``) that can silently fail in
sandboxed environments where the event-loop or transport policy differs.

The mock is injected via direct attribute assignment after the adapter is built:
    adapter._client.chat.completions.create = AsyncMock(...)
This is possible because ``openai.AsyncCompletions.create`` is a regular instance method
and Python does not prevent replacing it on the object level.

TAREFA-316: prompt is now system + user messages (ADR-015). render_fn replaces prompt_fn.
"""

from __future__ import annotations

import json
from pathlib import Path
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
    _default_render_fn,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE_URL = "http://localhost:8000/v1"
_MODEL = "test-model"
_ENDPOINT = f"{_BASE_URL}/chat/completions"

_FIXTURE_TEXT = "DNA replication is the process by which a DNA molecule is copied."
_FIXTURE_TOKENS_IN = 128
_FIXTURE_TOKENS_OUT = 16

_DUMMY_REQUEST = httpx.Request("POST", _ENDPOINT)
_DUMMY_RESP_429 = httpx.Response(429, request=_DUMMY_REQUEST)
_DUMMY_RESP_422 = httpx.Response(422, request=_DUMMY_REQUEST)
_DUMMY_RESP_400 = httpx.Response(400, request=_DUMMY_REQUEST)

_SYSTEM = "You are a biomedical assistant."
_USER = "Context:\n-----\nSome context.\n-----\nQuery: What is DNA?"

_CHUNK = Chunk(
    id="c1",
    text="DNA replication occurs in the cell nucleus.",
    score=0.95,
    source="12345678",
)
_LLM = LLMId("test-model")

_FIXTURES_DIR = Path(__file__).parent.parent.parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_completion(
    text: str = _FIXTURE_TEXT,
    tokens_in: int = _FIXTURE_TOKENS_IN,
    tokens_out: int = _FIXTURE_TOKENS_OUT,
) -> MagicMock:
    """Create a minimal ChatCompletion mock."""
    comp = MagicMock()
    comp.choices = [MagicMock()]
    comp.choices[0].message.content = text
    comp.usage = MagicMock()
    comp.usage.prompt_tokens = tokens_in
    comp.usage.completion_tokens = tokens_out
    return comp


def _make_render_fn(
    system: str = _SYSTEM,
    user: str = _USER,
) -> object:
    """Build a deterministic render_fn that returns fixed (system, user) strings."""

    def _render(question: str, contexts: object) -> tuple[str, str]:
        return (system, user)

    return _render


def _make_adapter(
    create_mock: AsyncMock | None = None,
    render_fn: object = None,
) -> VLLMGeneratorAdapter:
    """Return a VLLMGeneratorAdapter with ``create()`` and optionally render_fn set.

    When *create_mock* is ``None`` no SDK mock is applied (lifecycle / protocol tests).
    When *render_fn* is ``None`` a fixed deterministic render_fn is used.
    """
    adapter = VLLMGeneratorAdapter(
        url=_BASE_URL,
        model=_MODEL,
        render_fn=render_fn if render_fn is not None else _make_render_fn(),  # type: ignore[arg-type]
        _retry_stop=stop_after_attempt(3),
        _retry_wait=wait_none(),
    )
    if create_mock is not None:
        adapter._client.chat.completions.create = create_mock  # type: ignore[method-assign]
    return adapter


# ---------------------------------------------------------------------------
# Happy path — basic generation
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
# System + user messages (TAREFA-316)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_sends_exactly_two_messages() -> None:
    """Adapter must send [system, user] — never a single user message."""
    mock_create = AsyncMock(return_value=_mock_completion())
    adapter = _make_adapter(mock_create)

    await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.0
    )

    messages = mock_create.call_args.kwargs["messages"]
    assert len(messages) == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_first_message_is_system() -> None:
    mock_create = AsyncMock(return_value=_mock_completion())
    adapter = _make_adapter(mock_create)

    await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.0
    )

    messages = mock_create.call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == _SYSTEM


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_second_message_is_user() -> None:
    mock_create = AsyncMock(return_value=_mock_completion())
    adapter = _make_adapter(mock_create)

    await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.0
    )

    messages = mock_create.call_args.kwargs["messages"]
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == _USER


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_render_fn_receives_question_and_contexts() -> None:
    """render_fn must be called with the exact question and contexts passed to generate."""
    received: list[object] = []

    def _capture(question: str, contexts: object) -> tuple[str, str]:
        received.append((question, contexts))
        return (_SYSTEM, _USER)

    mock_create = AsyncMock(return_value=_mock_completion())
    adapter = VLLMGeneratorAdapter(
        url=_BASE_URL,
        model=_MODEL,
        render_fn=_capture,  # type: ignore[arg-type]
        _retry_wait=wait_none(),
    )
    adapter._client.chat.completions.create = mock_create  # type: ignore[method-assign]

    await adapter.generate(
        llm=_LLM, question="my question", contexts=[_CHUNK], seed=0, temperature=0.0
    )

    assert len(received) == 1
    q, ctx = received[0]  # type: ignore[misc]
    assert q == "my question"
    assert list(ctx) == [_CHUNK]  # type: ignore[call-overload]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_custom_render_fn_is_used() -> None:
    """Injecting a custom render_fn changes the messages sent to the LLM."""
    mock_create = AsyncMock(return_value=_mock_completion())
    adapter = VLLMGeneratorAdapter(
        url=_BASE_URL,
        model=_MODEL,
        render_fn=lambda q, _ctx: ("CUSTOM_SYS", f"CUSTOM_USER: {q}"),
        _retry_wait=wait_none(),
    )
    adapter._client.chat.completions.create = mock_create  # type: ignore[method-assign]

    await adapter.generate(
        llm=_LLM, question="my question", contexts=[_CHUNK], seed=0, temperature=0.1
    )

    messages = mock_create.call_args.kwargs["messages"]
    assert messages[0]["content"] == "CUSTOM_SYS"
    assert messages[1]["content"] == "CUSTOM_USER: my question"


# ---------------------------------------------------------------------------
# Strip <think> tags (TAREFA-316)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_strips_think_tags_inline() -> None:
    raw = "<think>hidden reasoning</think>Final answer."
    mock_create = AsyncMock(return_value=_mock_completion(text=raw))
    adapter = _make_adapter(mock_create)

    result = await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.0
    )

    assert result.text == "Final answer."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_strips_think_tags_multiline() -> None:
    raw = "<think>\nline 1\nline 2\n</think>Clean answer."
    mock_create = AsyncMock(return_value=_mock_completion(text=raw))
    adapter = _make_adapter(mock_create)

    result = await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.0
    )

    assert result.text == "Clean answer."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_no_think_tags_unchanged() -> None:
    raw = "  Answer without think tags.  "
    mock_create = AsyncMock(return_value=_mock_completion(text=raw))
    adapter = _make_adapter(mock_create)

    result = await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.0
    )

    assert result.text == "Answer without think tags."


# ---------------------------------------------------------------------------
# Fidelidade de referência — fixture de produção (TAREFA-316)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fidelity_against_production_fixture() -> None:
    """Validate that render_rag_generation with v1_production matches the production fixture."""
    from inteligenciomica_eval.infrastructure.prompts.registry import PromptRegistry

    fixture = json.loads(
        (_FIXTURES_DIR / "production_messages_fixture.json").read_text(encoding="utf-8")
    )
    registry = PromptRegistry()
    chunks = [
        Chunk(
            id=c["id"],
            text=c["text"],
            score=c["score"],
            source=c["source"],
        )
        for c in fixture["chunks"]
    ]
    system, user = registry.render_rag_generation(
        version="v1_production",
        question=fixture["question"],
        contexts=chunks,
    )

    # System must be non-empty and match the production system_prompt.txt content.
    assert len(system) > 100
    assert "InteligenciÔmica" in system

    # User must follow the exact production wrapper format.
    assert user == fixture["expected_user"]

    # Context entries must use PMID format without space: "[PMID:xxxxx]"
    assert "[PMID:38291047]" in user
    assert "[PMID:87654321]" in user


# ---------------------------------------------------------------------------
# Seleção por rodada — prompt_version muda com generation_prompt_version
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_render_fn_symbol_is_exported() -> None:
    """_default_render_fn must be importable (tested as a symbol, not called live)."""
    assert callable(_default_render_fn)


# ---------------------------------------------------------------------------
# Error handling — non-retryable
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_non_retryable_error_raises_generation_error() -> None:
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
    adapter = _make_adapter()
    await adapter.close()
