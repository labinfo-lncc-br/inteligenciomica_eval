# M0_TAREFA-001_B — Reauditoria do Bootstrap do Repositório

**Data**: 2026-05-23  
**Milestone**: M0 — Fundação  
**Épico**: E0  
**Skill**: code-reviewer + test-engineer  
**Prioridade / Tamanho**: P0 / S  
**Dependências**: M0_TAREFA-001_A  
**Camada**: tooling  

---

## Objetivo

Reauditar a TAREFA-001 após as correções registradas em
`docs/dev-log/M0_TAREFA-001_A_bootstrap-repositorio.md`, usando como baseline:

- `docs/arquitetura_detalhada_validacao_inteligenciomica.md`
- `CLAUDE.md`
- checklist do `prompt_M001B`

Sem reescrever a implementação; apenas verificar se as divergências apontadas anteriormente
foram de fato corrigidas.

---

## Veredito

**PASS**

Os bloqueadores do relatório anterior foram resolvidos:

1. `uv sync --frozen` agora produz um ambiente que executa `lint-imports` e `pytest -n auto`
   sem depender de `--all-extras`.
2. O `.importlinter` agora cobre a lista canônica de libs proibidas e adiciona um contrato
   `layers` coerente com a regra "application só importa domain" registrada em `CLAUDE.md`.

Permanece uma divergência **importante**, mas não bloqueadora: as dependências do
`pyproject.toml` continuam com limites mínimos (`>=`) em vez de pins estritos.

---

## Checagem Item a Item

### 1. Layout `src` bate com §8? `__init__.py` presentes?

**PASS**

- `src/inteligenciomica_eval/` contém `domain/`, `application/`, `infrastructure/`,
  `visualization/` e `cli.py`.
- `tests/unit/domain/`, `tests/unit/application/` e `tests/integration/adapters/` existem.
- `config/` e `docs/adr/` existem.
- Os `__init__.py` esperados estão presentes.

### 2. `pyproject`: Python 3.11+, entry point `ielm-eval`, deps runtime/dev pinadas, markers pytest?

**FAIL parcial**

- `requires-python = ">=3.11"` está correto.
- O entry point `ielm-eval = "inteligenciomica_eval.cli:app"` está correto.
- Os markers `unit`, `integration` e `e2e` estão registrados.
- A migração para `[dependency-groups].dev` foi realizada.
- `mutmut` foi adicionado ao grupo `dev`.
- As dependências continuam com `>=`, não com pins estritos.

### 3. `mypy` strict em `src`? coverage com `branch=true` e `fail_under=85`?

**PASS**

- `mypy` está em modo strict para `src`.
- Coverage está com `branch = true` e `fail_under = 85`.

### 4. `.importlinter` tem os contratos exigidos, lista canônica de libs proibidas e `root_package` correto?

**PASS**

- `root_package = inteligenciomica_eval` está correto.
- Há 3 contratos `forbidden`, conforme o checklist original.
- A lista canônica de libs proibidas foi ampliada com `qdrant_client`, `openai`, `ragas`,
  `deepeval` e `statsmodels`.
- Há também 1 contrato adicional do tipo `layers`, alinhado ao `CLAUDE.md` atual e coerente
  com a exigência "application só importa domain".

### 5. CI roda, na ordem, `ruff check`, `ruff format --check`, `mypy --strict`, `lint-imports`, `pytest` com cobertura e `-n auto`?

**PASS**

- A ordem no workflow está correta.
- Todos os comandos executaram com sucesso no ambiente padrão criado por `uv sync --frozen`.

### 6. CLI: `--help`, `version`, `KeyboardInterrupt` tratado? Smoke test cobre isso?

**PASS**

- `uv run ielm-eval --help` funciona.
- `uv run ielm-eval version` funciona.
- `KeyboardInterrupt` é tratado em `main()`.
- O smoke test cobre explicitamente a saída com código `130`.

### 7. DoD §14.2 integralmente?

**PASS parcial**

- `from __future__ import annotations`: OK nos módulos Python auditados.
- Type hints em APIs públicas do escopo entregue: OK.
- Docstrings no escopo entregue: OK.
- Sem segredos hardcoded: OK.
- Gates `ruff`, `mypy`, `import-linter` e `pytest` passam.
- Testes cobrem happy path e o cenário de interrupção do CLI.
- A única pendência remanescente é a ausência de pins estritos no `pyproject.toml`.

---

## Tabela de Divergências

| Critério | Arquivo:linha | Gravidade | Divergência |
|---|---|---|---|
| Dependências de runtime e dev pinadas | `pyproject.toml:12` | importante | O documento arquitetural usa a convenção de deps com pin; o arquivo atual usa limites mínimos (`>=`) em runtime e dev, não pins estritos. |

---

## Comandos Executados

| Comando | Resultado |
|---|---|
| `uv sync --frozen` | ✅ `Checked 70 packages in 4ms` |
| `uv run ruff check .` | ✅ `All checks passed!` |
| `uv run ruff format --check .` | ✅ `22 files already formatted` |
| `uv run mypy --strict src` | ✅ `Success: no issues found in 11 source files` |
| `uv run lint-imports` | ✅ `4 kept, 0 broken` |
| `uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n auto` | ✅ `6 passed`, cobertura total `90.00%` |
| `uv run ielm-eval --help` | ✅ mostra grupo Typer com subcomando `version` |
| `uv run ielm-eval version` | ✅ imprime `inteligenciomica-eval 0.1.0` |

---

## Resumo Final

As correções registradas no documento A foram majoritariamente realizadas e os problemas
bloqueadores do relatório B anterior deixaram de existir no estado atual do repositório.

O bootstrap agora atende os gates operacionais da TAREFA-001 e, por isso, o veredito é
**PASS**.

A única divergência remanescente é de rigor de versionamento: o `pyproject.toml` ainda não usa
pins estritos para runtime e dev dependencies.
