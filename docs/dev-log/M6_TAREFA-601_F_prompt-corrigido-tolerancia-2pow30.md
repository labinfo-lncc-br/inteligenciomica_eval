# M6_TAREFA-601_F — Prompt corrigido: tolerância 2**-30 e provas de equivalência

**Data**: 2026-06-02
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: test-engineer
**Prioridade / Tamanho**: P1 / S

---

## Objetivo

Adaptar a implementação ao prompt corrigido `docs/m6_tarefas_601_corrigido.md` (versão
arquiteto). A principal diferença em relação ao prompt original é o item 6: autoriza
explicitamente a troca `_WEIGHTS_TOLERANCE = 1e-9` → `2**-30` em `final_score.py`
como **única** mudança de produção, eliminando o mutante `mutmut_12` (`>→>=`). O
Prompt B corrigido também passa a aceitar sobreviventes com prova formal de equivalência
registrada no `mutation_report.txt`, em vez de exigir a morte de todo sobrevivente de
comparação.

---

## Arquivos Criados / Modificados

| Arquivo | Ação |
|---------|------|
| `src/inteligenciomica_eval/domain/services/final_score.py` | `_WEIGHTS_TOLERANCE: float = 2**-30` (única mudança de produção autorizada; comentário justifica 2^-30) |
| `tests/unit/domain/services/test_final_score.py` | Adicionado `test_construction_weights_sum_at_tolerance_boundary_is_accepted` — mata mutmut_12 |
| `tests/mutation/mutation_report.txt` | Regenerado: 263 mutantes, 244 killed, 19 survived, 92.8% PASS; provas formais de equivalência para todos os 19 sobreviventes |

---

## Decisões Técnicas

### Troca de `1e-9` por `2**-30` (item 6 do Prompt A corrigido)

`1e-9` não é um valor exatamente representável na grade de doubles próxima de 1.0.
Perto de 1.0 (faixa [1, 2)), o ULP é 2^-52; o valor mais próximo de `1e-9` nessa
grade distancia-se da "fronteira teórica" de 1.0 em ≈ 1.0000000827×10^-9, não em
exatamente 1e-9. Portanto, `abs(x - 1.0) == 1e-9` nunca é True para nenhum float,
tornando `>` e `>=` indistinguíveis.

`2**-30` é exatamente representável (potência de 2). Pelo Lema de Sterbenz,
`(1.0 + 2**-30) - 1.0 == 2**-30` exatamente. Logo, existe um float (`1.0 + 2**-30`)
para o qual `abs(x - 1.0) == 2**-30`, tornando a fronteira observável e testável.

Impacto comportamental em produção: nulo. A banda estreita [9.31×10^-10, 1×10^-9]
onde os dois valores divergiriam é inalcançável por qualquer vetor de pesos realista
(pesos são frações geralmente com 2 casas decimais).

### Teste de fronteira `test_construction_weights_sum_at_tolerance_boundary_is_accepted`

```python
w = {"answer_correctness": 1.0, "faithfulness": 2**-30}
FinalScoreCalculator(w)  # não deve levantar
```

`sum([1.0, 2**-30]) = 1.0 + 2**-30` (exato, por Sterbenz).
`abs((1.0 + 2**-30) - 1.0) = 2**-30 = _WEIGHTS_TOLERANCE`.
Com `>`: `2**-30 > 2**-30` = False → não levanta → teste PASSA.
Com mutante `>=`: `2**-30 >= 2**-30` = True → levanta → `pytest.raises` falha → mutante MORTO.

### Provas de equivalência no `mutation_report.txt`

O Prompt B corrigido aceita sobreviventes COM prova formal registrada. Adicionada
seção "Equivalence Proofs" ao relatório com 7 categorias cobrindo todos os 19
sobreviventes:

| Categoria | Mutantes | Mecanismo |
|---|---|---|
| A — `float("NAN")` ↔ `float("nan")` | 6 | Python float() case-insensitive |
| B — `n=4` default de `statistics.quantiles` | 1 | Valor igual ao default |
| C — Ramo inalcançável `n_questions==0` | 2 | Invariante do chamador (aggregate_all filtra grupos vazios) |
| D — Conteúdo de mensagem de exceção | 4 | reason/tolerance afetam só .args, não controle de fluxo |
| E — `typing.cast` é no-op em runtime | 1 | CPython: cast(typ, val) = val independente de typ |
| F — `or→and` na guarda NaN de rank_score | 3 | IEEE 754: w*NaN=NaN para qualquer w finito não-zero |
| G — Comparações na guarda NaN de final_score | 2 | Invariante weight≠0 pós-continue; IEEE 754 propagation |

---

## Validação (DoD)

```
uv run ruff check .            → All checks passed!
uv run ruff format --check .   → 139 files already formatted
uv run mypy --strict src       → Success: no issues found in 50 source files
uv run lint-imports            → Contracts: 4 kept, 0 broken.
uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4 -q
                               → 1072 passed, 6 skipped — 90.97%
uv run python scripts/mutation_gate.py
                               → Mutation score 92.8% >= 80%. [PASS]
```

---

## Critérios de Aceitação (Prompt A corrigido)

- [x] `_WEIGHTS_TOLERANCE = 2**-30` com comentário justificando 2^-30 em `final_score.py`.
- [x] `test_construction_weights_sum_at_tolerance_boundary_is_accepted` mata mutmut_12.
- [x] `mutation_report.txt` mostra mutmut_12 como MORTO (244 killed; era 243).
- [x] Score 92.8% ≥ 80%. Gate: PASS.
- [x] Todos os 19 sobreviventes têm prova formal de equivalência no relatório.
- [x] Nenhum sobrevivente não-documentado em lógica aritmética de scoring.
- [x] `funnel.py` não está em `paths_to_mutate`.
- [x] `final_score.py` é a ÚNICA mudança de produção.
- [x] ruff, mypy, lint-imports, pytest (≥85%) verdes.

---

## Observações para Próximas Tarefas

- O Prompt B corrigido deve verificar: mutmut_12 MORTO, sobreviventes com prova válida,
  score ≥ 80%, final_score.py única mudança de produção.
- Se o Codex aceitar as provas formais, TAREFA-601 está PASS e aguarda autorização
  para avançar para TAREFA-602 (Cohen's κ).
