# M1_TAREFA-013_E — Reauditoria Prompt B v1.1

**Data**: 2026-05-27
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1 — Adapters de Recuperação
**Skill**: code-reviewer, rag-engineer, test-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Reauditar a implementação da TAREFA-013 contra o Prompt B revisado da spec v1.1, sem
reescrever código, porque a TAREFA-013_B original já havia sido executada antes da
correção do prompt.

A avaliação considera explicitamente que esta máquina é ambiente de desenvolvimento:
não há servidor Qdrant de produção disponível aqui. Portanto, testes Qdrant que ficam
`SKIPPED` por indisponibilidade de Docker/daemon local são tratados como limitação
operacional esperada, não como defeito do adapter.

---

## Veredito

**FAIL condicional à spec v1.1 literal.**

A maior parte da TAREFA-013 já está conforme. Porém, a Nota de operacionalização M1
v1.1 promove `RetrieverPort.search()` para `async def` antes da TAREFA-013, e o código
atual mantém o port e o adapter síncronos, com wrapper `asyncio.run()`. Isso exige
alteração se a equipe quiser aplicar a spec corrigida sem exceção.

Nenhuma modificação de código foi feita nesta reauditoria.

---

## Tabela de Divergências

| Critério | Arquivo:linha | Gravidade |
|---|---:|---|
| Nota M1 item 1 exige ports async: `RetrieverPort.search()` deve ser `async def`; o contrato atual é `def search(...)`. | `docs/prompts_m1_tarefas_013_021_corrigido.md:47`; `src/inteligenciomica_eval/domain/ports.py:270` | Bloqueador se spec v1.1 literal |
| `QdrantRetrieverAdapter.search()` é wrapper síncrono e chama `asyncio.run(...)`, o que viola async-first e quebra em event loop já ativo. | `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:57`; `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:83` | Bloqueador se spec v1.1 literal |
| A extensão de ciclo de vida deveria ser `async close()`; o adapter expõe `async aclose()` e `def close()` síncrono com `asyncio.run(...)`. | `docs/prompts_m1_tarefas_013_021_corrigido.md:54`; `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:91`; `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:95` | Importante |

---

## Critérios do Prompt B

| Critério | Status | Evidência |
|---|---|---|
| 1. Usa `AsyncQdrantClient`; construtor recebe `url`, `collection_map`, `top_k` | PASS | `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:40-50` |
| 2. Assinatura keyword-only, `top_k` obrigatório, retorno `RetrievalResult` | PASS parcial | Parâmetros e DTO corretos em `src/inteligenciomica_eval/domain/ports.py:270-276` e `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:57-63`; falha apenas na decisão async da Nota M1 item 1 |
| 3. Não chama modelo de embedding separado; delega ao Qdrant | PASS | Docstring `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:21-38`; `Document(text=question, model=...)` em `:130` |
| 4. `RetrievalError`; `close()` fecha cliente | PASS parcial | Wrapping em `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:123-142`; fechamento existe em `:91-97`; divergência de API esperada: `async close()` vs `aclose()` |
| 5. Logging estruturado com `latency_ms`, `base`, `num_results` | PASS | `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:147-154` |
| 6. `GoldChunkReaderAdapter` síncrono, JSONL, `gold_for()`, `list[str]`, `StorageError` | PASS | `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:201-254`; fixture em `tests/fixtures/gold_chunks.jsonl:1` |
| 7. Integração com `testcontainers.qdrant`, container session, dados function, top_k e ordenação | PASS estático / não executado plenamente localmente | Fixtures em `tests/integration/adapters/test_qdrant_retriever_integration.py:79-143`; checks em `:192-270`; execução local: 2 passed, 7 skipped |
| 8. Cobertura >= 80%, `mypy --strict`, `lint-imports`, sem Pydantic em `domain/` | PASS parcial | `mypy` e `lint-imports` passaram; Pydantic não aparece em `domain/`; coverage completo não foi confirmado nesta execução |

---

## Comandos Executados

| Comando | Resultado |
|---|---|
| `uv run pytest -m integration tests/integration/adapters/test_qdrant_retriever_integration.py -v` | Falhou antes de rodar: cache default do `uv` em path read-only |
| `uv --cache-dir /tmp/uv-cache run pytest -m integration tests/integration/adapters/test_qdrant_retriever_integration.py -v` | `2 passed, 7 skipped`; os 7 skipped são Qdrant/Docker indisponível neste ambiente |
| `uv --cache-dir /tmp/uv-cache run lint-imports` | `Contracts: 4 kept, 0 broken` |
| `uv --cache-dir /tmp/uv-cache run mypy --strict src` | `Success: no issues found in 24 source files` |
| `uv --cache-dir /tmp/uv-cache run ruff check .` | `All checks passed!` |
| `uv --cache-dir /tmp/uv-cache run ruff format --check .` | `69 files already formatted` |
| `uv --cache-dir /tmp/uv-cache run pytest tests/unit/infrastructure/adapters/test_qdrant_retriever_unit.py tests/unit/infrastructure/adapters/test_gold_chunk_reader.py tests/unit/domain/test_ports_contract.py tests/unit/fakes/test_fakes_satisfy_ports.py -q` | `115 passed in 0.66s` |
| `timeout 180s uv --cache-dir /tmp/uv-cache run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -q` | Não produziu relatório final dentro do limite operacional; não usado como evidência de PASS |
| `rg -n "pydantic\|BaseModel\|Field\|ValidationError" src/inteligenciomica_eval/domain` | Sem Pydantic em `domain/`; ocorrências são apenas `ConfigValidationError` |

---

## Recomendação

Se a spec v1.1 corrigida é mandatória, abrir correção pequena para:

1. transformar `RetrieverPort.search()` em `async def`;
2. transformar `QdrantRetrieverAdapter.search()` em `async def` e remover `asyncio.run()`;
3. atualizar `StubRetriever`, stubs de contrato, harness e testes para `await retriever.search(...)`;
4. renomear/consolidar lifecycle para `async def close()` no adapter, mantendo fora de `RetrieverPort`.

Se a equipe decidir manter a exceção documentada em `CLAUDE.md` para o application layer
síncrono, não há alteração necessária em comportamento atual, mas essa exceção deve ser
registrada como waiver explícito contra a spec v1.1.
