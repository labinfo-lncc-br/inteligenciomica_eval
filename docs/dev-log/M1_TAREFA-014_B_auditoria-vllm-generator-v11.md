# M1_TAREFA-014_B — Auditoria VLLMGeneratorAdapter v1.1

**Data**: 2026-05-27
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1 — Adapters de Geração
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Auditar a implementação da TAREFA-014 contra o Prompt B corrigido da spec v1.1, sem
reescrever código. A avaliação inclui a divergência documentada pelo desenvolvedor:
`prompt_fn: Callable[[str, Sequence[Chunk]], str]` em vez de
`Callable[[str, list[str]], str]`.

---

## Veredito

**FAIL na verificação local**, por falha no gate obrigatório de teste.

O código do adapter atende aos critérios principais de implementação por leitura:
assinatura do `GeneratorPort`, `openai.AsyncOpenAI(api_key="EMPTY")`, `seed` em
`extra_body`, `temperature` repassado, `batch_invariant=False`, retry restrito e logging
estruturado. A divergência do `prompt_fn` é aceitável como decisão arquitetural porque
fica fora do `GeneratorPort` e preserva metadados de `Chunk` para a TAREFA-015.

Mesmo assim, o comando exigido pelo prompt,
`pytest tests/unit/infrastructure/adapters/test_vllm_generator.py -v`, não conclui neste
ambiente: ele trava no primeiro teste HTTP mockado e precisa ser encerrado por timeout.
Isso impede confirmar o PASS da TAREFA-014.

---

## Divergências e Riscos

| Critério | Arquivo:linha | Gravidade |
|---|---:|---|
| O gate obrigatório de teste trava no primeiro teste (`test_generate_returns_text_from_fixture`) e não produz os `16 passed` registrados no dev-log E. Repetição com `timeout 45s` terminou com código `124`. | `tests/unit/infrastructure/adapters/test_vllm_generator.py:72` | Bloqueador |
| A reprodução mínima com `respx` e `asyncio.wait_for(..., timeout=5)` chegou a `TimeoutError` com `route.call_count == 0`, indicando que a chamada do SDK OpenAI não está atingindo o mock HTTP neste ambiente. Assim, a estratégia de teste com `respx_mock` não está comprovada. | `tests/unit/infrastructure/adapters/test_vllm_generator.py:46`; `tests/unit/infrastructure/adapters/test_vllm_generator.py:78` | Bloqueador |
| `RateLimitError` está no conjunto retryable, mas não há teste específico para esse tipo; os testes contam retry apenas para erro de conexão. | `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py:23`; `tests/unit/infrastructure/adapters/test_vllm_generator.py:312` | Sugestão |
| `close()` só é validado como `callable`; não há teste de `await adapter.close()` fechando o cliente. | `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py:168`; `tests/unit/infrastructure/adapters/test_vllm_generator.py:370` | Sugestão |

---

## Tabela de Critérios

| Critério do Prompt B | Status | Evidência |
|---|---|---|
| 1. `generate` bate com `GeneratorPort`: keyword-only, `contexts: Sequence[Chunk]`, `temperature`, retorna `GenerationOutput` | PASS | `src/inteligenciomica_eval/domain/ports.py:297-305`; `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py:92-100`; retorno em `:144-150` |
| 2. Usa `openai.AsyncOpenAI(..., api_key="EMPTY")`; sem litellm/env var | PASS | `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py:7-8`; `:73-78`; sem `litellm` no adapter |
| 3. `seed` em `extra_body`; `temperature` repassado diretamente | PASS | `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py:132-133`; testes pretendem validar em `tests/unit/infrastructure/adapters/test_vllm_generator.py:99` e `:191`, mas o arquivo não completa localmente |
| 4. `batch_invariant=False` constante e não parametrizável | PASS | `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py:144-150`; sem parâmetro de construtor para batch invariance |
| 5. Retry apenas em `APIConnectionError` e `RateLimitError`; demais `OpenAIError` viram `GenerationError` | PASS | `_RETRYABLE` em `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py:23`; tenacity em `:121-127`; wrapping em `:135-136` |
| 6. Logging estruturado com campos corretos | PASS | `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py:152-160` |
| 7. Testes usam `respx`, verificam seed e contam retries | FAIL local | Uso de `respx` em `tests/unit/infrastructure/adapters/test_vllm_generator.py:14`; seed em `:99-113`; retry em `:312-328`; porém o comando trava antes de executar os asserts |
| 8. `mypy --strict`, `lint-imports`, cobertura >= 80%, sem `print` | PASS parcial | `mypy` e `lint-imports` passaram; `ruff` passou; sem `print`; cobertura não pôde ser confirmada porque o teste com coverage também travou |

---

## Avaliação da Divergência `prompt_fn`

**Especificação v1.1:** `prompt_fn: Callable[[str, list[str]], str]`, com conversão dos
chunks para textos antes da injeção.

**Implementação atual:** `prompt_fn: Callable[[str, Sequence[Chunk]], str]` em
`src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py:64`.

**Veredito:** waiver aceitável, sem necessidade de alteração agora. O contrato de domínio
continua correto (`GeneratorPort.generate(... contexts: Sequence[Chunk] ...)`) e o
`prompt_fn` é uma extensão de infraestrutura. Manter `Chunk` preserva `id` e `score` para
o futuro `PromptRegistry`. A documentação existe em `CLAUDE.md:366-371` e no dev-log E,
embora o `CLAUDE.md` pudesse explicitar melhor a razão (`id`/`score`), não apenas a
assinatura.

---

## Comandos Executados

| Comando | Resultado |
|---|---|
| `uv --cache-dir /tmp/uv-cache run lint-imports` | `Contracts: 4 kept, 0 broken` |
| `uv --cache-dir /tmp/uv-cache run mypy --strict src` | `Success: no issues found in 24 source files` |
| `uv --cache-dir /tmp/uv-cache run ruff check src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py tests/unit/infrastructure/adapters/test_vllm_generator.py` | `All checks passed!` |
| `uv --cache-dir /tmp/uv-cache run ruff format --check src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py tests/unit/infrastructure/adapters/test_vllm_generator.py` | `2 files already formatted` |
| `uv --cache-dir /tmp/uv-cache run pytest tests/unit/infrastructure/adapters/test_vllm_generator.py -v` | Travou no primeiro teste; processo encerrado manualmente |
| `timeout 45s uv --cache-dir /tmp/uv-cache run pytest tests/unit/infrastructure/adapters/test_vllm_generator.py -vv -s` | Timeout (`124`) no primeiro teste |
| `timeout 45s uv --cache-dir /tmp/uv-cache run pytest tests/unit/infrastructure/adapters/test_vllm_generator.py::test_generate_returns_text_from_fixture -vv -s` | Timeout (`124`) no primeiro teste isolado |
| Reprodução mínima com `respx` + `asyncio.wait_for(..., timeout=5)` | `TimeoutError`, `route.call_count == 0`; processo ainda precisou de `timeout` no encerramento |
| `rg -n "print\\(" src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py tests/unit/infrastructure/adapters/test_vllm_generator.py` | Sem ocorrências |

---

## Recomendação

Antes de considerar a TAREFA-014 como PASS, corrigir a estratégia de teste para que o
SDK OpenAI seja efetivamente interceptado pelo mock HTTP e falhe rápido quando não for.
Opções técnicas prováveis:

1. construir o `httpx.AsyncClient` injetado com transporte/mock explicitamente compatível
   com `respx` e `openai.AsyncOpenAI`;
2. configurar timeout baixo no `http_client` dos testes para evitar hangs;
3. adicionar teste específico para `RateLimitError`;
4. adicionar teste de `await adapter.close()`.

Nenhuma mudança de código foi aplicada nesta auditoria.
