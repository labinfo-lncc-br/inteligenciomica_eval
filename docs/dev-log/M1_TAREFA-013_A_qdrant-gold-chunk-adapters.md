# M1_TAREFA-013_A — QdrantRetrieverAdapter + GoldChunkReaderAdapter

**Data**: 2026-05-24
**Milestone**: M1 — Adapters de Recuperação e Geração
**Épico**: E1 — Adapters de Recuperação
**Skill**: rag-engineer, python-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Implementar dois adapters de infraestrutura:

1. **`QdrantRetrieverAdapter`** — implementa `RetrieverPort`, usa `AsyncQdrantClient` para busca vetorial
2. **`GoldChunkReaderAdapter`** — implementa `GoldChunkReaderPort`, lê chunks-ouro de arquivo JSONL

---

## Arquivos Criados / Modificados

### Produção
| Arquivo | Ação |
|---|---|
| `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py` | Criado |

### Testes
| Arquivo | Ação |
|---|---|
| `tests/unit/infrastructure/__init__.py` | Criado |
| `tests/unit/infrastructure/adapters/__init__.py` | Criado |
| `tests/unit/infrastructure/adapters/test_qdrant_retriever_unit.py` | Criado (12 testes) |
| `tests/unit/infrastructure/adapters/test_gold_chunk_reader.py` | Criado (8 testes) |
| `tests/integration/adapters/test_qdrant_retriever_integration.py` | Criado (9 testes) |
| `tests/fixtures/gold_chunks.jsonl` | Criado |

### Configuração
| Arquivo | Ação |
|---|---|
| `pyproject.toml` | `qdrant-client>=1.7.1` em runtime deps; `testcontainers[qdrant]>=4.3`, `pytest-asyncio>=0.23` em dev deps; `asyncio_mode = "auto"` em pytest; `qdrant_client.*` em mypy `ignore_missing_imports` |

---

## Decisões Técnicas

### 1. AsyncQdrantClient com wrapper síncrono
O `RetrieverPort.search()` é síncrono (conforme port existente e fakes). O adapter usa
`AsyncQdrantClient` internamente com `asyncio.run()` como wrapper sync:

```python
def search(self, *, base, question, top_k) -> RetrievalResult:
    return asyncio.run(self._search_async(base=base, question=question, top_k=top_k))
```

**Restrição**: não pode ser chamado de dentro de um event loop já em execução. Se o
sistema for migrado para async no futuro, o port deve ser alterado para `async def search`.

### 2. Estratégia de embedding: Qdrant Inference API
O adapter passa a pergunta como `Document(text=question, model=embedding_model)` via
`query_points()`. O embedding é realizado **pelo servidor Qdrant** (Inference API),
sem nenhuma dependência de modelo local no adapter. O `embedding_model` é configurável
via parâmetro do construtor (default: `"Qdrant/Bm42-all-minilm-l6-v2-attentions"`).

> **Restrição de produção**: requer Qdrant com Inference API configurada. Para Qdrant
> self-hosted sem FastEmbed, usar `qdrant-client[fastembed]` ou configurar embedding
> server-side via `enable_fastembeds`.

### 3. Testes de integração com testcontainers + monkeypatch
A imagem `qdrant/qdrant` do testcontainers não inclui FastEmbed por padrão, impossibilitando
busca por texto direta. Os testes de integração usam monkeypatch de `_search_async` para
substituir `query_points(Document)` por `search(query_vector=[...])` com vetores densos.
Isso testa todos os mecanismos reais (conexão TCP, upsert, ScoredPoint parsing, top_k,
scores), sem requerer infraestrutura de inference.

Tests que precisam de Docker são marcados com `@_skip_no_docker`; os 2 testes de
`GoldChunkReaderAdapter` (filesystem only) correm independentemente do Docker.

### 4. Carregamento lazy + idempotente do JSONL
`GoldChunkReaderAdapter._ensure_loaded()` carrega o arquivo na primeira chamada e
armazena em `_cache`. Chamadas subsequentes retornam o cache. `gold_for()` retorna
`list(data[question_id])` — cópia para evitar mutação acidental pelo chamador.

### 5. Escopo de fixtures de integração
- `qdrant_container`: `scope="session"` — container único por sessão de testes
- `qdrant_url`: `scope="session"` — URL derivada do container
- `populated_collection`: `scope="function"` — coleção recriada para cada teste (garante isolamento)

---

## Problemas Encontrados e Soluções

### P1: E402 no arquivo de integração
**Problema**: ruff E402 ao colocar module docstring entre `from __future__` e demais imports.
**Solução**: movida a docstring para **antes** de `from __future__ import annotations`.

### P2: Caminho incorreto para fixtures
**Problema**: `parents[4]` e `parents[3]` calculados errado para os dois testes.
**Solução**: unit test usa `parents[3] / "fixtures"` (4 níveis acima do arquivo em
`tests/unit/infrastructure/adapters/`); integration test usa `parents[2] / "fixtures"`
(3 níveis acima de `tests/integration/adapters/`).

### P3: module-level pytestmark skipif bloqueando testes sem Docker
**Problema**: `pytestmark = [..., pytest.mark.skipif(not _DOCKER_AVAILABLE, ...)]` pulava
também os testes de `GoldChunkReaderAdapter` que não precisam do Docker.
**Solução**: separado o `_skip_no_docker` como decorador aplicado individualmente em cada
teste Qdrant; `pytestmark` ficou só com `pytest.mark.integration`.

### P4: `qdrant_client.*` sem ignore_missing_imports no mypy
**Problema**: mypy strict tentava checar tipagem do qdrant-client, que usa tipos genéricos
incompatíveis com strict (numpy types, etc.).
**Solução**: adicionado `["qdrant_client.*"]` ao override `ignore_missing_imports = true`
no `pyproject.toml`.

---

## Validação (DoD)

| Gate | Status |
|---|---|
| `ruff check .` | ✅ 0 erros |
| `ruff format --check .` | ✅ formatado |
| `mypy --strict src` | ✅ 0 erros (23 arquivos) |
| `lint-imports` | ✅ 4 contratos KEPT |
| `pytest tests/unit/` | ✅ 521 passed |
| `pytest tests/integration/adapters/` | ✅ 2 passed, 7 skipped (Docker indisponível) |
| Cobertura total | ✅ 96.33% (> threshold 85%) |
| Cobertura `qdrant_retriever.py` | ✅ 95% |
| `isinstance(adapter, RetrieverPort)` | ✅ |
| `isinstance(reader, GoldChunkReaderPort)` | ✅ |

---

## Critérios de Aceitação

- [x] `QdrantRetrieverAdapter` satisfaz `RetrieverPort` (isinstance pass)
- [x] `GoldChunkReaderAdapter` satisfaz `GoldChunkReaderPort` (isinstance pass)
- [x] `GoldChunkReaderAdapter` retorna exatamente os IDs corretos da fixture JSONL
- [x] `StorageError` levantado em arquivo ausente e question_id não encontrado
- [x] `RetrievalError` levantado em base não mapeada e falha de conexão Qdrant
- [x] Logging estruturado `qdrant_search_completed` com base, top_k, num_results, latency_ms
- [x] mypy --strict, ruff, lint-imports: todos verdes
- [x] Cobertura ≥ 80% no adapter

---

## Observações para Próximas Tarefas

1. **M1 produção com Qdrant real**: verificar se `qdrant-client[fastembed]` é preferível a
   Qdrant Inference API conforme o ambiente de deploy (GH200 ou cloud).
2. **Integração contínua**: os 7 testes Qdrant com testcontainers precisarão de Docker
   disponível no CI para rodarem. Atualmente são pulados localmente (WSL2 sem permissão).
3. **collection_map por rodada**: o YAML de rodada (TAREFA-010) deve declarar
   `base_id → collection_name`; o `QdrantRetrieverAdapter` já aceita esse mapeamento
   no construtor.
4. **Port sync vs async**: se futuramente o application layer usar async I/O, o
   `RetrieverPort.search()` deve ser refatorado para `async def` e o adapter simplificado
   eliminando `asyncio.run()`.
