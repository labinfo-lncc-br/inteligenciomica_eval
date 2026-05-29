# M2_TAREFA-023_A — Upgrade `RAGASLayer1Adapter` (async + embed endpoint + golden PT)

**Data**: 2026-05-29
**Milestone**: M2 — Avaliação automática (Camadas 1+2, juiz determinístico)
**Épico**: E2
**Skill**: rag-engineer, ml-engineer
**Prioridade / Tamanho**: P0 / M
**Referência arquitetural**: TAREFA-202 (§14.5) — upgrade de M1/TAREFA-017 · ADR-003/006/007

## Objetivo

Consolidar o `RAGASLayer1Adapter` conforme §5.1 e ADR-006: endpoint de embedding
configurável e separado do juiz, `max_concurrency=1` explícito (determinismo),
`ragas_version` exposto e logado, golden PT-BR para smoke, e tratamento de falha
total de I/O via `MetricComputationError` (Nota M2 item 4).

## Arquivos Criados / Modificados

### Criados
- `src/inteligenciomica_eval/infrastructure/config/adapter_configs.py` —
  `RagasAdapterConfig` (frozen dataclass): `judge_url`, `judge_model`,
  `vllm_embed_url`, `vllm_embed_model`, `hf_embed_model`, `ragas_max_concurrency=1`.
- `tests/golden/ragas_pt_smoke.json` — 1 amostra PT-BR biomédica (resistência a
  betalactâmicos) + `expected_answer_correctness_min: 0.4`.
- `tests/integration/adapters/test_ragas_smoke.py` — smoke PT skipável
  (`@pytest.mark.integration`, skip sem `VLLM_JUDGE_URL`).

### Modificados
- `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py`:
  - construtor passa a receber `RagasAdapterConfig` (em vez de `judge_url`/`judge_model` soltos);
  - `RAGAS_MAX_CONCURRENCY: Final[int] = 1` com comentário ADR-003;
  - `_build_embeddings(config) -> (wrapper, source)` — fallback HF local vs vllm endpoint;
  - `_is_io_failure(exc)` — percorre `__cause__`/`__context__` p/ detectar I/O do SDK OpenAI;
  - `score`: falha de I/O total → `MetricComputationError`; parsing → NaN por campo;
  - `ragas_version` (de `importlib.metadata`), `embed_source` e `max_concurrency` no log;
  - `ragas_adapter_first_call` emitido só na 1ª chamada.
- `tests/unit/infrastructure/adapters/test_ragas_layer1.py` — helper migrado p/ config +
  4 novas classes (IOFailure, EmbedFallback, RagasVersion, log embed_source). 18 → 26 testes.
- Callers atualizados p/ `RagasAdapterConfig`: `tests/e2e/test_m1_smoke_e2e.py` (×2),
  `tests/integration/test_m1_pipeline_integration.py` (×1).

## Decisões Técnicas

1. **Fallback de embed = HF local** (Prompt A item 2 autoritativo). A "Nota M2 item 5"
   menciona `VLLM_EMBED_URL` com fallback para `VLLM_JUDGE_URL`; interpretei isso como
   resolução de **variável de ambiente na camada de settings/orquestração**, não no
   adapter. O adapter recebe `vllm_embed_url` explícito e, quando `None`, usa
   `HuggingFaceEmbeddings` (CPU, sem rede) — exatamente como o Prompt A item 2 exige.
2. **I/O total vs parsing** (Nota M2 item 4). `_is_io_failure` classifica a exceção:
   `openai.APIConnectionError`/`APITimeoutError` (direto ou encadeado) → `MetricComputationError`
   (o `RetryableMetricSuiteAdapter` da TAREFA-027 fará o backoff); qualquer outra exceção
   → NaN isolado por campo (comportamento de M1 preservado). Os testes de M1 (RuntimeError/
   ValueError) continuam virando NaN, sem regressão.
3. **`max_concurrency=1` efetivado pelo loop sequencial.** Não há `ragas.evaluate()` batch
   nem `asyncio.gather`; cada métrica é `await`-ada uma por vez. A constante documenta o
   invariante (ADR-003) e é logada (`max_concurrency`).
4. **`ragas_version` gravado via config do run.** O schema §5.3 já tem `ragas_version`
   (preenchido por `RowProvenance` no `ParquetStorage`); o adapter apenas **expõe**
   `adapter.ragas_version` para o orquestrador repassar à proveniência — sem alterar schema.
5. **`RagasAdapterConfig` = frozen dataclass**, não Pydantic: é DTO interno (não fronteira
   de I/O YAML/env). Pydantic permanece reservado a `schema.py`/`settings.py`.

## Problemas Encontrados e Soluções

- **Quebra de assinatura do construtor.** Migrar para `RagasAdapterConfig` quebrou 3
  callers (smoke e2e ×2, integration ×1) — todos atualizados. Os unit tests usam o helper
  `_make_adapter`, refatorado para aceitar `config`.
- **Cobrir os ramos de embed sem carregar modelo.** Extraí `_build_embeddings` como função
  de módulo e a testei isoladamente com `mocker.patch` em `HuggingFaceEmbeddings`/
  `OpenAIEmbeddings`/`LangchainEmbeddingsWrapper` — nenhum modelo real é carregado no unit.
- **isort.** Ruff reordenou os imports do teste; aplicado `ruff check --fix`.

## Validação (DoD §14.2)

```
ruff check / format       → OK (88 files)
mypy --strict src         → Success (31 source files)
lint-imports              → 4 kept, 0 broken
pytest test_ragas_layer1  → 26 passed
pytest (full, -n 4)       → 715 passed, 12 skipped — 96.87% cobertura
ragas_metrics.py          → 92% (linhas 176-192 = construção real, só no integration)
```

## Critérios de Aceitação (TAREFA-023)

- [x] `isinstance(adapter, MetricSuitePort)` True (`@runtime_checkable`).
- [x] `max_concurrency=1` como constante `Final[int]` documentada ADR-003; sem `evaluate()` batch.
- [x] Ramo HF-embed e ramo vllm-embed ambos cobertos no unit (`TestEmbedFallback`).
- [x] `ragas_version` lido de `importlib.metadata`, logado na 1ª chamada.
- [x] `embed_source` ("hf_local" | "vllm_endpoint") no log `ragas_layer1_computed`.
- [x] NaN por métrica individual; falha total → `MetricComputationError` (`TestIOFailure`).
- [x] Golden PT em `tests/golden/ragas_pt_smoke.json`; smoke skipável sem `VLLM_JUDGE_URL`.
- [x] `judge_url`/`embed_url` nunca hardcoded (sempre via config). import-linter OK; mypy --strict.

## Observações para Próximas Tarefas

- **TAREFA-027 (`RetryableMetricSuiteAdapter`)**: deve absorver o `MetricComputationError`
  agora levantado pelo adapter em falha de I/O, aplicar backoff e devolver `Layer1Metrics`
  all-NaN ao esgotar tentativas.
- **TAREFA-026 (`ComputeMetricsUseCase`)**: ao instanciar o `RAGASLayer1Adapter`, ler
  `adapter.ragas_version` e repassar ao `ParquetStorage`/`RowProvenance` (proveniência §5.3).
- O smoke real (`test_ragas_smoke.py`) roda no CI quando `VLLM_JUDGE_URL` estiver disponível
  (ambiente com juiz); localmente fica skipado.
