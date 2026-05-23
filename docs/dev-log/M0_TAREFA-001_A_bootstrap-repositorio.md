# M0_TAREFA-001_A — Bootstrap do Repositório

**Data**: 2026-05-23  
**Milestone**: M0 — Fundação  
**Épico**: E0  
**Skill**: python-engineer  
**Prioridade / Tamanho**: P0 / S  
**Dependências**: nenhuma (raiz do DAG)  
**ADRs referenciados**: ADR-001, ADR-008  
**Camada**: tooling  
**Auditoria**: `M0_TAREFA-001_B` — corrigiu 2 bloqueadores e 5 itens importantes;
este documento reflete o **estado final** após as correções.

---

## Objetivo

Criar o esqueleto completo do repositório com todas as ferramentas de qualidade
configuradas e passando antes de qualquer código de domínio ser escrito:
`pyproject.toml`, `uv.lock`, layout `src/`, CLI mínima, testes de smoke,
CI, pre-commit e contratos de arquitetura via import-linter.

---

## Arquivos Criados / Modificados

### Novos

| Arquivo | Descrição |
|---------|-----------|
| `pyproject.toml` | Configuração central: build (hatchling), deps runtime + dev, ruff, mypy, pytest, coverage |
| `uv.lock` | Lock file gerado por `uv sync` (70 pacotes) |
| `CLAUDE.md` | Guia persistente de desenvolvimento para o Claude Code |
| `README.md` | Quickstart copy-paste |
| `.gitignore` | Ignora `.venv/`, `__pycache__/`, caches de ferramentas e artefatos de CI |
| `.importlinter` | 4 contratos de arquitetura (3 forbidden + 1 layers) |
| `.pre-commit-config.yaml` | Hooks: ruff-lint, ruff-format, mypy (local/system) |
| `.github/workflows/ci.yml` | Pipeline GitHub Actions com uv |
| `src/inteligenciomica_eval/__init__.py` | Expõe `__version__` via importlib.metadata |
| `src/inteligenciomica_eval/cli.py` | App Typer com `@app.callback()` + comando `version` + `main()` |
| `src/inteligenciomica_eval/domain/__init__.py` | Esqueleto camada domain |
| `src/inteligenciomica_eval/domain/services/__init__.py` | Esqueleto |
| `src/inteligenciomica_eval/application/__init__.py` | Esqueleto |
| `src/inteligenciomica_eval/infrastructure/__init__.py` | Esqueleto |
| `src/inteligenciomica_eval/infrastructure/adapters/__init__.py` | Esqueleto |
| `src/inteligenciomica_eval/infrastructure/repositories/__init__.py` | Esqueleto |
| `src/inteligenciomica_eval/infrastructure/prompts/__init__.py` | Esqueleto |
| `src/inteligenciomica_eval/infrastructure/config/__init__.py` | Esqueleto |
| `src/inteligenciomica_eval/visualization/__init__.py` | Esqueleto |
| `tests/conftest.py` | Fixtures compartilhadas (vazio no bootstrap) |
| `tests/unit/test_cli_smoke.py` | 5 testes de smoke para `--help`, `version` e `KeyboardInterrupt` |
| `tests/unit/test_imports.py` | 1 teste que importa todos os sub-pacotes (cobre esqueleto) |
| `tests/unit/__init__.py` | |
| `tests/unit/domain/__init__.py` | Espelha `src/domain/` |
| `tests/unit/application/__init__.py` | Espelha `src/application/` |
| `tests/integration/__init__.py` | |
| `tests/integration/adapters/__init__.py` | Espelha `src/infrastructure/adapters/` |
| `tests/e2e/__init__.py` | |
| `tests/fakes/__init__.py` | |
| `tests/factories/__init__.py` | |
| `tests/golden/.gitkeep` | Diretório para datasets de referência |
| `config/.gitkeep` | Diretório para configurações externas |
| `docs/adr/.gitkeep` | Diretório para ADRs |
| `docs/dev-log/` | Este diretório |

### Modificados durante execução

| Arquivo | Motivo |
|---------|--------|
| `src/inteligenciomica_eval/__init__.py` | Ruff auto-fix: split `from importlib.metadata import PackageNotFoundError, version as _pkg_version` em duas linhas (isort I001) |
| `src/inteligenciomica_eval/cli.py` | Adição de `_err_console` (mypy: `Console.print` sem kwarg `err=`); adição de `@app.callback()` (Typer single-command bug); extração de `main()` para testabilidade do `KeyboardInterrupt` |
| `pyproject.toml` | Adição de `pytest-cov`; migração de `[project.optional-dependencies]` para `[dependency-groups] dev` (PEP 735); adição de `mutmut`; pins de versão mínima em runtime e dev deps |

---

## Decisões Técnicas

### D1 — Build backend: hatchling
Escolhido por ser o padrão do ecossistema `uv` e ter suporte nativo a src layout
via `[tool.hatch.build.targets.wheel] packages = ["src/inteligenciomica_eval"]`.

### D2 — Entry point `cli:app` com `@app.callback()`
A especificação pede `ielm-eval = "inteligenciomica_eval.cli:app"`. Em Typer ≥ 0.9,
um app com um único `@app.command()` colapsa o subcomando, tornando `ielm-eval version`
inválido. Solução: adicionar `@app.callback()` com corpo-docstring antes do primeiro
`@app.command()` para forçar modo grupo (multi-subcomando). O entry point permanece
`cli:app` (o objeto `typer.Typer` é callable).

### D3 — KeyboardInterrupt: `main()` + `# pragma: no cover`
O bloco `if __name__ == "__main__":` nunca é executado via `CliRunner`. Solução em
duas partes: (a) extrair `main()` como função pública testável via `mocker.patch`
— cobre o caminho de `KeyboardInterrupt` com `sys.exit(130)`; (b) manter
`if __name__ == "__main__":` marcado com `# pragma: no cover`, chamando apenas
`main()`. O `exclude_lines` do coverage também exclui `if __name__ == .__main__.:`.

### D4 — Stderr via `Console(stderr=True)`
`rich.Console.print()` não tem kwarg `err=`. Para mensagens de erro/interrupção,
usa-se um segundo Console: `_err_console = Console(stderr=True)`.

### D5 — Cobertura de esqueleto via `test_imports.py`
Os `__init__.py` de esqueleto (1 statement cada) nunca seriam importados por outros
testes, mantendo coverage global abaixo de 85%. Solução: `tests/unit/test_imports.py`
importa explicitamente todos os sub-pacotes, garantindo que sejam instrumentados.

### D6 — mypy com `mypy_path = ["src"]`
Com src layout e instalação via `uv sync`, o mypy encontra o pacote pelo `.venv`.
O `mypy_path` é necessário para execução sem instalação prévia (ex: CI após checkout
antes do `uv sync`). Na prática, ambos funcionam após `uv sync`.

### D7 — pre-commit hook mypy via `language: system`
Usa `entry: uv run mypy --strict` com `language: system`. Isso requer que o `.venv`
esteja ativo/presente (após `uv sync`). Alternativa seria `language: python` com
`additional_dependencies`, mas isso duplicaria a gestão de dependências.

### D8 — Import-linter: `include_external_packages = True`
Necessário para que os contratos `forbidden` possam referenciar pacotes externos
(pandas, polars, pyarrow, etc.) e não apenas módulos internos do pacote.

### D9 — Dev deps em `[dependency-groups] dev` (PEP 735)
Dev deps declaradas em `[dependency-groups] dev` em vez de `[project.optional-dependencies]`.
Com `[dependency-groups]`, `uv sync --frozen` instala runtime + dev por padrão — a CI
não precisa de `--all-extras`. Usar `uv sync --no-dev` para ambientes de produção.
*(Corrição apontada pela auditoria B: com `optional-dependencies`, `uv sync --frozen`
não instalava o tooling e os passos de CI falhavam.)*

### D10 — Quatro contratos import-linter (3 forbidden + 1 layers)
Além dos 3 contratos `forbidden` da especificação, adicionado um contrato do tipo
`layers` que enforça a hierarquia estrita `domain < application < infrastructure`.
Isso garante que `application` só importe `domain` — garantia que os contratos
`forbidden` sozinhos não provêem. Os contratos `forbidden` também cobrem
`qdrant_client`, `openai`, `ragas`, `deepeval` e `statsmodels`.
*(Correção apontada pela auditoria B.)*

---

## Problemas Encontrados e Soluções

### P1 — Ruff I001: isort no `__init__.py`
**Sintoma**: `from importlib.metadata import PackageNotFoundError, version as _pkg_version`
foi rejeitado pela regra isort I001.  
**Causa**: ruff isort prefere uma importação por símbolo quando há alias.  
**Solução**: `uv run ruff check --fix .` auto-corrigiu para duas linhas separadas.

### P2 — mypy: `Console.print` sem kwarg `err`
**Sintoma**: `error: Unexpected keyword argument "err" for "print" of "Console"`.  
**Causa**: `rich.Console.print()` não aceita `err=True`. Para escrever em stderr,
Rich usa um objeto Console configurado com `stderr=True`.  
**Solução**: Criado `_err_console = Console(stderr=True)` separado.

### P3 — Typer 0.25: single-command collapse
**Sintoma**: `runner.invoke(app, ["version"])` retornava exit code 2 com
`Got unexpected extra argument (version)`. `--help` mostrava `Usage: version [OPTIONS]`
em vez de mostrar o grupo com subcomandos.  
**Causa**: Typer ≥ 0.9 colapsa o único `@app.command()` fazendo o app ser
diretamente o comando (sem nível de subcomando).  
**Solução**: Adicionado `@app.callback()` com docstring. Isso força Typer a criar
um "grupo" onde `version` é um subcomando nomeado.

### P4 — pytest --cov não reconhecido
**Sintoma**: `pytest: error: unrecognized arguments: --cov=src`.  
**Causa**: `coverage[toml]` instala apenas a lib `coverage`; o plugin pytest
(`pytest-cov`) é um pacote separado.  
**Solução**: Adicionado `"pytest-cov"` ao `[dependency-groups] dev`.

### P5 — Coverage 45% (abaixo do threshold 85%)
**Sintoma**: Após corrigir P3 e P4, coverage total era 45%.  
**Causa**: Os 9 `__init__.py` de esqueleto nunca eram importados durante os testes,
sendo contados como 0% cobertos cada (1 statement perdido cada).  
**Solução**: Criado `tests/unit/test_imports.py` que importa todos os sub-pacotes.

### P6 — `uv sync --frozen` não instalava tooling de dev
**Sintoma**: `lint-imports` e `pytest -n auto` falhavam no ambiente gerado pela CI.  
**Causa**: Dev deps declaradas em `[project.optional-dependencies] dev` não são
instaladas por `uv sync --frozen`; exigem `--all-extras`.  
**Solução** *(auditoria B)*: Migrar para `[dependency-groups] dev` (PEP 735) — passa a ser
instalado por padrão pelo `uv sync --frozen`.

### P7 — `.importlinter` com lista de libs proibidas incompleta
**Sintoma**: `qdrant_client`, `openai`, `ragas`, `deepeval`, `statsmodels` não constavam
em `forbidden_modules`; garantia "application só importa domain" ausente.  
**Causa**: Lista inicial derivada apenas das deps de runtime do `pyproject.toml`,
sem consultar a arquitetura detalhada do projeto.  
**Solução** *(auditoria B)*: Adicionadas as 5 libs; adicionado contrato `layers`.

---

## Validação (DoD §14.2)

| Check | Comando | Resultado |
|-------|---------|-----------|
| from \_\_future\_\_ | inspeção | ✅ todos os módulos |
| type hints | `mypy --strict src` | ✅ 0 errors, 11 source files |
| ruff lint | `uv run ruff check .` | ✅ All checks passed |
| ruff format | `uv run ruff format --check .` | ✅ 22 files formatted |
| import contracts | `uv run lint-imports` | ✅ 4 KEPT, 0 broken |
| pytest | `uv run pytest ... --cov-fail-under=85` | ✅ 6 passed, 90% |
| `uv sync --frozen` | instalação sem extras | ✅ 70 packages |
| sem segredos | inspeção | ✅ |

---

## Critérios de Aceitação (TAREFA-001)

| Critério | Status |
|----------|--------|
| `uv sync --frozen` funciona | ✅ |
| CI verde em repositório vazio | ✅ (workflow criado, gates passam localmente) |
| pre-commit hooks instaláveis (`pre-commit install`) | ✅ |
| `uv run ielm-eval --help` funciona | ✅ |
| `uv run ielm-eval version` funciona | ✅ imprime `inteligenciomica-eval 0.1.0` |
| `lint-imports` passa com 4 contratos | ✅ |

---

## Observações para Próximas Tarefas

1. **`.gitignore`** foi criado durante a execução desta tarefa, antes do commit inicial,
   cobrindo `.venv/`, `__pycache__/`, `.mypy_cache/`, `.ruff_cache/`, `.coverage` e `*.xml`.
   *(Nota: o rascunho inicial afirmava incorretamente que o arquivo não havia sido criado;
   corrigido pelo relatório de auditoria M0_TAREFA-001_B.)*

2. **Stubs de tipo** para pandas e pyarrow estão configurados com `ignore_missing_imports = true`
   no mypy. Se a camada `infrastructure/` usar pandas/pyarrow intensivamente, avaliar
   adicionar `pandas-stubs` e `pyarrow-stubs` ao dev extras.

3. **pytest-asyncio** não foi incluído por não ser necessário no bootstrap. Adicionar quando
   a primeira coroutine for testada.

4. **`__version__` no `__init__.py`** tem 71% de cobertura: o branch `except PackageNotFoundError`
   nunca é exercitado. Aceitável para bootstrap; se coverage total cair próximo de 85%
   em futuras tarefas, adicionar teste com `monkeypatch` para cobrir esse branch.
