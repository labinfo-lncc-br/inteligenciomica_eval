"""Configurações dos adapters de infraestrutura (frozen dataclasses).

Objetos de configuração simples, passados programaticamente aos adapters de
``infrastructure/adapters/``. Diferentemente de :mod:`schema` e :mod:`settings`
(fronteira de I/O — YAML/env via Pydantic), estes são DTOs internos: frozen
dataclasses sem validação de fronteira, imutáveis e tipados.

Cada adapter de M2 recebe a sua própria config:

* :class:`RagasAdapterConfig` — ``RAGASLayer1Adapter`` (TAREFA-023).
* :class:`RubricJudgeAdapterConfig` — ``PrometheusRubricJudgeAdapter`` (TAREFA-024).
* :class:`DeterministicAdapterConfig` — ``DeterministicMetricsAdapter`` (TAREFA-025).
"""

from __future__ import annotations

from dataclasses import dataclass

# Defaults compartilhados (mantidos como literais aqui para evitar dependência
# circular config → adapter; espelham as constantes do módulo do adapter).
_DEFAULT_JUDGE_MODEL = "prometheus-eval/prometheus-8x7b-v2.0"
_DEFAULT_HF_EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_DEFAULT_VLLM_EMBED_MODEL = "text-embedding"
# BERTScore: modelo multilíngue + idioma canônico do corpus InteligenciÔmica (PT-BR).
_DEFAULT_BERT_MODEL = "bert-base-multilingual-cased"
_DEFAULT_BERT_LANG = "pt"


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


@dataclass(frozen=True, slots=True)
class RubricJudgeAdapterConfig:
    """Configuração do :class:`PrometheusRubricJudgeAdapter` (TAREFA-024, §5.2).

    Camada 2 formal: rubrica biomédica de 6 dimensões avaliada pelo vllm-judge
    determinístico (``temperature=0.0``, ADR-003). O ``prompt_version`` **não** é
    campo desta config — é propriedade do artefato versionado (arquivo de prompt)
    e o adapter o deriva do próprio arquivo, expondo ``adapter.prompt_version``
    (fonte única para o schema §5.3).

    Args:
        vllm_judge_url: URL base do vllm-judge OpenAI-compatible, incluindo ``/v1``.
        judge_model_name: identificador do modelo juiz.
        vllm_judge_api_key: chave de API (placeholder ``"EMPTY"`` para vLLM local).
        timeout_s: timeout por requisição ao juiz, em segundos.
    """

    vllm_judge_url: str
    judge_model_name: str = _DEFAULT_JUDGE_MODEL
    vllm_judge_api_key: str = "EMPTY"
    timeout_s: int = 180


@dataclass(frozen=True, slots=True)
class DeterministicAdapterConfig:
    """Configuração do :class:`DeterministicMetricsAdapter` (TAREFA-025, §5.1/§5.2).

    Métricas auxiliares de Camada 1 sem LLM (BERTScore-F1 e ROUGE-L), CPU-bound e
    determinísticas. Todos os campos têm default — o adapter pode ser construído sem
    config; ``DeterministicAdapterConfig()`` reproduz o comportamento canônico de M1.

    **``lang="pt"`` é o idioma canônico do corpus InteligenciÔmica (PT-BR biomédico).**
    Mudar para ``"en"`` (ou qualquer outro) exigiria um **novo golden dataset** calibrado
    e **aprovação explícita da equipe** — os thresholds em ``det_metrics_pt_golden.json``
    são específicos do idioma. ``"pt"`` faz o BERTScore usar o ``bert-base-multilingual-cased``
    e o baseline de reescala correspondente (Nota M2 item 2; alinhado a TAREFA-018).

    Args:
        model_type: modelo HuggingFace do BERTScore (multilíngue por padrão).
        lang: idioma do corpus — **``"pt"`` canônico** (ver acima). Usado tanto na
            seleção do modelo quanto no baseline de reescala.
        rescale_with_baseline: reescala os scores pelo baseline do idioma (padrão
            ``True``), tornando a faixa mais interpretável.
        device: dispositivo do BERTScore (padrão ``"cpu"``) — fixado para impedir uso
            acidental de GPU em ambientes CUDA (adapter CPU-bound por design, §5.2).
    """

    model_type: str = _DEFAULT_BERT_MODEL
    lang: str = _DEFAULT_BERT_LANG
    rescale_with_baseline: bool = True
    device: str = "cpu"
