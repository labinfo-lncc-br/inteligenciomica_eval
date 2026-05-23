# CLAUDE.md — Guia de Desenvolvimento InteligenciÔmica Eval

Este arquivo é lido automaticamente pelo Claude Code em cada sessão. Contém padrões,
decisões de arquitetura e convenções que devem ser respeitadas em **todas** as tarefas.

---

## 1. Stack e Ferramentas

| Categoria       | Ferramenta / Decisão                                       |
|-----------------|------------------------------------------------------------|
| Gerenciador pkg | **uv** — NUNCA usar pip install diretamente                |
| Build backend   | **hatchling** (configurado em `pyproject.toml`)            |
| Lint + format   | **ruff** (lint e format unificados)                        |
| Type checker    | **mypy --strict** (apenas em `src/`, não em `tests/`)      |
| Contratos arq.  | **import-linter** (`.importlinter` com 4 contratos)        |
| Testes          | **pytest** + **pytest-cov** + **pytest-xdist**             |
| Pre-commit      | ruff-lint · ruff-format · mypy (via hook `local`)          |
| Python          | **3.11+** (runtime); ambiente local usa 3.12               |

### Ordem obrigatória de validação (antes de qualquer commit)

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src
uv run lint-imports
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n auto
```

---

## 2. Layout do Projeto

```
src/inteligenciomica_eval/   ← pacote principal (src layout)
  __init__.py                ← expõe __version__
  cli.py                     ← Typer app (entry point: ielm-eval)
  domain/                    ← regras puras, sem I/O
    services/
  application/               ← use cases orquestrando domain
  infrastructure/            ← adapters, repos, config, prompts
    adapters/
    config/
    prompts/
    repositories/
  visualization/             ← helpers de renderização

tests/
  conftest.py
  unit/                      ← ≥ 70% dos testes, < 10 ms cada
    domain/                  ← espelha src/domain/
    application/             ← espelha src/application/
  integration/               ← adapters reais, containers
    adapters/                ← espelha src/infrastructure/adapters/
  e2e/                       ← fluxos fim-a-fim
  fakes/                     ← implementações in-memory das ports
  factories/                 ← builders de dados de teste
  golden/                    ← datasets de referência (ML/RAG)

docs/
  adr/                       ← Architecture Decision Records
  dev-log/                   ← relatórios de execução por tarefa
```

---

## 3. Contratos de Importação (import-linter)

Quatro contratos declarados em `.importlinter` (root_package = inteligenciomica_eval):

1. **domain-forbidden**: `domain` NÃO importa `application`, `infrastructure`, `cli` nem libs de I/O (pandas, polars, pyarrow, sqlalchemy, httpx, requests, boto3, qdrant_client, openai, ragas, deepeval, statsmodels).
2. **application-forbidden**: `application` NÃO importa `infrastructure`, `cli` nem libs de I/O (mesma lista).
3. **infrastructure-forbidden**: `infrastructure` NÃO importa `cli`.
4. **architecture-layers** (tipo `layers`): enforce hierarquia estrita `domain < application < infrastructure` — `application` só pode importar `domain`.

Ao adicionar uma nova lib de I/O, atualizar `forbidden_modules` nos contratos 1 e 2.

---

## 4. Padrões de Código

- `from __future__ import annotations` **no topo de todo arquivo Python** (sem exceções).
- Type hints em todas as assinaturas públicas.
- Docstrings Google-style nas funções/classes públicas.
- Zero `Any` sem comentário justificando.
- `# pragma: no cover` no bloco `if __name__ == "__main__":` de todo CLI/script.
- Nenhum `print()` em código de produção — usar `structlog` ou `rich.Console`.

---

## 5. CLI (Typer)

**Decisão crítica**: Typer ≥ 0.9 colapsa um app com um único `@app.command()` fazendo
o app ser o próprio comando (sem subcomandos). Isso quebra `ielm-eval version`.

**Regra**: sempre adicionar `@app.callback()` antes do primeiro `@app.command()` para
forçar o modo de grupo (multi-subcomando). Extrair também uma função `main()` para
permitir testes do caminho de `KeyboardInterrupt`:

```python
@app.callback()
def _main() -> None:
    """Texto de ajuda do grupo."""

@app.command()
def meu_comando() -> None:
    ...

def main() -> None:
    """Entry point wrapper — testável via mocker.patch."""
    try:
        app()
    except KeyboardInterrupt:
        _err_console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)

if __name__ == "__main__":  # pragma: no cover
    main()
```

---

## 6. Cobertura de Testes

- `branch = true`, `source = ["src/inteligenciomica_eval"]`, `fail_under = 85`.
- `pytest-cov` é um pacote **separado** de `coverage[toml]` — ambos devem estar em `dev` deps.
- Dev deps ficam em `[dependency-groups] dev` (PEP 735), **não** em `[project.optional-dependencies]`.
  Com `[dependency-groups]`, `uv sync --frozen` instala runtime + dev por padrão — não precisa de `--all-extras`.
- Módulos de esqueleto (`__init__.py` vazios) precisam ser importados em algum teste para
  entrarem na contagem. Ver `tests/unit/test_imports.py`.
- `exclude_lines` inclui `if __name__ == .__main__.:` e `if TYPE_CHECKING:`.

---

## 7. Dev Log — Padrão de Nomes de Relatórios

Localização: `docs/dev-log/`

### Formato do nome de arquivo

```
M{N}_TAREFA-{NNN}_{parte}_{slug}.md
```

| Campo    | Descrição                                              | Exemplo     |
|----------|--------------------------------------------------------|-------------|
| `M{N}`   | Número do milestone (sem padding)                      | `M0`        |
| `TAREFA-{NNN}` | Identificador da tarefa com zero-padding 3 dígitos | `TAREFA-001` |
| `{parte}` | Letra do prompt (A = implementação, B = revisão, etc.) | `A`         |
| `{slug}` | Kebab-case descritivo, max 40 chars                    | `bootstrap-repositorio` |

**Exemplos válidos**:
```
M0_TAREFA-001_A_bootstrap-repositorio.md
M0_TAREFA-002_A_dominio-core.md
M1_TAREFA-010_A_adapter-llm.md
M1_TAREFA-010_B_revisao-testes.md
```

### Estrutura interna do relatório

```markdown
# {M}_TAREFA-{NNN}_{parte} — {Título da Tarefa}

**Data**: YYYY-MM-DD
**Milestone**: M{N} — {Nome do Milestone}
**Épico**: E{N}
**Skill**: {skill usada}
**Prioridade / Tamanho**: P{N} / {S|M|L|XL}

## Objetivo
## Arquivos Criados / Modificados
## Decisões Técnicas
## Problemas Encontrados e Soluções
## Validação (DoD)
## Critérios de Aceitação
## Observações para Próximas Tarefas
```

---

## 8. Instalação e Comandos Rápidos

```bash
uv sync --frozen          # instala dependências (usa uv.lock)
uv run ielm-eval --help   # verifica entry point
uv run ielm-eval version  # imprime versão
uv run pre-commit install # instala hooks
uv run pre-commit run --all-files  # roda hooks em todos os arquivos
```

---

## 9. CI

Arquivo: `.github/workflows/ci.yml`

Passos em ordem: checkout → setup-uv → setup-python 3.11 → `uv sync --frozen` →
`ruff check` → `ruff format --check` → `mypy --strict src` → `lint-imports` →
`pytest --cov=src --cov-report=xml --cov-fail-under=85 -n auto`
