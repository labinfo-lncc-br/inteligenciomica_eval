# M3_TAREFA-307_C — Correção pós-FAIL: rank_calc morto + failed_waves deduplicação

**Data**: 2026-05-30
**Milestone**: M3 — Passadas de Avaliação
**Épico**: E3
**Skill**: backend-engineer
**Prioridade / Tamanho**: P0 / S

## Objetivo

Corrigir os dois bloqueadores apontados pelo auditor Codex no relatório B:

1. **`rank_calc` morto** — `self._rank_calc` era injetado mas nunca chamado; `rank_scores`
   era extraído de `agg.rank_score` (já calculado pelo `AggregationService`), tornando
   a dependência inerte e desalinhada com o prompt.
2. **`failed_waves` duplicado por modelo** — `failed_waves.append(wave.wave_index)` rodava
   dentro do loop `for model_name in wave.models`, podendo registrar o mesmo índice de
   onda múltiplas vezes se mais de um modelo falhasse na mesma onda.

## Arquivos Modificados

| Arquivo | Ação | Descrição |
|---------|------|-----------|
| `src/inteligenciomica_eval/application/use_cases/run_experiment.py` | Modificado | Recompute explícito de `rank_scores`; `set` para `failed_wave_set` |
| `tests/unit/application/use_cases/test_run_experiment.py` | Modificado | `_make_uc` aceita `rank_calc`; golden test passa `RankScoreCalculator` real |

## Decisões Técnicas

### Bloqueador 1 — Recompute explícito de `rank_scores`

```python
rank_scores = tuple(
    self._rank_calc.compute(
        RankScoreInputs(
            median_score=agg.median_score,
            failure_rate=agg.failure_rate,
            win_rate=agg.win_rate,
            critical_failure_rate=agg.critical_failure_rate,
        )
    )
    for agg in aggregates
)
```

`RankScoreInputs` adicionado ao import de `domain.services.rank_score`. A redundância
com `agg.rank_score` (calculado pelo `AggregationService` com seu próprio
`RankScoreCalculator` interno) é intencional: o orquestrador usa sua própria instância
injetada, permitindo pesos diferentes entre agregação e ranking final se necessário.

### Bloqueador 2 — `set` para deduplicação de `failed_wave_set`

`failed_waves: list[int]` → `failed_wave_set: set[int]`. Todos os `append` → `add`.
Conversão final: `tuple(sorted(failed_wave_set))` — determinístico, sem duplicatas.
Mesmo `sorted` no retorno parcial (shutdown).

### Impacto nos testes

`_make_uc` recebe parâmetro `rank_calc: Any = None` (padrão `_FakeRankCalc()`).
Teste golden `test_aggregates_and_rank_scores_populated` passa
`rank_calc=RankScoreCalculator(weights=DEFAULT_WEIGHTS)` — assim o `rank_scores[0]`
calculado pelo orquestrador coincide com o `golden_score` (mesmos inputs, mesmos pesos).

## Validação (DoD)

```
ruff check .          → All checks passed!
ruff format --check . → 114 files already formatted
mypy --strict src     → Success: no issues found in 42 source files
lint-imports          → 4 kept, 0 broken
pytest test_run_exp   → 23 passed
pytest suíte -n 4     → 902 passed, 15 skipped, 96.59% coverage
```
