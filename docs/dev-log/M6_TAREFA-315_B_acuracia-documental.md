# M6_TAREFA-315_B — Auditoria Codex

**Data**: 2026-06-08
**Commit auditado**: `2c9cccb`
**Status**: REQUEST CHANGES

## Achados

### ⚠️ Importante — manual ainda descreve o contrato antigo de `endpoint_masked`

- **Arquivo**: `docs/operations_manual.md:420-422`
- **Evidência**: o texto afirma `endpoint mascarado (scheme://host:port/***)`, mas o exemplo logo abaixo e o comportamento real de `mask_url()` pós-TAREFA-314 usam `scheme://host:port` sem `/***`.
- **Impacto**: o objetivo da TAREFA-315 era restaurar acurácia documental pós-313/314. Do jeito atual, o operador recebe duas definições contraditórias na mesma seção e o relatório A marca o item como corrigido, embora a prosa normativa continue desatualizada.
- **Sugestão**: alinhar a frase para `scheme://host:port` e, se quiser evitar regressão similar, adicionar uma asserção no smoke-test para esse formato explícito do manual.

## Validações reproduzidas

- `ruff check .` → OK
- `uv run mypy --strict src/` → OK
- `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` → OK
- `UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/validate_manual.py` → PASS
- `uv run pytest tests/unit/test_validate_manual.py -q` → `13 passed`
- `uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4 -q` → `1287 passed, 6 skipped, 89.61%`

## Conclusão

As correções de ADR-014, da seção de perguntas e das novas verificações do `validate_manual.py` estão majoritariamente corretas. O merge ainda não deve seguir porque o manual permanece internamente inconsistente no contrato de `endpoint_masked`, e isso é exatamente o tipo de drift documental que a tarefa se propôs a eliminar.
