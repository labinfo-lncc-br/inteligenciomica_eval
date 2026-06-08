# M3_TAREFA-312_A2 — Correções pós-auditoria Codex (ciclo B→A)

**Data**: 2026-06-07
**Milestone**: M3 — Gate transversal
**Épico**: E3 (transversal)
**Skill**: code-reviewer, test-engineer
**Ciclo**: A2 (correções após Prompt B — relatório da auditoria Codex em
`M3_TAREFA-312_B_auditoria-codex-integration-gate.md`)

---

## Veredito da auditoria

**FAIL** — 2 bloqueadores encontrados no commit `37e7314`.

---

## Bloqueadores corrigidos

### B1 — `ruff format --check` falhando em 2 arquivos

**Achado:** O relatório A afirmava que ruff format estava verde, mas a reprodução
do Codex encontrou reformatação pendente em:
- `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:301`
- `tests/unit/infrastructure/test_provenance_columns.py:278`

**Causa:** O ciclo A editou esses arquivos com linhas longas sem aplicar `ruff format`
antes do commit.

**Correção:** `uv run ruff format <arquivo>` nos dois arquivos. Verificado com
`ruff format --check .` → "170 files already formatted".

### B2 — `determinism_verified` semanticamente inconsistente

**Achado:** O ciclo A atualizou a spec (`arquitetura_detalhada_validacao_inteligenciomica.md`)
com "False por default — sem prova, sem True (ADR-014). Nunca True sem prova", mas o código
ainda defaultava para `True` em três lugares:

| Arquivo | Linha | Campo | Valor antes → depois |
|---------|-------|-------|---------------------|
| `src/inteligenciomica_eval/domain/entities.py` | 153 | `EvaluationResult.determinism_verified` | `True` → `False` |
| `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py` | 147 | `RowProvenance.determinism_verified` | `True` → `False` |
| `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py` | 328 | `from_row()` fallback legado | `row.get(..., True)` → `row.get(..., False)` |
| `src/inteligenciomica_eval/infrastructure/wiring.py` | 126 | `_ExperimentConfig.judge_determinism_verified` | `True` → `False` |

Também foi atualizado o log warning de `from_row()`:
`defaults["determinism_verified"]: True` → `False`

**Testes atualizados** (eram afirmações de defaults que agora são `False`):
- `test_row_provenance_default_determinism_verified`: `True` → `False`
- `test_evaluation_result_default_determinism_verified`: `True` → `False`
- `test_to_row_default_managed_mode`: `True` → `False`
- `test_from_row_defaults_when_columns_absent`: `True` → `False`
- Função auxiliar `_make_evaluation_result()`: parâmetro padrão `True` → `False`

---

## Validação pós-correção

```
ruff check .           — All checks passed
ruff format --check .  — 170 files already formatted
mypy --strict src      — Success: no issues in 60 files
lint-imports           — 4 contracts kept, 0 broken
pytest (unit, 89.52%)  — 1252 passed, 6 skipped
```

---

## Conformidade com critérios de auditoria

| Critério auditoria B | Ciclo A | Ciclo A2 |
|---------------------|---------|----------|
| ruff format --check verde | ❌ 2 arquivos pendentes | ✅ 170 files already formatted |
| `determinism_verified` default = False (ADR-014) | ❌ True em 3 locais + spec contraditória | ✅ False em entities, RowProvenance, from_row, wiring; testes consistentes |
| ruff check, mypy, lint-imports | ✅ | ✅ |
| 1252 passed ≥ 85% cobertura | ✅ | ✅ |
