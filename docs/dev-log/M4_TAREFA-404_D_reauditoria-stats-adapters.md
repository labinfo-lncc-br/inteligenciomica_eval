# M4_TAREFA-404_D — Reauditoria dos Stats Adapters

**Data**: 2026-06-01
**Milestone**: M4 — Análise Estatística e Publicação
**Tarefa reavaliada**: M4-TAREFA-404A após correção do achado 404B
**Resultado**: **PASS**
**Auditor**: Codex (Prompt B, round 2)

---

## Correção verificada

O bloqueador da auditoria anterior foi resolvido em
`src/inteligenciomica_eval/infrastructure/adapters/stats_adapters.py:445-450`.

Quando `model.fit(...)` retorna com `converged=False`, o adapter agora:

- registra `mlm_non_convergence`;
- faz early-return para `_degenerate(...)`;
- não expõe coeficientes, p-values nem AIC reais no relatório.

O helper `_degenerate(...)` também passou a aceitar
`convergence_warning: bool = True`, mantendo o contrato explícito do relatório.

---

## Teste novo validado

O teste `test_converged_false_returns_degenerate` em
`tests/unit/adapters/test_stats_adapters.py:524-553` cobre exatamente o ramo que
faltava: `smf.mixedlm` é mockado para retornar um resultado com
`converged=False`, e o teste verifica:

- `report.convergence_warning is True`
- `report.aic` é `NaN`
- `report.base_effect_coef` é `NaN`
- `report.base_effect_p_value` é `NaN`
- `report.llm_effect_p_values == {}`

---

## Verificações executadas

### Testes unitários

```text
uv run pytest tests/unit/adapters/test_stats_adapters.py -v
26 passed
```

### Testes de integração

```text
uv run pytest tests/integration/adapters/test_stats_integration.py -v
8 passed
```

### Type check

```text
uv run mypy --strict src
Success: no issues found in 47 source files
```

### Import-linter

```text
uv run lint-imports
Contracts: 4 kept, 0 broken.
```

---

## Conclusão

Não encontrei novos achados. O ramo `converged=False` do
`MixedLinearModelAdapter` agora respeita o contrato de degradação graciosa, e a
lacuna de teste foi fechada. Pela revisão Codex, a TAREFA-404 está aprovada.
