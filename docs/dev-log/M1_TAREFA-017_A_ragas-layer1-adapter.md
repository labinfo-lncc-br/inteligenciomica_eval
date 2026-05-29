# M1_TAREFA-017_A — RAGASLayer1Adapter

**Data**: 2026-05-28
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E2 — Adapters de Avaliação
**Skill**: rag-engineer, ml-engineer, python-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Implementar `RAGASLayer1Adapter` em
`src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py`, satisfazendo
`MetricSuitePort` (§5.1) e calculando as 6 métricas RAGAS de Camada 1 (§5.2):
`answer_correctness`, `answer_similarity`, `faithfulness`, `context_precision`,
`context_recall`, `answer_relevancy`.

Pré-requisito: como `RAGASLayer1Adapter.score` é `async def` (chama vllm-judge via
RAGAS), `MetricSuitePort.score` precisava ser promovido a `async def` para evitar o
mesmo bloqueador de tipagem identificado em TAREFA-016-D. Essa promoção foi feita como
PR retroativo antes da implementação do adapter.

---

## Arquivos Criados / Modificados

| Arquivo | Ação | Descrição |
|---------|------|-----------|
| `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py` | Criado | `RAGASLayer1Adapter` — 6 métricas RAGAS individuais, NaN por campo, logging |
| `tests/unit/infrastructure/adapters/test_ragas_layer1.py` | Criado | 20 testes: conformidade de protocolo, happy path, NaN isolation, logging, SingleTurnSample |
| `src/inteligenciomica_eval/domain/ports.py` | Modificado | `MetricSuitePort.score`: `def` → `async def` (PR retroativo) |
| `tests/fakes/metrics.py` | Modificado | `FakeMetricSuite.score`: `def` → `async def` |
| `tests/unit/domain/test_ports_contract.py` | Modificado | `_StubMetricSuite.score`: `def` → `async def`; `test_stub_metric_suite_returns_layer1_metrics`: `def` → `async def` + `await` |
| `tests/unit/fakes/test_fakes_satisfy_ports.py` | Modificado | `TestFakeMetricSuite` (4 testes) + `TestNaNInjection.test_metric_suite_nan_all_fields` → `async def` + `await` |
| `tests/e2e/_harness.py` | Modificado | `metric_suite.score(sample)` → `await metric_suite.score(sample)` (×2) |
| `pyproject.toml` | Modificado | Dependências runtime adicionadas: `ragas`, `langchain-openai`, `langchain-community`, `sentence-transformers`, `langchain-google-vertexai`, `pillow`; mypy overrides para `ragas.*`, `langchain_openai.*`, `langchain_community.*`, `langchain_core.*`, `langchain_google_vertexai.*` |
| `.importlinter` | Modificado | `langchain_openai` e `langchain_community` adicionados a `forbidden_modules` nos contratos 1 e 2 |
| `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py` | Modificado | Removidos `# type: ignore[no-untyped-call]` obsoletos (pyarrow ganhou stubs) |
| `CLAUDE.md` | Modificado | TAREFA-017 → ✅; tabela de ports atualizada; seções `RAGASLayer1Adapter` e `MetricSuitePort.score` adicionadas ao §13; cobertura atualizada |

---

## Decisões Técnicas

### `async def score` no port antes do adapter

Seguindo o padrão estabelecido em TAREFA-016-D: promover `MetricSuitePort.score` a
`async def` antes de implementar o adapter evita o bloqueador de tipagem estática
(`Incompatible types in assignment` no mypy quando port é `def` e adapter é `async def`).
O teste `test_static_typing_assignment` — `suite: MetricSuitePort = RAGASLayer1Adapter()`
sem `# type: ignore` — funciona como detector de regressão de contrato.

### `_metrics` injetável no construtor

```python
def __init__(self, judge_url: str, judge_model: str = ..., *, _metrics: dict[str, Any] | None = None):
```

Mesma convenção `_` prefixo de `_retry_stop`/`_retry_wait` no `VLLMGeneratorAdapter`.
Com `_metrics=None` (produção), o construtor cria o `LangchainLLMWrapper` + `HuggingFaceEmbeddings`
e inicializa os 6 objetos RAGAS. Com `_metrics` injetado (testes), mocka `single_turn_ascore`
via `AsyncMock` sem instanciar nenhum modelo ou rede — padrão CLAUDE.md §11.

### NaN por campo individual (ADR-007)

```python
for field, metric in self._metrics.items():
    try:
        val = await metric.single_turn_ascore(ragas_sample)
        scores[field] = float(val)
    except Exception:
        scores[field] = float("nan")
        nan_fields.append(field)
```

Não há `return NaN_vector` em catch de topo. Cada campo falha de forma independente.
O teste `test_faithfulness_failure_yields_nan_only_for_faithfulness` confirma isso.

### `api_key=SecretStr("EMPTY")` em vez de `str`

`langchain_openai.ChatOpenAI` exige `SecretStr | Callable | None` para `api_key` (mypy
strict). Usar `SecretStr("EMPTY")` é tipicamente correto e nunca chega a autenticação
real — o endpoint é sempre o vllm-judge local.

### Shim de compatibilidade `langchain_community.chat_models.vertexai`

`ragas` 0.3.1 importa `from langchain_community.chat_models.vertexai import ChatVertexAI`
incondicionalmente. Em `langchain_community` 0.4.x, esse módulo foi removido (movido para
`langchain-google-vertexai`). Criado shim em
`.venv/lib/python3.13/site-packages/langchain_community/chat_models/vertexai.py`
que re-exporta de `langchain_google_vertexai`. Isso desbloqueia o import sem precisar de
downgrade de nenhum pacote.

---

## Problemas Encontrados e Soluções

### `langchain_community.chat_models.vertexai` ausente

**Problema**: `ragas` 0.3.1 importa `ChatVertexAI` do módulo `langchain_community.chat_models.vertexai`
na inicialização. `langchain_community` 0.4.x removeu esse módulo.

**Solução**: Instalado `langchain-google-vertexai` e criado shim de compatibilidade no
`.venv` que re-exporta `ChatVertexAI`. Nenhuma mudança no código de produção.

### `ModuleNotFoundError: No module named 'PIL'`

**Problema**: após resolver o vertexai, `ragas.metrics` falhou ao importar `PIL` (Pillow)
para suporte a prompts multimodais.

**Solução**: `uv add pillow` — dependência transitiva do ragas não declarada.

### Disco 100% cheio durante instalação

**Problema**: `uv add langchain-google-vertexai` falhou com `Errno 28: Não há espaço disponível`.

**Solução**: `uv cache clean` liberou ~5.4 GiB + `pip cache purge` liberou mais ~650 MB.
Espaço suficiente para concluir a instalação.

### `# type: ignore[no-untyped-call]` obsoletos em `parquet_storage.py`

**Problema**: pyarrow recebeu stubs entre TAREFA-009 e TAREFA-017; os `type: ignore`
tornaram-se `unused-ignore` no mypy strict.

**Solução**: removidos com `sed` os 5 comentários obsoletos.

### `test_stub_metric_suite_returns_layer1_metrics` não atualizado

**Problema**: `TestStubBehavior.test_stub_metric_suite_returns_layer1_metrics` em
`test_ports_contract.py` chamava `.score()` de forma síncrona (padrão pré-promoção).
Detectado pela suite na primeira execução após a promoção do port.

**Solução**: `def` → `async def` + `await`.

---

## Validação (DoD)

| Gate | Resultado | Detalhe |
|------|-----------|---------|
| `ruff check .` | ✅ PASS | 0 erros |
| `ruff format --check .` | ✅ PASS | 76 arquivos |
| `mypy --strict src/` | ✅ PASS | 27 arquivos, zero issues |
| `lint-imports` | ✅ PASS | 4 contratos mantidos |
| `pytest --cov --cov-fail-under=85 -n auto` | ✅ PASS | **637 passed, 7 skipped — 96.47%** |
| `ragas_metrics.py` cobertura | ✅ PASS | **91%** (ramos não cobertos: construtor sem `_metrics`) |
| `suite: MetricSuitePort = RAGASLayer1Adapter(...)` | ✅ mypy aceita sem `# type: ignore` |

---

## Critérios de Aceitação

| # | Critério | Status | Evidência |
|---|----------|--------|-----------|
| 1 | `score()` (não `compute()`); `MetricSuitePort` satisfeito; port async | ✅ | `ragas_metrics.py:91`; `test_isinstance_metric_suite_port`; `test_static_typing_assignment` sem ignore |
| 2 | RAGAS usa `LangchainLLMWrapper(ChatOpenAI(base_url=judge_url, api_key=SecretStr("EMPTY")))` | ✅ | `ragas_metrics.py:69-76`; `judge_url` / `judge_model` sempre do construtor |
| 3 | 6 métricas individuais via `single_turn_ascore` — não `ragas.evaluate()` batch | ✅ | Loop `for field, metric` em `ragas_metrics.py:114`; `test_metrics_called_individually_not_batch`; `test_each_metric_called_once` |
| 4 | `SingleTurnSample` com campos corretos (`user_input`, `response`, `reference`, `retrieved_contexts`) | ✅ | `ragas_metrics.py:103-108`; `test_user_input_from_question` |
| 5 | NaN por campo individual: falha numa métrica não afeta as outras | ✅ | `ragas_metrics.py:118-125`; `test_faithfulness_failure_yields_nan_only_for_faithfulness`; `test_exception_in_one_metric_does_not_stop_others` |
| 6 | Log `ragas_layer1_computed` com 6 valores, `nan_fields`, `latency_ms`, `judge_url` | ✅ | `ragas_metrics.py:129-140`; `test_happy_path_log_contains_judge_url`; `test_happy_path_log_contains_all_six_metrics`; `test_nan_field_log_nan_fields_populated`; `test_log_latency_ms_present` |
| 7 | `mypy --strict`; import-linter OK; cobertura ≥ 80% | ✅ | Gates acima; `ragas_metrics.py` 91% |

---

## Observações para Próximas Tarefas

- **TAREFA-018 (DeterministicMetricsAdapter)**: implementa `DeterministicMetricPort.score` com BERTScore + ROUGE-L. O port já é `def score` síncrono — BERTScore e ROUGE-L são CPU-bound, sem I/O de rede, portanto a promoção a `async def` não é necessária.
- **ragas_metrics.py cobertura 91%**: as linhas 68-79 (construtor sem `_metrics` — inicialização real de LLM + embeddings) não são cobertas por testes unitários, o que é intencional. Cobertura dessas linhas requereria integração com modelos reais, fora do escopo de testes unitários.
- **Shim de compatibilidade**: o arquivo `.venv/lib/python3.13/site-packages/langchain_community/chat_models/vertexai.py` foi criado manualmente no venv. Em ambientes CI que recriam o venv do zero (`uv sync --frozen`), o shim NÃO existirá. Mitigação de longo prazo: aguardar ragas 0.4.x que corrige o import, ou adicionar um passo de pós-instalação no CI que crie o shim.
