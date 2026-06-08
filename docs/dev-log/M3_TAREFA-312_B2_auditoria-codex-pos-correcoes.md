# M3_TAREFA-312_B2 — Auditoria Codex pós-correções do gate de integração

**Data**: 2026-06-07
**Milestone**: M3 — Gate transversal (integração 309/310/311 + coerência com 606)
**Épico**: E3 (transversal)
**Skill**: code-reviewer, test-engineer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Reauditar o commit `86d18e6` após as correções do ciclo A2, validando os dois
bloqueadores apontados no relatório
`docs/dev-log/M3_TAREFA-312_B_auditoria-codex-integration-gate.md`.

## Resultado

**PASS**

Os dois bloqueadores foram corrigidos:

1. `ruff format --check .` agora fecha verde.
2. `determinism_verified` agora defaulta para `False` de forma consistente com
   ADR-014, o código executável, a retrocompatibilidade de Parquet legado e os
   testes.

## Verificações reproduzidas

### Gates estáticos

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
All checks passed!
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .
170 files already formatted
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src
Success: no issues found in 60 source files
```

```text
$ uv run lint-imports
Contracts: 4 kept, 0 broken.
```

### Testes e smoke-checks

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/test_provenance_columns.py -q
28 passed in 0.16s
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/e2e/test_m3_full_cycle.py -q --timeout=30
5 passed in 0.81s
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/validate_manual.py
PASS — todos os subcomandos e flags validados existem na CLI.
```

## Conferências cirúrgicas

- `EvaluationResult.determinism_verified` agora é `False` por default em
  `src/inteligenciomica_eval/domain/entities.py:153`
- `RowProvenance.determinism_verified` agora é `False` por default em
  `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:147`
- `from_row()` defaulta `determinism_verified=False` para Parquet legado e o
  warning reflete isso em
  `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:313`
  e `:330`
- `_ExperimentConfig.judge_determinism_verified` agora é `False` por default em
  `src/inteligenciomica_eval/infrastructure/wiring.py:126`
- os testes de retrocompatibilidade e defaults foram atualizados em
  `tests/unit/infrastructure/test_provenance_columns.py`

## Conclusão

O commit `86d18e6` resolve os bloqueadores do ciclo anterior sem abrir regressão
nos checks reproduzidos. O gate 312 fica íntegro para aprovação nesta rodada.

**Recomendação**: `Approve`.
