from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from inteligenciomica_eval.domain.ports import Chunk, GenerationOutput
from inteligenciomica_eval.domain.value_objects import LLMId

_RESPONSE_TEMPLATE = "Fake answer for [{llm}|seed={seed}]: {question}"


@dataclass
class GenerateCall:
    """Record of a single call to FakeGenerator.generate.

    Args:
        llm: model identifier used.
        question: question text.
        contexts: chunks provided as context.
        seed: reproducibility seed.
        temperature: sampling temperature.
    """

    llm: LLMId
    question: str
    contexts: tuple[Chunk, ...]
    seed: int
    temperature: float


class FakeGenerator:
    """In-memory GeneratorPort returning deterministic text and recording calls.

    The response text is derived from *template* with ``{llm}``, ``{seed}``, and
    ``{question}`` placeholders so that every identical (llm, question, seed) triple
    always yields the same output across test runs.

    Args:
        template: format string with ``{llm}``, ``{seed}``, ``{question}`` keys.
        tokens_in: fixed token-in count returned in every GenerationOutput.
        tokens_out: fixed token-out count returned in every GenerationOutput.
        latency_ms: fixed latency in ms returned in every GenerationOutput.
    """

    def __init__(
        self,
        template: str = _RESPONSE_TEMPLATE,
        *,
        tokens_in: int = 64,
        tokens_out: int = 32,
        latency_ms: int = 10,
    ) -> None:
        self._template = template
        self._tokens_in = tokens_in
        self._tokens_out = tokens_out
        self._latency_ms = latency_ms
        self.calls: list[GenerateCall] = []

    def generate(
        self,
        *,
        llm: LLMId,
        question: str,
        contexts: Sequence[Chunk],
        seed: int,
        temperature: float,
    ) -> GenerationOutput:
        """Return a deterministic response derived from (llm, question, seed).

        Appends a GenerateCall record to ``self.calls`` for assertion in tests.

        Args:
            llm: model identifier.
            question: question text.
            contexts: retrieved chunks (recorded but not used for text generation).
            seed: reproducibility seed.
            temperature: sampling temperature (recorded but not used).

        Returns:
            GenerationOutput with deterministic text and fixed token/latency counts.
        """
        self.calls.append(
            GenerateCall(
                llm=llm,
                question=question,
                contexts=tuple(contexts),
                seed=seed,
                temperature=temperature,
            )
        )
        text = self._template.format(llm=llm.value, seed=seed, question=question)
        return GenerationOutput(
            text=text,
            tokens_in=self._tokens_in,
            tokens_out=self._tokens_out,
            latency_ms=self._latency_ms,
        )
