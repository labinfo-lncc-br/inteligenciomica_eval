# M3_TAREFA-305_B — Auditoria de RunMetricsPassUseCase

**Data**: 2026-05-30
**Milestone**: M3 — Orquestração experimental
**Épico**: E3
**Resultado**: PASS

## Escopo auditado

- `src/inteligenciomica_eval/application/use_cases/run_metrics_pass.py`
- `src/inteligenciomica_eval/domain/ports.py`
- `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py`
- `src/inteligenciomica_eval/infrastructure/adapters/retryable_metric_adapter.py`
- `tests/fakes/metrics.py`
- `tests/unit/domain/test_ports_contract.py`
- `tests/unit/application/use_cases/test_run_metrics_pass.py`

## Verificação

1. O use case permanece na camada `application` e não importa `infrastructure`.
2. A idempotência por `answer_correctness` preenchido e o contador de `generated_answer` ausente estão implementados corretamente.
3. `MetricComputationError` é tratado por retry em lote e degrada para `NaN` persistido ao esgotar tentativas.
4. O fluxo usa `score_batch` no `MetricSuitePort` e `deterministic.score(answer=..., ground_truth=...)`.
5. `update_metrics` usa `regime=DeterminismRegime.GENERATOR`.
6. `MetricsPassReport` expõe todos os campos esperados e é `frozen`.
7. O PR retroativo de contrato (`score_batch`) está consistente com adapters, fake e teste de contrato.

## Evidências

- `.venv/bin/pytest tests/unit/application/use_cases/test_run_metrics_pass.py -q` -> `22 passed`
- `.venv/bin/lint-imports` -> `4 kept, 0 broken`

## Observação

- O desvio consciente em relação ao prompt A, `MetricsPassConfig` em vez de `RoundConfig`, está documentado no relatório de implementação e não quebra a regra de camada.
