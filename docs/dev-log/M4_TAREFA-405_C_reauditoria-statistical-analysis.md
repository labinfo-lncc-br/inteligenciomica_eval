# M4_TAREFA-405_C — StatisticalAnalysisUseCase — Correção pós-auditoria Codex

**Data**: 2026-06-01
**Milestone**: M4 — Análise Estatística e Relatório
**Épico**: E4
**Skill**: claude-code (implementação/correção)
**Prioridade / Tamanho**: P1 / M

---

## Objetivo

Corrigir os dois bloqueadores identificados pelo Codex na auditoria 405B:

1. **[Contrato]** Use case não usava `statsmodels.stats.multitest.multipletests` — implementava BH/Holm em código próprio, contrariando a spec da TAREFA-405.
2. **[Correção/Modelo]** `top_llm_by_friedman` contava "aparições em pares significativos" (qualquer LLM do par), não "vitórias" (LLM com média superior).

---

## Arquivos Criados / Modificados

| Arquivo | Tipo | Alteração |
|---------|------|-----------|
| `src/inteligenciomica_eval/domain/value_objects.py` | Modificado | Campo `winner: str | None = None` adicionado a `NemenyiPair`; docstring atualizada |
| `src/inteligenciomica_eval/infrastructure/adapters/stats_adapters.py` | Modificado | `FriedmanNemenyiAdapter.friedman_nemenyi()`: computa `mean_scores` por grupo e popula `NemenyiPair.winner` quando `significant=True` |
| `src/inteligenciomica_eval/application/statistical_analysis.py` | Reescrito | Substituída implementação local BH/Holm por `multipletests` do statsmodels; `_apply_bh_holm_correction` → `_apply_multiple_correction`; `_derive_top_llm_by_friedman` usa `pair.winner` |
| `.importlinter` | Modificado | `ignore_imports = inteligenciomica_eval.application.statistical_analysis -> statsmodels` (nível raiz — tentativa anterior com sub-módulo causava "No matches") |
| `tests/unit/application/test_statistical_analysis.py` | Modificado | Todos `NemenyiPair` atualizados com campo `winner=`; `TestTopLLMByFriedman` reescrita com semântica correta de vitórias; import atualizado para `_apply_multiple_correction`; novos testes `test_winner_none_not_counted` e `test_tie_resolved_alphabetically` (tie real, 4 LLMs distintos) |

---

## Decisões Técnicas

### 1. `multipletests` em application — exceção de importação

O contrato `application-forbidden` proíbe `statsmodels`. A spec TAREFA-405 exige
`multipletests` no use case. Solução: `ignore_imports` no `.importlinter` apontando
para o pacote raiz `statsmodels` (não sub-módulo `statsmodels.stats.multitest`):

```ini
ignore_imports =
    inteligenciomica_eval.application.statistical_analysis -> statsmodels
```

`import-linter` 2.11 rastreia importações ao nível do pacote raiz; a tentativa
anterior com o sub-módulo retornava "No matches".

### 2. `NemenyiPair.winner` — campo opcional com `default=None`

O `FriedmanNemenyiAdapter` já tinha os `groups_arrays` computados para o teste
de Friedman. Adicionar `winner` foi natural: calcula `mean_scores[i] > mean_scores[j]`
para cada par e popula `winner` apenas quando `significant=True`. O campo usa
`default=None` para compatibilidade com testes e callers existentes.

### 3. `_apply_multiple_correction` — variáveis de loop renomeadas

Para evitar erro mypy de re-atribuição de tipo (`r` inferida como `WilcoxonReport`
e depois reatribuída como `FriedmanReport`), os loops usam `wr` e `fr` como variáveis
distintas.

---

## Problemas Encontrados e Soluções

| Problema | Causa | Solução |
|----------|-------|---------|
| `import-linter` "No matches" para `ignore_imports -> statsmodels.stats.multitest` | Linter rastreia pacote raiz | Usar `-> statsmodels` (raiz) |
| `ruff format` reformatou 2 arquivos | Linhas longas em comentários e docstrings | `uv run ruff format` aplicado antes do gate |
| Mypy erro em loop com variável `r` reutilizada | Tipo inferido da primeira iteração | Renomear para `wr` / `fr` |

---

## Validação (DoD)

```
uv run ruff check .            → All checks passed!
uv run ruff format --check .   → 127 files already formatted
uv run mypy --strict src/      → Success: no issues found in 48 source files
uv run lint-imports            → 4 kept, 0 broken
uv run pytest tests/unit/application/test_statistical_analysis.py -v
                               → 29 passed in 0.48s
uv run pytest -m "not integration" -n 4 --cov=src --cov-fail-under=85 -q
                               → 1016 passed, 5 skipped — 93.04% coverage
```

---

## Critérios de Aceitação

- [x] `multipletests` do statsmodels usado no use case (não implementação local)
- [x] `top_llm_by_friedman` conta vitórias via `NemenyiPair.winner` (média superior)
- [x] `winner` populado pelo `FriedmanNemenyiAdapter` quando par é significativo
- [x] `winner=None` em pares não-significativos (não contribuem para contagem)
- [x] Empate resolvido alfabeticamente (primeiro candidato em `sorted(candidates)`)
- [x] `lint-imports` — 4 contratos mantidos, 0 quebrados (exceção registrada)
- [x] `mypy --strict src/` — 0 erros
- [x] `ruff check/format` — 0 alertas
- [x] 29/29 testes unitários do use case passando
- [x] Suíte completa: 1016 passed, 93.04% cobertura (gate 85% ✓)

---

## Observações para Próximas Tarefas

- `StatsReport.top_llm_by_friedman` doc-string ainda referencia "aparições" — foi
  atualizada para "vitórias via `NemenyiPair.winner`".
- `golden/stats_report_expected.json` foi criado na passagem A; o campo
  `top_llm_by_friedman: "llm_A"` é consistente com o novo critério (llm_A aparece
  como `winner` em 2 pares significativos no golden).
- A TAREFA-406 (HTMLReportAdapter) consumirá `StatsReport` diretamente — nenhuma
  mudança de interface esperada.
