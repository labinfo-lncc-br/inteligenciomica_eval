# M6_TAREFA-601_G — Auditoria final do prompt corrigido

**Data**: 2026-06-02
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: code-reviewer, test-engineer
**Base auditada**: working tree atual sobre `origin/main`
**Status final**: **PASS**

## Objetivo

Auditar a implementação da `TAREFA-601` contra o prompt corrigido em
`docs/m6_tarefas_601_corrigido.md`, com foco nos novos critérios: única alteração
de produção autorizada em `final_score.py`, morte do `mutmut_12`, e
aceitabilidade dos sobreviventes restantes somente com prova formal registrada no
`mutation_report.txt`.

## Arquivos Inspecionados

- `docs/m6_tarefas_601_corrigido.md`
- `pyproject.toml`
- `.github/workflows/ci.yml`
- `scripts/mutation_gate.py`
- `src/inteligenciomica_eval/domain/services/final_score.py`
- `src/inteligenciomica_eval/domain/services/aggregation.py`
- `tests/unit/domain/services/test_final_score.py`
- `tests/unit/domain/services/test_rank_score.py`
- `tests/mutation/mutation_report.txt`
- `docs/dev-log/M6_TAREFA-601_F_prompt-corrigido-tolerancia-2pow30.md`

## Resultado Executivo

A implementação atual atende ao prompt corrigido:

- Há exatamente **uma** alteração de produção, em
  `src/inteligenciomica_eval/domain/services/final_score.py`.
- `_WEIGHTS_TOLERANCE` foi alterado para `2**-30` com comentário justificando a
  fronteira observável e a morte do `mutmut_12`.
- O teste de fronteira foi adicionado e referencia explicitamente `mutmut_12`.
- O `mutation_report.txt` mostra **263** mutantes, **244** mortos,
  **19** sobreviventes e **92.8%** de mutation score.
- `mutmut_12` não aparece entre os sobreviventes e é explicitamente registrado
  como **MORTO** no relatório.
- Os 19 sobreviventes remanescentes têm prova formal registrada no relatório;
  nenhuma divergência material foi encontrada nessas provas.

## Validações

### 1. Única alteração de produção autorizada

- `git diff --name-only` mostra somente:
  - `src/inteligenciomica_eval/domain/services/final_score.py`
  - `tests/mutation/mutation_report.txt`
  - `tests/unit/domain/services/test_final_score.py`
- Em `final_score.py`, a alteração autorizada está em:
  - `src/inteligenciomica_eval/domain/services/final_score.py:14-15`
- O comentário exigido pelo prompt está presente:
  "dyadic exato → fronteira testável via Lema de Sterbenz (mata mutmut_12)".

### 2. Teste que mata o `mutmut_12`

- `tests/unit/domain/services/test_final_score.py:80-86` adiciona
  `test_construction_weights_sum_at_tolerance_boundary_is_accepted`.
- O comentário cita explicitamente:
  `# mata mutmut_12: fronteira de tolerância observável (2**-30)`.
- O caso constrói soma `1.0 + 2**-30` e valida o comportamento de fronteira
  exigido pelo prompt corrigido.

### 3. Mutation report

- `tests/mutation/mutation_report.txt:1-15` está presente e parsável.
- Score exato lido do artefato: **92.8%**.
- Totais lidos:
  - `Total mutants  : 263`
  - `Killed         : 244`
  - `Survived       : 19`
  - `Gate           : PASS`

### 4. `mutmut_12` morto

- `tests/mutation/mutation_report.txt:306-308` registra explicitamente:
  `mutmut_12 (...) foi MORTO pela troca de _WEIGHTS_TOLERANCE=1e-9 para
  _WEIGHTS_TOLERANCE=2**-30 e pelo teste
  test_construction_weights_sum_at_tolerance_boundary_is_accepted.`
- O mutante `final_score.__init____mutmut_12` não aparece na lista de
  sobreviventes.

### 5. Provas formais dos sobreviventes

- O relatório contém seção dedicada:
  `Equivalence Proofs for Surviving Mutants`
  em `tests/mutation/mutation_report.txt:311-432`.
- Categorias auditadas:
  - `float("NAN")` vs `float("nan")`: `:318-328`
  - `statistics.quantiles(..., n=4)` default: `:331-339`
  - ramos inalcançáveis em `_win_rates`: `:342-355`
  - conteúdo de mensagens de exceção: `:358-371`
  - `typing.cast` como no-op runtime: `:374-383`
  - guarda `or→and` em `rank_score.compute`: `:386-409`
  - comparações em guarda NaN de `final_score.compute`: `:412-432`
- As provas são compatíveis com o código atual e suficientes para classificar os
  19 sobreviventes como aceitáveis sob o prompt corrigido.

### 6. Testes de reforço

- `tests/unit/domain/services/test_rank_score.py:89-91` mantém comentário
  `# reforçado:` para mutante de peso zero.
- `tests/unit/domain/services/test_rank_score.py:182-202` mantém comentário
  `# reforçado:` para mutantes de chave string.
- `tests/unit/domain/services/test_final_score.py:232-236` mantém comentário
  `# reforçado:` para `continue→break`.
- Os asserts permanecem específicos, com valores exatos (`0.65`, `0.67`, etc.).

### 7. CI e gate script

- `pyproject.toml:153-160` configura corretamente o `mutmut`:
  target `domain/services`, `tests_dir`, `pytest -x`, sem `funnel.py`.
- `.github/workflows/ci.yml:104-137` mantém `mutation-gate` apenas para `main`
  ou `workflow_dispatch`.
- `scripts/mutation_gate.py:189-227`:
  - aborta em crash de `mutmut run`
  - retorna exit code `1` quando `score < 80%`
  - grava o relatório em `tests/mutation/mutation_report.txt`

## Validação DoD

| Gate | Resultado |
|---|---|
| `ruff` | ✅ `All checks passed!` |
| `mypy --strict src` | ✅ `Success: no issues found in 50 source files` |
| `import-linter` | ✅ `Contracts: 4 kept, 0 broken.` |
| Type hints em `mutation_gate.py` | ✅ Presentes |

## Critérios de Aceitação

| Critério | Status | Evidência |
|---|---|---|
| 1. `[tool.mutmut]` aponta para `domain/services` e `tests/unit/domain/services`, sem `funnel.py` | ✅ PASS | `pyproject.toml:153-160` |
| 2. `mutation_report.txt` existe, é parsável e mostra score ≥ 80% | ✅ PASS | `tests/mutation/mutation_report.txt:1-15` mostra **92.8%** |
| 3. Sobreviventes em lógica aritmética/comparação só passam com prova formal; `mutmut_12` deve estar morto | ✅ PASS | `tests/mutation/mutation_report.txt:306-432` |
| 4. Testes de reforço referenciam mutantes e usam asserts específicos | ✅ PASS | `tests/unit/domain/services/test_final_score.py:80-86,232-236`; `tests/unit/domain/services/test_rank_score.py:89-91,182-202` |
| 5. CI step `mutation-gate` existe e roda apenas em `main` ou `workflow_dispatch` | ✅ PASS | `.github/workflows/ci.yml:104-137` |
| 6. `mutation_gate.py` falha quando score < 80% e gera artefato corretamente | ✅ PASS | `scripts/mutation_gate.py:182-229` |
| 7. A alteração em `final_score.py` é a única mudança de produção e justifica `2**-30` | ✅ PASS | `src/inteligenciomica_eval/domain/services/final_score.py:14-15`; `git diff --name-only` |
| 8. DoD §14.2: type hints, `ruff`, `mypy`, `import-linter` | ✅ PASS | gates conferidos nesta auditoria |

## Tabela de Divergências

Nenhuma divergência bloqueadora ou importante encontrada.

## Conclusão

Com a correção do prompt e a implementação atual, a `TAREFA-601` atende aos
critérios de auditoria. O score de mutação é **92.8%**, `mutmut_12` está morto,
e os sobreviventes restantes estão formalmente justificados no relatório. A
entrega está apta para `add/commit`.
