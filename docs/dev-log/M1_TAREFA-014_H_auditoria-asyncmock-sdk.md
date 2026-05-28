# M1_TAREFA-014_H - Auditoria da correcao AsyncMock no SDK OpenAI

**Data**: 2026-05-27
**Milestone**: M1 - Adapters de Infraestrutura
**Tarefa**: TAREFA-014 - `VLLMGeneratorAdapter`
**Prompt**: B - verificacao / reauditoria apos correcao G
**Papel**: code-reviewer + rag-engineer
**Resultado**: PASS com waiver documentado para o criterio de `respx.mock`

---

## Objetivo

Avaliar a resposta do desenvolvedor registrada em
`docs/dev-log/M1_TAREFA-014_G_correcao-asyncmock-sdk.md`, que substituiu a estrategia de
mock HTTP (`respx` / `httpx.MockTransport`) por mock no nivel do SDK:

```python
adapter._client.chat.completions.create = AsyncMock(...)
```

O foco da auditoria foi verificar se a correcao eliminou o travamento observado no
ambiente de desenvolvimento/auditoria, sem exigir servidor vLLM real e sem degradar os
contratos da TAREFA-014.

---

## Avaliacao de necessidade de alteracao

Nao identifiquei necessidade de alterar o codigo de producao.

A unica divergencia em relacao ao Prompt B original e o item que exigia `respx.mock` nos
testes. Essa divergencia e intencional, esta documentada em `CLAUDE.md` secao 11 e no
dev-log G, e corrige um bloqueador real: tanto o patch global de `respx` quanto
`httpx.MockTransport` injetado no `openai.AsyncOpenAI` podiam nao interceptar a chamada
antes do timeout neste ambiente.

Decisao da auditoria: aceitar o mock no nivel do SDK como waiver para este adapter
especifico. O teste continua validando os parametros enviados ao SDK (`extra_body`,
`temperature`, `messages`) e a contagem de retries, mas nao depende de I/O real nem de
interceptacao HTTP interna ao SDK.

---

## Arquivos inspecionados

| Arquivo | Observacao |
|---|---|
| `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py` | Adapter usa `openai.AsyncOpenAI`, `api_key="EMPTY"`, `extra_body={"seed": seed}`, `temperature` recebido por parametro, retry com tenacity e `batch_invariant=False`. |
| `tests/unit/infrastructure/adapters/test_vllm_generator.py` | Testes usam `AsyncMock` em `adapter._client.chat.completions.create`, validam seed, temperature, prompt, erros retryable/non-retryable e `close()`. |
| `docs/dev-log/M1_TAREFA-014_G_correcao-asyncmock-sdk.md` | Documenta causa raiz, decisao tecnica e gates do desenvolvedor. |
| `CLAUDE.md` | Secao 11 documenta o padrao de mock no nivel SDK; ha referencias antigas a `respx` em outras secoes, registradas como divergencia documental menor. |
| `src/inteligenciomica_eval/domain/ports.py` | `GeneratorPort.generate` permanece async, keyword-only, com `contexts: Sequence[Chunk]`, `temperature: float` e retorno `GenerationOutput`. |

---

## Criterios do Prompt B

| Criterio | Evidencia | Status |
|---|---|---|
| 1. Assinatura de `generate` bate com `GeneratorPort` | `domain/ports.py:297-305`; `vllm_generator.py:92-100` | PASS |
| 2. Usa `openai.AsyncOpenAI(..., api_key="EMPTY")` | `vllm_generator.py:73-78` | PASS |
| 3. Seed em `extra_body` e `temperature` passado diretamente | `vllm_generator.py:129-134`; testes em `test_vllm_generator.py:118-127` e `185-194` | PASS |
| 4. `batch_invariant=False` constante | `vllm_generator.py:144-150`; teste em `test_vllm_generator.py:132-140` | PASS |
| 5. Retry apenas para `APIConnectionError` e `RateLimitError` | `_RETRYABLE` em `vllm_generator.py:23`; tenacity em `122-127`; testes em `286-299`, `304-325`, `335-348` | PASS |
| 6. Logging estruturado com campos corretos | `vllm_generator.py:152-160` | PASS |
| 7. Testes verificam seed/retries sem I/O real | `test_vllm_generator.py:72-87`, `118-127`, `286-299`, `335-348` | PASS com waiver: substitui `respx.mock` por `AsyncMock` no SDK |
| 8. `mypy --strict`, `lint-imports`, cobertura >= 80%, sem `print` | comandos abaixo; `rg` sem ocorrencias de `print(` | PASS |

---

## Divergencias

| Criterio | Arquivo:linha | Gravidade | Avaliacao |
|---|---:|---|---|
| Prompt B pedia `respx.mock`, mas testes usam `AsyncMock` no SDK | `tests/unit/infrastructure/adapters/test_vllm_generator.py:1-11`, `72-87` | Waiver aceito | A mudanca e justificada pelo travamento reproduzido no ambiente de auditoria. Nao bloqueia merge. |
| `CLAUDE.md` ainda tem referencias antigas dizendo que testes de adapters usam `respx.mock` / `respx` para OpenAI | `CLAUDE.md:19`, `39`, `86`, `359` | Menor | Recomendo limpar para evitar ambiguidade futura, mantendo a secao 11 como decisao vigente. Nao bloqueia a TAREFA-014. |

---

## Comandos executados

```bash
uv --cache-dir /tmp/uv-cache run pytest tests/unit/infrastructure/adapters/test_vllm_generator.py -v
```

Resultado: `17 passed in 0.83s` (sem travamento).

```bash
uv --cache-dir /tmp/uv-cache run pytest tests/unit/infrastructure/adapters/test_vllm_generator.py \
  --cov=inteligenciomica_eval.infrastructure.adapters.vllm_generator \
  --cov-report=term-missing \
  --cov-fail-under=80 \
  -q
```

Resultado: `17 passed in 1.08s`; cobertura de
`src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py` = `100%`.

```bash
uv --cache-dir /tmp/uv-cache run mypy --strict src
```

Resultado: `Success: no issues found in 24 source files`.

```bash
uv --cache-dir /tmp/uv-cache run lint-imports
```

Resultado: `4 contracts kept, 0 broken`.

```bash
uv --cache-dir /tmp/uv-cache run ruff check tests/unit/infrastructure/adapters/test_vllm_generator.py src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py
uv --cache-dir /tmp/uv-cache run ruff format --check tests/unit/infrastructure/adapters/test_vllm_generator.py src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py
```

Resultado: ambos passaram.

```bash
rg -n "pydantic|BaseModel|print\(" \
  src/inteligenciomica_eval/domain \
  src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py \
  tests/unit/infrastructure/adapters/test_vllm_generator.py
```

Resultado: nenhuma ocorrencia.

---

## Conclusao

PASS.

A correcao G resolveu o bloqueador observado pelo auditor: os testes do
`VLLMGeneratorAdapter` agora executam de forma deterministica, offline e sem depender de
servidor vLLM real ou de interceptacao HTTP do SDK OpenAI.

O waiver para nao usar `respx.mock` neste adapter e tecnicamente defensavel porque os
testes continuam validando o contrato externo do adapter e os argumentos encaminhados ao
SDK. A unica acao recomendada e ajustar referencias antigas em `CLAUDE.md` para nao
conflitar com a decisao registrada na secao 11.
