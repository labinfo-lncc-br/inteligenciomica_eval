# M3_TAREFA-309_H — Reauditoria pós-correções do ciclo G

**Data**: 2026-06-03
**Milestone**: M3 — Orquestração end-to-end
**Épico**: E3
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / S

## Objetivo

Reauditar as duas correções declaradas no ciclo G:
- remoção da fragilidade de identidade de `DIContainer` em `test_wiring.py`
- correção do cálculo de células para as barras de progresso por fase efetiva

## Arquivos Criados / Modificados

- `docs/dev-log/M3_TAREFA-309_H_reauditoria-pos-correcoes-ciclo-g.md`

## Decisões Técnicas

- A reauditoria combinou leitura pontual do `cli.py`, reexecução do arquivo
  `test_wiring.py` e smoke de `--dry-run --phase B`.
- O foco ficou restrito ao delta do ciclo G.

## Problemas Encontrados e Soluções

### 1. Corrigido — `test_wiring.py` deixou de depender de `reload()`

**Arquivo**: `tests/unit/infrastructure/test_wiring.py`

O teste de lazy import foi reescrito para inspecionar `vars(wiring_mod)` em vez de
recarregar o módulo. Isso eliminou o problema de identidade de `DIContainer`.

Validação:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/unit/infrastructure/test_wiring.py -vv
```

Resultado:

```text
13 passed
```

### 2. Parcialmente corrigido — contagem textual por fase ficou certa

**Arquivo**: `src/inteligenciomica_eval/cli.py:162-178`

O cálculo de `_cells_phase_a`, `_cells_phase_b`, `_cells_per_wave` e `_n_cells` agora
reflete corretamente as fases efetivas para as barras do `run`.

### 3. FAIL — wave map do dry-run ainda ignora o filtro de `--phase`

**Arquivo**: `src/inteligenciomica_eval/cli.py:318-324`

Embora o texto do dry-run com `--phase B` mostre:

```text
phases       : ['B']
Phase B  : 5 LLM(s) x 3 seed(s) x 2 questions = 30 cells
```

o planejamento de ondas ainda usa:

```python
plan = scheduler.plan(specs, cfg)
```

ou seja, o `cfg` original com `phases=['A', 'B']`. Como consequência, a tabela e o
rodapé continuam mostrando números de ambas as fases:

```text
Total cells per pass: 90
```

quando o correto para `phase B` seria 30.

## Validação (DoD)

### Comandos executados

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/unit/infrastructure/test_wiring.py -vv
PYTHONPATH=tests UV_CACHE_DIR=/tmp/uv-cache uv run ielm-eval run --config config/experiment_round1.yaml --run-id test --dry-run --phase B
```

### Resultados observados

- `test_wiring.py` ✅ `13 passed`
- `--dry-run --phase B`:
  - contagem textual ✅
  - wave map / total cells per pass ❌ ainda calculados como se fossem `['A', 'B']`

## Critérios de Aceitação

| Critério | Evidência | Status |
|---|---|---|
| `test_wiring.py` estável sem bug de identidade/reload | pytest do arquivo | ✅ |
| Cálculo textual por fase efetiva está correto | smoke `--phase B` | ✅ |
| Planejamento completo do dry-run respeita `--phase` | wave map + total cells | ❌ |

## Observações para Próximas Tarefas

- Fazer o dry-run montar uma view/config filtrada para passar ao `WaveSchedulerService`,
  em vez de usar `cfg` bruto ao planejar ondas.

## Resultado

**FAIL**

Resumo:
- a fragilidade de `test_wiring.py` foi resolvida
- o cálculo textual por fase foi corrigido
- ainda resta inconsistência objetiva entre a contagem mostrada e o wave plan do
  dry-run quando `--phase` filtra as fases
