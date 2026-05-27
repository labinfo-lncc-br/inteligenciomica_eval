# M1_TAREFA-014_C — Correção: MockTransport explícito nos testes HTTP

**Data**: 2026-05-27
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1 — Adapters de Geração
**Skill**: python-engineer, test-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Corrigir o bloqueador identificado na auditoria `M1_TAREFA-014_B_auditoria-vllm-generator-v11.md`:
testes com `respx_mock` travavam (exit code 124) no ambiente do auditor porque o patch
global de `httpcore` não interceptava as chamadas do `openai.AsyncOpenAI`, fazendo o SDK
tentar uma conexão TCP real a `localhost:8000` — que pende indefinidamente.

Adicionalmente, implementar as duas sugestões do auditor:
- Teste específico para retry em `RateLimitError`
- Teste de `await adapter.close()`

---

## Diagnóstico da causa raiz

O `respx_mock` fixture (de `pytest-respx`) funciona em dois modos:

| Modo | Mecanismo | Fragilidade |
|---|---|---|
| **Global patch** (modo antigo) | Patcha `httpcore` ao iniciar o fixture | Falha silenciosamente em ambientes sandboxed/containers onde a camada de rede é isolada — a chamada real sai pela rede e pende |
| **Transport explícito** (modo robusto) | `httpx.MockTransport(router.handler)` passado ao `AsyncClient` | Determinístico: o cliente NÃO pode fazer chamadas reais; se nenhuma rota corresponder, levanta `ConnectionError` imediatamente |

A confirmação experimental:
```python
# Modo global — route.call_count == 0, timeout com hang
_ = respx_mock
http_client = httpx.AsyncClient()  # usa httpcore patchado ← frágil

# Modo explícito — funciona em qualquer ambiente
http_client = httpx.AsyncClient(transport=httpx.MockTransport(respx_mock.handler))
```

`httpx.MockTransport` implementa `handle_async_request` (verificado), portanto é
compatível com `httpx.AsyncClient` sem ressalvas.

---

## Arquivos Modificados

| Arquivo | Mudança |
|---|---|
| `tests/unit/infrastructure/adapters/test_vllm_generator.py` | `_make_adapter`: `httpx.AsyncClient()` → `httpx.AsyncClient(transport=httpx.MockTransport(respx_mock.handler))` |
| `tests/unit/infrastructure/adapters/test_vllm_generator.py` | `test_custom_prompt_fn_is_used`: mesmo ajuste no `VLLMGeneratorAdapter` inline |
| `tests/unit/infrastructure/adapters/test_vllm_generator.py` | Novo: `test_retries_three_times_on_rate_limit_error` (sugestão auditor) |
| `tests/unit/infrastructure/adapters/test_vllm_generator.py` | `test_adapter_has_close_method` → `test_adapter_close_shuts_down_client` com `await adapter.close()` (sugestão auditor) |
| `CLAUDE.md` | Seção 11 — padrão de testes HTTP: atualizado para transport explícito |

---

## Decisões Técnicas

### 1. `httpx.MockTransport(respx_mock.handler)` em vez de patch global

`httpx.MockTransport` é uma classe da biblioteca `httpx` que:
- Implementa `handle_request` (síncrono) e `handle_async_request` (assíncrono)
- Recebe um callable `handler(request) -> response`
- `respx_mock.handler` é exatamente esse callable, retornando a resposta mockada ou
  lançando o `side_effect` configurado

Ao passar esse transporte ao `AsyncClient`, o cliente fica completamente isolado de I/O
real — não há risco de conexão TCP real e não há dependência de estado global.

### 2. `test_retries_three_times_on_rate_limit_error`

A resposta HTTP 429 faz o openai SDK levantar `openai.RateLimitError`, que está em
`_RETRYABLE`. Com `max_retries=0` no `AsyncOpenAI`, o retry é exclusivamente do
tenacity (3 tentativas). `route.call_count == 3` valida o comportamento.

### 3. `test_adapter_close_shuts_down_client`

Substitui `test_adapter_has_close_method` (que só verificava `callable(adapter.close)`)
por um teste que efetivamente executa `await adapter.close()`. Isso colocou a cobertura
de `vllm_generator.py` a **100%**.

---

## Validação (DoD)

```
uv run ruff check .                   → All checks passed!
uv run ruff format --check .          → 69 files already formatted
uv run mypy --strict src              → Success: no issues found in 24 source files
uv run lint-imports                   → Contracts: 4 kept, 0 broken
uv run pytest tests/unit/infrastructure/adapters/test_vllm_generator.py -v
                                      → 17 passed in 0.66s
Cobertura vllm_generator.py           → 100% (42 stmts, 0 miss)
uv run pytest --cov=src --cov-fail-under=85 -n auto -q
                                      → 580 passed, 7 skipped — 96.55%
```

---

## Critérios de Aceitação

| Critério | Status |
|---|---|
| Testes não pendem em ambiente sandboxed | ✅ Transport explícito isola o cliente de I/O real |
| `test_retries_three_times_on_rate_limit_error` — `route.call_count == 3` | ✅ |
| `test_adapter_close_shuts_down_client` — `await adapter.close()` sem exceção | ✅ |
| Cobertura `vllm_generator.py` = 100% | ✅ |
| Suite completa verde | ✅ 580 passed, 7 skipped |
| `mypy --strict`, `ruff`, `lint-imports` passam | ✅ |

---

## Observações para Próximas Tarefas

- O padrão `httpx.MockTransport(respx_mock.handler)` deve ser usado em **todos** os
  adapters HTTP de M1 que vierem (`PrometheusJudgeAdapter`, `RAGASLayer1Adapter`,
  `VLLMServerManagerAdapter`). O `CLAUDE.md` foi atualizado com o padrão correto.
- O `respx_mock` fixture ainda deve ser recebido como parâmetro nos testes para que o
  router tenha as rotas registradas antes de construir o adapter.
