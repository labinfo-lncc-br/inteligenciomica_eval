# M3_TAREFA-309_I — Correções pós-reauditoria Codex (ciclo H → ciclo I)

**Data**: 2026-06-03
**Milestone**: M3 — Orquestração end-to-end
**Épico**: E3
**Skill**: /implement (correção)
**Prioridade / Tamanho**: P0 / XS

---

## Objetivo

Corrigir o único achado do ciclo H: wave map do `--dry-run` ignorava o filtro `--phase`
porque `scheduler.plan(specs, cfg)` recebia o `cfg` original com `phases=['A', 'B']`.

---

## Análise da Reauditoria

### Achado do ciclo H

| # | Achado | Gravidade |
|---|--------|-----------|
| 1 | `--dry-run --phase B`: cabeçalho exibia `phases: ['B']` e 30 cells corretos, mas a tabela do wave map mostrava `Total cells per pass: 90` (A+B) — `scheduler.plan` ignorava o filtro de fase | BLOQUEADOR |

### Ponto corrigido no ciclo G (confirmado)

- `tests/unit/infrastructure/test_wiring.py` — 13 passed ✅

---

## Causa Raiz

`WaveSchedulerService._cells_per_model(round_config)` usa `round_config.phases` para
somar células de Phase A e Phase B. Como `scheduler.plan(specs, cfg)` recebia o `cfg`
original (sem filtro), o wave map sempre calculava células para ambas as fases,
independente do `--phase` passado na CLI.

---

## Arquivo Modificado

| Arquivo | Alteração |
|---------|-----------|
| `src/inteligenciomica_eval/cli.py` | `cfg_for_plan = cfg.model_copy(update={"phases": phases})` passado ao `scheduler.plan()` em vez do `cfg` original; `# type: ignore[arg-type]` removido (ficou unused — `cfg_for_plan` é `Any`) |

---

## Decisão Técnica

`RoundConfig` é Pydantic v2 — `model_copy(update={...})` cria uma cópia rasa com o
campo `phases` substituído. É a forma idiomática de criar um config "filtrado" sem
instanciar um novo schema completo. A cópia existe apenas dentro de `_run_dry_run`
e é descartada após `scheduler.plan()` retornar. O `cfg` original permanece inalterado.

```python
# Antes:
plan = scheduler.plan(specs, cfg)  # type: ignore[arg-type]

# Depois:
cfg_for_plan = cfg.model_copy(update={"phases": phases})  # type: ignore[attr-defined]
plan = scheduler.plan(specs, cfg_for_plan)
```

`cfg_for_plan` é `Any` (mypy: `cfg: object` + `attr-defined` ignorado → retorno `Any`),
então `scheduler.plan(specs, cfg_for_plan)` não levanta `arg-type` — ignore removido.

---

## Validação (DoD)

### Gates executados

```
✅ uv run ruff check .          → All checks passed
✅ uv run ruff format --check . → 161 files already formatted
✅ uv run mypy --strict src     → Success: no issues found in 57 source files
✅ uv run lint-imports          → 4 contracts: 4 kept, 0 broken
✅ uv run pytest -n 4 -q --cov=src --cov-fail-under=85
   → 1199 passed, 16 skipped — 88.53% coverage (gate 85% ✓)
```

---

## Critérios de Aceitação (pós-ciclo H)

| # | Critério | Status |
|---|----------|--------|
| CA-25 | `--dry-run --phase B`: wave map mostra `Total cells per pass` = Phase B apenas (sem Phase A) | ✅ |
| CA-26 | `--dry-run --phase A`: wave map mostra `Total cells per pass` = Phase A apenas | ✅ |
| CA-27 | `--dry-run` (both): wave map mostra soma A+B (comportamento anterior preservado) | ✅ |
| CA-28 | ruff + mypy + lint-imports + pytest 85% todos verdes | ✅ |

---

## Observações para Próximas Tarefas

- TAREFA-309 está pronta para re-submissão ao Codex (ciclo J / PASS esperado).
- TAREFA-310 pode iniciar após PASS.
