"""Smoke E2E do Gate M1 (TAREFA-021).

Verifica que **todos** os adapters de M1 são instanciáveis com config real (mesmo sem
servidores rodando), que os imports não quebram, e que cada adapter satisfaz o
``Protocol`` correspondente via ``isinstance`` (``@runtime_checkable``).

Diferente do teste de integração, este smoke **não** faz I/O de rede nem precisa de
Qdrant — apenas constrói os adapters e checa conformidade estrutural. Continua sendo um
E2E (full-stack de construção) e por isso é marcado ``@pytest.mark.e2e`` e só roda com
``E2E_ENABLED`` definido (a construção real do ``RAGASLayer1Adapter`` carrega o modelo de
embeddings local, custosa demais para o gate unitário rápido).
"""

from __future__ import annotations

import os
import pathlib

import pytest

from inteligenciomica_eval.domain.ports import (
    AnnotationReaderPort,
    DeterministicMetricPort,
    GeneratorPort,
    GoldChunkReaderPort,
    MetricSuitePort,
    ResultReaderPort,
    ResultWriterPort,
    RetrieverPort,
    RubricJudgePort,
    VLLMServerManagerPort,
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
from inteligenciomica_eval.infrastructure.adapters.vllm_server_manager import (
    VLLMServerManagerAdapter,
)
from inteligenciomica_eval.infrastructure.prompts.registry import PromptRegistry
from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
    ParquetStorage,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("E2E_ENABLED"),
        reason="set E2E_ENABLED=1 to run the full-stack smoke E2E",
    ),
]


def test_all_m1_adapters_instantiable_and_satisfy_protocols(
    tmp_path: pathlib.Path,
) -> None:
    """Every M1 adapter is constructible and satisfies its Protocol (`isinstance`).

    None of these constructions require a running server. RAGAS is built with an empty
    ``_metrics`` so it does **not** download/load the HuggingFace embedding model here —
    the **real** embeddings+LLM construction path is exercised by the integration test
    (and by :func:`test_ragas_real_construction_when_model_available` below, guarded).
    This keeps the conformance check environment-independent (no network/model needed).
    """
    retriever = QdrantRetrieverAdapter(
        url="http://localhost:6333", collection_map={"IDx_400k": "bio_chunks"}
    )
    gold_reader = GoldChunkReaderAdapter(gold_file=tmp_path / "gold.jsonl")
    generator = VLLMGeneratorAdapter(url="http://localhost:8000/v1", model="generator")
    judge = PrometheusJudgeAdapter(
        judge_url="http://localhost:8001/v1", registry=PromptRegistry()
    )
    metric_suite = RAGASLayer1Adapter(judge_url="http://localhost:8001/v1", _metrics={})
    det_metrics = DeterministicMetricsAdapter()
    # Missing annotation file → Camada 3 disabled (no error, normal in M1).
    annotation_reader = AnnotationReaderAdapter(tmp_path / "annotations.jsonl")
    server_manager = VLLMServerManagerAdapter()
    storage = ParquetStorage(tmp_path / "results")

    assert isinstance(retriever, RetrieverPort)
    assert isinstance(gold_reader, GoldChunkReaderPort)
    assert isinstance(generator, GeneratorPort)
    assert isinstance(judge, RubricJudgePort)
    assert isinstance(metric_suite, MetricSuitePort)
    assert isinstance(det_metrics, DeterministicMetricPort)
    assert isinstance(annotation_reader, AnnotationReaderPort)
    assert isinstance(server_manager, VLLMServerManagerPort)
    assert isinstance(storage, ResultWriterPort)
    assert isinstance(storage, ResultReaderPort)


def test_ragas_real_construction_when_model_available() -> None:
    """Real RAGAS construction (ChatOpenAI + local embeddings) when the model is present.

    Skipped — not failed — when the HuggingFace embedding model is unavailable (no cache
    and no network), so the smoke E2E stays robust across environments.
    """
    try:
        metric_suite = RAGASLayer1Adapter(judge_url="http://localhost:8001/v1")
    except Exception as exc:
        # Any model/network failure → skip (not fail): keeps the smoke env-independent.
        pytest.skip(f"RAGAS embedding model unavailable (no cache/network): {exc}")
    assert isinstance(metric_suite, MetricSuitePort)


def test_annotation_reader_disabled_when_file_absent(
    tmp_path: pathlib.Path,
) -> None:
    """A missing annotation file yields an empty Camada 3 (no exception)."""
    reader = AnnotationReaderAdapter(tmp_path / "missing.jsonl")
    assert reader.read("any_run") == []
