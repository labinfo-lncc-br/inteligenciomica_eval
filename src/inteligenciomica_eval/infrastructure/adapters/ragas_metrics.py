from __future__ import annotations

import importlib
import importlib.metadata
import sys
import time
from types import ModuleType
from typing import Any, Final

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

import openai  # noqa: E402
import structlog  # noqa: E402
from langchain_community.embeddings import HuggingFaceEmbeddings  # noqa: E402
from langchain_openai import ChatOpenAI, OpenAIEmbeddings  # noqa: E402
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

from inteligenciomica_eval.domain.errors import MetricComputationError  # noqa: E402
from inteligenciomica_eval.domain.ports import (  # noqa: E402
    EvaluationSample,
    Layer1Metrics,
)
from inteligenciomica_eval.infrastructure.config.adapter_configs import (  # noqa: E402
    RagasAdapterConfig,
)

_log = structlog.get_logger()

# ADR-003: o juiz determinístico exige concorrência 1; chamamos cada métrica
# sequencialmente (um ``await`` por vez, sem ``asyncio.gather``), o que efetiva
# este limite — nunca via ``ragas.evaluate(dataset)`` em batch.
RAGAS_MAX_CONCURRENCY: Final[int] = 1

# Erros transitórios de I/O do servidor juiz: viram MetricComputationError
# (falha total — Nota M2 item 4), distinta da falha de parsing (NaN por campo).
_IO_FAILURE_TYPES: Final[tuple[type[Exception], ...]] = (
    openai.APIConnectionError,
    openai.APITimeoutError,
)

_METRIC_FIELDS = (
    "answer_correctness",
    "answer_similarity",
    "faithfulness",
    "context_precision",
    "context_recall",
    "answer_relevancy",
)


def _is_io_failure(exc: BaseException) -> bool:
    """Retorna ``True`` se ``exc`` (ou sua cadeia de causas) é falha de I/O.

    RAGAS encapsula a exceção original do SDK OpenAI; percorremos
    ``__cause__``/``__context__`` para detectar ``APIConnectionError`` ou
    ``APITimeoutError`` em qualquer nível — sinal de servidor juiz indisponível.

    Args:
        exc: exceção capturada ao avaliar uma métrica RAGAS.

    Returns:
        ``True`` para falha total de I/O; ``False`` para falha de parsing/validação.
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, _IO_FAILURE_TYPES):
            return True
        current = current.__cause__ or current.__context__
    return False


def _build_embeddings(config: RagasAdapterConfig) -> tuple[Any, str]:
    """Constrói o wrapper de embeddings RAGAS e devolve a sua origem (Nota M2 item 5).

    Lógica de fallback:

    * ``config.vllm_embed_url`` definido → :class:`OpenAIEmbeddings` apontando para
      o endpoint OpenAI-compatible (origem ``"vllm_endpoint"``).
    * caso contrário → :class:`HuggingFaceEmbeddings` local em CPU, sem rede para
      embeddings (origem ``"hf_local"``, padrão).

    Args:
        config: configuração do adapter RAGAS.

    Returns:
        Tupla ``(LangchainEmbeddingsWrapper, embed_source)``.
    """
    if config.vllm_embed_url:
        base = OpenAIEmbeddings(
            base_url=config.vllm_embed_url,
            model=config.vllm_embed_model,
            api_key=SecretStr("EMPTY"),
            check_embedding_ctx_length=False,  # endpoint não-OpenAI (sem tiktoken)
        )
        return LangchainEmbeddingsWrapper(base), "vllm_endpoint"
    base_hf = HuggingFaceEmbeddings(model_name=config.hf_embed_model)
    return LangchainEmbeddingsWrapper(base_hf), "hf_local"


class RAGASLayer1Adapter:
    """Adapter MetricSuitePort que calcula as 6 métricas RAGAS de Camada 1 (§5.2).

    Cada métrica é calculada individualmente via ``single_turn_ascore`` — nunca em
    batch — para que falhas de parsing sejam isoladas por campo (ADR-007).

    O LLM-juiz aponta para o vllm-judge determinístico (Nota M1, item 5):
    ``ChatOpenAI(base_url=judge_url, temperature=0.0, api_key=SecretStr("EMPTY"))``.

    ``batch_invariant=True`` constante: RAGAS chama o mesmo vllm-judge configurado
    com ``VLLM_BATCH_INVARIANT=1`` (ADR-003, DeterminismRegime.JUDGE).

    Expõe :attr:`ragas_version` (lido de ``importlib.metadata``) para gravação no
    schema §5.3 — o campo ``ragas_version`` do Parquet é preenchido **via a config
    do run** (``RowProvenance.ragas_version`` do ``ParquetStorage``); o orquestrador
    lê ``adapter.ragas_version`` e o repassa à proveniência (opção escolhida).

    Args:
        config: :class:`RagasAdapterConfig` com URL do juiz, endpoint de embedding
            e ``ragas_max_concurrency`` (ADR-003).
        _metrics: dict injetável de ``{campo: objeto_métrica}`` — usado exclusivamente
            em testes para substituir os objetos RAGAS por AsyncMocks (pula a
            construção real de LLM/embeddings).
    """

    def __init__(
        self,
        config: RagasAdapterConfig,
        *,
        _metrics: dict[str, Any] | None = None,
    ) -> None:
        self._config = config
        self._judge_url = config.judge_url
        self._max_concurrency = config.ragas_max_concurrency
        # Versão do RAGAS exposta para proveniência (§5.3) e log da 1ª chamada.
        self.ragas_version: str = importlib.metadata.version("ragas")
        self._version_logged = False
        # Origem dos embeddings, sempre definida (mesmo com _metrics injetado).
        self._embed_source: str = (
            "vllm_endpoint" if config.vllm_embed_url else "hf_local"
        )

        if _metrics is None:
            llm = LangchainLLMWrapper(
                ChatOpenAI(
                    base_url=config.judge_url,
                    model=config.judge_model,
                    temperature=0.0,
                    api_key=SecretStr("EMPTY"),
                )
            )
            embeddings, self._embed_source = _build_embeddings(config)
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
            :class:`Layer1Metrics` com os 6 valores; campos individuais podem ser NaN
            quando o parsing/validação de uma métrica falha (isolado por campo).

        Raises:
            MetricComputationError: falha total de I/O (servidor juiz indisponível —
                ``APIConnectionError``/``APITimeoutError``). Não é absorvida como NaN;
                o ``RetryableMetricSuiteAdapter`` (TAREFA-027) faz o backoff (Nota M2
                item 4).
        """
        if not self._version_logged:
            _log.info(
                "ragas_adapter_first_call",
                ragas_version=self.ragas_version,
                embed_source=self._embed_source,
                max_concurrency=self._max_concurrency,
            )
            self._version_logged = True

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
            except Exception as exc:
                if _is_io_failure(exc):
                    # Falha total de I/O — propaga para o decorator de retry (ADR-007).
                    _log.error(
                        "ragas_io_failure",
                        field=field,
                        judge_url=self._judge_url,
                        error_type=type(exc).__name__,
                    )
                    raise MetricComputationError(
                        "ragas_layer1", f"I/O failure on {field}: {exc}"
                    ) from exc
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
            ragas_version=self.ragas_version,
            embed_source=self._embed_source,
            max_concurrency=self._max_concurrency,
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
