# M6_TAREFA-601_B — Reauditoria Mutation Testing em `domain/services`

**Data**: 2026-06-02
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: code-reviewer, test-engineer
**Commit auditado**: `06899cb`
**Status final**: **FAIL**

## Objetivo

Reauditar a `TAREFA-601A` contra o prompt `M6-601B` após o ciclo de correção
B→A, verificando a configuração do mutmut, o relatório commitado, os testes de
reforço, o gate de CI e o cumprimento do DoD sem reescrever a solução.

## Arquivos Inspecionados

- `docs/m6_tarefas_601.md`
- `pyproject.toml`
- `scripts/mutation_gate.py`
- `.github/workflows/ci.yml`
- `tests/mutation/mutation_report.txt`
- `tests/unit/domain/services/test_final_score.py`
- `tests/unit/domain/services/test_rank_score.py`
- `src/inteligenciomica_eval/domain/services/final_score.py`
- `src/inteligenciomica_eval/domain/services/rank_score.py`
- `src/inteligenciomica_eval/domain/services/aggregation.py`

## Resultado Executivo

O gate funcional de mutation testing foi corrigido:

- `tests/mutation/mutation_report.txt:8-14` mostra **249** mutantes, **236**
  mortos, **13** sobreviventes e **94.8%** de mutation score.
- Não há mais sobreviventes em operadores aritméticos ou comparações de
  `final_score.py`, `rank_score.py` ou `aggregation.py`.
- `scripts/mutation_gate.py:181-188` agora aborta quando `mutmut run` termina
  com código `>= 2`.
- `.github/workflows/ci.yml:7` declara `workflow_dispatch`.

Mesmo assim, o prompt `M6-601B` continua **FAIL** porque o critério 7 exige que
esta tarefa não altere código de produção, e o commit `06899cb` modifica
arquivos em `src/`.

## Achados

### 1. Bloqueador — houve alteração de código de produção, vedada pelo prompt

- **Evidência de escopo**: `docs/m6_tarefas_601.md:116-117` diz
  "Esta tarefa NÃO altera código de produção" e `docs/m6_tarefas_601.md:218-219`
  exige "Nenhum código de produção alterado".
- **Arquivos alterados no commit**: `git show --name-only --format= 06899cb`
  inclui `src/inteligenciomica_eval/domain/services/final_score.py` e
  `src/inteligenciomica_eval/domain/services/rank_score.py`.
- **Linhas afetadas**:
  - `src/inteligenciomica_eval/domain/services/final_score.py:14`
  - `src/inteligenciomica_eval/domain/services/final_score.py:95-99`
  - `src/inteligenciomica_eval/domain/services/rank_score.py:112-114`
  - `src/inteligenciomica_eval/domain/services/rank_score.py:133-139`
- **Impacto**: mesmo que as mudanças sejam tecnicamente defensáveis e tenham
  eliminado mutantes críticos, o prompt B pede auditoria de conformidade com o
  escopo da tarefa. Neste critério, o commit não passa.

## Verificações que passaram

### Mutation report

- `tests/mutation/mutation_report.txt:1-14` está presente e parsável.
- O score exato lido do artefato é **94.8%**.
- Os 13 sobreviventes remanescentes aparecem em:
  - `aggregation.py` com variantes equivalentes de `float("nan")` e chamada a
    `statistics.quantiles(..., n=4)` cujo `n=4` é o default visível no diff do
    mutante (`tests/mutation/mutation_report.txt:18-122`).
  - `final_score.py` e `rank_score.py` apenas em payload de exceção/cast/NaN
    canônico, sem alteração de fórmula ou de comparação
    (`tests/mutation/mutation_report.txt:124-214`).

### Testes de reforço

- `tests/unit/domain/services/test_final_score.py:230-246` contém comentário
  `# reforçado:` e assert de valor exato `0.65`.
- `tests/unit/domain/services/test_rank_score.py:87-92` contém comentário
  `# reforçado:` para validação de peso zero.
- `tests/unit/domain/services/test_rank_score.py:181-202` contém comentário
  `# reforçado:` e assert exato `0.67`.

### Gate script e CI

- `scripts/mutation_gate.py:211-219` retorna exit code `1` quando o score fica
  abaixo de `80%`.
- `scripts/mutation_gate.py:181-188` aborta com exit code `2` em crash do
  `mutmut run`, evitando leitura de cache antigo.
- `.github/workflows/ci.yml:7` declara `workflow_dispatch`.
- `.github/workflows/ci.yml:84-87` mantém o job `mutation-gate` restrito a
  `push` em `main` ou disparo manual, não em cada PR.
- `.github/workflows/ci.yml:106-112` publica
  `tests/mutation/mutation_report.txt` como artefato.

## Validação DoD

| Gate | Resultado |
|---|---|
| `ruff` | ✅ `All checks passed!` |
| `mypy --strict src` | ✅ `Success: no issues found in 50 source files` |
| `import-linter` | ⚠️ Rerrodagem local falhou por `Read-only file system (os error 30)` neste ambiente de auditoria |
| Type hints em `mutation_gate.py` | ✅ Presentes em `scripts/mutation_gate.py:27-170` |

## Critérios de Aceitação

| Critério | Status | Evidência |
|---|---|---|
| 1. `[tool.mutmut]` aponta para `domain/services` e `tests/unit/domain/services`, sem `funnel.py` | ✅ PASS | `pyproject.toml:153-160` |
| 2. `mutation_report.txt` existe, é parsável e mostra score ≥ 80% | ✅ PASS | `tests/mutation/mutation_report.txt:1-14` mostra **94.8%** |
| 3. Nenhum sobrevivente em lógica aritmética/comparações de scoring/ranking | ✅ PASS | Sobreviventes remanescentes em `tests/mutation/mutation_report.txt:18-214` não alteram fórmula/comparação |
| 4. Testes de reforço referenciam mutantes e usam asserts específicos | ✅ PASS | `tests/unit/domain/services/test_final_score.py:230-246`, `tests/unit/domain/services/test_rank_score.py:87-92`, `tests/unit/domain/services/test_rank_score.py:181-202` |
| 5. CI step `mutation-gate` existe e roda apenas em `main` ou `workflow_dispatch` | ✅ PASS | `.github/workflows/ci.yml:7`, `.github/workflows/ci.yml:84-87` |
| 6. `mutation_gate.py` falha quando score < 80% e gera artefato corretamente | ✅ PASS | `scripts/mutation_gate.py:181-219` |
| 7. Nenhum código de produção alterado | ❌ FAIL | `git show --name-only --format= 06899cb` inclui `src/.../final_score.py` e `src/.../rank_score.py` |
| 8. DoD §14.2: type hints, `ruff`, `mypy`, `import-linter` | ⚠️ PARCIAL | `ruff` e `mypy` conferidos; `import-linter` não pôde ser rerrodado neste sandbox |

## Tabela de Divergências

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| Alteração de código de produção em tarefa explicitamente restrita a testes/configuração | `docs/m6_tarefas_601.md:116-117` | BLOQUEADOR |
| Alteração de código de produção em desacordo com o item 7 do prompt B | `docs/m6_tarefas_601.md:218-219` | BLOQUEADOR |
| Mudanças efetivas em produção no commit auditado | `src/inteligenciomica_eval/domain/services/final_score.py:14` | BLOQUEADOR |
| Mudanças efetivas em produção no commit auditado | `src/inteligenciomica_eval/domain/services/final_score.py:95-99` | BLOQUEADOR |
| Mudanças efetivas em produção no commit auditado | `src/inteligenciomica_eval/domain/services/rank_score.py:112-114` | BLOQUEADOR |
| Mudanças efetivas em produção no commit auditado | `src/inteligenciomica_eval/domain/services/rank_score.py:133-139` | BLOQUEADOR |

## Conclusão

O ciclo B→A resolveu os bloqueadores funcionais da auditoria anterior e elevou o
gate para **94.8%** com sobreviventes remanescentes compatíveis com equivalência
ou detalhes não aritméticos. Ainda assim, pela letra do `M6-601B`, a tarefa
permanece **FAIL** porque `06899cb` alterou código de produção em `src/`, e esse
tipo de mudança foi explicitamente proibido para a `TAREFA-601`.
