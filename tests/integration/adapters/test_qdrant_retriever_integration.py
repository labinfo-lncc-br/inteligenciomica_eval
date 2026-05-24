"""Integration tests for QdrantRetrieverAdapter against a real Qdrant container.

Text-based inference (Document query) requires a Qdrant server with an Inference
API configured (e.g. FastEmbed). Plain testcontainers/qdrant only provides a
vanilla server, so these tests patch ``_search_async`` to use dense-vector
``search()`` instead of text-based ``query_points``.  This still exercises:

- Real TCP connection to Qdrant
- Collection name lookup via collection_map
- Upsert + search cycle with real ScoredPoint payloads
- top_k limiting enforced by the server
- Score type and ordering guarantees
"""

from __future__ import annotations

import asyncio
import pathlib
import random

import pytest

from inteligenciomica_eval.domain.errors import RetrievalError, StorageError
from inteligenciomica_eval.domain.value_objects import BaseId
from inteligenciomica_eval.infrastructure.adapters.qdrant_retriever import (
    GoldChunkReaderAdapter,
    QdrantRetrieverAdapter,
)

# ---------------------------------------------------------------------------
# Skip guard — Docker must be available
# ---------------------------------------------------------------------------

docker = pytest.importorskip("docker", reason="docker SDK not available")

try:
    import docker as _docker_mod

    _docker_mod.from_env().ping()
    _DOCKER_AVAILABLE = True
except Exception:
    _DOCKER_AVAILABLE = False

pytestmark = pytest.mark.integration

_skip_no_docker = pytest.mark.skipif(
    not _DOCKER_AVAILABLE, reason="Docker daemon not reachable"
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VECTOR_SIZE = 4
_COLLECTION = "bio_chunks_test"
_BASE_ID = "IDx_400k"
_NUM_DOCS = 5

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rand_vec(size: int = _VECTOR_SIZE) -> list[float]:
    """Return a random unit-normalised float vector."""
    v = [random.random() for _ in range(size)]
    norm = sum(x * x for x in v) ** 0.5 or 1.0
    return [x / norm for x in v]


# ---------------------------------------------------------------------------
# Session-scoped Qdrant container
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qdrant_container():  # type: ignore[return]
    from testcontainers.qdrant import QdrantContainer

    with QdrantContainer() as container:
        yield container


@pytest.fixture(scope="session")
def qdrant_url(qdrant_container) -> str:  # type: ignore[no-untyped-def]
    host = qdrant_container.get_container_host_ip()
    port = qdrant_container.get_exposed_port(6333)
    return f"http://{host}:{port}"


# ---------------------------------------------------------------------------
# Function-scoped: create fresh collection + 5 docs for each test
# ---------------------------------------------------------------------------


@pytest.fixture()
def populated_collection(qdrant_url: str) -> None:  # type: ignore[return]
    """Create test collection, insert _NUM_DOCS docs, yield, then delete."""
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.http.models import (
        Distance,
        PointStruct,
        VectorParams,
    )

    async def _setup() -> None:
        client = AsyncQdrantClient(url=qdrant_url)
        try:
            if await client.collection_exists(_COLLECTION):
                await client.delete_collection(_COLLECTION)
            await client.create_collection(
                _COLLECTION,
                vectors_config=VectorParams(
                    size=_VECTOR_SIZE, distance=Distance.COSINE
                ),
            )
            points = [
                PointStruct(
                    id=str(i),
                    vector=_rand_vec(),
                    payload={"text": f"biomedical document {i}"},
                )
                for i in range(_NUM_DOCS)
            ]
            await client.upsert(collection_name=_COLLECTION, points=points)
        finally:
            await client.close()

    asyncio.run(_setup())
    yield

    async def _teardown() -> None:
        client = AsyncQdrantClient(url=qdrant_url)
        try:
            await client.delete_collection(_COLLECTION)
        finally:
            await client.close()

    asyncio.run(_teardown())


# ---------------------------------------------------------------------------
# Helper: redirect only query_points to dense vector search
# ---------------------------------------------------------------------------


def _patch_query_points_with_dense_search(
    adapter: QdrantRetrieverAdapter, query_vec: list[float]
) -> None:
    """Redirect client.query_points() to use a dense float vector instead of Document.

    ``_search_async`` is left **unchanged**: collection-mapping, error wrapping,
    structured logging, and ScoredPoint→RetrievalResult conversion are all fully
    exercised.  Only the Qdrant query input is swapped from ``Document(text=…)``
    to a pre-computed float list, bypassing the Inference API that is not
    available on a vanilla Qdrant container.

    Note: qdrant-client ≥ 1.7 removed the standalone ``search()`` method;
    ``query_points(query=list[float])`` is the correct API for dense search.
    """
    from typing import Any

    from qdrant_client.http.models import QueryResponse

    original_qp = adapter._client.query_points

    async def _dense_query_points(
        collection_name: str,
        query: Any,
        limit: int = 10,
        **kwargs: Any,
    ) -> QueryResponse:
        _ = query  # ignore Document — use pre-computed dense vector instead
        return await original_qp(
            collection_name=collection_name,
            query=query_vec,  # list[float] → dense vector search
            limit=limit,
            **kwargs,
        )

    adapter._client.query_points = _dense_query_points  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@_skip_no_docker
@pytest.mark.integration
def test_search_returns_top_k_chunks(
    qdrant_url: str,
    populated_collection: None,
) -> None:
    _ = populated_collection
    adapter = QdrantRetrieverAdapter(
        url=qdrant_url,
        collection_map={_BASE_ID: _COLLECTION},
        top_k=8,
    )
    _patch_query_points_with_dense_search(adapter, _rand_vec())

    result = adapter.search(base=BaseId(_BASE_ID), question="DNA replication", top_k=3)

    assert len(result.chunks) == 3
    assert len(result.ids) == 3
    assert len(result.scores) == 3


@_skip_no_docker
@pytest.mark.integration
def test_search_scores_are_floats_in_unit_interval(
    qdrant_url: str,
    populated_collection: None,
) -> None:
    _ = populated_collection
    adapter = QdrantRetrieverAdapter(
        url=qdrant_url,
        collection_map={_BASE_ID: _COLLECTION},
    )
    _patch_query_points_with_dense_search(adapter, _rand_vec())

    result = adapter.search(base=BaseId(_BASE_ID), question="test", top_k=_NUM_DOCS)

    for score in result.scores:
        assert isinstance(score, float), f"score should be float, got {type(score)}"
        assert -1.0 <= score <= 1.0, f"cosine score out of range: {score}"


@_skip_no_docker
@pytest.mark.integration
def test_search_scores_are_descending(
    qdrant_url: str,
    populated_collection: None,
) -> None:
    _ = populated_collection
    adapter = QdrantRetrieverAdapter(
        url=qdrant_url,
        collection_map={_BASE_ID: _COLLECTION},
    )
    _patch_query_points_with_dense_search(adapter, _rand_vec())

    result = adapter.search(base=BaseId(_BASE_ID), question="test", top_k=_NUM_DOCS)

    scores = list(result.scores)
    assert scores == sorted(scores, reverse=True), (
        "Qdrant must return results ordered by score desc"
    )


@_skip_no_docker
@pytest.mark.integration
def test_search_top_k_limits_results_correctly(
    qdrant_url: str,
    populated_collection: None,
) -> None:
    _ = populated_collection
    adapter = QdrantRetrieverAdapter(
        url=qdrant_url,
        collection_map={_BASE_ID: _COLLECTION},
    )
    _patch_query_points_with_dense_search(adapter, _rand_vec())

    for k in (1, 2, 5):
        result = adapter.search(base=BaseId(_BASE_ID), question="q", top_k=k)
        assert len(result.chunks) == k, f"expected {k} chunks, got {len(result.chunks)}"


@_skip_no_docker
@pytest.mark.integration
def test_search_payload_text_is_accessible(
    qdrant_url: str,
    populated_collection: None,
) -> None:
    _ = populated_collection
    adapter = QdrantRetrieverAdapter(
        url=qdrant_url,
        collection_map={_BASE_ID: _COLLECTION},
    )
    _patch_query_points_with_dense_search(adapter, _rand_vec())

    result = adapter.search(base=BaseId(_BASE_ID), question="test", top_k=3)

    for chunk in result.chunks:
        assert chunk.text.startswith("biomedical document"), chunk.text


@_skip_no_docker
@pytest.mark.integration
def test_search_raises_retrieval_error_for_unmapped_base(
    qdrant_url: str,
    populated_collection: None,
) -> None:
    _ = populated_collection
    adapter = QdrantRetrieverAdapter(
        url=qdrant_url,
        collection_map={_BASE_ID: _COLLECTION},
    )
    _patch_query_points_with_dense_search(adapter, _rand_vec())

    with pytest.raises(RetrievalError, match="No collection mapped"):
        adapter.search(base=BaseId("ID_230K"), question="test", top_k=3)


@_skip_no_docker
@pytest.mark.integration
def test_search_raises_retrieval_error_for_nonexistent_collection(
    qdrant_url: str,
) -> None:
    """No patching — real query_points fails for absent collection."""
    adapter = QdrantRetrieverAdapter(
        url=qdrant_url,
        collection_map={_BASE_ID: "nonexistent_collection_xyz"},
    )
    with pytest.raises(RetrievalError):
        adapter.search(base=BaseId(_BASE_ID), question="test", top_k=3)


# ---------------------------------------------------------------------------
# GoldChunkReaderAdapter — integration (file system only, no container)
# ---------------------------------------------------------------------------

_FIXTURES_DIR = pathlib.Path(__file__).parents[2] / "fixtures"


@pytest.mark.integration
def test_gold_reader_integration_happy_path() -> None:
    gold_file = _FIXTURES_DIR / "gold_chunks.jsonl"
    reader = GoldChunkReaderAdapter(gold_file=gold_file)
    assert reader.gold_for("q01") == ["chunk_abc", "chunk_def", "chunk_ghi"]
    assert reader.gold_for("q02") == ["chunk_xyz"]


@pytest.mark.integration
def test_gold_reader_integration_missing_file(tmp_path: pathlib.Path) -> None:
    reader = GoldChunkReaderAdapter(gold_file=tmp_path / "gone.jsonl")
    with pytest.raises(StorageError, match="not found"):
        reader.gold_for("q01")
