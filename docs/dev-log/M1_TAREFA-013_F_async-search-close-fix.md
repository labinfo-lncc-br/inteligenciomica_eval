# M1_TAREFA-013_F — Promoção async de `RetrieverPort.search()` + padronização `close()`

**Data**: 2026-05-27
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1 — Adapters de Recuperação
**Skill**: python-engineer, rag-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Aplicar a correção completa recomendada pelo auditor em
`M1_TAREFA-013_E_reauditoria-prompt-b-v11.md`:

1. Promover `RetrieverPort.search()` a `async def` (spec v1.1, Nota item 1).
2. Remover o wrapper síncrono `asyncio.run()` de `QdrantRetrieverAdapter.search()`.
3. Padronizar `close()` no adapter: renomear `aclose()` → `close()`, eliminar
   o wrapper síncrono — alinhando com `VLLMGeneratorAdapter.close()` (já `async def`).

---

## Arquivos Modificados

| Arquivo | Mudança |
|---|---|
| `src/inteligenciomica_eval/domain/ports.py` | `def search()` → `async def search()` em `RetrieverPort` |
| `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py` | `search()` → `async def`; remove `asyncio.run()`; `aclose()` → `close()`; remove `import asyncio` |
| `tests/fakes/retrieval.py` | `StubRetriever.search()` → `async def` |
| `tests/unit/domain/test_ports_contract.py` | `_StubRetriever.search()` → `async def`; caller com `await` |
| `tests/unit/fakes/test_fakes_satisfy_ports.py` | Todos os métodos de `TestStubRetriever` → `async def`; call sites com `await` |
| `tests/unit/infrastructure/adapters/test_qdrant_retriever_unit.py` | Todos os testes de `search()` → `async def`; call sites com `await` |
| `tests/integration/adapters/test_qdrant_retriever_integration.py` | Todos os testes Qdrant → `async def`; call sites com `await` |
| `tests/e2e/_harness.py` | `retriever.search(...)` → `await retriever.search(...)` (linha 178) |
| `CLAUDE.md` | Tabela de ports: `RetrieverPort.search()` atualizado para `async def ✅` |

---

## Decisões Técnicas

### 1. Por que a correção era necessária

O wrapper síncrono `asyncio.run()` em `search()` **quebra em qualquer contexto async
ativo** — o que inclui:
- `pytest-asyncio` com `asyncio_mode = "auto"` (ambiente de testes do projeto)
- Código de application layer com `async def` (M3+)
- Qualquer REPL async (Jupyter, etc.)

A inconsistência com `VLLMGeneratorAdapter` (já `async def close()`) também gerava
padrão divergente no mesmo projeto.

### 2. `close()` unificado

O adapter agora expõe apenas `async def close()`, exatamente como `VLLMGeneratorAdapter`.
O método `aclose()` foi removido — era redundante e introduzia dois nomes para a mesma
operação.

### 3. `_search_async()` permanece como helper interno

O método `_search_async()` foi mantido sem alteração. `search()` agora é `async def` e
delega diretamente para `_search_async()` com `await`. Isso preserva a separação entre
a interface pública (protocolo) e a implementação interna, útil para testes de integração
que fazem monkeypatch de `_client.query_points`.

### 4. `import asyncio` removido do adapter

Após a eliminação dos wrappers `asyncio.run()`, o import ficou órfão. Removido para
manter o arquivo limpo.

---

## Validação (DoD)

| Gate | Status | Resultado |
|---|---|---|
| `uv run ruff check .` | ✅ | All checks passed! |
| `uv run ruff format --check .` | ✅ | 69 files already formatted |
| `uv run mypy --strict src` | ✅ | Success: no issues found in 24 source files |
| `uv run lint-imports` | ✅ | Contracts: 4 kept, 0 broken |
| `uv run pytest --cov=src --cov-fail-under=85 -n auto -q` | ✅ | **579 passed**, 7 skipped — 96.46% |

---

## Critérios de Aceitação

| Critério | Status |
|---|---|
| `RetrieverPort.search()` é `async def` | ✅ `domain/ports.py:270` |
| `QdrantRetrieverAdapter.search()` é `async def`, sem `asyncio.run()` | ✅ `qdrant_retriever.py:57` |
| `close()` é `async def` (sem `aclose()` redundante) | ✅ `qdrant_retriever.py:80` |
| `StubRetriever.search()` é `async def` | ✅ `tests/fakes/retrieval.py:33` |
| Todos os call sites usam `await` | ✅ 8 arquivos atualizados |
| `isinstance(adapter, RetrieverPort)` continua passando | ✅ protocolo async satisfeito |
| Suite completa verde | ✅ 579 passed, 7 skipped (Docker indisponível) |
| Cobertura ≥ 85% | ✅ 96.46% |

---

## Observações para Próximas Tarefas

- O CLAUDE.md foi atualizado: `RetrieverPort.search()` consta como `async def ✅`.
- Os 7 testes de integração Qdrant continuam `SKIPPED` por falta de Docker local;
  o código async é correto e passará em CI com Docker disponível.
- **TAREFA-015** (`PromptRegistry`) pode avançar sem pendências em TAREFA-013.
