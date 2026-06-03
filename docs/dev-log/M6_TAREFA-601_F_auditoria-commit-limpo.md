# M6_TAREFA-601_F — Auditoria do commit limpo `bc878cf`

**Data**: 2026-06-02
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: code-reviewer, test-engineer
**Commit auditado**: `bc878cf`
**Status final**: **FAIL**

## Objetivo

Auditar o commit `bc878cf` contra o prompt `M6-601B`, verificando se o histórico
foi saneado para um diff sem produção, se os entregáveis exigidos estão
presentes e se o artefato `tests/mutation/mutation_report.txt` não deixa
sobreviventes bloqueadores conforme a letra do item 3.

## Arquivos Inspecionados

- `docs/m6_tarefas_601.md`
- `pyproject.toml`
- `.github/workflows/ci.yml`
- `scripts/mutation_gate.py`
- `tests/mutation/mutation_report.txt`
- `tests/unit/domain/services/test_final_score.py`
- `tests/unit/domain/services/test_rank_score.py`
- `docs/dev-log/M6_TAREFA-601_A_mutation-testing-domain-services.md`
- `docs/dev-log/M6_TAREFA-601_B_auditoria-mutation-testing-domain-services.md`
- `docs/dev-log/M6_TAREFA-601_C_correcao-producao-e-equivalencia.md`
- `docs/dev-log/M6_TAREFA-601_D_reauditoria-reversao-producao-equivalencia.md`

## Resultado Executivo

O commit `bc878cf` corrige o problema de escopo do item 7:

- `git show --name-only --format= bc878cf` contém apenas `pyproject.toml`,
  `.gitignore`, `scripts/`, `tests/`, `.github/` e `docs/dev-log/`.
- `git diff --name-only origin/main..bc878cf` não mostra nenhum arquivo em
  `src/`.

Mesmo assim, o commit continua **FAIL** porque o artefato
`tests/mutation/mutation_report.txt` ainda registra um sobrevivente de
comparação `>`→`>=` em `final_score.py`, e o item 3 do prompt `M6-601B`
classifica explicitamente sobreviventes em comparações `<`, `>`, `<=`, `>=`
como bloqueadores.

## Achados

### 1. Bloqueador — sobrevivente remanescente em comparação de `final_score.py`

- **Evidência**:
  - `tests/mutation/mutation_report.txt:220-232`
  - O mutante `inteligenciomica_eval.domain.services.final_score.xǁFinalScoreCalculatorǁ__init____mutmut_12`
    sobrevive alterando:
    `if abs(total - 1.0) > _WEIGHTS_TOLERANCE`
    para
    `if abs(total - 1.0) >= _WEIGHTS_TOLERANCE`
- **Impacto**: o item 3 do prompt B é literal ao tratar sobreviventes em
  comparações de `final_score.py`, `rank_score.py` ou `aggregation.py` como
  bloqueadores.

## Verificações que passaram

### 1. Escopo do commit

- `git show --name-only --format= bc878cf` lista somente:
  `.github/workflows/ci.yml`, `.gitignore`, `docs/dev-log/...`,
  `pyproject.toml`, `scripts/mutation_gate.py`,
  `tests/mutation/mutation_report.txt`,
  `tests/unit/domain/services/test_final_score.py`,
  `tests/unit/domain/services/test_rank_score.py`.
- O critério 7 do prompt está atendido no sentido estrito do diff:
  nenhum arquivo de produção foi alterado.

### 2. Configuração `mutmut`

- `pyproject.toml:153-160` aponta para
  `src/inteligenciomica_eval/domain/services/` e
  `tests/unit/domain/services/`.
- `pytest_add_cli_args = ["-x", "-q", "--no-header"]`.
- `funnel.py` não consta do alvo.

### 3. Relatório de mutação

- `tests/mutation/mutation_report.txt:1-15` está presente e parsável.
- Score exato lido: **92.4%**.
- Totais: **263** mutantes, **243** mortos, **20** sobreviventes.

### 4. Testes de reforço

- `tests/unit/domain/services/test_final_score.py:221-236` contém comentário
  `# reforçado:` e assert exato `0.65`.
- `tests/unit/domain/services/test_rank_score.py:88-91` contém comentário
  `# reforçado:` para peso zero.
- `tests/unit/domain/services/test_rank_score.py:181-202` contém comentário
  `# reforçado:` e assert exato `0.67`.

### 5. CI e gate script

- `.github/workflows/ci.yml:8` declara `workflow_dispatch`.
- `.github/workflows/ci.yml:104-137` define `mutation-gate` apenas para `push`
  em `main` ou disparo manual.
- `scripts/mutation_gate.py:189-197` aborta em crash do `mutmut run`.
- `scripts/mutation_gate.py:223-227` retorna exit code `1` se o score ficar
  abaixo de `80%`.

## Validação DoD

| Gate | Resultado |
|---|---|
| `ruff` | ✅ `All checks passed!` |
| `mypy --strict src` | ✅ `Success: no issues found in 50 source files` |
| `import-linter` | ⚠️ Rerrodagem local falhou por `Read-only file system (os error 30)` neste sandbox |
| Type hints em `mutation_gate.py` | ✅ Presentes em `scripts/mutation_gate.py:24-233` |

## Critérios de Aceitação

| Critério | Status | Evidência |
|---|---|---|
| 1. `[tool.mutmut]` aponta para `domain/services` e `tests/unit/domain/services`, sem `funnel.py` | ✅ PASS | `pyproject.toml:153-160` |
| 2. `mutation_report.txt` existe, é parsável e mostra score ≥ 80% | ✅ PASS | `tests/mutation/mutation_report.txt:1-15` mostra **92.4%** |
| 3. Nenhum sobrevivente em linha aritmética/comparação de `final_score.py`, `rank_score.py` ou `aggregation.py` | ❌ FAIL | `tests/mutation/mutation_report.txt:220-232` mostra `>`→`>=` sobrevivente em `final_score.py` |
| 4. Testes de reforço referenciam mutantes e usam asserts específicos | ✅ PASS | `tests/unit/domain/services/test_final_score.py:221-236`, `tests/unit/domain/services/test_rank_score.py:88-91`, `tests/unit/domain/services/test_rank_score.py:181-202` |
| 5. CI step `mutation-gate` existe e roda apenas em `main` ou `workflow_dispatch` | ✅ PASS | `.github/workflows/ci.yml:104-137` |
| 6. `mutation_gate.py` falha quando score < 80% e gera artefato corretamente | ✅ PASS | `scripts/mutation_gate.py:182-229` |
| 7. Nenhum código de produção alterado | ✅ PASS | `git diff --name-only origin/main..bc878cf` sem `src/` |
| 8. DoD §14.2: type hints, `ruff`, `mypy`, `import-linter` | ⚠️ PARCIAL | `ruff` e `mypy` conferidos; `import-linter` não pôde ser rerrodado neste sandbox |

## Tabela de Divergências

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| Sobrevivente em comparação `>`→`>=` em `FinalScoreCalculator.__init__` | `tests/mutation/mutation_report.txt:220-232` | BLOQUEADOR |

## Conclusão

O commit `bc878cf` finalmente atende ao requisito de escopo e deixa o diff
limpo de produção. Ainda assim, pela letra do item 3 do `M6-601B`, a tarefa
permanece **FAIL** porque o artefato de mutação commitado contém um sobrevivente
em operador de comparação dentro de `final_score.py`.
