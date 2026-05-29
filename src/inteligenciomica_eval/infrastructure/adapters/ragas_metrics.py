from __future__ import annotations

import importlib
import sys
import time
from types import ModuleType
from typing import Any

# ---------------------------------------------------------------------------
# Compatibility shim (versioned in-repo, CI-reproducible): ragas 0.3.x
# unconditionally imports langchain_community.chat_models.vertexai, but
# langchain-community >=0.4 removed that module (moved to langchain-google-
# vertexai). Using importlib.import_module avoids a top-level from-import
# that ruff I001/N814 would flag. The stub is injected into sys.modules
# before any ragas import so the chain resolves on every environment built
# from uv.lock without manual venv patching.
# ---------------------------------------------------------------------------
_LC_VERTEXAI = "langchain_community.chat_models.vertexai"
if _LC_VERTEXAI not in sys.modules:
    _stub = ModuleType(_LC_VERTEXAI)
    try:
        _lgv = importlib.import_module("langchain_google_vertexai")
        _stub.ChatVertexAI = getattr(_lgv, "ChatVertexAI", None)  # type: ignore[attr-defined]
        del _lgv
    except ImportError:
        pass
    sys.modules[_LC_VERTEXAI] = _stub
    del _stub
del _LC_VERTEXAI

import structlog  # noqa: E402
from langchain_community.embeddings import HuggingFaceEmbeddings  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic import SecretStr  # noqa: E402
from ragas.dataset_schema import SingleTurnSample  # noqa: E402
from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import (  # noqa: E402
    AnswerCorrectness,
    AnswerRelevancy,
    AnswerSimilarity,
    ContextPrecision,
    ContextRecall,
    Faithfulness,
)

from inteligenciomica_eval.domain.ports import (  # noqa: E402
    EvaluationSample,
    Layer1Metrics,
)

_log = structlog.get_logger()

_DEFAULT_JUDGE_MODEL = "prometheus-eval/prometheus-8x7b-v2.0"
_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

_METRIC_FIELDS = (
    "answer_correctness",
    "answer_similarity",
    "faithfulness",
    "context_precision",
    "context_recall",
    "answer_relevancy",
)


class RAGASLayer1Adapter:
    """Adapter MetricSuitePort que calcula as 6 métricas RAGAS de Camada 1 (§5.2).

    Cada métrica é calculada individualmente via ``single_turn_ascore`` — nunca em
    batch — para que falhas de parsing sejam isoladas por campo (ADR-007).

    O LLM-juiz aponta para o vllm-judge determinístico (Nota M1, item 5):
    ``ChatOpenAI(base_url=judge_url, temperature=0.0, api_key=SecretStr("EMPTY"))``.

    ``batch_invariant=True`` constante: RAGAS chama o mesmo vllm-judge configurado
    com ``VLLM_BATCH_INVARIANT=1`` (ADR-003, DeterminismRegime.JUDGE).

    Args:
        judge_url: URL base do vllm-judge (ex: ``"http://localhost:8001/v1"``).
        judge_model: identificador do modelo no vllm-judge.
        _metrics: dict injetável de ``{campo: objeto_métrica}`` — usado exclusivamente
            em testes para substituir os objetos RAGAS por AsyncMocks.
    """

    def __init__(
        self,
        judge_url: str,
        judge_model: str = _DEFAULT_JUDGE_MODEL,
        *,
        _metrics: dict[str, Any] | None = None,
    ) -> None:
        self._judge_url = judge_url

        if _metrics is None:
            llm = LangchainLLMWrapper(
                ChatOpenAI(
                    base_url=judge_url,
                    model=judge_model,
                    temperature=0.0,
                    api_key=SecretStr("EMPTY"),
                )
            )
            embeddings = LangchainEmbeddingsWrapper(
                HuggingFaceEmbeddings(model_name=_EMBED_MODEL)
            )
            # AnswerCorrectness needs answer_similarity wired explicitly: it is set
            # only in RAGAS's ``init(run_config)``, which ``single_turn_ascore`` does
            # NOT call — without this, ``_ascore`` asserts and answer_correctness is
            # always NaN (weights[1]=0.25 ≠ 0). Surfaced by the M1 integration gate
            # (TAREFA-021); the unit tests inject ``_metrics`` and never built this
            # branch. The same instance doubles as the standalone metric.
            answer_similarity = AnswerSimilarity(embeddings=embeddings)
            self._metrics: dict[str, Any] = {
                "answer_correctness": AnswerCorrectness(
                    llm=llm,
                    embeddings=embeddings,
                    answer_similarity=answer_similarity,
                ),
                "answer_similarity": answer_similarity,
                "faithfulness": Faithfulness(llm=llm),
                "context_precision": ContextPrecision(llm=llm),
                "context_recall": ContextRecall(llm=llm),
                "answer_relevancy": AnswerRelevancy(llm=llm, embeddings=embeddings),
            }
        else:
            self._metrics = _metrics

    async def score(self, sample: EvaluationSample) -> Layer1Metrics:
        """Calcula as 6 métricas RAGAS de Camada 1 para uma amostra.

        Cada métrica é calculada individualmente; exceções são capturadas por campo e
        retornam ``float("nan")`` sem afetar as demais métricas (ADR-007).

        Args:
            sample: amostra com pergunta, resposta gerada, ground truth e contextos.

        Returns:
            :class:`Layer1Metrics` com os 6 valores; campos individuais podem ser NaN.
        """
        ragas_sample = SingleTurnSample(
            user_input=sample.question,
            response=sample.generated_answer,
            reference=sample.ground_truth,
            retrieved_contexts=list(sample.contexts),
        )

        t0 = time.monotonic()
        scores: dict[str, float] = {}
        nan_fields: list[str] = []

        for field, metric in self._metrics.items():
            try:
                val = await metric.single_turn_ascore(ragas_sample)
                scores[field] = float(val)
            except Exception:
                _log.warning(
                    "ragas_metric_failed",
                    field=field,
                    judge_url=self._judge_url,
                )
                scores[field] = float("nan")
                nan_fields.append(field)

        latency_ms = int((time.monotonic() - t0) * 1000)

        _log.info(
            "ragas_layer1_computed",
            judge_url=self._judge_url,
            answer_correctness=scores["answer_correctness"],
            answer_similarity=scores["answer_similarity"],
            faithfulness=scores["faithfulness"],
            context_precision=scores["context_precision"],
            context_recall=scores["context_recall"],
            answer_relevancy=scores["answer_relevancy"],
            nan_fields=nan_fields,
            latency_ms=latency_ms,
        )

        return Layer1Metrics(
            answer_correctness=scores["answer_correctness"],
            answer_similarity=scores["answer_similarity"],
            faithfulness=scores["faithfulness"],
            context_precision=scores["context_precision"],
            context_recall=scores["context_recall"],
            answer_relevancy=scores["answer_relevancy"],
        )
