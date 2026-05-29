"""Configurações dos adapters de infraestrutura (frozen dataclasses).

Objetos de configuração simples, passados programaticamente aos adapters de
``infrastructure/adapters/``. Diferentemente de :mod:`schema` e :mod:`settings`
(fronteira de I/O — YAML/env via Pydantic), estes são DTOs internos: frozen
dataclasses sem validação de fronteira, imutáveis e tipados.

Cada adapter de M2 recebe a sua própria config:

* :class:`RagasAdapterConfig` — ``RAGASLayer1Adapter`` (TAREFA-023).
"""

from __future__ import annotations

from dataclasses import dataclass

# Defaults compartilhados (mantidos como literais aqui para evitar dependência
# circular config → adapter; espelham as constantes do módulo do adapter).
_DEFAULT_JUDGE_MODEL = "prometheus-eval/prometheus-8x7b-v2.0"
_DEFAULT_HF_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_DEFAULT_VLLM_EMBED_MODEL = "text-embedding"


@dataclass(frozen=True, slots=True)
class RagasAdapterConfig:
    """Configuração do :class:`RAGASLayer1Adapter` (TAREFA-023, §5.2, ADR-006).

    O endpoint de embedding é **separado** do juiz (Nota M2 item 5): quando
    ``vllm_embed_url`` está definido, os embeddings de
    :class:`~ragas.metrics.AnswerSimilarity` vêm de um endpoint OpenAI-compatible
    (``vllm_endpoint``); caso contrário, do modelo local HuggingFace
    (``hf_local``). Veja :func:`~...ragas_metrics._build_embeddings`.

    Args:
        judge_url: URL base do vllm-judge OpenAI-compatible, incluindo ``/v1``.
        judge_model: identificador do modelo no vllm-judge.
        vllm_embed_url: URL base de um endpoint de embedding OpenAI-compatible,
            incluindo ``/v1``; ``None`` ⇒ fallback para HuggingFace local.
        vllm_embed_model: nome do modelo de embedding servido em ``vllm_embed_url``
            (relevante apenas quando ``vllm_embed_url`` está definido).
        hf_embed_model: modelo de embedding HuggingFace local (CPU) usado no
            fallback — leve, sem chamada de rede para embeddings.
        ragas_max_concurrency: concorrência máxima das chamadas RAGAS; mantido
            em ``1`` para preservar o determinismo do juiz (ADR-003). Ver a
            constante ``RAGAS_MAX_CONCURRENCY`` no módulo do adapter.
    """

    judge_url: str
    judge_model: str = _DEFAULT_JUDGE_MODEL
    vllm_embed_url: str | None = None
    vllm_embed_model: str = _DEFAULT_VLLM_EMBED_MODEL
    hf_embed_model: str = _DEFAULT_HF_EMBED_MODEL
    # ADR-003: determinismo do juiz exige concorrência 1 (espelha RAGAS_MAX_CONCURRENCY).
    ragas_max_concurrency: int = 1
