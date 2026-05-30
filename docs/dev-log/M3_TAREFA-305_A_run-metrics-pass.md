# M3_TAREFA-305_A — RunMetricsPassUseCase (Passada 2 de Métricas)

**Data**: 2026-05-30
**Milestone**: M3 — Orquestração experimental
**Épico**: E3
**Skill**: ml-engineer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Implementar `RunMetricsPassUseCase` em
`src/inteligenciomica_eval/application/use_cases/run_metrics_pass.py` — Passada 2 da
arquitetura de 3 passadas (ADR-004): computa métricas RAGAS (Camada 1) + BERTScore para
cada linha da Passada 1 e persiste MetricVector + FinalScore via `writer.update_metrics`
(ADR-009). Inclui PR retroativo para adicionar `score_batch` ao `MetricSuitePort` e
todas as implementações que satisfazem o Protocol.

## Arquivos Criados / Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/.../domain/ports.py` | **Modificado**: `score_batch` adicionado ao `MetricSuitePort` (PR retroativo). |
| `src/.../infrastructure/adapters/ragas_metrics.py` | **Modificado**: `score_batch` adicionado ao `RAGASLayer1Adapter` (implementação sequencial via `score`). |
| `src/.../infrastructure/adapters/retryable_metric_adapter.py` | **Modificado**: `score_batch` adicionado ao `RetryableMetricSuiteAdapter` (delegação ao adapter interno — `isinstance` correto). |
| `tests/fakes/metrics.py` | **Modificado**: `score_batch` adicionado ao `FakeMetricSuite`. |
| `tests/unit/domain/test_ports_contract.py` | **Modificado**: `score_batch` adicionado ao `_StubMetricSuite` (contract test). |
| `src/.../application/use_cases/run_metrics_pass.py` | **Novo**: `RunMetricsPassUseCase`, `MetricsPassConfig`, `MetricsPassReport`. |
| `tests/unit/application/use_cases/test_run_metrics_pass.py` | **Novo**: 22 testes (6 classes). |

## Decisões Técnicas

1. **PR retroativo `score_batch` no `MetricSuitePort`.**
   A spec (Nota M3 item 5) declara `score_batch` como extensão opcional. O `@runtime_checkable`
   de Python verifica TODOS os métodos do Protocol em `isinstance()`, não apenas os chamados.
   Portanto, para manter `isinstance(RetryableMetricSuiteAdapter(), MetricSuitePort) == True`
   (testado em `test_retryable_metric_adapter.py:92`), o `score_batch` precisou ser adicionado
   ao `RetryableMetricSuiteAdapter` além dos demais implementadores.

2. **`config: MetricsPassConfig` (dataclass de aplicação), NÃO `RoundConfig`.**
   A spec pede `config: RoundConfig`, mas `RoundConfig` é infrastructure (import-linter
   Contract 2/4). Os campos necessários (`batch_size`, `max_metric_retries`,
   `log_progress_every`) NÃO existem em `RoundConfig` — são parâmetros de orquestração.
   Decisão: `MetricsPassConfig` frozen dataclass com defaults sensatos (batch_size=10,
   max_metric_retries=3, log_progress_every=10).

3. **`rubric_biomed_score=NaN` no MetricVector da Passada 2.**
   A rubrica biomédica é preenchida pela Passada 3 (`RunJudgePassUseCase`, TAREFA-306).
   Na Passada 2, `rubric_biomed_score` fica sempre NaN. O orquestrador (TAREFA-309/310)
   deve injetar um `FinalScoreCalculator` com `rubric_biomed_score: 0.0` para que
   `FinalScore` possa ser não-NaN nesta passada.

4. **`_process_batch` com retry por lote (ADR-007).**
   `score_batch(samples)` é retentado até `max_metric_retries` vezes em
   `MetricComputationError`; ao esgotar, retorna `[_ALL_NAN_LAYER1] * len(batch)`.
   Cada amostra do lote fica com MetricVector all-NaN + FinalScore(NaN) persistido
   (ADR-007: NaN é estado legítimo, não descarte).

5. **`strict=False` no `zip(batch, layer1_list)`.**
   Necessário para satisfazer ruff B905. Os dois iteráveis têm sempre o mesmo
   comprimento (invariante de `_process_batch`), mas `strict=False` é explícito.

6. **Idempotência por campo preenchido (`answer_correctness` não-NaN).**
   Diferente da Passada 1 (que usa `writer.exists(row_id)`), a Passada 2 detecta
   linhas já avaliadas pelo campo `answer_correctness`: se não-NaN, a linha já passou
   pelo RAGAS e é pulada (`n_skipped++`). Linhas sem geração (`generated_answer == ""`)
   são contadas em `n_skipped_missing_generation` (contagem separada, conforme spec).

7. **`MetricSuitePort.score_batch` no `MetricSuitePort`: assinatura e tipo de retorno.**
   O Protocol usa `list[EvaluationSample]` e `list[Layer1Metrics]` — não tuplas —
   para ser consistente com a spec (Nota M3 item 5). Adapters concretos convertem
   internamente conforme necessário.

## Problemas Encontrados e Soluções

- **`object.__setattr__` não levanta `AttributeError` em frozen+slots dataclass**: o
  `object.__setattr__` bypassa o `__setattr__` overridden pelo frozen dataclass e
  acessa o slot diretamente sem erro. Solução: usar atribuição direta
  `report.n_evaluated = 999` para levantar `dataclasses.FrozenInstanceError`.
- **Import `from tests.factories import ...` → ModuleNotFoundError**: o `testpaths=["tests"]`
  faz com que `tests/` seja a raiz dos imports de teste. Corrigido para
  `from factories import ...` e `from fakes.storage import ...`.
- **RUF002 (`×`)**, **RUF059** (variáveis não usadas), **B905** (`zip` sem `strict`),
  **B017** (`pytest.raises(Exception)`) — todos corrigidos.

## Validação (DoD §14.2)

```text
ruff check .                    -> All checks passed!
ruff format --check .           -> 110 files already formatted
mypy --strict src               -> Success: no issues found in 40 source files
lint-imports                    -> Contracts: 4 kept, 0 broken
pytest --cov -n 4 --cov-fail-under=85
  -> 862 passed, 15 skipped — coverage 96.97%
  -> run_metrics_pass.py: 94% (220-222 warning log, 233 progress log, 308 type guard)
```

## Critérios de Aceitação (tabela TAREFA-305)

| Critério | Estado | Evidência |
|----------|--------|-----------|
| Linhas já avaliadas puladas (idempotência por campo preenchido) | ✅ | `TestIdempotency::test_already_evaluated_row_is_skipped` |
| MetricComputationError: 3 retries → NaN aceito e persistido (ADR-007) | ✅ | `TestMetricErrorRetry::test_metric_error_nan_persisted_after_exhaustion` |
| score_batch chamado (não N chamadas individuais a score) | ✅ | `TestBatchProcessing::test_score_batch_called_not_individual_score` |
| batch_size configurável | ✅ | `TestBatchProcessing::test_batch_size_limits_samples_per_call` |
| MetricVector com bertscore_f1 do DeterministicMetricPort | ✅ | `TestMetricsAndPersistence::test_bertscore_comes_from_deterministic_not_ragas` |
| NaN em métrica com peso>0 → FinalScore(NaN) | ✅ | `TestNanPropagation::test_nan_layer1_metrics_propagate_to_final_score` |
| update_metrics com regime=DeterminismRegime.GENERATOR | ✅ | `TestMetricsAndPersistence::test_update_metrics_called_with_generator_regime` |
| MetricsPassReport com todos os campos preenchidos | ✅ | `TestMetricsPassReport::test_report_fields_populated` |
| application NÃO importa infrastructure | ✅ | `lint-imports` 4/0 |

## Observações para Próximas Tarefas

- **Desvios conscientes a sinalizar ao Codex (Prompt B)**:
  1. `config: MetricsPassConfig` (dataclass de aplicação) em vez de `RoundConfig`
     (infrastructure — import-linter Contract 2/4). Campos necessários não existem em
     `RoundConfig`.
  2. `rubric_biomed_score=NaN` sempre na Passada 2 — preenchido pela TAREFA-306.
     O orquestrador deve usar `FinalScoreCalculator` com `rubric_biomed_score: 0.0`
     para que `n_evaluated > 0` nesta passada.
  3. PR retroativo inclui 5 arquivos além dos 2 novos:
     `domain/ports.py`, `ragas_metrics.py`, `retryable_metric_adapter.py`,
     `tests/fakes/metrics.py`, `tests/unit/domain/test_ports_contract.py`.
  4. Linhas sem cobertura (94%): 220-222 (log warning geração ausente — coberto pela
     lógica mas o log em si não é verificado), 233 (progress log ≥10 linhas — sem
     teste com ≥10 células), 308 (type guard inalcançável pós-retry).

- **TAREFA-306 (RunJudgePassUseCase)**: preencherá `rubric_biomed_score` com
  `PrometheusJudgeAdapter.score()` e chamará `writer.update_metrics` com
  `regime=DeterminismRegime.JUDGE`.
- **TAREFA-309 (Orquestrador)**: ao injetar o `RunMetricsPassUseCase`, fornecer um
  `FinalScoreCalculator` com pesos que excluam `rubric_biomed_score` (peso 0.0)
  para que `n_evaluated > 0` seja possível na Passada 2.
