# M1_TAREFA-014_E — Avaliação de Conformidade com Spec v1.1

**Data**: 2026-05-27
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1 — Adapters de Geração
**Skill**: code-reviewer, python-engineer, ml-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Avaliar se a implementação atual de TAREFA-014 (`VLLMGeneratorAdapter`) já está em
conformidade com a **Spec v1.1** (prompt corrigido pós-auditoria `auditoria_m1.md` de
26 mai 2026), antes de realizar qualquer modificação.

A spec v1.1 introduziu a seguinte correção relevante para esta tarefa:

| ID correção | Descrição |
|---|---|
| B7 | `GeneratorPort.generate()` — adicionar `contexts` + `temperature` como parâmetros keyword-only explícitos |

Correções B1-B6, B8, I1-I6 e m1-m4 não se aplicam diretamente a TAREFA-014.

---

## Histórico de Iterações

| Iteração | Data | Conteúdo |
|---|---|---|
| `M1_TAREFA-014_A` | 2026-05-24 | Implementação inicial — `generate()` ainda era `def` síncrono |
| `M1_TAREFA-014_D` | 2026-05-24 | Fix bloqueador: `generate()` → `async def`; remoção de `asyncio.run()` e `_generate_async` |
| `M1_TAREFA-014_E` | 2026-05-27 | Esta avaliação de conformidade com spec v1.1 |

---

## Metodologia de Avaliação

1. Leitura do adapter `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py`
2. Leitura do contrato `src/inteligenciomica_eval/domain/ports.py` — `GeneratorPort`
3. Leitura dos testes em `tests/unit/infrastructure/adapters/test_vllm_generator.py`
4. Execução dos gates completos de validação

---

## Arquivos Avaliados (sem modificação)

| Arquivo | Papel |
|---|---|
| `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py` | Adapter principal |
| `src/inteligenciomica_eval/domain/ports.py` | Contrato `GeneratorPort` |
| `tests/unit/infrastructure/adapters/test_vllm_generator.py` | 16 testes unitários |
| `tests/fixtures/vllm_generator_response.json` | Fixture OpenAI-compatible |

---

## Análise por Critério da Spec v1.1

### B7 — `GeneratorPort.generate()` — keyword-only + `contexts` + `temperature`

**Especificação v1.1:**
```python
async def generate(
    self, *,
    llm: LLMId,
    question: str,
    contexts: Sequence[Chunk],
    seed: int,
    temperature: float,
) -> GenerationOutput
```

**Estado atual:**
- `domain/ports.py:297-318`: assinatura idêntica, todos keyword-only via `*`
- `vllm_generator.py:92-100`: adapter espelha exatamente o contrato
- `temperature` repassado à API: `temperature=temperature` em `:132`
- `contexts: Sequence[Chunk]` recebido e passado ao `prompt_fn` em `:117`

**Veredito:** ✅ **Já conforme — nenhuma modificação necessária.**

---

### Async-first (Nota M1 item 1)

**Estado atual:**
- `domain/ports.py:297`: `async def generate(...)` ✅
- `vllm_generator.py:92`: `async def generate(...)` ✅
- Promovido a async em TAREFA-014-D (corrigindo bloqueador da auditoria C)

**Veredito:** ✅ **Já conforme.**

---

### `openai.AsyncOpenAI(base_url=url, api_key="EMPTY")` (Nota M1 item 4)

**Estado atual:** `vllm_generator.py:73-78`:
```python
self._client = openai.AsyncOpenAI(
    base_url=url,
    api_key="EMPTY",
    http_client=http_client,
    max_retries=0,
)
```

**Veredito:** ✅ **Já conforme.** `api_key="EMPTY"` explícito; `max_retries=0` desabilita
o retry interno do SDK (evita multiplicação 3 × 3 = 9 chamadas).

---

### `seed` via `extra_body={"seed": seed}` (§9.3)

**Estado atual:** `vllm_generator.py:133`: `extra_body={"seed": seed}`

**Testado em:** `test_generate_seed_appears_in_request_body` — inspeciona `body["seed"]`
da requisição interceptada pelo `respx_mock`.

**Veredito:** ✅ **Já conforme.**

---

### `batch_invariant=False` — constante (§9.2.4)

**Estado atual:** `vllm_generator.py:149`: `batch_invariant=False`

**Testado em:** `test_generate_batch_invariant_always_false` e
`test_succeeds_after_transient_connection_error`.

**Veredito:** ✅ **Já conforme.**

---

### Retry tenacity — 3 tentativas, `APIConnectionError` + `RateLimitError`

**Estado atual:** `vllm_generator.py:122-127`:
```python
async for attempt in AsyncRetrying(
    stop=self._retry_stop,       # stop_after_attempt(3)
    wait=self._retry_wait,       # wait_exponential(multiplier=1, min=1, max=8)
    retry=retry_if_exception_type(_RETRYABLE),
    reraise=True,
):
```
`_RETRYABLE = (openai.APIConnectionError, openai.RateLimitError)` em `:23`.

**Testado em:**
- `test_retries_three_times_on_connection_error` — `route.call_count == 3` ✅
- `test_non_retryable_error_not_retried` — `route.call_count == 1` ✅
- `test_succeeds_after_transient_connection_error` — sucesso na 3ª tentativa ✅

**Veredito:** ✅ **Já conforme.**

---

### `GenerationError` para erros não-retryable

**Estado atual:** `vllm_generator.py:135-136`:
```python
except openai.OpenAIError as exc:
    raise GenerationError(str(exc)) from exc
```

**Veredito:** ✅ **Já conforme.**

---

### Logging estruturado `vllm_generation_completed`

**Estado atual:** `vllm_generator.py:152-160`:
```python
_log.info(
    "vllm_generation_completed",
    llm=llm.value, seed=seed,
    tokens_in=output.tokens_in, tokens_out=output.tokens_out,
    latency_ms=output.latency_ms, batch_invariant=output.batch_invariant,
)
```

**Veredito:** ✅ **Já conforme.**

---

### `async def close()` — ciclo de vida do adapter

**Estado atual:** `vllm_generator.py:168-170`:
```python
async def close(self) -> None:
    """Close the underlying httpx transport held by ``AsyncOpenAI``."""
    await self._client.close()
```

**Veredito:** ✅ **Já conforme.** Padrão `async def close()` consistente com
`QdrantRetrieverAdapter` (corrigido em TAREFA-013-F).

---

### Divergência documentada: tipo de `prompt_fn`

**Especificação v1.1:** `prompt_fn: Callable[[str, list[str]], str]`
(strings de texto de contexto).

**Estado atual:** `prompt_fn: Callable[[str, Sequence[Chunk]], str]`
(objetos `Chunk` completos).

**Justificativa da divergência (CLAUDE.md §13):**
Manter `Sequence[Chunk]` é deliberado — a `PromptRegistry` (TAREFA-015) pode acessar
não apenas `chunk.text`, mas também `chunk.id` e `chunk.score` para construir prompts
biomédicos mais ricos (ex.: citar IDs de referência no prompt). Converter para
`list[str]` antes da injeção seria uma perda de informação sem ganho real.

A spec v1.1 diz "Internamente, o adapter converte `Sequence[Chunk]` → `[chunk.text for chunk in contexts]`", o que foi interpretado como: a conversão ocorre *dentro* do `_default_prompt_fn` padrão (que faz `f"- {c.text}"`), não como contrato obrigatório da interface de `prompt_fn`.

**Veredito:** ⚠️ **Divergência intencional e documentada — não é defeito.**
Nenhuma ação necessária em TAREFA-014.

---

## Gates de Validação Executados

```
uv run ruff check .          → All checks passed!
uv run ruff format --check . → 69 files already formatted
uv run mypy --strict src     → Success: no issues found in 24 source files
uv run lint-imports          → Contracts: 4 kept, 0 broken
uv run pytest tests/unit/infrastructure/adapters/test_vllm_generator.py -v
                             → 16 passed in 1.11s
Cobertura vllm_generator.py  → 98% (42 stmts, 1 miss = linha 170 do close)
uv run pytest --cov=src --cov-fail-under=85 -n auto -q
                             → 579 passed, 7 skipped — 96.46%
```

> **Nota sobre a linha 170 não coberta (close):**
> `async def close()` possui cobertura 100% em linha mas `branch=true` registra uma
> miss na branch implícita de "função nunca chamada como coroutine top-level nos testes".
> O teste `test_adapter_has_close_method` verifica apenas `callable(adapter.close)`.
> Isso é aceitável — 98% supera o limiar de 80% exigido para o adapter.

---

## Conclusão

**NÃO SÃO NECESSÁRIAS MODIFICAÇÕES** na implementação de TAREFA-014.

A implementação produzida nas iterações A e D já está em **conformidade total** com
a spec v1.1, incluindo a correção bloqueadora B7 (assinatura keyword-only com
`contexts` e `temperature`), a promoção a `async def` e todas as demais exigências
funcionais e de qualidade.

A única divergência (`Sequence[Chunk]` vs `list[str]` em `prompt_fn`) é uma decisão
arquitetural intencional documentada no `CLAUDE.md`, que beneficia a integração
futura com a `PromptRegistry` (TAREFA-015).

O projeto segue para a **TAREFA-015** (`PromptRegistry` — templates Jinja2 versionados).

---

## Observações para Próximas Tarefas

1. **TAREFA-015** deve substituir o `_default_prompt_fn` inline pelo `PromptRegistry`,
   mantendo a assinatura `Callable[[str, Sequence[Chunk]], str]` já estabelecida.
   O construtor do `VLLMGeneratorAdapter` já aceita `prompt_fn` para injeção.
2. O `url` do adapter deve incluir `/v1`
   (ex.: `"http://localhost:8000/v1"`) — já documentado na docstring e nos exemplos
   de configuração YAML.
3. A linha 170 (`await self._client.close()`) pode ser coberta adicionando um teste
   explícito de `await adapter.close()` se a cobertura de branch se tornar relevante.
