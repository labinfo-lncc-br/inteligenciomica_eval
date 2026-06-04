# M3_TAREFA-309_E — Correções pós-reauditoria Codex (ciclo D → ciclo E)

**Data**: 2026-06-03
**Milestone**: M3 — Orquestração end-to-end
**Épico**: E3
**Skill**: /implement (correção)
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Corrigir os três achados do ciclo D (re-auditoria Codex sobre as correções do ciclo C).

---

## Análise da Reauditoria

### Achados do ciclo D

| # | Achado | Gravidade |
|---|--------|-----------|
| 1 | `--dry-run` sem `PYTHONPATH=tests` falha com `ModuleNotFoundError` exibindo stacktrace (quebra contrato UX) | BLOQUEADOR |
| 2 | `--phase` não passado para `_run_dry_run` → plano exibe fases do YAML, ignorando a flag | IMPORTANTE |
| 3 | 3 barras de progresso com `total=None` e sem `advance` — não mostram progresso real | IMPORTANTE |

---

## Arquivos Modificados

| Arquivo | Alteração |
|---------|-----------|
| `src/inteligenciomica_eval/cli.py` | `_run_dry_run` recebe `phase`; trata `ImportError` de `build_fake_container` com fallback silencioso (`_log.debug`); filtra `phases` por `--phase`; 3 barras com `total` calculado + `progress.advance()` |

---

## Decisões Técnicas

### 1. Fallback silencioso no `--dry-run` para `ImportError`

O `_run_dry_run` tenta `build_fake_container(cfg)` dentro de `try/except ImportError`.
Se `tests/fakes` não estiver em `sys.path` (CLI em produção), o `except` captura o erro,
registra `_log.debug("dry_run_fakes_unavailable", ...)` e cai para `load_questions()`
direto. Nenhum stacktrace chega ao usuário. Comportamento:

- **Com `PYTHONPATH=tests`** (contexto de dev): usa `build_fake_container`, 2 perguntas,
  log `[info] wiring_fake_container_built`.
- **Sem `PYTHONPATH=tests`** (CLI de produção): fallback, 3 perguntas do arquivo
  empacotado, log `[debug] dry_run_fakes_unavailable`. UX preservada.

### 2. `--phase` propagado para `_run_dry_run`

`_run_dry_run` recebe `phase: str` (novo parâmetro).
Dentro da função:
```python
phases: list[str] = (
    [phase.upper()] if phase.lower() != "both" else list(cfg.phases)
)
```
O plano exibido (cell counts, wave map) usa essa lista filtrada — consistente com a
execução real.

### 3. Barras de progresso com `advance` real

Substituído `total=None` por totais calculados a partir do `cfg` e das `questions`:
- `task_waves`: `total=len(cfg.llms)` (1 onda por LLM, estimativa conservadora)
- `task_gen`: `total = len(questions) * len(cfg.seeds) * len(cfg.bases) * len(cfg.llms)`
- `task_eval`: `total=2` (1 passada métricas + 1 passada juiz)

Callbacks com `progress.advance()`:
- `"generation:<model>"` → `advance(task_waves, 1)` + `advance(task_gen, cells_per_wave)`
- `"metrics_pass_done"` → `advance(task_eval, 1)`
- `"judge_pass_done"` → `advance(task_eval, 1)`

Adicionado `MofNCompleteColumn` no `Progress` para exibir `N/M` ao lado de cada barra.

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| mypy `[unused-ignore]` em 7 locais — `cfg` no escopo do `run()` já tem tipo `RoundConfig` | Removidos todos os `# type: ignore[attr-defined]` do bloco de totais de progresso |
| ruff format precisou de reformatação | `uv run ruff format src/inteligenciomica_eval/cli.py` |

---

## Validação (DoD)

### Gates executados

```
✅ uv run ruff check .          → All checks passed
✅ uv run ruff format --check . → 161 files already formatted
✅ uv run mypy --strict src     → Success: no issues found in 57 source files
✅ uv run lint-imports          → 4 contracts: 4 kept, 0 broken
✅ uv run pytest -n 4 -q --cov=src --cov-fail-under=85
   → 1199 passed, 16 skipped — 88.52% coverage (gate 85% ✓)
```

### Smoke tests

```bash
# COM PYTHONPATH=tests (usa build_fake_container):
$ PYTHONPATH=tests uv run ielm-eval run --config config/experiment_round1.yaml --dry-run
[info] wiring_fake_container_built  round_id=round-1
phases       : ['A', 'B']
Perguntas carregadas: 2
...

# SEM PYTHONPATH=tests (fallback silencioso, sem stacktrace):
$ uv run ielm-eval run --config config/experiment_round1.yaml --dry-run
[debug] dry_run_fakes_unavailable  hint='Define PYTHONPATH=tests...'
phases       : ['A', 'B']
Perguntas carregadas: 3
...

# --phase A (dry-run filtra fases):
$ PYTHONPATH=tests uv run ielm-eval run --config ... --dry-run --phase A
phases       : ['A']
  Phase A  : 2 base(s) x 5 LLM(s) x 3 seed(s) x 2 questions = 60 cells
```

---

## Critérios de Aceitação (pós-ciclo D)

| # | Critério | Status |
|---|----------|--------|
| CA-15 | `--dry-run` sem `PYTHONPATH=tests` → fallback silencioso, sem stacktrace | ✅ |
| CA-16 | `--dry-run --phase A` → plano exibe só `phases: ['A']` e células de Phase A | ✅ |
| CA-17 | 3 barras com `total` calculado; `advance` chamado em cada onda/passada | ✅ |
| CA-18 | `MofNCompleteColumn` exibe `N/M` nas 3 barras | ✅ |
| CA-19 | ruff + mypy + lint-imports + pytest 85% todos verdes | ✅ |

---

## Observações para Próximas Tarefas

- TAREFA-309 está pronta para re-submissão ao Codex (ciclo F / PASS esperado).
- TAREFA-310 pode iniciar após PASS: `build_fake_container` + `ParquetStorage(tmp_path)`
  + 2 perguntas do bundled JSONL.
- O `total=len(cfg.llms)` para `task_waves` é estimativa conservadora; ondas concorrentes
  (ADR-012) podem completar em menos steps. O usuário verá a barra chegar a 100% cedo ou
  pode ultrapassar se o scheduler agrupar. Comportamento aceitável para estimativa de UX.
