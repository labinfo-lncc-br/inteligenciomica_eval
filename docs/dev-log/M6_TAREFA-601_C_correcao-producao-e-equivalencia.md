# M6_TAREFA-601_C — Correção de violação de `src/` e análise de equivalência semântica

**Data**: 2026-06-02
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: test-engineer
**Prioridade / Tamanho**: P1 / S

---

## Objetivo

Corrigir a violação identificada na segunda auditoria Codex (commit 06899cb): o ciclo B→A
anterior modificou arquivos em `src/` (proibido pelo Prompt A da TAREFA-601). Reverter as
alterações de produção, manter as correções de infraestrutura (mutation_gate.py, ci.yml) e
documentar com análise técnica completa por que os sobreviventes de comparação são
semanticamente equivalentes.

---

## Arquivos Criados / Modificados

| Arquivo | Ação |
|---------|------|
| `src/inteligenciomica_eval/domain/services/rank_score.py` | Revertido ao estado de a0338dd (guarda NaN restaurada) |
| `src/inteligenciomica_eval/domain/services/final_score.py` | Revertido ao estado de a0338dd (`_WEIGHTS_TOLERANCE=1e-9`, `weight>0.0` restaurado) |
| `tests/unit/domain/services/test_final_score.py` | Removido `test_construction_weights_sum_at_tolerance_boundary_is_accepted` (só funcionava com `2**-30`) |
| `tests/mutation/mutation_report.txt` | Regenerado com código original: 263 mutantes, 92.4% PASS |
| `docs/dev-log/M6_TAREFA-601_A_mutation-testing-domain-services.md` | Atualizado: dados corretos, análise técnica dos sobreviventes de comparação |

---

## Decisões Técnicas

### Por que as alterações em `src/` foram revertidas

O Prompt A da TAREFA-601 é explícito (linha 109, 116–118):

> "Camadas: testes (não altera código de produção)"
> "Esta tarefa NÃO altera código de produção: adiciona configuração de mutation testing
> e, se necessário, fortalece os testes unitários existentes para sobreviventes críticos."

O commit 06899cb modificou `rank_score.py` (removeu guarda NaN) e `final_score.py`
(removeu `weight > 0.0`, trocou `_WEIGHTS_TOLERANCE`). Mesmo que as alterações fossem
comportamentalmente corretas e sem impacto funcional, violaram a restrição formal do prompt.
Revertidos.

### Análise de equivalência semântica dos sobreviventes de comparação

Três mutantes sobreviventes envolvem operadores de comparação em `final_score.py`.
A análise demonstra que são inmatáveis sem alteração de `src/`:

#### mutmut_12 — `abs(total - 1.0) > _WEIGHTS_TOLERANCE` → `>=`

`_WEIGHTS_TOLERANCE = 1e-9`. Em Python (IEEE 754 double), `1e-9` cai num "gap" entre
doubles representáveis próximos de 1.0:

```python
abs((1.0 + 1e-9) - 1.0) = 1.0000000827e-9  # > 1e-9 → ambas levantam exceção
abs((1.0 - 1e-9) - 1.0) = 9.9999998e-10    # < 1e-9 → ambas aceitam
```

Não existe float `x` para o qual `abs(x - 1.0) == 1e-9` exatamente. Logo `>` e `>=`
produzem resultado idêntico para qualquer `sum(weights.values())` representável como
`float`. Nenhum teste pode distingui-los sem que a tolerância seja alterada para um valor
exatamente representável (ex.: `2**-30`), o que constitui alteração de `src/`.

#### mutmut_16 — `weight > 0.0 and math.isnan(value)` → `weight >= 0.0 and ...`

Após `if weight == 0.0: continue`, `weight ≠ 0` é garantido. Para qualquer `weight ≠ 0`:
- Se `weight > 0`: `weight > 0.0` = True; `weight >= 0.0` = True → ambas disparam a guarda.
- Se `weight < 0`: `weight > 0.0` = False; `weight >= 0.0` = False → nenhuma dispara;
  e `weight * NaN = NaN` propaga via IEEE 754 igualmente.

Comportamento observável idêntico para todo float finito não-zero.

#### mutmut_17 — `weight > 0.0 and math.isnan(value)` → `weight > 1.0 and ...`

Pesos válidos passam pela validação `abs(sum(w) - 1.0) <= 1e-9`, então na prática
`w ∈ (0, 1]`. Para esses valores: `weight > 0.0` = True mas `weight > 1.0` = False.
A guarda não dispara com `> 1.0` → aritmética `weight * NaN = NaN` propaga igualmente.
Para o único caso onde `weight > 1.0` poderia ser True (`w > 1.0`), a validação de soma
impediria tal configuração sem outro peso negativo compensando — e `NaN` propagaria de
qualquer forma.

Comportamento observável idêntico em toda configuração válida.

### Classificação dos sobreviventes de comparação

Prompt A §5: *"Mutações em guard clauses que já são cobertas por testes de exceção:
ACEITÁVEL."*

Os três mutantes estão em guard clauses:
- mutmut_12: guarda de validação de soma de pesos no `__init__`.
- mutmut_16/17: guarda de propagação de NaN no `compute`.

Todos têm cobertura de teste:
- mutmut_12: `test_construction_weights_not_sum_to_one_raises` + `test_construction_weights_exactly_one_ok`.
- mutmut_16/17: `test_compute_nan_in_weighted_metric_propagates` (parametrizado para todos os campos).

### Operadores `or→and` em `rank_score.compute` (mutmut_1/2/3)

Os três mutantes que sobrevivem na guarda NaN de `rank_score.compute` (linhas 120–126)
envolvem operadores **booleanos** (`or → and`), que não constam na lista de operadores
proibidos do Prompt B item 3 (restrita a `+`, `-`, `*`, `/`, `<`, `>`, `<=`, `>=`).
Adicionalmente, são semanticamente equivalentes: `w * NaN = NaN` (IEEE 754) para qualquer
peso finito, tornando a guarda explícita redundante com a propagação aritmética.

---

## Validação (DoD)

```
uv run ruff check .            → All checks passed!
uv run ruff format --check .   → 139 files already formatted
uv run mypy --strict src       → Success: no issues found in 50 source files
uv run lint-imports            → Contracts: 4 kept, 0 broken.
uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4 -q
                               → 1071 passed, 6 skipped — 90.97%
uv run python scripts/mutation_gate.py
                               → Mutation score 92.4% >= 80%. [PASS]
```

---

## Observações para Próximas Tarefas

- Se o Codex aceitar a classificação de "guard clause" para mutmut_12/16/17, a TAREFA-601
  está aprovada. Caso contrário, discutir com o utilizador se a restrição "sem alteração
  de src/" pode ser flexibilizada para permitir substituição de `1e-9` por `2**-30`
  (mudança zero em comportamento, mas que elimina o "gap" de doubles).
- O ciclo A↔B deve continuar até aprovação mútua antes de avançar para TAREFA-602.
