# M1_TAREFA-014_A — VLLMGeneratorAdapter

**Data**: 2026-05-24
**Milestone**: M1 — Adapters de Recuperação e Geração
**Épico**: E1 — Adapters de Recuperação
**Skill**: python-engineer, ml-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Implementar `VLLMGeneratorAdapter` satisfazendo `GeneratorPort` via API OpenAI-compatible
do vLLM. Inclui retry com tenacity, logging estruturado, `batch_invariant=False` fixo (§9.2.4)
e cobertura ≥ 80% com testes usando `respx.mock`.

---

## Arquivos Criados / Modificados

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py` | **Criado** | Adapter principal |
| `tests/unit/infrastructure/adapters/test_vllm_generator.py` | **Criado** | 16 testes unitários |
| `tests/fixtures/vllm_generator_response.json` | **Criado** | Fixture OpenAI chat completion |
| `src/inteligenciomica_eval/domain/ports.py` | **Modificado** | Adicionado campo `batch_invariant: bool` a `GenerationOutput` |
| `tests/fakes/generation.py` | **Modificado** | `FakeGenerator` passa `batch_invariant=False` |
| `tests/unit/domain/test_ports_contract.py` | **Modificado** | `GenerationOutput` atualizado (2 instâncias) |
| `pyproject.toml` | **Modificado** | Deps `openai>=1.0`, `tenacity>=8.0`; mypy override para `tenacity.*` |

---

## Decisões Técnicas

### 1. `batch_invariant` em `GenerationOutput`
O campo foi adicionado como obrigatório sem default para forçar que cada adapter declare
explicitamente seu regime. Todos os callers existentes foram atualizados para
`batch_invariant=False`.

### 2. `max_retries=0` no `AsyncOpenAI`
O openai SDK v2 tem retry interno (default 2 tentativas). Desabilitamos com `max_retries=0`
para que o tenacity seja o único dono da lógica de retry — sem isso, cada tentativa do
tenacity faz 3 chamadas HTTP (3 × 3 = 9 em vez de 3).

### 3. `base_url` deve incluir `/v1`
`AsyncOpenAI(base_url="http://host:port")` envia para `{base_url}/chat/completions`
(sem `/v1`). Para vLLM, o endpoint correto é `http://host:port/v1/chat/completions`.
O parâmetro `url` do adapter deve ser `"http://localhost:8000/v1"`. Documentado na
docstring do construtor.

### 4. Injeção de `http_client` para testes
`AsyncOpenAI(http_client=httpx.AsyncClient())` criado **dentro** do contexto
`respx_mock` usa o httpcore patchado pelo fixture. Não usar `transport=respx_mock`
diretamente (respx `MockRouter` não implementa `handle_async_request`).

### 5. `_retry_stop` / `_retry_wait` injetáveis
Parâmetros com `_` prefixo para testes, usando `wait_none()` para evitar delays.

### 6. Não-retryable erros (400, 422 etc.)
A openai SDK transforma esses em `APIStatusError` (subclasse de `OpenAIError` mas
**não** de `APIConnectionError`/`RateLimitError`). O filtro tenacity não os captura;
propagam direto e o outer `except openai.OpenAIError` os envolve em `GenerationError`.

---

## Problemas Encontrados e Soluções

### P1: `respx.MockRouter` como transporte direto falha
- **Problema**: `httpx.AsyncClient(transport=respx_mock)` resulta em
  `AttributeError: 'MockRouter' object has no attribute 'handle_async_request'`
- **Causa**: respx v0.23 patcha `httpcore` globalmente; o `MockRouter` não implementa
  a interface `httpx.AsyncTransport`.
- **Solução**: Criar `httpx.AsyncClient()` simples DENTRO do contexto do `respx_mock`
  fixture (após `router.start()`). O httpcore estará patchado e o cliente o usará.

### P2: `route.call_count == 9` em vez de 3 no retry test
- **Causa**: openai SDK v2 tem retry próprio (padrão 2 tentativas = 3 chamadas),
  multiplicando os 3 do tenacity.
- **Solução**: `max_retries=0` no construtor de `AsyncOpenAI`.

### P3: URL sem `/v1`
- **Causa**: `AsyncOpenAI(base_url="http://localhost:8000")` → `POST /chat/completions`
  (sem `/v1`). respx não intercetava a rota registrada.
- **Solução**: `base_url` deve incluir `/v1`. Documentado e teste atualizado para
  `_BASE_URL = "http://localhost:8000/v1"`.

---

## Validação (DoD)

| Gate | Resultado |
|------|-----------|
| `ruff check .` | ✅ All checks passed |
| `ruff format --check .` | ✅ 69 files already formatted |
| `mypy --strict src` | ✅ no issues found in 24 source files |
| `lint-imports` | ✅ 4 contracts kept, 0 broken |
| `pytest --cov-fail-under=85` | ✅ 579 passed, 7 skipped — **96.31% coverage** |
| `vllm_generator.py` coverage | ✅ **96%** (45 stmts, 2 miss = sync wrapper e close) |

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| `isinstance(adapter, GeneratorPort)` | ✅ `test_adapter_satisfies_generator_port` |
| seed em `extra_body` da requisição | ✅ `test_generate_seed_appears_in_request_body` |
| latência medida e em `GenerationOutput` | ✅ `test_generate_latency_ms_is_non_negative` |
| `GenerationError` em falha não-retryable | ✅ `test_non_retryable_error_raises_generation_error` |
| 3 retries em `APIConnectionError` | ✅ `test_retries_three_times_on_connection_error` |
| `batch_invariant=False` sempre | ✅ `test_generate_batch_invariant_always_false` |

---

## Observações para Próximas Tarefas

- **TAREFA-015 (PromptRegistry)**: substituir `_default_prompt_fn` inline pelo
  `PromptRegistry`. O construtor já aceita `prompt_fn: Callable[[str, Sequence[Chunk]], str]`
  para injeção.
- **Config YAML**: o `url` deve incluir `/v1` — atualizar schema/exemplo YAML de configuração
  do servidor gerador.
- **openai SDK v2**: confirmar que `extra_body={"seed": seed}` continua suportado em
  versões futuras do SDK (comportamento vLLM-específico).
