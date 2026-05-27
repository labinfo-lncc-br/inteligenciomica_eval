from __future__ import annotations

from collections.abc import Sequence

from inteligenciomica_eval.domain.ports import Chunk, RetrievalResult
from inteligenciomica_eval.domain.value_objects import BaseId

_DEFAULT_CHUNK: Chunk = Chunk(
    id="chunk-default", text="Default stub context.", score=0.9
)


class StubRetriever:
    """In-memory RetrieverPort returning planted chunks without I/O.

    Args:
        responses: optional mapping of question text → chunks to return.
            Unknown questions fall back to ``default_chunks``.
        default_chunks: chunks returned when the question is not in responses.
    """

    def __init__(
        self,
        responses: dict[str, Sequence[Chunk]] | None = None,
        *,
        default_chunks: Sequence[Chunk] = (_DEFAULT_CHUNK,),
    ) -> None:
        self._responses: dict[str, tuple[Chunk, ...]] = {
            q: tuple(chunks) for q, chunks in (responses or {}).items()
        }
        self._default: tuple[Chunk, ...] = tuple(default_chunks)

    async def search(
        self, *, base: BaseId, question: str, top_k: int
    ) -> RetrievalResult:
        """Return planted chunks for *question*, capped at *top_k*.

        Args:
            base: knowledge-base identifier (accepted but unused).
            question: query text used to look up the planted response.
            top_k: maximum number of chunks to return.

        Returns:
            RetrievalResult with matching chunks, ids, and scores.
        """
        chunks = self._responses.get(question, self._default)[:top_k]
        return RetrievalResult(
            chunks=tuple(chunks),
            ids=tuple(c.id for c in chunks),
            scores=tuple(c.score for c in chunks),
        )
