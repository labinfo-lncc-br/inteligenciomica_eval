"""Unit tests for VLLMGeneratorAdapter (TAREFA-014).

Uses respx.mock to intercept httpx calls to the OpenAI-compatible vLLM endpoint.
All tests call the public async generate() method directly.
"""

from __future__ import annotations

import json
import pathlib

import httpx
import pytest
import respx
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
_FIXTURES_DIR = pathlib.Path(__file__).parents[3] / "fixtures"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def vllm_response() -> dict:  # type: ignore[type-arg]
    """Load the vLLM chat-completion fixture from tests/fixtures/."""
    return json.loads((_FIXTURES_DIR / "vllm_generator_response.json").read_text())


def _make_adapter(respx_mock: respx.MockRouter) -> VLLMGeneratorAdapter:
    """Return a VLLMGeneratorAdapter whose httpx calls are intercepted by respx_mock.

    The ``respx_mock`` fixture patches httpcore globally; a plain ``httpx.AsyncClient``
    created inside a test that uses ``respx_mock`` will route through the mock.
    """
    _ = respx_mock  # ensures the fixture is active (httpcore is patched)
    http_client = httpx.AsyncClient()
    return VLLMGeneratorAdapter(
        url=_BASE_URL,
        model=_MODEL,
        http_client=http_client,
        _retry_stop=stop_after_attempt(3),
        _retry_wait=wait_none(),
    )


_CHUNK = Chunk(id="c1", text="DNA replication occurs in the cell nucleus.", score=0.95)
_LLM = LLMId("test-model")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_returns_text_from_fixture(
    respx_mock: respx.MockRouter,
    vllm_response: dict,  # type: ignore[type-arg]
) -> None:
    respx_mock.post(_ENDPOINT).mock(
        return_value=httpx.Response(200, json=vllm_response)
    )
    adapter = _make_adapter(respx_mock)

    result = await adapter.generate(
        llm=_LLM,
        question="What is DNA replication?",
        contexts=[_CHUNK],
        seed=42,
        temperature=0.1,
    )

    assert (
        result.text
        == "DNA replication is the process by which a DNA molecule is copied."
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_seed_appears_in_request_body(
    respx_mock: respx.MockRouter,
    vllm_response: dict,  # type: ignore[type-arg]
) -> None:
    route = respx_mock.post(_ENDPOINT).mock(
        return_value=httpx.Response(200, json=vllm_response)
    )
    adapter = _make_adapter(respx_mock)

    await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=99, temperature=0.1
    )

    body = json.loads(route.calls[0].request.content)
    assert body["seed"] == 99


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_batch_invariant_always_false(
    respx_mock: respx.MockRouter,
    vllm_response: dict,  # type: ignore[type-arg]
) -> None:
    respx_mock.post(_ENDPOINT).mock(
        return_value=httpx.Response(200, json=vllm_response)
    )
    adapter = _make_adapter(respx_mock)

    result = await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.1
    )

    assert result.batch_invariant is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_returns_generation_output_type(
    respx_mock: respx.MockRouter,
    vllm_response: dict,  # type: ignore[type-arg]
) -> None:
    respx_mock.post(_ENDPOINT).mock(
        return_value=httpx.Response(200, json=vllm_response)
    )
    adapter = _make_adapter(respx_mock)

    result = await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=1, temperature=0.1
    )

    assert isinstance(result, GenerationOutput)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_token_counts_from_fixture(
    respx_mock: respx.MockRouter,
    vllm_response: dict,  # type: ignore[type-arg]
) -> None:
    respx_mock.post(_ENDPOINT).mock(
        return_value=httpx.Response(200, json=vllm_response)
    )
    adapter = _make_adapter(respx_mock)

    result = await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.1
    )

    assert result.tokens_in == 128
    assert result.tokens_out == 16


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_latency_ms_is_non_negative(
    respx_mock: respx.MockRouter,
    vllm_response: dict,  # type: ignore[type-arg]
) -> None:
    respx_mock.post(_ENDPOINT).mock(
        return_value=httpx.Response(200, json=vllm_response)
    )
    adapter = _make_adapter(respx_mock)

    result = await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=5, temperature=0.1
    )

    assert result.latency_ms >= 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_generate_temperature_in_request_body(
    respx_mock: respx.MockRouter,
    vllm_response: dict,  # type: ignore[type-arg]
) -> None:
    route = respx_mock.post(_ENDPOINT).mock(
        return_value=httpx.Response(200, json=vllm_response)
    )
    adapter = _make_adapter(respx_mock)

    await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.25
    )

    body = json.loads(route.calls[0].request.content)
    assert body["temperature"] == pytest.approx(0.25)


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
async def test_custom_prompt_fn_is_used(
    respx_mock: respx.MockRouter,
    vllm_response: dict,  # type: ignore[type-arg]
) -> None:
    route = respx_mock.post(_ENDPOINT).mock(
        return_value=httpx.Response(200, json=vllm_response)
    )
    adapter = VLLMGeneratorAdapter(
        url=_BASE_URL,
        model=_MODEL,
        http_client=httpx.AsyncClient(),
        prompt_fn=lambda q, _ctx: f"CUSTOM: {q}",
        _retry_wait=wait_none(),
    )

    await adapter.generate(
        llm=_LLM, question="my question", contexts=[_CHUNK], seed=0, temperature=0.1
    )

    body = json.loads(route.calls[0].request.content)
    assert body["messages"][0]["content"] == "CUSTOM: my question"


# ---------------------------------------------------------------------------
# Error handling — non-retryable
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_non_retryable_error_raises_generation_error(
    respx_mock: respx.MockRouter,
) -> None:
    """HTTP 422 (UnprocessableEntity) is non-retryable; must raise GenerationError."""
    respx_mock.post(_ENDPOINT).mock(
        return_value=httpx.Response(
            422,
            json={
                "error": {"message": "invalid request", "type": "invalid_request_error"}
            },
        )
    )
    adapter = _make_adapter(respx_mock)

    with pytest.raises(GenerationError):
        await adapter.generate(
            llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.1
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_non_retryable_error_not_retried(
    respx_mock: respx.MockRouter,
) -> None:
    """A 400 bad-request must not be retried — exactly one HTTP call."""
    route = respx_mock.post(_ENDPOINT).mock(
        return_value=httpx.Response(
            400,
            json={"error": {"message": "bad request", "type": "invalid_request_error"}},
        )
    )
    adapter = _make_adapter(respx_mock)

    with pytest.raises(GenerationError):
        await adapter.generate(
            llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.1
        )

    assert route.call_count == 1


# ---------------------------------------------------------------------------
# Retry behavior — APIConnectionError
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retries_three_times_on_connection_error(
    respx_mock: respx.MockRouter,
) -> None:
    """APIConnectionError (wraps httpx.ConnectError) triggers up to 3 attempts."""
    route = respx_mock.post(_ENDPOINT).mock(
        side_effect=httpx.ConnectError("connection refused")
    )
    adapter = _make_adapter(respx_mock)

    with pytest.raises(GenerationError):
        await adapter.generate(
            llm=_LLM, question="Q?", contexts=[_CHUNK], seed=0, temperature=0.1
        )

    assert route.call_count == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_succeeds_after_transient_connection_error(
    respx_mock: respx.MockRouter,
    vllm_response: dict,  # type: ignore[type-arg]
) -> None:
    """Adapter succeeds on the 3rd attempt after 2 connection failures."""
    call_count = 0

    def _side_effect(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise httpx.ConnectError("transient failure")
        return httpx.Response(200, json=vllm_response)

    respx_mock.post(_ENDPOINT).mock(side_effect=_side_effect)
    adapter = _make_adapter(respx_mock)

    result = await adapter.generate(
        llm=_LLM, question="Q?", contexts=[_CHUNK], seed=42, temperature=0.1
    )

    assert call_count == 3
    assert result.batch_invariant is False


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_adapter_satisfies_generator_port(respx_mock: respx.MockRouter) -> None:
    adapter = _make_adapter(respx_mock)
    assert isinstance(adapter, GeneratorPort)


@pytest.mark.unit
def test_adapter_has_close_method(respx_mock: respx.MockRouter) -> None:
    adapter = _make_adapter(respx_mock)
    assert callable(adapter.close)
