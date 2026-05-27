# M1_TAREFA-014_G — Correção final: mock no nível do SDK OpenAI

**Data**: 2026-05-27
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1 — Adapters de Geração
**Skill**: python-engineer, test-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Resolver definitivamente o bloqueador identificado nas auditorias
`M1_TAREFA-014_B` e `M1_TAREFA-014_F`: os testes do `VLLMGeneratorAdapter` travavam
(exit code 124) no ambiente do auditor porque a estratégia de mock baseada em
`httpx.MockTransport` ou no patch global de `httpcore` não interceptava as chamadas do
SDK `openai.AsyncOpenAI` naquele ambiente.

---

## Diagnóstico da causa raiz

### Histórico de tentativas

| Estratégia | Ambiente dev | Ambiente auditor |
|---|---|---|
| `respx_mock` global (httpcore patch) | PASS | FAIL — hang (exit 124) |
| `httpx.AsyncClient(transport=httpx.MockTransport(handler))` injetado via `http_client=` | PASS | FAIL — `route.call_count == 0`, TimeoutError |

### Investigação da segunda tentativa

O SDK `openai 2.38.0` preserva o `http_client` passado como `self._client`:

```python
# openai/_base_client.py AsyncAPIClient.__init__
self._client = http_client or AsyncHttpxClientWrapper(...)
```

Isso foi verificado empiricamente: `client._client is http_client → True` e
`client._client._transport type: MockTransport`. No **nosso** ambiente, a chamada
funciona. No ambiente do auditor, não.

### Causa identificada

O SDK v2 executa `get_platform()` em thread na **primeira** chamada a `request()`:

```python
# openai/_base_client.py AsyncAPIClient.request()
self._platform = await asyncify(get_platform)()
```

`asyncify` usa `sniffio.current_async_library()` para escolher entre
`asyncio.to_thread()` (se "asyncio") e `anyio.to_thread.run_sync()` (qualquer outro).
Em alguns ambientes com combinações específicas de `anyio`/`sniffio`/`pytest-asyncio`,
esse dispatch pode resultar em um deadlock ou troca de event loop que impede que o
transporte injetado seja chamado antes do timeout.

O resultado é: a mesma combinação `openai.AsyncOpenAI + http_client=MockTransport`
funciona em Python 3.13.13 + pytest-asyncio 1.3.0 **aqui**, mas não no ambiente do
auditor com as mesmas versões declaradas — provavelmente por diferença em variáveis de
ambiente, isolamento de rede ou configuração do pool de threads.

### Solução definitiva

Mockar **no nível do SDK**, não no nível HTTP. O ponto de interceptação correto é:

```python
adapter._client.chat.completions.create = AsyncMock(return_value=mock_completion)
```

`openai.AsyncCompletions.create` é um método de instância regular — Python permite
substituí-lo por `AsyncMock` sem `__slots__` nem descriptors bloqueando a atribuição.
Isso foi verificado: `client.chat.completions.create = AsyncMock(...)` funciona com
a versão `openai 2.38.0` instalada.

---

## Arquivos Modificados

| Arquivo | Mudança |
|---|---|
| `tests/unit/infrastructure/adapters/test_vllm_generator.py` | Reescrita completa: removido `respx`, `httpx.MockTransport`, `http_client` injection; substituído por `AsyncMock` em `adapter._client.chat.completions.create` |
| `CLAUDE.md` | Seção 11 — padrão atualizado para mock no nível SDK |

---

## Decisões Técnicas

### 1. `AsyncMock` em `adapter._client.chat.completions.create`

- **Por quê**: intercepta no ponto exato chamado pelo adapter, sem depender de
  transporte, event-loop ou versão de anyio/sniffio.
- **Como**: atribuição direta pós-construção; funciona porque `AsyncCompletions.create`
  não usa `__slots__`.
- **Verificação de parâmetros**: `mock_create.call_args.kwargs["extra_body"]["seed"]`
  em vez de `json.loads(route.calls[0].request.content)`.
- **Contagem de retries**: `mock_create.call_count` em vez de `route.call_count`.

### 2. Criação de erros SDK com objetos httpx mínimos

Os construtores de `openai.APIConnectionError`, `openai.RateLimitError`,
`openai.BadRequestError` e `openai.UnprocessableEntityError` exigem objetos `httpx.Request`
e/ou `httpx.Response`. Esses objetos são criados com URLs fictícias — **nunca chegam à
rede**; servem apenas para satisfazer as assinaturas dos construtores de exceção.

```python
_DUMMY_REQUEST = httpx.Request("POST", _ENDPOINT)
_DUMMY_RESP_429 = httpx.Response(429, request=_DUMMY_REQUEST)
exc = openai.RateLimitError("rate limit exceeded", response=_DUMMY_RESP_429, body=None)
mock_create = AsyncMock(side_effect=exc)
```

### 3. Remoção de `respx` dos testes do VLLMGeneratorAdapter

`respx` foi removido de **todos** os imports de
`test_vllm_generator.py`. A dependência de dev `respx>=0.20` permanece no
`pyproject.toml` para uso nos adapters HTTP que vierem em M1 (Prometheus, RAGAS, VLLMServerManager),
mas nesses casos o padrão correto também será o mock no nível SDK.

---

## Validação (DoD)

```
uv run ruff check tests/unit/infrastructure/adapters/test_vllm_generator.py
                                      → All checks passed!
uv run ruff format --check .          → reformatted (1 file), depois All checks passed!
uv run mypy --strict src              → Success: no issues found in 24 source files
uv run lint-imports                   → Contracts: 4 kept, 0 broken
uv run pytest tests/unit/infrastructure/adapters/test_vllm_generator.py -v
                                      → 17 passed in 0.86s  ← sem travamento
uv run pytest --cov=src --cov-fail-under=85 -n auto -q
                                      → 580 passed, 7 skipped — 96.55%
Cobertura vllm_generator.py           → 100% (42 stmts, 0 miss)
```

---

## Critérios de Aceitação

| Critério | Status |
|---|---|
| 17 testes passam sem timeout | ✅ 0.86s |
| Mock 100% ambiente-independente (sem `httpx.MockTransport`, sem `respx`) | ✅ |
| `seed` verificado via `mock_create.call_args.kwargs` | ✅ |
| `temperature` verificado via `mock_create.call_args.kwargs` | ✅ |
| `route.call_count` substituído por `mock_create.call_count` | ✅ |
| `RateLimitError` retried 3× | ✅ |
| `APIConnectionError` retried 3× | ✅ |
| Erros não-retryáveis (400, 422) → `GenerationError` sem retry | ✅ |
| `await adapter.close()` sem exceção | ✅ |
| Cobertura `vllm_generator.py` = 100% | ✅ |
| Suite completa verde | ✅ 580 passed, 7 skipped |
| `mypy --strict`, `ruff`, `lint-imports` passam | ✅ |

---

## Observações para Próximas Tarefas

- O padrão `AsyncMock` no nível SDK deve ser adotado em **todos** os adapters que
  envolvem SDKs Python com camada HTTP interna:
  - `PrometheusJudgeAdapter` — mock em `client.generate()` (SDK do Prometheus)
  - `RAGASLayer1Adapter` — mock em `ragas.evaluate()` ou no LLM interno
  - `VLLMServerManagerAdapter` — mock em `asyncio.create_subprocess_exec()` ou
    `aiohttp.ClientSession.get()` (para polling de `/health`)
- Para adapters que fazem `httpx.AsyncClient.get/post()` diretamente **sem SDK
  intermediário**, `respx_mock` com o patch global é aceitável (funciona diretamente
  com `httpx.AsyncClient`), mas prefer `httpx.MockTransport` se o fixture global for
  instável.
- A dependência `respx>=0.20` fica em `pyproject.toml` como dev dep, mas pode ser
  reavaliada em M2 se nenhum adapter novo precisar dela.
