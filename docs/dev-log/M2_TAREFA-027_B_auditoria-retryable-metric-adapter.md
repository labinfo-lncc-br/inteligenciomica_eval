## TAREFA-027 Prompt B - Auditoria Codex

Data: 2026-05-29
Escopo: auditar `RetryableMetricSuiteAdapter` e `RetryableRubricJudgeAdapter` contra a spec da M2 e ADR-007.
Veredito: PASS / Approve

### Evidencias por criterio

| Criterio | Evidencia |
| --- | --- |
| Dois decorators async; conformidade com os Protocols | `RetryableMetricSuiteAdapter.score(...)` e `RetryableRubricJudgeAdapter.score(...)` sao `async def` em `src/inteligenciomica_eval/infrastructure/adapters/retryable_metric_adapter.py:145-174`. Os Protocols `MetricSuitePort` e `RubricJudgePort` sao `@runtime_checkable` em `src/inteligenciomica_eval/domain/ports.py:348-388`. `isinstance(...)` e testado em `tests/unit/infrastructure/adapters/test_retryable_metric_adapter.py:89-102`. |
| `RetryConfig` correto | `@dataclass(frozen=True, slots=True)` com `max_retries: int = 3`, `initial_wait_s: float = 1.0`, `jitter: bool = False` em `src/inteligenciomica_eval/infrastructure/adapters/retryable_metric_adapter.py:52-65`. |
| Retry apenas para `MetricComputationError` | `_score_with_retry(...)` captura somente `except MetricComputationError` em `src/inteligenciomica_eval/infrastructure/adapters/retryable_metric_adapter.py:103-130`. Nao ha `except Exception` concorrente que esconda bugs. |
| NaN parcial retorna sem retry | O helper apenas retorna `await call()` no caminho de sucesso em `src/inteligenciomica_eval/infrastructure/adapters/retryable_metric_adapter.py:105-106`; como NaN parcial nao levanta `MetricComputationError`, ele e devolvido como esta. O comportamento esta coberto em `tests/unit/infrastructure/adapters/test_retryable_metric_adapter.py:162-172`. |
| Excecao inesperada propaga imediatamente | Qualquer erro fora de `MetricComputationError` escapa do helper; teste explicito em `tests/unit/infrastructure/adapters/test_retryable_metric_adapter.py:180-190`. |
| Esgotamento devolve NaN-sentinel sem excecao | `if attempt >= config.max_retries: ... return make_sentinel(attempt)` em `src/inteligenciomica_eval/infrastructure/adapters/retryable_metric_adapter.py:107-117`. Layer 1 usa sentinel todos-NaN em `:68-77`; rubrica usa `feedback="[retry_exhausted:N]"` em `:80-82`. Testes em `tests/unit/infrastructure/adapters/test_retryable_metric_adapter.py:126-154`. |
| Contagem do sentinel da rubrica consistente com a spec operacional | Com `max_retries=3`, o helper faz 4 chamadas e retorna `make_sentinel(3)` na exaustao em `src/inteligenciomica_eval/infrastructure/adapters/retryable_metric_adapter.py:107-117`. O teste exige `"[retry_exhausted:3]"` em `tests/unit/infrastructure/adapters/test_retryable_metric_adapter.py:137-144`. |
| Espera async e backoff corretos | O modulo usa `await asyncio.sleep(wait_s)` em `src/inteligenciomica_eval/infrastructure/adapters/retryable_metric_adapter.py:119-130`; nao ha `time.sleep` no arquivo. O backoff e `initial_wait_s * (2.0**attempt)` em `:119`. Spy de `asyncio.sleep` valida `[1.0, 2.0, 4.0]` em `tests/unit/infrastructure/adapters/test_retryable_metric_adapter.py:146-154`. |
| Logging estruturado em WARNING | Tentativas falhas fazem `_log.warning("metric_retry_attempt", ...)` em `src/inteligenciomica_eval/infrastructure/adapters/retryable_metric_adapter.py:122-128`; exaustao faz `_log.warning("metric_retry_exhausted", ...)` em `:109-116`. |
| Todos os cenarios obrigatorios estao presentes | O arquivo de testes cobre `isinstance`, retry-then-success, retry exhausted para os 2 ports, backoff, NaN parcial sem retry, excecao inesperada, factories e jitter em `tests/unit/infrastructure/adapters/test_retryable_metric_adapter.py:89-208`. |
| Cobertura, `lint-imports`, `mypy --strict` | Cobertura direcionada de `100%` no modulo; `lint-imports` com `4 kept, 0 broken`; `mypy --strict src` sem erros. |

### Gates executados

- `uv run pytest tests/unit/infrastructure/adapters/test_retryable_metric_adapter.py -q` -> `10 passed`
- `uv run pytest tests/unit/infrastructure/adapters/test_retryable_metric_adapter.py --cov=inteligenciomica_eval.infrastructure.adapters.retryable_metric_adapter --cov-report=term-missing -q` -> `100%` em `retryable_metric_adapter.py`
- `uv run lint-imports` -> `Contracts: 4 kept, 0 broken`
- `uv run mypy --strict src` -> `Success: no issues found in 34 source files`

### Observacoes

- A spec do Prompt A cita `tests/unit/adapters/test_retryable_metric_adapter.py`, mas a implementacao usou `tests/unit/infrastructure/adapters/test_retryable_metric_adapter.py`, coerente com a convencao atual do repositorio. Nao tratei isso como divergencia.
- O modulo usa `structlog` para cumprir o requisito de logging estruturado. Embora a restricao textual mencione stdlib, a implementacao nao introduz biblioteca de retry externa nem I/O real, e segue o padrao ja adotado no projeto para logging.

### Recomendacao

Approve.
