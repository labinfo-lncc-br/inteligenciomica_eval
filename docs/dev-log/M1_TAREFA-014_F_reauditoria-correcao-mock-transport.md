# M1_TAREFA-014_F — Reauditoria da correção MockTransport

**Data**: 2026-05-27
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1 — Adapters de Geração
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Reauditar a correção registrada em
`docs/dev-log/M1_TAREFA-014_C_correcao-mock-transport.md`, cujo objetivo era resolver o
FAIL anterior dos testes unitários do `VLLMGeneratorAdapter` usando
`httpx.MockTransport(respx_mock.handler)` em vez de depender do patch global do `respx`.

Esta máquina é ambiente de desenvolvimento, não o servidor de execução da aplicação.
Isso não deveria afetar estes testes: por serem unitários, eles devem permanecer 100%
offline e não depender de vLLM real nem de rede local.

---

## Veredito

**FAIL.**

A mudança é conceitualmente na direção correta, mas o gate obrigatório continua travando
no primeiro teste (`test_generate_returns_text_from_fixture`) neste ambiente. Portanto,
não é possível aceitar a TAREFA-014 como PASS localmente.

---

## Achados

| Critério | Arquivo:linha | Gravidade |
|---|---:|---|
| `pytest tests/unit/infrastructure/adapters/test_vllm_generator.py -v` ainda trava no primeiro teste e foi encerrado por `timeout 60s` com código `124`. | `tests/unit/infrastructure/adapters/test_vllm_generator.py:76` | Bloqueador |
| `httpx.MockTransport(respx_mock.handler)` funciona com `httpx.AsyncClient` direto, mas a chamada via `openai.AsyncOpenAI(..., http_client=http_client)` não atinge o handler: reprodução mínima resultou em `TimeoutError` e `route.call_count == 0`. A estratégia de teste ainda não comprova que o SDK OpenAI está isolado de I/O real. | `tests/unit/infrastructure/adapters/test_vllm_generator.py:55`; `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py:73` | Bloqueador |
| O novo teste de `close()` executa `await adapter.close()`, mas não verifica observavelmente que o cliente foi fechado. É melhor do que `callable(adapter.close)`, mas ainda é uma asserção fraca. | `tests/unit/infrastructure/adapters/test_vllm_generator.py:402` | Sugestão |

---

## O Que Foi Verificado

| Item | Resultado |
|---|---|
| `_make_adapter` usa `httpx.AsyncClient(transport=httpx.MockTransport(respx_mock.handler))` | Confirmado em `tests/unit/infrastructure/adapters/test_vllm_generator.py:55` |
| `test_custom_prompt_fn_is_used` usa o mesmo transporte explícito | Confirmado em `tests/unit/infrastructure/adapters/test_vllm_generator.py:247` |
| Teste de `RateLimitError` foi adicionado | Confirmado em `tests/unit/infrastructure/adapters/test_vllm_generator.py:367` |
| Teste de `close()` foi trocado para `await adapter.close()` | Confirmado em `tests/unit/infrastructure/adapters/test_vllm_generator.py:402` |
| Adapter continua injetando o `http_client` no `openai.AsyncOpenAI` | Confirmado em `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py:73-77` |

---

## Comandos Executados

| Comando | Resultado |
|---|---|
| `timeout 60s uv --cache-dir /tmp/uv-cache run pytest tests/unit/infrastructure/adapters/test_vllm_generator.py -v` | Timeout (`124`) no primeiro teste |
| `uv --cache-dir /tmp/uv-cache run lint-imports` | `Contracts: 4 kept, 0 broken` |
| `uv --cache-dir /tmp/uv-cache run mypy --strict src` | `Success: no issues found in 24 source files` |
| `uv --cache-dir /tmp/uv-cache run ruff check tests/unit/infrastructure/adapters/test_vllm_generator.py src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py` | `All checks passed!` |
| Reprodução direta `httpx.AsyncClient(transport=httpx.MockTransport(respx_mock.handler))` | PASS: `status 200`, `route.call_count == 1` |
| Reprodução via `VLLMGeneratorAdapter` + `openai.AsyncOpenAI` + mesmo `MockTransport` | FAIL: `TimeoutError`, `route.call_count == 0` |
| Reprodução via `openai.AsyncOpenAI` direto + `httpx.AsyncClient(transport=httpx.MockTransport(handler))` customizado | FAIL: `TimeoutError`, handler customizado não foi chamado |

---

## Interpretação

O problema não é ausência de servidor vLLM nesta máquina. O teste deveria ser offline. A
evidência atual aponta que, nesta combinação de ambiente/dependências, a chamada
`client.chat.completions.create(...)` do SDK OpenAI não chega ao transporte mockado antes
de bloquear. Como o primeiro teste não progride, também não é possível validar seed,
temperature, retry de 429, `close()` ou cobertura.

As versões locais relevantes observadas são:

- `openai 2.38.0`
- `httpx 0.28.1`
- `respx 0.23.1`
- Python `3.13.13`

---

## Recomendação

Manter a implementação do adapter como está por enquanto, mas trocar a estratégia de teste
para uma que intercepte no ponto efetivamente usado pelo SDK OpenAI neste ambiente. Caminhos
possíveis:

1. usar um `httpx.AsyncBaseTransport` customizado diretamente, sem `respx`, que registre as
   requisições e retorne `httpx.Response`;
2. usar um fake/stub do `openai.AsyncOpenAI` injetável apenas em teste, mantendo o adapter
   de produção com SDK oficial;
3. fixar/validar combinação de versões `openai`/`httpx`/`respx` se a equipe quiser manter
   `respx` como requisito.

Depois disso, repetir o comando obrigatório:

```bash
uv run pytest tests/unit/infrastructure/adapters/test_vllm_generator.py -v
```

Nenhuma mudança de código foi aplicada nesta auditoria.
