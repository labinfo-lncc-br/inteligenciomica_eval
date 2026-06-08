from __future__ import annotations

import json
import pathlib
import time
from collections.abc import Mapping
from typing import Any

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import Document, ScoredPoint

from inteligenciomica_eval.domain.errors import RetrievalError, StorageError
from inteligenciomica_eval.domain.ports import Chunk, RetrievalResult
from inteligenciomica_eval.domain.value_objects import BaseId

_log = structlog.get_logger(__name__)


class QdrantRetrieverAdapter:
    """Retrieves chunks from Qdrant using the server-side Inference API.

    Design decision: text-to-vector embedding is delegated entirely to Qdrant.
    The adapter passes the question as a ``Document`` object to ``query_points``,
    which forwards the text to the embedding model configured on the Qdrant
    collection server-side (Qdrant Inference / FastEmbed).  No external embedding
    service is called by this adapter; embedding happens inside the Qdrant server.

    Args:
        url: base URL of the Qdrant server (e.g. ``"http://localhost:6333"``).
        collection_map: mapping of ``BaseId.value`` → Qdrant collection name;
            configured per-round in the YAML config (§5.3).
        top_k: default number of chunks to retrieve when the caller does not
            provide an explicit ``top_k`` parameter.
        embedding_model: name of the embedding model registered on the Qdrant
            Inference API (e.g. ``"Qdrant/Bm42-all-minilm-l6-v2-attentions"``).
    """

    def __init__(
        self,
        url: str,
        collection_map: Mapping[str, str],
        top_k: int = 8,
        *,
        embedding_model: str = "Qdrant/Bm42-all-minilm-l6-v2-attentions",
    ) -> None:
        self._client: AsyncQdrantClient = AsyncQdrantClient(url=url)
        self._collection_map: dict[str, str] = dict(collection_map)
        self.default_top_k: int = top_k
        self._embedding_model: str = embedding_model

    # ------------------------------------------------------------------
    # RetrieverPort interface
    # ------------------------------------------------------------------

    async def search(
        self,
        *,
        base: BaseId,
        question: str,
        top_k: int,
    ) -> RetrievalResult:
        """Retrieve top-k chunks for *question* from the collection mapped to *base*.

        Args:
            base: identifier of the knowledge base to search.
            question: query text forwarded to the Qdrant Inference API.
            top_k: maximum number of chunks to return.

        Returns:
            :class:`~inteligenciomica_eval.domain.ports.RetrievalResult` with
            chunks ordered by descending relevance score.

        Raises:
            RetrievalError: if the collection is not mapped, does not exist on
                the Qdrant server, or any network/protocol error occurs.
        """
        return await self._search_async(base=base, question=question, top_k=top_k)

    # ------------------------------------------------------------------
    # Lifecycle helpers (not part of the Protocol)
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying async HTTP connection to Qdrant."""
        await self._client.close()

    # ------------------------------------------------------------------
    # Internal async implementation
    # ------------------------------------------------------------------

    async def _search_async(
        self,
        *,
        base: BaseId,
        question: str,
        top_k: int,
    ) -> RetrievalResult:
        """Async implementation of the Qdrant search.

        Args:
            base: knowledge-base identifier; resolved via ``collection_map``.
            question: raw query text embedded server-side by Qdrant.
            top_k: number of results to request from Qdrant.

        Returns:
            :class:`~inteligenciomica_eval.domain.ports.RetrievalResult`.

        Raises:
            RetrievalError: on missing collection mapping or Qdrant failure.
        """
        collection_name = self._collection_map.get(base.value)
        if collection_name is None:
            raise RetrievalError(
                f"No collection mapped for base {base.value!r}; "
                f"known bases: {sorted(self._collection_map)}"
            )

        doc = Document(text=question, model=self._embedding_model)
        t0 = time.monotonic()
        try:
            response = await self._client.query_points(
                collection_name=collection_name,
                query=doc,
                limit=top_k,
                with_payload=True,
            )
        except Exception as exc:
            raise RetrievalError(
                f"Qdrant query_points failed for collection {collection_name!r}: {exc}"
            ) from exc

        latency_ms = int((time.monotonic() - t0) * 1000)
        points: list[ScoredPoint] = response.points

        _log.info(
            "qdrant_search_completed",
            base=base.value,
            collection=collection_name,
            top_k=top_k,
            num_results=len(points),
            latency_ms=latency_ms,
        )

        chunks = tuple(
            Chunk(
                id=str(p.id),
                text=str((p.payload or {}).get("text", "")),
                score=p.score,
                source=str((p.payload or {}).get("source", "")),
            )
            for p in points
        )
        return RetrievalResult(
            chunks=chunks,
            ids=tuple(c.id for c in chunks),
            scores=tuple(c.score for c in chunks),
        )


# ---------------------------------------------------------------------------
# GoldChunkReaderAdapter
# ---------------------------------------------------------------------------


class GoldChunkReaderAdapter:
    """Reads gold chunk IDs from a JSONL file for Retrieval Evaluation (Rodada 2).

    Each line in the JSONL file must follow the schema::

        {"question_id": "q01", "gold_chunk_ids": ["chunk_abc", "chunk_def"]}

    Loading is lazy (on first call to :meth:`gold_for`) and idempotent.

    Args:
        gold_file: path to the JSONL file containing gold chunk annotations.

    Raises:
        StorageError: at load time if the file does not exist or a line is
            malformed; at query time if *question_id* is not found.
    """

    def __init__(self, gold_file: pathlib.Path) -> None:
        self._gold_file: pathlib.Path = gold_file
        self._cache: dict[str, list[str]] | None = None

    # ------------------------------------------------------------------
    # GoldChunkReaderPort interface
    # ------------------------------------------------------------------

    def gold_for(self, question_id: str) -> list[str]:
        """Return the list of gold chunk IDs for *question_id*.

        Args:
            question_id: identifier of the question whose gold chunks are sought.

        Returns:
            Fresh ``list[str]`` of gold chunk IDs in the order they appear in
            the JSONL file.

        Raises:
            StorageError: if the JSONL file cannot be read (operation=``'read'``)
                or *question_id* is not present (operation=``'read'``).
        """
        data = self._ensure_loaded()
        if question_id not in data:
            raise StorageError(
                "read",
                f"question_id {question_id!r} not found in {self._gold_file.name}",
            )
        return list(data[question_id])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> dict[str, list[str]]:
        """Load the JSONL file into ``_cache`` on first call; idempotent thereafter."""
        if self._cache is not None:
            return self._cache

        if not self._gold_file.exists():
            raise StorageError(
                "read",
                f"Gold chunk file not found: {self._gold_file}",
            )

        cache: dict[str, list[str]] = {}
        with self._gold_file.open(encoding="utf-8") as fh:
            for lineno, raw_line in enumerate(fh, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record: Any = json.loads(line)
                    cache[record["question_id"]] = list(record["gold_chunk_ids"])
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    raise StorageError(
                        "read",
                        f"Invalid JSONL at line {lineno} in {self._gold_file.name}: {exc}",
                    ) from exc

        self._cache = cache
        return self._cache
