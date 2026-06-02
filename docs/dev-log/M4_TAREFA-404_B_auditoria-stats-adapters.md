# M4_TAREFA-404_B — Auditoria dos Stats Adapters

**Data**: 2026-06-01
**Milestone**: M4 — Análise Estatística e Publicação
**Tarefa auditada**: M4-TAREFA-404A
**Resultado**: **FAIL**
**Auditor**: Codex (Prompt B)

---

## Escopo auditado

- `src/inteligenciomica_eval/domain/value_objects.py`
- `src/inteligenciomica_eval/domain/ports.py`
- `src/inteligenciomica_eval/infrastructure/adapters/stats_adapters.py`
- `src/inteligenciomica_eval/infrastructure/config/adapter_configs.py`
- `tests/unit/adapters/test_stats_adapters.py`
- `tests/integration/adapters/test_stats_integration.py`
- `tests/golden/stats_wilcoxon_expected.json`

---

## Achados

### 1. Bloqueador — MLM não degrada quando `mixedlm.fit()` retorna `converged=False`

**Arquivo**: `src/inteligenciomica_eval/infrastructure/adapters/stats_adapters.py:441-495`

O contrato da TAREFA-404 exige degradação graciosa tanto para exceção numérica quanto
para não convergência: `convergence_warning=True` **e p-values=NaN**, sem propagar
exceção. A implementação atual só degrada no `except`. Quando o ajuste retorna um
`result` válido com `converged=False`, o adapter apenas seta
`convergence_warning = True` e devolve coeficientes/p-values reais.

Reprodução local controlada, substituindo `smf.mixedlm` por um fake que retorna
`converged=False`:

```text
MLMReport(formula='final_score ~ base + (1 | question_id)',
base_effect_coef=0.1,
base_effect_p_value=0.04,
llm_effect_p_values={},
interaction_p_value=nan,
interaction_significant=False,
aic=123.0,
n_observations=10,
convergence_warning=True)
```

Isso viola diretamente a spec do prompt A e o item 5 do prompt B. O conserto é
tratar `not result.converged` como caminho degenerado, não apenas como flag
informativa.

### 2. Importante — Falta teste cobrindo o ramo `converged=False`

**Arquivo**: `tests/unit/adapters/test_stats_adapters.py:496-517`

O teste chamado `test_non_convergence_returns_nan_without_exception` valida apenas o
caminho de exceção com `ResultFrame(results=())`, não o caso em que o statsmodels
retorna normalmente com `converged=False`. Como esse ramo é justamente o que hoje
quebra o contrato, falta um teste direcionado com monkeypatch/fake result para evitar
regressão.

---

## Verificações confirmadas

- VOs `NemenyiPair`, `WilcoxonReport`, `FriedmanReport` e `MLMReport` são frozen dataclasses em `domain/value_objects.py`.
- Os três adapters satisfazem `StatsPort` estruturalmente; os testes de `isinstance(..., StatsPort)` passam.
- Wilcoxon pareia por `(question_id, seed)` e o cálculo de `effect_size_r = Z / sqrt(N)` está implementado.
- Friedman calcula Nemenyi apenas quando `p_value < alpha`.
- `pandas` / `scipy` / `statsmodels` / `scikit_posthocs` permanecem restritos à infraestrutura.

---

## Comandos executados

### Testes unitários

```text
uv run pytest tests/unit/adapters/test_stats_adapters.py -v
25 passed
```

### Testes de integração

```text
uv run pytest tests/integration/adapters/test_stats_integration.py -v
8 passed
```

### Import-linter

```text
uv run lint-imports
Contracts: 4 kept, 0 broken.
```

### Grep pedido no prompt B (item 6)

Comando:

```text
grep -rn "import scipy\|import statsmodels\|import pandas" src/inteligenciomica_eval/domain/ src/inteligenciomica_eval/application/
```

Saída:

```text
(sem saída)
```

---

## Recomputação do golden de Wilcoxon

Arquivo auditado: `tests/golden/stats_wilcoxon_expected.json`

Recomputei os 13 pares com `scipy.stats.wilcoxon(alternative="two-sided", zero_method="wilcox")`.

Resultado:

```text
statistic=0.000000
p_value=0.000244140625
golden_p_value=0.000244140000
```

O golden está consistente dentro da precisão esperada.

---

## Conclusão

Os gates e os goldens estão em ordem, mas a degradação do `MixedLinearModelAdapter`
está incompleta no ramo `converged=False`, que é parte explícita do contrato da
TAREFA-404. A tarefa deve voltar para correção antes de aprovação.
