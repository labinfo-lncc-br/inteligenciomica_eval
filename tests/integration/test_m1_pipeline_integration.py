"""Gate de Integração M1 — pipeline adapter end-to-end (TAREFA-021).

Exercita TODOS os adapters de M1 em sequência para UMA pergunta, substituindo os
fakes de M0 por adapters reais:

    QdrantRetriever → GoldChunkReader → VLLMGenerator → RAGASLayer1 →
    PrometheusJudge → DeterministicMetrics → AnnotationReader → ParquetStorage

Mecanismos de teste (Nota M1 itens 1, 7; CLAUDE.md §11):

- **Qdrant REAL** via ``QDRANT_URL`` (serviço ``services.qdrant`` no CI) ou
  ``testcontainers`` (local com Docker); pulado se nenhum disponível. O container é
  *session-scoped*; os dados (coleção) são *function-scoped* (criados e apagados por
  teste) — nenhum dado persiste entre testes.
- **vLLM (generator + judge) MOCKADO via respx**: ``respx.mock`` intercepta as chamadas
  HTTP do SDK ``openai.AsyncOpenAI`` (probe confirmou interceptação do SDK neste
  ambiente; a ressalva do §11 era específica de ``http_client=MockTransport``, não do
  ``respx.mock`` global). ``assert_all_called`` garante que ambas as rotas são exercidas;
  qualquer chamada HTTP não-roteada (escape para rede real) faz o teste falhar.
- **RAGAS REAL com LLM mockado por respx** (item 3 do Prompt B): o adapter é construído
  sem ``_metrics`` — suas 6 métricas chamam o LLM-juiz, e essas chamadas HTTP são
  interceptadas por uma rota respx com *side-effect* (`_ragas_llm_route`) que devolve, por
  métrica, o JSON que o parser interno daquela métrica espera (uma rota estática deixaria
  answer_correctness/faithfulness/context_precision sem parse → NaN → ``final_score`` NaN).
  Os embeddings permanecem locais (HuggingFace em cache, sem HTTP).
- **BERTScore + ROUGE reais** (CPU, modelo multilíngue em cache) — ``DeterministicMetrics``.
- **Anotação de fixture** (JSONL em ``tmp_path``) — ``AnnotationReader`` (Camada 3).
- **FinalScoreCalculator** e **ParquetStorage** reais (domínio + M0; roundtrip).
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import pathlib
from typing import Any

import httpx
import pyarrow.parquet as pq
import pytest
import respx

from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
)
from inteligenciomica_eval.domain.ports import (
    Chunk,
    EvaluationSample,
)
from inteligenciomica_eval.domain.services.final_score import (
    DEFAULT_WEIGHTS,
    FinalScoreCalculator,
)
from inteligenciomica_eval.domain.value_objects import (
    BaseId,
    DeterminismRegime,
    LLMId,
    MetricVector,
    RowId,
    Seed,
)
from inteligenciomica_eval.infrastructure.adapters.annotation_reader import (
    AnnotationReaderAdapter,
)
from inteligenciomica_eval.infrastructure.adapters.deterministic_metrics import (
    DeterministicMetricsAdapter,
)
from inteligenciomica_eval.infrastructure.adapters.prometheus_judge import (
    PrometheusJudgeAdapter,
)
from inteligenciomica_eval.infrastructure.adapters.qdrant_retriever import (
    GoldChunkReaderAdapter,
    QdrantRetrieverAdapter,
)
from inteligenciomica_eval.infrastructure.adapters.ragas_metrics import (
    RAGASLayer1Adapter,
)
from inteligenciomica_eval.infrastructure.adapters.vllm_generator import (
    VLLMGeneratorAdapter,
)
from inteligenciomica_eval.infrastructure.config.adapter_configs import (
    RagasAdapterConfig,
)
from inteligenciomica_eval.infrastructure.prompts.registry import PromptRegistry
from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
    ParquetStorage,
)

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

_FIXTURES_DIR = pathlib.Path(__file__).parents[1] / "fixtures"
_FIXTURE: dict[str, Any] = json.loads(
    (_FIXTURES_DIR / "integration_question.json").read_text(encoding="utf-8")
)

_RUN_ID: str = _FIXTURE["run_id"]
_ROUND_ID: str = _FIXTURE["round_id"]
_PHASE: str = _FIXTURE["phase"]
_BASE: str = _FIXTURE["base"]
_LLM: str = _FIXTURE["llm"]
_SEED: int = _FIXTURE["seed"]
_QID: str = _FIXTURE["question_id"]
_QUESTION: str = _FIXTURE["question"]
_GROUND_TRUTH: str = _FIXTURE["ground_truth"]
_FIXED_ANSWER: str = _FIXTURE["fixed_answer"]
_JUDGE_SCORE: float = _FIXTURE["judge_score"]
_JUDGE_FEEDBACK: str = _FIXTURE["judge_feedback"]
_GOLD_CHUNK_IDS: list[str] = _FIXTURE["gold_chunk_ids"]
_CHUNK_TEXTS: list[str] = [c["text"] for c in _FIXTURE["chunks"]]

_COLLECTION = "bio_chunks_m1_gate"
_VECTOR_SIZE = 8
_GEN_URL = "http://vllm-gen-m1:8000/v1"
_JUDGE_URL = "http://vllm-judge-m1:8001/v1"
# RAGAS uses its own judge URL so its LLM calls are routed independently from the
# Prometheus rubric judge (both speak the OpenAI chat API; distinct URLs keep the
# respx routes unambiguous).
_RAGAS_URL = "http://vllm-ragas-m1:8002/v1"
_GEN_MODEL = "llm-biomed-gen"
_JUDGE_MODEL = "prometheus-eval/prometheus-8x7b-v2.0"


# ---------------------------------------------------------------------------
# Docker / service availability
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    """Return True if a reachable Docker daemon is available for testcontainers."""
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Deterministic vectors (vanilla Qdrant container has no Inference API)
# ---------------------------------------------------------------------------


def _dense_vec(seed_offset: int) -> list[float]:
    """Return a deterministic unit-normalised vector keyed by an integer offset."""
    raw = [((seed_offset * 31 + i * 7) % 17) / 17.0 + 0.1 for i in range(_VECTOR_SIZE)]
    norm = sum(x * x for x in raw) ** 0.5 or 1.0
    return [x / norm for x in raw]


def _patch_query_points_with_dense_search(
    adapter: QdrantRetrieverAdapter, query_vec: list[float]
) -> None:
    """Redirect ``client.query_points`` to a dense vector query.

    ``_search_async`` is left unchanged: collection mapping, error wrapping,
    structured logging and ScoredPoint→RetrievalResult conversion are all fully
    exercised. Only the query input is swapped from ``Document(text=…)`` (which
    needs the Inference API, absent on a vanilla Qdrant) to a pre-computed vector.
    """
    from qdrant_client.http.models import QueryResponse

    original_qp = adapter._client.query_points

    async def _dense_query_points(
        collection_name: str,
        query: Any,
        limit: int = 10,
        **kwargs: Any,
    ) -> QueryResponse:
        _ = query
        return await original_qp(
            collection_name=collection_name,
            query=query_vec,
            limit=limit,
            **kwargs,
        )

    adapter._client.query_points = _dense_query_points  # type: ignore[method-assign,assignment]


# ---------------------------------------------------------------------------
# respx helpers
# ---------------------------------------------------------------------------


def _chat_completion(content: str) -> httpx.Response:
    """Build a minimal OpenAI-compatible chat completion response carrying *content*."""
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-m1-gate",
            "object": "chat.completion",
            "created": 1700000000,
            "model": "m",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 128,
                "completion_tokens": 48,
                "total_tokens": 176,
            },
        },
    )


def _ragas_llm_content(body: str) -> str:
    """Return the judge JSON RAGAS expects for the metric prompt embedded in *body*.

    RAGAS computes each metric individually, sending a distinct prompt whose embedded
    output schema names the fields the parser requires. Matching on those tokens lets a
    single respx route drive every metric to a non-NaN value (a static blob would leave
    answer_correctness/faithfulness/context_precision unparsed → NaN → NaN final_score).
    """
    if "noncommittal" in body:  # answer_relevancy: generated question
        return json.dumps({"question": _QUESTION, "noncommittal": 0})
    if (
        '"TP"' in body or "true positive" in body.lower()
    ):  # answer_correctness classifier
        return json.dumps(
            {
                "TP": [{"statement": "betalactamases", "reason": "supported"}],
                "FP": [],
                "FN": [],
            }
        )
    if "attributed" in body:  # context_recall classification
        return json.dumps(
            {
                "classifications": [
                    {"statement": "mecanismo", "reason": "presente", "attributed": 1}
                ]
            }
        )
    if "statements" in body and "verdict" in body:  # faithfulness NLI
        return json.dumps(
            {
                "statements": [
                    {
                        "statement": "betalactamases",
                        "reason": "no contexto",
                        "verdict": 1,
                    }
                ]
            }
        )
    if "statements" in body:  # statement generation (faithfulness / answer_correctness)
        return json.dumps(
            {"statements": ["As bactérias resistem via betalactamases e PBPs."]}
        )
    if "verdict" in body:  # context_precision verification
        return json.dumps({"reason": "o contexto é útil", "verdict": 1})
    return json.dumps({})


def _ragas_llm_route(request: httpx.Request) -> httpx.Response:
    """respx side-effect: route each RAGAS internal LLM call to a per-metric response."""
    return _chat_completion(_ragas_llm_content(request.content.decode("utf-8")))


# ---------------------------------------------------------------------------
# Qdrant fixtures — container session-scoped, data function-scoped
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qdrant_url() -> Any:
    """Yield a Qdrant base URL.

    Resolution order:
      1. ``QDRANT_URL`` env var — the ``services.qdrant`` container in CI.
      2. ``testcontainers`` (session-scoped) when Docker is available locally.
      3. otherwise skip — no Qdrant backend reachable.
    """
    env_url = os.getenv("QDRANT_URL")
    if env_url:
        yield env_url
        return

    if not _docker_available():
        pytest.skip("no Qdrant backend: set QDRANT_URL or run a Docker daemon")

    from testcontainers.qdrant import QdrantContainer

    with QdrantContainer() as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6333)
        yield f"http://{host}:{port}"


@pytest.fixture()
def populated_collection(qdrant_url: str) -> Any:
    """Create a fresh collection with the 5 fixture chunks; delete on teardown."""
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
                    id=i,
                    vector=_dense_vec(i),
                    payload={"text": text},
                )
                for i, text in enumerate(_CHUNK_TEXTS)
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
# The gate: one question through every M1 adapter
# ---------------------------------------------------------------------------


async def test_m1_pipeline_end_to_end(
    qdrant_url: str,
    populated_collection: None,
    tmp_path: pathlib.Path,
) -> None:
    """Drive one question through all M1 adapters and assert the persisted row."""
    _ = populated_collection

    # ── 1-2. Retrieval (Qdrant REAL) — outside respx, since respx would also
    #         intercept Qdrant's own httpx traffic. Top-3 of the 5 chunks. ──────
    retriever = QdrantRetrieverAdapter(
        url=qdrant_url,
        collection_map={_BASE: _COLLECTION},
        top_k=8,
    )
    _patch_query_points_with_dense_search(retriever, _dense_vec(0))
    retrieval = await retriever.search(base=BaseId(_BASE), question=_QUESTION, top_k=3)
    await retriever.close()

    assert len(retrieval.chunks) == 3
    assert len(retrieval.ids) == 3
    assert len(retrieval.scores) == 3
    assert all(isinstance(c, Chunk) for c in retrieval.chunks)

    # ── GoldChunkReader (Rodada 2 / retrieval-eval path) ────────────────────────
    gold_file = tmp_path / "gold_chunks.jsonl"
    gold_file.write_text(
        json.dumps({"question_id": _QID, "gold_chunk_ids": _GOLD_CHUNK_IDS}) + "\n",
        encoding="utf-8",
    )
    gold_reader = GoldChunkReaderAdapter(gold_file=gold_file)
    assert gold_reader.gold_for(_QID) == _GOLD_CHUNK_IDS

    # ── 3-5. Generation + judging — ALL vLLM HTTP mocked via respx ──────────────
    # generator, Prometheus judge and RAGAS's internal LLM each hit a distinct URL.
    # RAGAS is the REAL adapter (no _metrics): its LLM calls flow through respx
    # (item 3), driven per-metric so the 6 metrics are non-NaN. Embeddings stay local
    # (HuggingFace, no HTTP). assert_all_called + assert_all_mocked guarantee no real
    # network call escapes.
    registry = PromptRegistry()
    generator = VLLMGeneratorAdapter(url=_GEN_URL, model=_GEN_MODEL)
    judge = PrometheusJudgeAdapter(
        judge_url=_JUDGE_URL, registry=registry, model=_JUDGE_MODEL
    )
    ragas = RAGASLayer1Adapter(
        RagasAdapterConfig(judge_url=_RAGAS_URL, judge_model=_JUDGE_MODEL)
    )

    with respx.mock(assert_all_called=True) as mock:
        gen_route = mock.post(f"{_GEN_URL}/chat/completions").mock(
            return_value=_chat_completion(_FIXED_ANSWER)
        )
        judge_route = mock.post(f"{_JUDGE_URL}/chat/completions").mock(
            return_value=_chat_completion(
                json.dumps({"score": _JUDGE_SCORE, "feedback": _JUDGE_FEEDBACK})
            )
        )
        ragas_route = mock.post(f"{_RAGAS_URL}/chat/completions").mock(
            side_effect=_ragas_llm_route
        )

        generation = await generator.generate(
            llm=LLMId(_LLM),
            question=_QUESTION,
            contexts=retrieval.chunks,
            seed=_SEED,
            temperature=0.0,
        )
        sample = EvaluationSample(
            question_id=_QID,
            question=_QUESTION,
            ground_truth=_GROUND_TRUTH,
            generated_answer=generation.text,
            contexts=tuple(c.text for c in retrieval.chunks),
        )
        layer1 = await ragas.score(sample)
        rubric = await judge.score(sample)

    await generator.close()
    await judge.close()

    assert gen_route.called
    assert judge_route.called
    assert ragas_route.called  # RAGAS genuinely called its LLM through respx
    assert generation.text == _FIXED_ANSWER
    assert generation.batch_invariant is False  # generator regime (§9.2.4)
    assert rubric.score == pytest.approx(_JUDGE_SCORE)
    # Every weighted RAGAS field is finite (so final_score below is non-NaN).
    assert not math.isnan(layer1.answer_correctness)
    assert not math.isnan(layer1.faithfulness)
    assert not math.isnan(layer1.context_precision)
    assert not math.isnan(layer1.context_recall)
    assert not math.isnan(layer1.answer_relevancy)

    # ── 6. Deterministic metrics (BERTScore + ROUGE, CPU, real) ─────────────────
    det = DeterministicMetricsAdapter()
    aux = det.score(answer=generation.text, ground_truth=_GROUND_TRUTH)
    assert not math.isnan(aux.bertscore_f1)

    # ── 7. Final score (domain service) ─────────────────────────────────────────
    metrics = MetricVector(
        answer_correctness=layer1.answer_correctness,
        answer_similarity=layer1.answer_similarity,
        faithfulness=layer1.faithfulness,
        context_precision=layer1.context_precision,
        context_recall=layer1.context_recall,
        answer_relevancy=layer1.answer_relevancy,
        bertscore_f1=aux.bertscore_f1,
        rubric_biomed_score=rubric.score,
    )
    final_score = FinalScoreCalculator(DEFAULT_WEIGHTS).compute(metrics)
    assert not math.isnan(final_score.value)

    # ── 8. AnnotationReader (Camada 3) — apply the human critical-failure flag ──
    row_id = RowId.from_cell(
        run_id=_RUN_ID,
        phase=_PHASE,
        base=_BASE,
        llm=_LLM,
        seed=_SEED,
        question_id=_QID,
    )
    ann_file = tmp_path / "annotations.jsonl"
    ann_file.write_text(
        json.dumps({"run_id": _RUN_ID, "row_id": row_id.value, "flag": 0, "note": None})
        + "\n",
        encoding="utf-8",
    )
    annotations = AnnotationReaderAdapter(ann_file).read(_RUN_ID)
    flag = next((a.flag for a in annotations if a.row_id.value == row_id.value), None)
    assert flag == 0

    answer = GeneratedAnswer(
        row_id=row_id,
        question=Question(question_id=_QID, text=_QUESTION, ground_truth=_GROUND_TRUTH),
        base=BaseId(_BASE),
        llm=LLMId(_LLM),
        seed=Seed(_SEED),
        phase=_PHASE,
        generated_answer=generation.text,
        retrieved_chunk_ids=retrieval.ids,
        retrieved_chunks_text=tuple(c.text for c in retrieval.chunks),
        retrieval_scores=retrieval.scores,
    )
    result = EvaluationResult(
        answer=answer,
        metrics=metrics,
        final_score=final_score,
        # Generation cell → GENERATOR regime → batch_invariant=False in Parquet.
        determinism_regime=DeterminismRegime.GENERATOR,
        critical_failure_flag=flag,
        critical_failure_note=None,
    )

    # ── 9. Persist (ParquetStorage, real) ───────────────────────────────────────
    storage = ParquetStorage(
        tmp_path / "results",
        run_id=_RUN_ID,
        round_id=_ROUND_ID,
        judge_model=_JUDGE_MODEL,
        embedding_model="qdrant-inference",
        chunk_strategy="sentence",
        top_k=3,
        prompt_version=registry.prompt_version,
        temperature=0.0,
    )
    storage.append(result)

    # ── 10. Roundtrip + Parquet-level assertions ────────────────────────────────
    frame = storage.load(round_id=_ROUND_ID, phase=_PHASE)
    assert len(frame.results) == 1
    loaded = frame.results[0]
    assert loaded.answer.row_id.value == row_id.value
    assert loaded.answer.question.question_id == _QID
    assert loaded.answer.generated_answer == _FIXED_ANSWER
    assert not math.isnan(loaded.final_score.value)
    assert loaded.determinism_regime == DeterminismRegime.GENERATOR
    assert loaded.critical_failure_flag == 0

    # Direct Parquet column check: exactly 1 row, batch_invariant=False.
    # ParquetFile.read() bypasses Hive partition auto-detection, which would
    # otherwise infer a dictionary-typed ``round_id`` partition column conflicting
    # with the string ``round_id`` column stored in the file.
    parquet_files = list((tmp_path / "results").rglob(f"{row_id.value}.parquet"))
    assert len(parquet_files) == 1
    table = pq.ParquetFile(parquet_files[0]).read()
    assert table.num_rows == 1
    assert table.column("row_id")[0].as_py() == row_id.value
    assert table.column("batch_invariant")[0].as_py() is False
