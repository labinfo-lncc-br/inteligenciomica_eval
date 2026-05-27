# M1_TAREFA-013_G — Auditoria da correção async search/close

**Data**: 2026-05-27
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1 — Adapters de Recuperação
**Skill**: code-reviewer, rag-engineer, test-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Avaliar a implementação registrada em
`docs/dev-log/M1_TAREFA-013_F_async-search-close-fix.md`, que promoveu
`RetrieverPort.search()` para `async def`, removeu `asyncio.run()` do
`QdrantRetrieverAdapter` e padronizou `close()` como método async de ciclo de vida do
adapter.

---

## Veredito

**PASS**, com uma ressalva de teste: a alteração de `close()` está correta por leitura de
código, mas ainda não possui teste unitário direto garantindo que o cliente Qdrant seja
fechado com `await`.

Não foram encontrados bloqueadores de contrato, arquitetura ou tipagem.

---

## Achados

| Critério | Resultado | Evidência |
|---|---|---|
| `RetrieverPort.search()` é async e mantém `top_k` obrigatório/keyword-only | PASS | `src/inteligenciomica_eval/domain/ports.py:270-276` |
| `QdrantRetrieverAdapter.search()` é async, sem `asyncio.run()` | PASS | `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:56-78` |
| `QdrantRetrieverAdapter.close()` é async e não faz parte do port | PASS | `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:80-86`; `RetrieverPort` sem `close()` |
| Call sites reais de `search()` usam `await` | PASS | Busca em `src/` e `tests/` encontrou chamadas reais apenas com `await` |
| `StubRetriever` e stubs de contrato foram promovidos para async | PASS | `tests/fakes/retrieval.py:33`; `tests/unit/domain/test_ports_contract.py:125` |
| Harness E2E foi atualizado para `await retriever.search(...)` | PASS | `tests/e2e/_harness.py:178` |
| Integração Qdrant mantém container session e dados function | PASS estático / skip local esperado | `tests/integration/adapters/test_qdrant_retriever_integration.py:79-143` |
| `close()` tem teste unitário direto | RESSALVA | Não há teste em `tests/unit/infrastructure/adapters/test_qdrant_retriever_unit.py` validando `await adapter.close()` |

---

## Comandos Executados

| Comando | Resultado |
|---|---|
| `uv --cache-dir /tmp/uv-cache run ruff check .` | `All checks passed!` |
| `uv --cache-dir /tmp/uv-cache run ruff format --check .` | `69 files already formatted` |
| `uv --cache-dir /tmp/uv-cache run mypy --strict src` | `Success: no issues found in 24 source files` |
| `uv --cache-dir /tmp/uv-cache run lint-imports` | `Contracts: 4 kept, 0 broken` |
| `uv --cache-dir /tmp/uv-cache run pytest tests/unit/infrastructure/adapters/test_qdrant_retriever_unit.py tests/unit/infrastructure/adapters/test_gold_chunk_reader.py tests/unit/domain/test_ports_contract.py tests/unit/fakes/test_fakes_satisfy_ports.py tests/e2e/test_min_round_stub.py -q` | `122 passed in 1.07s` |
| `uv --cache-dir /tmp/uv-cache run pytest -m integration tests/integration/adapters/test_qdrant_retriever_integration.py -v` | `2 passed, 7 skipped` — skips Qdrant/Docker esperados neste ambiente |
| `rg -n "pydantic\|BaseModel\|Field\(\|ValidationError" src/inteligenciomica_eval/domain` | Sem Pydantic no domínio; ocorrências são `ConfigValidationError` |
| `rg -n "search\(" src tests \| rg -v "await \|async def\|\.pyc\|__pycache__"` | Sem call site real faltando `await`; ocorrências restantes são docstrings/helper names |
| `timeout 240s uv --cache-dir /tmp/uv-cache run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n auto -q` | Timeout local após avançar até 86%; não usado como evidência de cobertura |

---

## Recomendação

A correção pode seguir. Para fechar a pequena lacuna de teste, adicionar um teste unitário
simples no adapter:

```python
async def test_close_closes_underlying_client(
    adapter: QdrantRetrieverAdapter,
    mock_qdrant_client: MagicMock,
) -> None:
    await adapter.close()
    mock_qdrant_client.close.assert_awaited_once()
```

Essa lacuna não invalida a correção principal porque o método é trivial e foi verificado
por leitura, mas vale cobrir por ser parte explícita da spec v1.1.
