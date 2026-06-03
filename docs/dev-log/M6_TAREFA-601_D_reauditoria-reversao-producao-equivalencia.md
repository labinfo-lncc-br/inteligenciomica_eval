# M6_TAREFA-601_D — Reauditoria da reversão de produção e tese de equivalência

**Data**: 2026-06-02
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: code-reviewer, test-engineer
**Base de comparação**: working tree atual vs commit `06899cb`
**Status final**: **FAIL**

## Objetivo

Auditar o estado atual do working tree informado pelo desenvolvedor após a
reversão das mudanças em produção, verificando se a nova proposta elimina a
não conformidade do prompt `M6-601B` sem reabrir bloqueadores funcionais.

## Arquivos Inspecionados

- `docs/m6_tarefas_601.md`
- `pyproject.toml`
- `.github/workflows/ci.yml`
- `scripts/mutation_gate.py`
- `src/inteligenciomica_eval/domain/services/final_score.py`
- `src/inteligenciomica_eval/domain/services/rank_score.py`
- `tests/unit/domain/services/test_final_score.py`
- `tests/mutation/mutation_report.txt`
- `docs/dev-log/M6_TAREFA-601_A_mutation-testing-domain-services.md`

## Resultado Executivo

O working tree atual volta o comportamento de produção para a linha de base de
`a0338dd` e preserva os acertos infraestruturais de `06899cb`:

- `tests/mutation/mutation_report.txt:8-14` mostra **263** mutantes,
  **243** mortos, **20** sobreviventes e **92.4%** de mutation score.
- `pyproject.toml:153-160`, `.github/workflows/ci.yml:104-124` e
  `scripts/mutation_gate.py:189-227` continuam conformes com o prompt.
- `ruff` e `mypy --strict src` seguem verdes neste estado.

Mesmo assim, o diff proposto para commit continua **FAIL** no item 7 do prompt
`M6-601B`, porque ele ainda altera arquivos de produção em `src/`. O fato de o
conteúdo final coincidir com um commit anterior não muda a natureza do diff do
PR: ele contém modificações em produção.

## Achados

### 1. Bloqueador — o diff proposto continua alterando código de produção

- **Prompt**:
  - `docs/m6_tarefas_601.md:116-117` — "Esta tarefa NÃO altera código de produção"
  - `docs/m6_tarefas_601.md:226-227` — item 7: "Nenhum código de produção alterado"
- **Diff real do working tree**:
  - `src/inteligenciomica_eval/domain/services/final_score.py:14`
  - `src/inteligenciomica_eval/domain/services/final_score.py:95-99`
  - `src/inteligenciomica_eval/domain/services/rank_score.py:120-126`
- **Impacto**: a proposta segue incompatível com o escopo da `TAREFA-601` tal
  como escrito. O PR até pode restaurar o estado antigo de produção, mas ainda
  é um PR que mexe em produção.

## Verificações que passaram

### 1. Configuração `mutmut`

- `pyproject.toml:153-160` aponta para
  `src/inteligenciomica_eval/domain/services/` e
  `tests/unit/domain/services/`.
- O runner efetivo mantém `-x` em `pytest_add_cli_args`.
- `funnel.py` não consta do target.

### 2. Relatório de mutação

- `tests/mutation/mutation_report.txt:1-14` está presente e parsável.
- O score exato lido do artefato é **92.4%**.

### 3. Sobreviventes remanescentes

- Os sobreviventes em `aggregation.py` seguem sendo variantes equivalentes ou de
  materialização de `NaN`/default de API:
  `tests/mutation/mutation_report.txt:18-122`.
- Em `final_score.py`, os sobreviventes remanescentes são:
  - payload de exceção `reason=None`:
    `tests/mutation/mutation_report.txt:124-136`
  - comparação `>`→`>=` na tolerância:
    `tests/mutation/mutation_report.txt:138-149`
  - payload de exceção `tolerance=None` / omitido:
    `tests/mutation/mutation_report.txt:151-169`
- Em `rank_score.py`, os sobreviventes remanescentes são:
  - payload de exceção `reason=None`:
    `tests/mutation/mutation_report.txt:90-102`
  - guarda de `NaN` com mutações `or`→`and`:
    `tests/mutation/mutation_report.txt:104-148`
  - `float("nan")`→`float("NAN")`:
    `tests/mutation/mutation_report.txt:150-160`

### 4. Testes de reforço

- `tests/unit/domain/services/test_final_score.py:221-236` mantém comentário
  `# reforçado:` e assert de valor exato `0.65`.
- A remoção do teste de fronteira baseado em `2**-30` é coerente com a reversão
  do `_WEIGHTS_TOLERANCE` para `1e-9`.

### 5. CI e gate script

- `.github/workflows/ci.yml:8` declara `workflow_dispatch`.
- `.github/workflows/ci.yml:109-111` restringe `mutation-gate` a `push` em
  `main` ou disparo manual.
- `scripts/mutation_gate.py:192-197` continua abortando quando `mutmut run`
  falha com código `>= 2`.
- `scripts/mutation_gate.py:223-227` continua retornando exit code `1` quando o
  score fica abaixo do limiar.

## Validação DoD

| Gate | Resultado |
|---|---|
| `ruff` | ✅ `All checks passed!` |
| `mypy --strict src` | ✅ `Success: no issues found in 50 source files` |
| `import-linter` | ⚠️ Não rerrodado nesta reauditoria; limitação operacional anterior do sandbox permanece |
| Type hints em `mutation_gate.py` | ✅ Presentes |

## Critérios de Aceitação

| Critério | Status | Evidência |
|---|---|---|
| 1. `[tool.mutmut]` aponta para `domain/services` e `tests/unit/domain/services`, sem `funnel.py` | ✅ PASS | `pyproject.toml:153-160` |
| 2. `mutation_report.txt` existe, é parsável e mostra score ≥ 80% | ✅ PASS | `tests/mutation/mutation_report.txt:1-14` mostra **92.4%** |
| 3. Sobreviventes em linhas aritméticas/comparações de scoring | ⚠️ DISCUTÍVEL | Há `>`→`>=` em `final_score.py` no relatório (`tests/mutation/mutation_report.txt:138-149`), mas o desenvolvedor o classifica como equivalente/guard; o prompt não fornece exceção explícita para comparação de tolerância |
| 4. Testes de reforço referenciam mutantes e usam asserts específicos | ✅ PASS | `tests/unit/domain/services/test_final_score.py:221-236` |
| 5. CI step `mutation-gate` existe e roda apenas em `main` ou `workflow_dispatch` | ✅ PASS | `.github/workflows/ci.yml:8`, `.github/workflows/ci.yml:109-111` |
| 6. `mutation_gate.py` falha quando score < 80% e gera artefato corretamente | ✅ PASS | `scripts/mutation_gate.py:189-227` |
| 7. Nenhum código de produção alterado | ❌ FAIL | `final_score.py` e `rank_score.py` aparecem no diff atual vs `06899cb` |
| 8. DoD §14.2: type hints, `ruff`, `mypy`, `import-linter` | ⚠️ PARCIAL | `ruff` e `mypy` conferidos; `import-linter` não rerrodado |

## Tabela de Divergências

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| O diff proposto continua alterando produção em tarefa explicitamente restrita a testes/configuração | `docs/m6_tarefas_601.md:116-117` | BLOQUEADOR |
| O item 7 do prompt B continua não atendido porque o diff toca `src/` | `docs/m6_tarefas_601.md:226-227` | BLOQUEADOR |
| Reversão em produção ainda é alteração de produção no PR | `src/inteligenciomica_eval/domain/services/final_score.py:14` | BLOQUEADOR |
| Reversão em produção ainda é alteração de produção no PR | `src/inteligenciomica_eval/domain/services/final_score.py:95-99` | BLOQUEADOR |
| Reversão em produção ainda é alteração de produção no PR | `src/inteligenciomica_eval/domain/services/rank_score.py:120-126` | BLOQUEADOR |

## Conclusão

Pela letra do prompt `M6-601B`, a proposta permanece **FAIL**. A reversão limpa o
estado final de produção, mas não resolve o problema de conformidade do PR:
continuam existindo modificações em `src/` no diff a ser commitado. Se o objetivo
for obter `PASS` estrito neste prompt, o próximo diff precisa conter apenas
configuração, script, testes, CI e relatório, sem qualquer arquivo de produção.
