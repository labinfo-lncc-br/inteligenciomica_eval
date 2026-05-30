# M3_TAREFA-306_B — Auditoria de RunJudgePassUseCase

**Data**: 2026-05-30
**Milestone**: M3 — Orquestração experimental
**Épico**: E3
**Skill**: code-reviewer
**Resultado**: PASS

## Escopo auditado

- `src/inteligenciomica_eval/application/use_cases/run_judge_pass.py`
- `tests/unit/application/use_cases/test_run_judge_pass.py`
- `docs/dev-log/M3_TAREFA-306_A_run-judge-pass.md`

## Verificação

1. O use case permanece na camada `application` e não importa `infrastructure`.
2. Linhas com `rubric_biomed_score` não-NaN são puladas por idempotência.
3. Linhas com `final_score` NaN continuam elegíveis e são processadas.
4. `JudgeUnavailableError` é tratado com retry sequencial e degrada para `NaN` após esgotar tentativas.
5. A ordem de submissão ao juiz é estável por `row_id` antes da iteração.
6. `update_metrics` usa `regime=DeterminismRegime.JUDGE`.
7. `JudgePassReport` expõe `batch_invariant_assumed=True` e é imutável.
8. O processamento é sequencial, sem paralelismo.

## Evidências

- `.venv/bin/pytest tests/unit/application/use_cases/test_run_judge_pass.py -q` -> `17 passed`
- `.venv/bin/lint-imports` -> `4 kept, 0 broken`

## Observações

- O desvio consciente em relação ao prompt A, `config: JudgePassConfig` em vez de `RoundConfig`, está documentado no relatório de implementação e não viola a arquitetura: a camada `application` não depende de `infrastructure`.
- O uso de `score_calc: FinalScoreCalculator` no construtor é coerente com a necessidade de recomputar `FinalScore` após preencher `rubric_biomed_score`.
