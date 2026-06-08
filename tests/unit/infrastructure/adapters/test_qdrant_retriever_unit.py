from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from inteligenciomica_eval.domain.errors import RetrievalError
from inteligenciomica_eval.domain.ports import RetrievalResult
from inteligenciomica_eval.domain.value_objects import BaseId
from inteligenciomica_eval.infrastructure.adapters.qdrant_retriever import (
    QdrantRetrieverAdapter,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_COLLECTION_MAP = {"IDx_400k": "coll_idx400k", "ID_230K": "coll_id230k"}


def _make_scored_point(
    point_id: str | int,
    text: str,
    score: float,
) -> MagicMock:
    """Build a lightweight ScoredPoint-like mock."""
    sp = MagicMock()
    sp.id = point_id
    sp.score = score
    sp.payload = {"text": text}
    return sp


def _make_query_response(points: list[MagicMock]) -> MagicMock:
    resp = MagicMock()
    resp.points = points
    return resp


@pytest.fixture()
def mock_qdrant_client(mocker: pytest.FixtureRequest) -> MagicMock:  # type: ignore[type-arg]
    """Replace AsyncQdrantClient with a fully-mocked instance."""
    mock = MagicMock()
    mock.query_points = AsyncMock(
        return_value=_make_query_response(
            [
                _make_scored_point("chunk-1", "DNA replication context.", 0.92),
                _make_scored_point("chunk-2", "Protein synthesis details.", 0.78),
            ]
        )
    )
    mock.close = AsyncMock()
    mocker.patch(
        "inteligenciomica_eval.infrastructure.adapters.qdrant_retriever.AsyncQdrantClient",
        return_value=mock,
    )
    return mock  # type: ignore[return-value]


@pytest.fixture()
def adapter(mock_qdrant_client: MagicMock) -> QdrantRetrieverAdapter:
    return QdrantRetrieverAdapter(
        url="http://localhost:6333",
        collection_map=_COLLECTION_MAP,
        top_k=8,
    )


# ---------------------------------------------------------------------------
# BaseId → collection mapping
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_search_maps_base_id_to_correct_collection(
    adapter: QdrantRetrieverAdapter,
    mock_qdrant_client: MagicMock,
) -> None:
    await adapter.search(base=BaseId("IDx_400k"), question="What is DNA?", top_k=5)
    call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
    assert call_kwargs["collection_name"] == "coll_idx400k"


@pytest.mark.unit
async def test_search_maps_second_base_to_correct_collection(
    adapter: QdrantRetrieverAdapter,
    mock_qdrant_client: MagicMock,
) -> None:
    await adapter.search(base=BaseId("ID_230K"), question="Protein folding?", top_k=3)
    call_kwargs = mock_qdrant_client.query_points.call_args.kwargs
    assert call_kwargs["collection_name"] == "coll_id230k"


@pytest.mark.unit
async def test_search_passes_top_k_as_limit(
    adapter: QdrantRetrieverAdapter,
    mock_qdrant_client: MagicMock,
) -> None:
    await adapter.search(base=BaseId("IDx_400k"), question="test", top_k=3)
    assert mock_qdrant_client.query_points.call_args.kwargs["limit"] == 3


# ---------------------------------------------------------------------------
# ScoredPoint → RetrievalResult conversion
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_search_converts_scored_points_to_retrieval_result(
    adapter: QdrantRetrieverAdapter,
    mock_qdrant_client: MagicMock,
) -> None:
    result = await adapter.search(base=BaseId("IDx_400k"), question="test", top_k=5)
    assert isinstance(result, RetrievalResult)
    assert result.ids == ("chunk-1", "chunk-2")
    assert result.scores == (0.92, 0.78)
    assert result.chunks[0].text == "DNA replication context."
    assert result.chunks[1].text == "Protein synthesis details."


@pytest.mark.unit
async def test_search_result_ids_match_chunks_order(
    adapter: QdrantRetrieverAdapter,
    mock_qdrant_client: MagicMock,
) -> None:
    result = await adapter.search(base=BaseId("IDx_400k"), question="test", top_k=5)
    assert result.ids == tuple(c.id for c in result.chunks)
    assert result.scores == tuple(c.score for c in result.chunks)


@pytest.mark.unit
async def test_search_handles_integer_point_id(
    adapter: QdrantRetrieverAdapter,
    mock_qdrant_client: MagicMock,
) -> None:
    mock_qdrant_client.query_points.return_value = _make_query_response(
        [_make_scored_point(42, "integer id doc", 0.55)]
    )
    result = await adapter.search(base=BaseId("IDx_400k"), question="test", top_k=5)
    assert result.ids == ("42",)


@pytest.mark.unit
async def test_search_handles_missing_text_payload(
    adapter: QdrantRetrieverAdapter,
    mock_qdrant_client: MagicMock,
) -> None:
    sp = MagicMock()
    sp.id = "no-text"
    sp.score = 0.5
    sp.payload = None  # no payload at all
    mock_qdrant_client.query_points.return_value = _make_query_response([sp])
    result = await adapter.search(base=BaseId("IDx_400k"), question="test", top_k=5)
    assert result.chunks[0].text == ""


@pytest.mark.unit
async def test_search_returns_empty_result_on_no_hits(
    adapter: QdrantRetrieverAdapter,
    mock_qdrant_client: MagicMock,
) -> None:
    mock_qdrant_client.query_points.return_value = _make_query_response([])
    result = await adapter.search(
        base=BaseId("IDx_400k"), question="obscure query", top_k=5
    )
    assert result.chunks == ()
    assert result.ids == ()
    assert result.scores == ()


# ---------------------------------------------------------------------------
# RetrievalError propagation
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_search_raises_retrieval_error_for_unmapped_base(
    adapter: QdrantRetrieverAdapter,
) -> None:
    with pytest.raises(RetrievalError, match="No collection mapped"):
        await adapter.search(base=BaseId("fixed"), question="test", top_k=5)


@pytest.mark.unit
async def test_search_raises_retrieval_error_on_qdrant_exception(
    adapter: QdrantRetrieverAdapter,
    mock_qdrant_client: MagicMock,
) -> None:
    mock_qdrant_client.query_points.side_effect = RuntimeError("connection refused")
    with pytest.raises(RetrievalError, match="connection refused"):
        await adapter.search(base=BaseId("IDx_400k"), question="test", top_k=5)


# ---------------------------------------------------------------------------
# Public default_top_k attribute (used by callers who want the configured default)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_default_top_k_is_public_and_matches_constructor(
    mock_qdrant_client: MagicMock,
) -> None:
    _ = mock_qdrant_client
    adapter = QdrantRetrieverAdapter(
        url="http://localhost:6333",
        collection_map={},
        top_k=12,
    )
    assert adapter.default_top_k == 12


# ---------------------------------------------------------------------------
# Chunk.source — PMID from payload (TAREFA-316)
# ---------------------------------------------------------------------------


@pytest.mark.unit
async def test_search_populates_chunk_source_from_payload(
    adapter: QdrantRetrieverAdapter,
    mock_qdrant_client: MagicMock,
) -> None:
    """Chunk.source must be filled from payload['source'] (PMID)."""
    sp = MagicMock()
    sp.id = "c1"
    sp.score = 0.9
    sp.payload = {"text": "Some biomedical text.", "source": "38291047"}
    mock_qdrant_client.query_points.return_value = _make_query_response([sp])

    result = await adapter.search(base=BaseId("IDx_400k"), question="test", top_k=1)

    assert result.chunks[0].source == "38291047"


@pytest.mark.unit
async def test_search_chunk_source_empty_when_payload_missing_source(
    adapter: QdrantRetrieverAdapter,
    mock_qdrant_client: MagicMock,
) -> None:
    """When payload has no 'source' key, Chunk.source must default to ''."""
    sp = MagicMock()
    sp.id = "c1"
    sp.score = 0.9
    sp.payload = {"text": "Text without source."}
    mock_qdrant_client.query_points.return_value = _make_query_response([sp])

    result = await adapter.search(base=BaseId("IDx_400k"), question="test", top_k=1)

    assert result.chunks[0].source == ""


@pytest.mark.unit
async def test_search_chunk_source_empty_when_no_payload(
    adapter: QdrantRetrieverAdapter,
    mock_qdrant_client: MagicMock,
) -> None:
    """When payload is None, Chunk.source must default to ''."""
    sp = MagicMock()
    sp.id = "c1"
    sp.score = 0.9
    sp.payload = None
    mock_qdrant_client.query_points.return_value = _make_query_response([sp])

    result = await adapter.search(base=BaseId("IDx_400k"), question="test", top_k=1)

    assert result.chunks[0].source == ""


# ---------------------------------------------------------------------------
# isinstance check — RetrieverPort structural conformance
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_adapter_satisfies_retriever_port_protocol(
    adapter: QdrantRetrieverAdapter,
) -> None:
    from inteligenciomica_eval.domain.ports import RetrieverPort

    assert isinstance(adapter, RetrieverPort)
