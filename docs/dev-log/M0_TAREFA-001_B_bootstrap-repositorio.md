# M0_TAREFA-001_B — Verificação do Bootstrap do Repositório

**Data**: 2026-05-23  
**Milestone**: M0 — Fundação  
**Épico**: E0  
**Skill**: code-reviewer + test-engineer  
**Prioridade / Tamanho**: P0 / S  
**Dependências**: M0_TAREFA-001_A  
**Camada**: tooling  

---

## Objetivo

Auditar o diff da TAREFA-001 contra `docs/arquitetura_detalhada_validacao_inteligenciomica.md`,
`CLAUDE.md`, DoD §14.2, nota de operacionalização do fluxo dev↔verify e critérios do prompt
de verificação, sem reescrever a implementação.

---

## Escopo Auditado

- Diff entre `c721864` e `HEAD` (bootstrap do repositório).
- `docs/arquitetura_detalhada_validacao_inteligenciomica.md`:
  - §8 Estrutura de código detalhada
  - §11.6 CI
  - §14.2 DoD transversal
  - §14.3 TAREFA-001
  - §16.1–16.4 ciclo de verificação
- `CLAUDE.md`:
  - layout
  - ordem de validação
  - padrão de nome do dev log

---

## Veredito

**FAIL**

Há **2 bloqueadores** no bootstrap:

1. O workflow de CI não sobe um ambiente com o tooling de dev exigido pelos próprios passos.
2. O `.importlinter` não implementa integralmente a garantia arquitetural descrita no documento principal.

Sem resolver esses pontos, o PR não atende o critério "CI verde em repositório vazio" da
TAREFA-001 nem estabelece os contratos de camada prometidos pelo bootstrap.

---

## Checagem Item a Item

### 1. Layout `src` bate com §8? `__init__.py` presentes?

**FAIL parcial**

- As pastas-base existem em `src/inteligenciomica_eval/` e os `__init__.py` foram criados.
- `config/` e `docs/adr/` existem.
- O espelhamento de testes pedido em `tests/unit/{domain,application}/` e
  `tests/integration/adapters/` **não** foi criado; há apenas `tests/unit/` flat e
  `tests/integration/__init__.py`.

### 2. `pyproject`: Python 3.11+, entry point `ielm-eval`, deps runtime/dev pinadas, markers pytest?

**FAIL parcial**

- `requires-python = ">=3.11"` está correto.
- O entry point `ielm-eval = "inteligenciomica_eval.cli:app"` está correto.
- Os markers `unit`, `integration` e `e2e` estão registrados.
- As dependências não estão pinadas no `pyproject.toml`.
- A pilha de dev/test do documento inclui `mutmut`, mas ela não foi declarada.

### 3. `mypy` strict em `src`? coverage com `branch=true` e `fail_under=85`?

**PASS**

- `mypy` está com `strict = true`, `files = ["src"]`.
- Coverage está com `branch = true` e `fail_under = 85`.

### 4. `.importlinter` tem EXATAMENTE os 3 contratos forbidden descritos, com lista canônica de libs proibidas?

**FAIL**

- O arquivo tem exatamente 3 contratos `forbidden`.
- `root_package = inteligenciomica_eval` está correto.
- A lista implementada é **mais fraca** do que a arquitetura exige: faltam libs explicitamente
  citadas como proibidas fora de `infrastructure/adapters/`, como `qdrant_client`, `openai`,
  `ragas`, `deepeval` e `statsmodels`.
- O texto arquitetural também afirma que `application` "só importa domain", o que não é
  garantido pelos contratos atuais.

### 5. CI roda, na ordem, os gates pedidos?

**FAIL**

- A ordem no YAML está correta.
- Na execução real, `uv sync --frozen` não disponibiliza `lint-imports` nem `pytest-xdist`,
  então os passos seguintes falham no mesmo ambiente que a CI cria.

### 6. CLI: `--help`, `version`, `KeyboardInterrupt` tratado? Smoke test cobre isso?

**FAIL parcial**

- `uv run ielm-eval --help` funciona.
- `uv run ielm-eval version` funciona.
- `KeyboardInterrupt` é tratado no bloco `__main__`.
- O smoke test **não cobre** o caminho de interrupção.

### 7. DoD §14.2 integralmente?

**FAIL**

- `from __future__ import annotations`: OK nos módulos Python criados.
- Type hints na API pública: OK no escopo entregue.
- Docstrings públicas: OK no escopo entregue.
- Sem segredos hardcoded: OK.
- Testes happy+borda+erro: **não integral**; só há smoke tests de `help`/`version` e um teste
  de importação de namespaces.
- `ruff`/`mypy`: OK.
- `import-linter`/`pytest -n auto`: não passam no ambiente produzido por `uv sync --frozen`.

---

## Tabela de Divergências

| Critério | Arquivo:linha | Gravidade | Divergência |
|---|---|---|---|
| CI verde em repositório vazio | `.github/workflows/ci.yml:27` | bloqueador | O job instala o ambiente com `uv sync --frozen`, mas os próximos passos exigem ferramentas declaradas apenas em `optional-dependencies.dev`; no ambiente criado, `lint-imports` não existe e `pytest -n auto` falha por ausência de `pytest-xdist`. |
| Tooling de dev incompatível com os próprios comandos documentados | `pyproject.toml:26` | bloqueador | A separação atual entre runtime e `dev` torna inválido o fluxo afirmado no bootstrap: o ambiente padrão não contém todos os binários necessários para CI/README/dev log. |
| Garantia arquitetural de imports está incompleta | `.importlinter:13` | bloqueador | A arquitetura exige que `domain`/`application` não importem `qdrant_client`, `openai`, `ragas`, `deepeval` ou `statsmodels` fora de `infrastructure/adapters`, mas esses pacotes não aparecem em `forbidden_modules`. |
| `application` não está restrita a "só importa domain" | `.importlinter:28` | bloqueador | O documento principal declara essa garantia, mas o contrato atual apenas veda `infrastructure`, `cli` e algumas libs de I/O; imports third-party adicionais ainda passariam. |
| Estrutura de testes não espelha `src` como §8 pede | `tests/unit/test_cli_smoke.py:1` | importante | O layout esperado é `tests/unit/{domain,application}/` e `tests/integration/adapters/`; o PR entrega apenas `tests/unit/` flat e `tests/integration/__init__.py`. |
| Dependências não estão pinadas no `pyproject` | `pyproject.toml:12` | importante | O documento arquitetural pede deps com pin; o arquivo usa faixas soltas ou sem versão explícita em runtime e dev. |
| Dependência de tooling `mutmut` ausente | `pyproject.toml:27` | importante | A stack de dev/test do documento inclui `mutmut`, mas o bootstrap não a declara. |
| README instrui um fluxo que não funciona | `README.md:21` | importante | A seção "Development" afirma "Install with dev dependencies" usando `uv sync --frozen`, mas esse comando não instala o tooling que as linhas seguintes invocam (`lint-imports`, `pytest -n auto`). |
| Smoke test não cobre `KeyboardInterrupt` | `tests/unit/test_cli_smoke.py:15` | importante | O CLI trata interrupção em `src/inteligenciomica_eval/cli.py:35`, mas o teste de smoke cobre apenas `--help` e `version`, deixando o caminho de erro do bootstrap sem validação. |
| DoD de testes happy+borda+erro não foi atingido | `tests/unit/test_cli_smoke.py:15` | importante | Os testes entregues não cobrem cenário de erro nem borda relevante do CLI; `tests/unit/test_imports.py` só força cobertura estrutural. |
| Dev log A afirma validações que não reproduzem com `uv sync --frozen` | `docs/dev-log/M0_TAREFA-001_A_bootstrap-repositorio.md:159` | importante | O relatório registra `lint-imports` e `pytest` como verdes no fluxo principal, mas isso só ocorre após instalar extras; com o comando aceito pela CI/TAREFA-001, a reprodução falha. |
| Dev log A afirma "CI verde" sem sustentar o ambiente real da workflow | `docs/dev-log/M0_TAREFA-001_A_bootstrap-repositorio.md:171` | importante | O status reportado não bate com a execução reproduzida do workflow descrito no próprio PR. |
| Dev log A contém afirmação factualmente incorreta sobre `.gitignore` | `docs/dev-log/M0_TAREFA-001_A_bootstrap-repositorio.md:181` | sugestão | O texto diz que `.gitignore` não foi criado, mas o arquivo existe no PR. |

---

## Comandos Executados

### Ambiente padrão do bootstrap

| Comando | Resultado |
|---|---|
| `uv sync --frozen` | ✅ `Checked 24 packages in 2ms` |
| `uv run ruff check .` | ✅ `All checks passed!` |
| `uv run ruff format --check .` | ✅ `19 files already formatted` |
| `uv run mypy --strict src` | ✅ `Success: no issues found in 11 source files` |
| `uv run lint-imports` | ❌ `Failed to spawn: lint-imports` |
| `uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n auto` | ❌ `pytest: error: unrecognized arguments: -n` |
| `uv run pre-commit install` | ✅ `pre-commit installed at .git/hooks/pre-commit` |
| `uv run ielm-eval --help` | ✅ mostra grupo Typer com subcomando `version` |
| `uv run ielm-eval version` | ✅ imprime `inteligenciomica-eval 0.1.0` |

### Confirmação da causa raiz com extras

| Comando | Resultado |
|---|---|
| `uv sync --frozen --all-extras` | ✅ instalou 39 pacotes adicionais de tooling |
| `uv run lint-imports` | ✅ `3 kept, 0 broken` |
| `uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n auto` | ✅ `5 passed`, cobertura total `88.24%` |

**Conclusão operacional:** os comandos de validação funcionam **somente** após instalar os extras;
portanto o problema central não é o conteúdo dos testes/linters, mas a maneira como o bootstrap
monta o ambiente padrão e como a CI o reproduz.

---

## Resumo Final

O bootstrap está próximo do objetivo, mas ainda não cumpre integralmente a TAREFA-001.
Os dois bloqueadores são:

1. O ambiente criado por `uv sync --frozen` não sustenta a própria pipeline declarada.
2. O `.importlinter` entrega uma proteção de arquitetura mais fraca do que a especificação promete.

Enquanto esses pontos permanecerem, o veredito continua **FAIL**.
