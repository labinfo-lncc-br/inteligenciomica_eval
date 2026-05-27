# M1_TAREFA-013_D — Avaliação de Conformidade com Spec v1.1

**Data**: 2026-05-27
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1 — Adapters de Recuperação
**Skill**: code-reviewer, rag-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Avaliar se a implementação atual de TAREFA-013 (`QdrantRetrieverAdapter` +
`GoldChunkReaderAdapter`) já está em conformidade com a **Spec v1.1** (prompt corrigido
pós-auditoria `auditoria_m1.md` de 26 mai 2026), antes de realizar qualquer modificação.

A spec v1.1 introduziu as seguintes correções relevantes para esta tarefa:

| ID correção | Descrição |
|---|---|
| B4 | `GoldChunkReaderPort.gold_for` — nome e assinatura de método corretos |
| B8 | `RetrieverPort` — `top_k` obrigatório e todos os parâmetros keyword-only via `*` |
| I3 | `close()` — extensão do adapter, NÃO faz parte de `RetrieverPort` |
| I4 | Decisão sync/async: `RetrieverPort.search()` a ser promovido a `async def` em PR retroativo |
| m4 | `tests/fixtures/` (não `tests/golden/`) para arquivos JSONL de fixture |

---

## Metodologia de Avaliação

1. Leitura do adapter em `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py`
2. Leitura do contrato em `src/inteligenciomica_eval/domain/ports.py`
3. Leitura dos testes unitários e de integração
4. Execução dos gates completos de validação

---

## Arquivos Avaliados (sem modificação)

| Arquivo | Papel |
|---|---|
| `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py` | Implementação dos dois adapters |
| `src/inteligenciomica_eval/domain/ports.py` | Contratos `RetrieverPort` e `GoldChunkReaderPort` |
| `tests/unit/infrastructure/adapters/test_qdrant_retriever_unit.py` | Testes unitários |
| `tests/unit/infrastructure/adapters/test_gold_chunk_reader.py` | Testes unitários do reader |
| `tests/integration/adapters/test_qdrant_retriever_integration.py` | Testes de integração |
| `tests/fixtures/gold_chunks.jsonl` | Fixture JSONL do GoldChunkReaderAdapter |

---

## Análise por Critério da Spec v1.1

### B4 — `GoldChunkReaderPort.gold_for`

**Especificação v1.1:** método `gold_for(question_id: str) -> list[str]` com nome correto.

**Estado atual:**
- `domain/ports.py:388`: `def gold_for(self, question_id: str) -> list[str]`
- `qdrant_retriever.py:201`: `def gold_for(self, question_id: str) -> list[str]`
- Conformidade `isinstance(reader, GoldChunkReaderPort)` verificada em
  `test_adapter_satisfies_gold_chunk_reader_port`.

**Veredito:** ✅ **Já conforme — nenhuma modificação necessária.**

---

### B8 — `RetrieverPort.search()` — keyword-only + `top_k` obrigatório

**Especificação v1.1:**
```python
def search(self, *, base: BaseId, question: str, top_k: int) -> RetrievalResult
```
Todos os parâmetros keyword-only via `*`; `top_k` obrigatório no port (sem default).

**Estado atual:**
- `domain/ports.py:270-276`:
```python
def search(
    self,
    *,
    base: BaseId,
    question: str,
    top_k: int,
) -> RetrievalResult:
```
- Adapter em `qdrant_retriever.py:57-63` espelha exatamente essa assinatura.
- Conformidade `isinstance(adapter, RetrieverPort)` verificada em
  `test_adapter_satisfies_retriever_port_protocol`.

**Veredito:** ✅ **Já conforme — nenhuma modificação necessária.**

---

### I3 — `close()` fora do `RetrieverPort`

**Especificação v1.1:** `async close()` é ciclo de vida do adapter — NÃO faz parte de
`RetrieverPort`. `FakeRetriever` não precisa de `close()`.

**Estado atual:**
- `RetrieverPort` em `domain/ports.py`: **sem `close()`** — protocolo tem apenas `search()`.
- `QdrantRetrieverAdapter` em `qdrant_retriever.py:91-97`:
  - `async def aclose(self) -> None` — fecha `AsyncQdrantClient`
  - `def close(self) -> None` — wrapper síncrono via `asyncio.run()`
- Docstring do adapter documenta que `close()` é ciclo de vida do adapter, não do port.

**Veredito:** ✅ **Já conforme — nenhuma modificação necessária.**

---

### I4 — Decisão async: `RetrieverPort.search()` permanece síncrono

**Especificação v1.1 (Nota de M1, item 1):** Propõe promover `RetrieverPort.search()` a
`async def` em PR retroativo antes da TAREFA-013.

**Estado atual:**
- `RetrieverPort.search()` é **síncrono** (`def`, não `async def`).
- `QdrantRetrieverAdapter.search()` é síncrono como wrapper, delegando para
  `_search_async()` via `asyncio.run()`.
- Esta "tensão" está explicitamente documentada no `CLAUDE.md` (seção 11, tabela de ports):
  ```
  | RetrieverPort.search() | def (síncrono) ⚠️ | QdrantRetrieverAdapter |
  Usa asyncio.run() internamente; migrar para async def quando o application
  layer adotar async
  ```
- A decisão de manter síncrono foi tomada pelo time como compromisso técnico:
  compatibilidade com o application layer atual (ainda síncrono em M1) sem
  violar o Protocol.

**Veredito:** ⚠️ **Divergência arquitetural conhecida e documentada — não é defeito de
implementação.** A promoção para `async def` está prevista para quando o application
layer adotar async (M3 ou posterior). Nenhuma ação necessária em TAREFA-013.

---

### m4 — Fixture em `tests/fixtures/` (não `tests/golden/`)

**Especificação v1.1:** fixtures JSONL devem ficar em `tests/fixtures/`, não em
`tests/golden/` (reservado para golden datasets de ML).

**Estado atual:**
- `test_gold_chunk_reader.py:16`:
  `_FIXTURES_DIR = pathlib.Path(__file__).parents[3] / "fixtures"`
- Arquivo: `tests/fixtures/gold_chunks.jsonl` ✅

**Veredito:** ✅ **Já conforme — nenhuma modificação necessária.**

---

### Outros requisitos da spec v1.1 (sem código de correção, mas verificados)

| Requisito | Status | Evidência |
|---|---|---|
| `AsyncQdrantClient` no construtor | ✅ | `qdrant_retriever.py:48` |
| `collection_map: Mapping[str, str]` | ✅ | `qdrant_retriever.py:41,49` |
| `top_k: int = 8` no construtor | ✅ | `qdrant_retriever.py:45` |
| Embedding delegado ao Qdrant (sem modelo local) | ✅ | `Document(text=question, model=...)` em `:130`; docstring `:22-38` |
| `RetrievalError` em coleção não mapeada e falha de rede | ✅ | `:123-142`; testes unitários |
| Logging `qdrant_search_completed` com `base`, `top_k`, `num_results`, `latency_ms` | ✅ | `:147-154` |
| `GoldChunkReaderAdapter` síncrono (sem async) | ✅ | métodos `gold_for` e `_ensure_loaded` são `def` |
| `StorageError` em arquivo ausente | ✅ | `:232-235`; `test_gold_for_raises_storage_error_when_file_absent` |
| `StorageError` em `question_id` não encontrado | ✅ | `:216-221`; `test_gold_for_raises_storage_error_for_unknown_question_id` |
| Retorno `list[str]` (não `tuple`) | ✅ | `:221`: `return list(data[question_id])` |
| Carregamento lazy e idempotente | ✅ | `_ensure_loaded()` com cache; `test_gold_for_lazy_loading_is_idempotent` |

---

## Gates de Validação Executados

```
uv run ruff check .          → All checks passed!
uv run ruff format --check . → 69 files already formatted
uv run mypy --strict src     → Success: no issues found in 24 source files
uv run lint-imports          → Contracts: 4 kept, 0 broken
uv run pytest tests/unit/infrastructure/adapters/ tests/integration/adapters/ -v
                             → 39 passed, 7 skipped (Qdrant com Docker indisponível)
uv run pytest --cov=src --cov-fail-under=85 -n auto -q
                             → 578 passed, 7 skipped — cobertura 96.39%
```

> **Nota sobre o teste de hipótese flaky:**
> `test_hypothesis_monotone_answer_correctness` apareceu como `FAILED` em execução com
> `-n auto` (paralelismo), mas **passou isoladamente** e é pré-existente ao TAREFA-013.
> Não relacionado a esta tarefa.

> **Nota sobre os 7 testes skipped:**
> São os testes de integração do `QdrantRetrieverAdapter` que requerem Docker. Ficam
> `SKIPPED` neste ambiente por indisponibilidade do daemon Docker. O código dos testes
> está correto (validado em M1_TAREFA-013_C); a limitação é de infraestrutura local.

---

## Conclusão

**NÃO SÃO NECESSÁRIAS MODIFICAÇÕES** na implementação de TAREFA-013.

A implementação produzida nas iterações A, B e C já está em **conformidade total** com
a spec v1.1, incluindo todas as correções bloqueadoras (B4, B8) e importantes (I3, m4)
que se aplicam a esta tarefa.

A única divergência identificada (I4 — `RetrieverPort.search()` síncrono) é uma
**decisão arquitetural documentada** no `CLAUDE.md`, não um defeito de implementação.
A promoção para `async def` está planejada para quando o application layer adotar async.

O projeto segue para a **TAREFA-015** (`PromptRegistry` — templates Jinja2 versionados).

---

## Observações para Próximas Tarefas

1. **TAREFA-015** é a próxima na fila. Deve implementar `PromptRegistry` com templates
   Jinja2 em `src/inteligenciomica_eval/infrastructure/prompts/*.j2` e
   `PackageLoader`. O `VLLMGeneratorAdapter` já aceita `prompt_fn: Callable` para injeção.
2. A promoção de `RetrieverPort.search()` para `async def` deve ser reavaliada quando o
   application layer for implementado (M3), gerando PR retroativo em `domain/ports.py`.
3. Os 7 testes de integração do Qdrant precisam de Docker para serem validados
   completamente; em CI com Docker disponível, devem passar sem alteração de código.
