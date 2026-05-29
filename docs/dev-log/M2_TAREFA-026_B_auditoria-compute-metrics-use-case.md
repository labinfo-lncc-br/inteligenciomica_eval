## TAREFA-026 Prompt B - Auditoria Codex

Data: 2026-05-29
Escopo: auditar `ComputeMetricsUseCase` e o PR retroativo de `ResultWriterPort.update_metrics`.
Veredito: PASS / Approve

### Evidencias por criterio

| Criterio | Evidencia |
| --- | --- |
| `execute` async; adapters awaited corretamente | `ComputeMetricsUseCase.execute` e `_score_and_persist` em `src/inteligenciomica_eval/application/compute_metrics_use_case.py:141-209` e `:224-277`. `metric_suite.score(...)` awaited em `:242`; `rubric_judge.score(...)` awaited em `:243`; `aux_metrics.score(...)` sync em `:244-247`. |
| Use case isolado em `application`; sem import de `infrastructure` | Imports do modulo em `src/inteligenciomica_eval/application/compute_metrics_use_case.py:42-52`. Apenas `domain` + `structlog`. |
| Construtor usa ports corretos por DI | `reader: ResultReaderPort`, `writer: ResultWriterPort`, `metric_suite: MetricSuitePort`, `rubric_judge: RubricJudgePort`, `aux_metrics: DeterministicMetricPort` em `src/inteligenciomica_eval/application/compute_metrics_use_case.py:122-132`. |
| `DeterminismRegime.JUDGE` propagado ao writer | `updated = result.with_metrics(..., DeterminismRegime.JUDGE)` e `writer.update_metrics(... regime=updated.determinism_regime)` em `src/inteligenciomica_eval/application/compute_metrics_use_case.py:260-266`. Spy de teste valida `JUDGE` em `tests/unit/application/test_compute_metrics_use_case.py:356-364`. |
| Idempotencia default + `force=True` | Regra em `_needs_processing` `force or math.isnan(result.final_score.value)` em `src/inteligenciomica_eval/application/compute_metrics_use_case.py:215-222`. Testes em `tests/unit/application/test_compute_metrics_use_case.py:225-248`. |
| Excecao inesperada por linha continua o loop | `except Exception ... continue` em `src/inteligenciomica_eval/application/compute_metrics_use_case.py:172-185`. Teste em `tests/unit/application/test_compute_metrics_use_case.py:277-288`. |
| NaN propagado e persistido | `final_score = self._score_calculator.compute(metrics)` e `writer.update_metrics(...)` sempre chamado antes de retornar `is_nan` em `src/inteligenciomica_eval/application/compute_metrics_use_case.py:257-277`. Teste em `tests/unit/application/test_compute_metrics_use_case.py:256-269`. |
| Ordem deterministica por `row_id` | Docstring do modulo em `src/inteligenciomica_eval/application/compute_metrics_use_case.py:30-32`; sort em `:152-155`. Teste via spy em `tests/unit/application/test_compute_metrics_use_case.py:339-354`. |
| `ComputeMetricsReport` correto; golden 4 linhas confere | Dataclass com `run_id`, `n_processed`, `n_skipped`, `n_nan_excluded`, `n_failed_terminal`, `failed_row_ids` em `src/inteligenciomica_eval/application/compute_metrics_use_case.py:74-92`. Golden em `tests/golden/compute_metrics_expected.json:1-25`; validações em `tests/unit/application/test_compute_metrics_use_case.py:371-426`. |
| Concorrencia serial documentada; sem `asyncio.gather` | Docstring do modulo em `src/inteligenciomica_eval/application/compute_metrics_use_case.py:30-32`. Nao ha uso de `asyncio.gather` no arquivo. |
| Retrofit do writer persiste `final_score` e `batch_invariant` | Contrato em `src/inteligenciomica_eval/domain/ports.py:446-465`; implementacao em `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:440-503`; testes em `tests/integration/repositories/test_parquet_storage.py:398-424` e `tests/unit/fakes/test_fakes_satisfy_ports.py:414-432`. |

### Gates executados

- `uv run pytest tests/unit/application/test_compute_metrics_use_case.py -q` -> `12 passed`
- `uv run pytest tests/unit/application/test_compute_metrics_use_case.py --cov=inteligenciomica_eval.application.compute_metrics_use_case --cov-report=term-missing -q` -> `100%` em `compute_metrics_use_case.py`
- `uv run lint-imports` -> `Contracts: 4 kept, 0 broken`
- `uv run mypy --strict src` -> `Success: no issues found in 33 source files`
- `uv run pytest tests/integration/repositories/test_parquet_storage.py -q` -> `32 passed`
- `uv run pytest tests/unit/fakes/test_fakes_satisfy_ports.py tests/unit/domain/test_ports_contract.py -q` -> `95 passed`

### Observacoes

- A spec textual do Prompt A mostra `await reader.load(...)`, mas o contrato efetivo do projeto mantem `ResultReaderPort.load()` sincrono em `src/inteligenciomica_eval/domain/ports.py:487-496`. O use case segue o contrato real do repositorio; nao tratei isso como divergencia.
- O item 9 do Prompt B fala em "`ComputeMetricsReport` com 5 campos", mas a especificacao da TAREFA-026 define 6 campos, incluindo `failed_row_ids`. A implementacao e o golden seguem a especificacao detalhada.

### Recomendacao

Approve.
