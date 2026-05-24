# M1_TAREFA-013_B — Auditoria QdrantRetrieverAdapter + GoldChunkReaderAdapter

**Data**: 2026-05-24
**Milestone**: M1 — Adapters de Recuperação e Geração
**Épico**: E1
**Skill**: code-reviewer, rag-engineer, test-engineer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Auditar a implementação da TAREFA-013 contra `docs/arquitetura_detalhada_validacao_inteligenciomica.md` §5.1, a nota operacional de M1, e os critérios de teste/containers, sem reescrever o código.

## Arquivos Criados / Modificados

| Arquivo | Ação |
|---|---|
| `docs/dev-log/M1_TAREFA-013_B_auditoria-qdrant-gold-chunk.md` | Criado |

## Decisões Técnicas

- A verificação foi feita por leitura de contrato (`domain/ports.py`), adapter real, testes unitários/integrados e execução dos gates pedidos.
- O item de cobertura foi avaliado pelo gate real do projeto (`pyproject.toml` usa `fail_under = 85`, não 80).
- O item de integração Qdrant foi avaliado com duas lentes: estrutura dos testes e execução real do comando pedido.

## Problemas Encontrados e Soluções

### Divergência principal

Os testes de integração do retriever usam `testcontainers.qdrant`, `scope="session"` para o container e fixture funcional para dados, mas **não exercitam o caminho real de produção** (`query_points` com `Document`). Em vez disso, fazem monkeypatch de `_search_async` para usar `adapter._client.search(...)` com vetor denso (`tests/integration/adapters/test_qdrant_retriever_integration.py:148-200`). Isso reduz a força da evidência sobre o critério arquitetural "busca por texto do Qdrant".

### Limitação operacional observada

O comando solicitado `pytest -m integration tests/integration/adapters/test_qdrant_retriever_integration.py -v` foi executado, mas os 7 testes dependentes de Docker ficaram `SKIPPED` por indisponibilidade do daemon. Portanto, o requisito de integração real com Qdrant containerizado não foi comprovado nesta máquina.

## Validação (DoD)

| Gate | Status | Evidência |
|---|---|---|
| `uv run pytest -m integration tests/integration/adapters/test_qdrant_retriever_integration.py -v` | ⚠️ Parcial | `2 passed, 7 skipped` |
| `uv run lint-imports` | ✅ | `4 kept, 0 broken` |
| `uv run mypy --strict src` | ✅ | `Success: no issues found in 23 source files` |
| `uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n auto` | ✅ | `562 passed, 7 skipped`, cobertura total `96.33%` |
| `Pydantic` ausente em `domain/` | ✅ | sem ocorrências em `src/inteligenciomica_eval/domain/`; imports apenas em `infrastructure/config/schema.py:7-9` e `infrastructure/config/settings.py:6` |

## Critérios de Aceitação

| Critério | Status | Evidência |
|---|---|---|
| 1. `QdrantRetrieverAdapter` usa `AsyncQdrantClient`; construtor recebe `url`, `collection_map`, `top_k` | ✅ | `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:40-51` |
| 2. `search` bate com `RetrieverPort.search` e retorna `RetrievalResult` | ✅ | contrato `src/inteligenciomica_eval/domain/ports.py:267-284`; implementação `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:57-85`; DTO `src/inteligenciomica_eval/domain/ports.py:37-49` |
| 3. Adapter não chama embedding externo; usa texto no Qdrant; docstring explica | ✅ | docstring `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:22-38`; uso de `Document(text=question, model=self._embedding_model)` em `:130-138` |
| 4. `RetrievalError` em falha de conexão/coleção inexistente; `close()` existe | ✅ | `RetrievalError` em `src/inteligenciomica_eval/domain/errors.py:181-190`; wrapping em `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:123-142`; `close/aclose` em `:91-97`; teste de coleção inexistente em `tests/integration/adapters/test_qdrant_retriever_integration.py:324-335` |
| 5. Logging estruturado com `latency_ms`, `base`, `num_results` | ✅ | `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:147-154` |
| 6. `GoldChunkReaderAdapter` lê JSONL, é síncrono, levanta `StorageError` nos dois casos | ✅ | implementação `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:176-254`; `StorageError` em `src/inteligenciomica_eval/domain/errors.py:247-258`; testes `tests/unit/infrastructure/adapters/test_gold_chunk_reader.py:81-118` |
| 7. Integração usa `testcontainers.qdrant` com `scope="session"` e dados `scope="function"`; verifica `top_k` e ordenação | ⚠️ Parcial | fixtures `tests/integration/adapters/test_qdrant_retriever_integration.py:77-98`; checks `:251-285`; porém o caminho real é monkeypatched em `:148-200`, e a execução local ficou `SKIPPED` nos casos Qdrant |
| 8. Cobertura ≥ 80%; `mypy --strict` + `lint-imports` passam; Pydantic não aparece em `domain/` | ✅ | cobertura `96.33%` via gate do projeto; `mypy` e `lint-imports` verdes; sem `pydantic` em `domain/` |

## Observações para Próximas Tarefas

- Para transformar o item 7 em evidência forte, a suíte de integração precisa rodar com Docker disponível e, idealmente, sem monkeypatch do caminho `_search_async`.
- O adapter guarda `top_k` default em `self._default_top_k` (`src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:50`), mas o contrato atual exige `top_k` explícito em `search`; esse default não participa do comportamento público hoje.
