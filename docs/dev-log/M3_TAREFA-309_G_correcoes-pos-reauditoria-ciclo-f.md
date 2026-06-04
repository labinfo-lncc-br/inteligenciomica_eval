# M3_TAREFA-309_G — Correções pós-reauditoria Codex (ciclo F → ciclo G)

**Data**: 2026-06-03
**Milestone**: M3 — Orquestração end-to-end
**Épico**: E3
**Skill**: /implement (correção)
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Corrigir os dois achados do ciclo F (reauditoria Codex sobre as correções do ciclo E).

---

## Análise da Reauditoria

### Achados do ciclo F

| # | Achado | Gravidade |
|---|--------|-----------|
| 1 | `test_wiring.py` completo falha com `assert isinstance(container, DIContainer)` quando `test_import_wiring_does_not_pull_fakes` roda antes — `importlib.reload()` recria a classe, quebrando identidade de tipo | BLOQUEADOR |
| 2 | `_n_cells` calculado com `len(cfg.bases) * len(cfg.llms) * len(cfg.seeds) * len(questions)` para todas as fases — superconta `--phase B` (Phase B não usa bases) e subconta `both` (deveria somar Phase A + Phase B) | IMPORTANTE |

---

## Arquivos Modificados

| Arquivo | Alteração |
|---------|-----------|
| `tests/unit/infrastructure/test_wiring.py` | Substituído `importlib.reload()` por inspeção de `vars(wiring_mod)` — sem efeito colateral de reload; removido `import sys` (ficou sem uso) |
| `src/inteligenciomica_eval/cli.py` | `_n_cells` e `_cells_per_wave` calculados por fase efetiva (`_eff_phases`); linha duplicada `_cells_per_wave = len(...) * len(...) * len(...)` dentro do bloco `with Progress` removida |

---

## Decisões Técnicas

### 1. Substituição de `importlib.reload()` por inspeção de globals

O teste `TestNoFakesAtModuleLevel.test_import_wiring_does_not_pull_fakes` usava
`importlib.reload(_wiring_module)` para "garantir estado limpo". O problema:

- `importlib.reload(module)` atualiza o dict de globals **in-place** do módulo
- Funções definidas no módulo (ex: `build_fake_container`) têm `__globals__` apontando
  para esse mesmo dict → após reload, passam a criar instâncias da **nova** `DIContainer`
- O topo do arquivo de teste importou `DIContainer` antes do reload → referência à
  **antiga** classe → `isinstance(container, DIContainer)` → **False**
- Com `pytest-randomly`, a ordem de execução é aleatória — o bug ocorre quando
  `test_import_wiring_does_not_pull_fakes` roda antes de `test_constructs_without_error`

**Solução**: sem reload. A propriedade testada — "fakes não são importadas no nível do
módulo" — pode ser verificada inspecionando `vars(wiring_mod)`:

```python
eager_fakes = [
    name for name in vars(_wiring_mod)
    if name.startswith("Fake") or name.startswith("fake_")
]
assert eager_fakes == []
```

Quando `from fakes import X` ocorre dentro de uma função, `X` é local à função
— nunca aparece no namespace global do módulo. Se o import fosse no topo do arquivo,
`X` estaria em `vars(wiring_mod)`. A assertiva é correta e order-independent.

### 2. `_n_cells` por fase efetiva

Phase A (retrieval): usa `bases` → `n_q * n_bases * n_llms * n_seeds`
Phase B (geração direta): sem `bases` → `n_q * n_llms * n_seeds`

Cálculo correto:

```python
_eff_phases = phases_filter if phases_filter is not None else list(cfg.phases)
_cells_phase_a = (
    len(questions) * len(cfg.bases) * len(cfg.seeds) if "A" in _eff_phases else 0
)
_cells_phase_b = len(questions) * len(cfg.seeds) if "B" in _eff_phases else 0
_cells_per_wave = _cells_phase_a + _cells_phase_b
_n_cells = _cells_per_wave * len(cfg.llms)
```

Casos:
- `--phase A` → `_n_cells = n_q * n_bases * n_seeds * n_llms` ✓
- `--phase B` → `_n_cells = n_q * n_seeds * n_llms` (sem bases) ✓
- `both` → `_n_cells = (n_q*n_bases*n_seeds + n_q*n_seeds) * n_llms` ✓

`_cells_per_wave` é usado em `_progress_callback` para `progress.advance(task_gen, ...)`.
A linha duplicada `_cells_per_wave = len(questions) * len(cfg.seeds) * len(cfg.bases)`
dentro do bloco `with Progress` foi removida.

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| `import sys` ficou sem uso após remoção de `sys.modules` do teste | Removido |
| `_cells_per_wave` estava definido 2×: uma vez correto (antes do `with`) e uma vez errado (dentro do `with`) | Removida a segunda definição |

---

## Validação (DoD)

### Gates executados

```
✅ uv run ruff check .          → All checks passed
✅ uv run ruff format --check . → 161 files already formatted
✅ uv run mypy --strict src     → Success: no issues found in 57 source files
✅ uv run lint-imports          → 4 contracts: 4 kept, 0 broken
✅ uv run pytest -n 4 -q tests/unit/infrastructure/test_wiring.py
   → 13 passed (era 1 failed + 12 passed)
✅ uv run pytest -n 4 -q --cov=src --cov-fail-under=85
   → 1199 passed, 16 skipped — 88.53% coverage (gate 85% ✓)
```

---

## Critérios de Aceitação (pós-ciclo F)

| # | Critério | Status |
|---|----------|--------|
| CA-20 | `pytest tests/unit/infrastructure/test_wiring.py` completo → 13 passed (0 failed) independente de ordem | ✅ |
| CA-21 | `--phase A`: `_n_cells = n_q * n_bases * n_seeds * n_llms` | ✅ |
| CA-22 | `--phase B`: `_n_cells = n_q * n_seeds * n_llms` (sem bases) | ✅ |
| CA-23 | `both` (default): `_n_cells` = soma Phase A + Phase B | ✅ |
| CA-24 | ruff + mypy + lint-imports + pytest 85% todos verdes | ✅ |

---

## Observações para Próximas Tarefas

- TAREFA-309 está pronta para re-submissão ao Codex (ciclo H / PASS esperado).
- TAREFA-310 pode iniciar após PASS.
