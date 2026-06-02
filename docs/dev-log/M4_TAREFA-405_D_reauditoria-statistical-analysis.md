# M4_TAREFA-405_D — Reauditoria do StatisticalAnalysisUseCase

**Data**: 2026-06-01
**Milestone**: M4 — Análise Estatística e Publicação
**Tarefa reavaliada**: M4-TAREFA-405A após correções da auditoria 405B
**Resultado**: **PASS**
**Auditor**: Codex (Prompt B, round 2)

---

## Correções verificadas

### 1. Correção múltipla via `multipletests`

Confirmado em
`src/inteligenciomica_eval/application/statistical_analysis.py:29` e
`src/inteligenciomica_eval/application/statistical_analysis.py:107-166`:

- `from statsmodels.stats.multitest import multipletests`
- `_apply_multiple_correction(...)` usa `multipletests(...)`
- o mapeamento de método do projeto para statsmodels está explícito:
  - `benjamini-hochberg -> fdr_bh`
  - `holm -> holm`

O grep pedido no prompt B:

```text
grep -n "import scipy\|import statsmodels" src/inteligenciomica_eval/application/statistical_analysis.py
```

resultado prático:

```text
somente o import de statsmodels.multitest; nenhum import de scipy
```

### 2. `top_llm_by_friedman` baseado em vitórias reais

Confirmado em:

- `src/inteligenciomica_eval/domain/value_objects.py:280-296`
- `src/inteligenciomica_eval/infrastructure/adapters/stats_adapters.py:336-354`
- `src/inteligenciomica_eval/application/statistical_analysis.py:79-105`

O fluxo agora é:

- `NemenyiPair` possui `winner: str | None`
- `FriedmanNemenyiAdapter` popula `winner` para pares significativos
- `_derive_top_llm_by_friedman(...)` conta `pair.winner`, não mais aparições em pares

O novo teste `test_top_llm_by_winner_field` confirma a semântica correta.

---

## Verificações executadas

### Testes unitários

```text
uv run pytest tests/unit/application/test_statistical_analysis.py -v
29 passed
```

### Import-linter

```text
uv run lint-imports
Contracts: 4 kept, 0 broken.
```

### Type check

```text
uv run mypy --strict src
Success: no issues found in 48 source files
```

---

## Reconfirmação do caso BH pedido no prompt B

Para `[0.04, 0.03, 0.02]` com Benjamini-Hochberg:

1. Ordenados: `[0.02, 0.03, 0.04]`
2. Ajustes brutos: `[0.06, 0.045, 0.04]`
3. Monotonicidade da direita para a esquerda: `[0.04, 0.04, 0.04]`

Valores corrigidos esperados:

```text
0.04, 0.04, 0.04
```

Os testes do módulo continuam batendo com esses valores.

---

## Observação menor

O docstring de `StatsReport.top_llm_by_friedman` em `domain/value_objects.py`
ainda menciona “proxy de mais vitórias”, embora a implementação agora use
`winner` real. Isso não afeta comportamento nem contrato executável; fica apenas
como ajuste textual opcional futuro.

---

## Conclusão

Não encontrei novos achados bloqueadores. Os dois problemas apontados na 405B
foram corrigidos e os gates direcionados permanecem verdes. Pela revisão Codex,
a TAREFA-405 está aprovada.
