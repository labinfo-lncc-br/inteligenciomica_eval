# M1_TAREFA-016_A — PrometheusJudgeAdapter

**Data**: 2026-05-28
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E2 — Adapters de Avaliação
**Skill**: ml-engineer, python-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Implementar o `PrometheusJudgeAdapter` — adapter de Camada 2 que avalia amostras
usando o modelo Prometheus-2 8x7B via vllm-judge determinístico (§9.1–9.5 da
arquitetura).  Implementa `RubricJudgePort` com política NaN-or-retry (ADR-007) e
`batch_invariant=True` constante (ADR-003, `DeterminismRegime.JUDGE`).

Dependências diretas concluídas antes desta tarefa:
- TAREFA-015: `PromptRegistry` com `biomed_rubric.j2` (template da rubrica biomédica)
- TAREFA-014: `VLLMGeneratorAdapter` (padrão de cliente vLLM via OpenAI SDK)
- TAREFA-005: `RubricJudgePort` e `EvaluationSample`/`RubricResult` em `domain/ports.py`

---

## Arquivos Criados / Modificados

| Arquivo | Ação | Descrição |
|---------|------|-----------|
| `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py` | Criado | Implementação do `PrometheusJudgeAdapter` |
| `tests/unit/infrastructure/adapters/test_prometheus_judge.py` | Criado | 21 testes unitários (AsyncMock, sem respx) |
| `tests/fixtures/prometheus_judge_response_valid.json` | Criado | Fixture de resposta OpenAI-compatible com `{"score": 0.85, ...}` |
| `tests/fixtures/prometheus_judge_response_malformed.json` | Criado | Fixture com conteúdo não-JSON para testar path NaN |

Nenhum arquivo de domínio foi modificado.

---

## Decisões Técnicas

### 1. Método `score` como `async def` (conflito aparente com port síncrono)

`RubricJudgePort.score` está definido em `domain/ports.py` como `def score` (síncrono).
Porém, a Nota de M1 item 1 determina que todos os adapters I/O-bound usem `async/await`.

**Decisão**: implementar `async def score` no adapter.

- O check `isinstance(adapter, RubricJudgePort)` continua passando em runtime porque
  `@runtime_checkable` verifica apenas a presença do atributo, não se é async ou sync.
- `mypy --strict` não reporta erro enquanto nenhuma variável for anotada como
  `RubricJudgePort = adapter` explicitamente (o que não ocorre nos testes unitários).
- Em M2, quando o use case anotar explicitamente `judge: RubricJudgePort`, o port
  deverá ser atualizado para `async def score` (e os fakes/harness e2e adaptados).
  Esse ajuste está fora do escopo de TAREFA-016.

### 2. Padrão de retry: tenacity para NaN-or-retry, NOT para connection errors

A política NaN-or-retry (ADR-007) diferencia dois tipos de falha:

| Tipo de falha | Tratamento |
|---|---|
| Parsing JSON inválido / score fora de `[0, 1]` | Retry (até 3 tentativas) → NaN |
| `APIConnectionError` / `APITimeoutError` | Raise `JudgeUnavailableError` imediatamente |

Implementação:
- `tenacity.AsyncRetrying(retry=retry_if_exception_type(_ParseFailureError), reraise=True)`
- Dentro do bloco `with attempt:`, `APIConnectionError`/`APITimeoutError` são capturados
  ANTES que tenacity os veja, convertidos em `JudgeUnavailableError` e re-lançados.
- Como `JudgeUnavailableError` não é `_ParseFailureError`, tenacity propaga sem retry.
- Após 3 falhas de parsing, tenacity re-lança `_ParseFailureError` (reraise=True), que
  é capturado pelo `except _ParseFailureError` externo → retorna `RubricResult(nan)`.

### 3. `_ParseFailureError` como exceção interna privada

A exceção `_ParseFailureError(Exception)` é usada exclusivamente como sinal interno
para o mecanismo de retry do tenacity. Nunca escapa da camada do adapter (convertida
em NaN antes de retornar). Nome com sufixo `Error` conforme convenção N818 do ruff.

### 4. AsyncMock no nível do SDK (não respx)

Seguindo a decisão TAREFA-014-G registrada em CLAUDE.md §11:
- Testes mocam `adapter._client.chat.completions.create` via `AsyncMock`.
- Não usa `respx.mock`, `httpx.MockTransport` nem injeção de `http_client`.
- Verifica `call_args.kwargs["temperature"]`, `call_args.kwargs["extra_body"]["seed"]`
  e `call_args.kwargs["model"]` para garantir parâmetros críticos no body da request.

O prompt especificava `respx.mock`, mas CLAUDE.md §11 (DECISÃO FINAL TAREFA-014-G)
sobrescreve essa recomendação — o padrão AsyncMock é mais determinístico em qualquer
ambiente (incluindo CI containerizado).

### 5. `PromptRegistry` injetado no construtor

O registry não é instanciado internamente no adapter: o construtor recebe
`registry: PromptRegistry`. Isso garante:
- Testabilidade: nos testes, `PromptRegistry()` é construído diretamente (sem mock
  do subprocess de git, pois o template é renderizado normalmente).
- Inversão de dependência: o adapter não cria dependências opacas.
- Em produção: `get_default_registry()` (singleton via `functools.cache`) pode ser
  passado diretamente.

### 6. Constantes não-configuráveis

| Constante | Valor | Motivo |
|---|---|---|
| `_JUDGE_TEMPERATURE` | `0.0` | Determinismo do juiz (§9.3) |
| `_JUDGE_SEED` | `42` | Determinismo extra além do VLLM_BATCH_INVARIANT |
| `batch_invariant` | `True` | ADR-003, DeterminismRegime.JUDGE — nunca parametrizável |

Estas constantes são exportadas com prefixo `_` e importadas nos testes para
validação (não são `_private` no sentido de "não testável", mas indicam que são
detalhes de implementação, não parte da API pública).

### 7. Logging estruturado

Dois eventos de log emitidos:

```
prometheus_judge_completed  → INFO   → score, nan=False, feedback_len, latency_ms, batch_invariant=True
prometheus_judge_nan        → ERROR  → nan_reason, raw_content[:500], model, latency_ms, batch_invariant=True
prometheus_judge_parse_failure → WARNING → por tentativa de parsing que falhou
```

O campo `batch_invariant=True` aparece em TODOS os eventos de log do adapter —
testado explicitamente via `structlog.testing.capture_logs()`.

---

## Problemas Encontrados e Soluções

### Problema 1 — RUF002: EN DASH no docstring

O caractere "–" (EN DASH U+2013) na referência "§9.1–9.5" disparou RUF002 do ruff.

**Solução**: substituído por hífen-minus "§9.1-9.5" e por texto descritivo
"secoes 9.1-9.5" no docstring do módulo.

### Problema 2 — N818: sufixo `Error` ausente na exceção interna

A classe interna `_ParseFailure` não seguia a convenção `N818` do ruff (nome de
exceção deve terminar em `Error`).

**Solução**: renomeada para `_ParseFailureError` com replace_all no arquivo.

### Problema 3 — I001: ordem de imports no arquivo de testes

O auto-sorter do ruff reorganizou os imports (identificadores do pacote local fora
de ordem alfabética dentro do bloco `from ... import (...)`).

**Solução**: `uv run ruff check --fix` auto-corrigiu; `uv run ruff format` ajustou
a formatação. Nenhuma mudança semântica.

---

## Validação (DoD)

| Gate | Resultado | Detalhe |
|------|-----------|---------|
| `ruff check .` | ✅ PASS | 0 erros após correções de lint |
| `ruff format --check .` | ✅ PASS | 2 arquivos novos formatados corretamente |
| `mypy --strict src/` | ✅ PASS | 26 arquivos, zero issues |
| `lint-imports` | ✅ PASS | 4 contratos mantidos, 56 arquivos analisados |
| `pytest -v test_prometheus_judge.py` | ✅ PASS | **21/21 testes passando** |
| `pytest --cov --cov-fail-under=85` | ✅ PASS | **96.66% global** |
| Cobertura `prometheus_judge.py` | ✅ PASS | **100%** |
| Suite total | ✅ PASS | **620 passed, 7 skipped** |

---

## Critérios de Aceitação (verificados)

| Critério | Status | Evidência |
|----------|--------|-----------|
| Happy path: score 0.85 de fixture válida | ✅ | `test_score_parsed_from_valid_json` |
| NaN path: 3 tentativas + `RubricResult(nan)` | ✅ | `test_three_attempts_made_on_malformed_response`, `test_nan_returned_after_three_malformed_responses` |
| `JudgeUnavailableError` em falha de conexão | ✅ | `test_connection_error_raises_judge_unavailable`, `test_connection_error_not_retried` |
| `temperature=0.0` no body da request | ✅ | `test_temperature_zero_in_request` |
| `seed=42` em `extra_body` | ✅ | `test_seed_constant_in_extra_body` |
| `batch_invariant=True` no log de sucesso | ✅ | `test_batch_invariant_logged_on_success` |
| `batch_invariant=True` no log de NaN | ✅ | `test_batch_invariant_logged_on_nan` |
| Prompt contém question, ground_truth, generated_answer | ✅ | `test_prompt_contains_question_and_ground_truth` |
| `isinstance(adapter, RubricJudgePort)` | ✅ | `test_isinstance_rubric_judge_port` |
| `mypy --strict` + `lint-imports` | ✅ | Gates acima |
| Cobertura adapter ≥ 80% | ✅ | 100% |
| `PromptRegistry` injetado (não instanciado internamente) | ✅ | Construtor recebe `registry: PromptRegistry` |
| `APITimeoutError` também gera `JudgeUnavailableError` | ✅ | `test_timeout_error_raises_judge_unavailable` |
| Recuperação após 2 falhas (3ª tentativa válida) | ✅ | `test_recovery_after_two_failures` |

---

## Observações para Próximas Tarefas

### TAREFA-017 (RAGASLayer1Adapter)
- Dependência DIRETA do `PrometheusJudgeAdapter` para configurar o LLM do RAGAS
  (Nota M1 item 5: `LangchainLLMWrapper(ChatOpenAI(base_url=judge_url, ...))`).
- O padrão AsyncMock deve ser adaptado para as chamadas internas que o RAGAS faz ao LLM.

### Ajuste futuro em `RubricJudgePort` (M2)
- Em M2, quando `RunExperimentUseCase` anotar variáveis como `judge: RubricJudgePort`,
  o port precisará ser atualizado para `async def score(...)`.
- Ao fazer isso, `FakeRubricJudge` em `tests/fakes/metrics.py` e o harness e2e em
  `tests/e2e/_harness.py` precisarão ser atualizados para `async def score` e `await`
  nas chamadas correspondentes.

### Padrão para TAREFA-019 (VLLMServerManagerAdapter)
- `_retry_stop` e `_retry_wait` injetáveis no construtor (com prefixo `_`) é o padrão
  estabelecido por TAREFA-014 e replicado aqui — deve ser seguido em todos os adapters
  com tenacity.
