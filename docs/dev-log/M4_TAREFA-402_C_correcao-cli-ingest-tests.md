# M4_TAREFA-402_C — Correção: Testes CLI annotate --ingest

**Data**: 2026-06-01
**Milestone**: M4 — Anotação Humana e Persistência
**Épico**: E4
**Skill**: Claude Code (correção pós-auditoria)
**Prioridade / Tamanho**: P1 / S

## Objetivo

Corrigir a lacuna de testes apontada pelo Codex na auditoria M4-TAREFA-402_B: o
subcomando `annotate --ingest` não tinha testes dedicados de CLI. A auditoria exigiu
cobertura do wiring de `_run_ingest_annotate`, do repasse de `--force` e do caminho
de arquivo inexistente.

## Arquivos Criados / Modificados

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `tests/unit/test_cli_annotate_export.py` | Modificado | Adicionada classe `TestAnnotateIngest` (3 testes) + helpers `_make_writer` / `_write_jsonl` |

## Decisões Técnicas

### 1. Estratégia de mock

Mesmo padrão dos testes `--export`: patch de
`inteligenciomica_eval.infrastructure.factories.build_annotation_writer` para retornar
um `InMemoryResultWriter` pré-populado. O writer compartilha um `InMemoryResultStore`,
o que permite verificar o estado dos flags após a invocação da CLI.

### 2. Três casos adicionados

| Teste | Cenário | Asserção principal |
|-------|---------|-------------------|
| `test_ingest_happy_path` | 2 linhas com flags válidos | `exit_code=0`, tabela "Ingeridas" visível, flags persistidos no writer |
| `test_ingest_force_overwrites_existing` | Linha já anotada (flag=0), JSONL com flag=1 | Sem `--force`: flag mantido em 0; com `--force`: flag sobrescrito para 1 |
| `test_ingest_file_not_found` | `ingest_path` não existe | `exit_code=1`, mensagem "encontrado" no output |

### 3. Helpers de módulo

`_make_writer(*row_ids)` e `_write_jsonl(path, rows)` foram definidos como funções de
módulo (não métodos da classe) para permitir reutilização futura e evitar duplicação.

## Validação (DoD)

```
uv run ruff check .              → All checks passed!
uv run ruff format --check .     → 121 files already formatted
uv run mypy --strict src         → Success: no issues found in 45 source files
uv run lint-imports              → 4 kept, 0 broken
uv run pytest tests/unit/test_cli_annotate_export.py
                                 → 16 passed (13 export + 3 ingest)
uv run pytest --cov=src --cov-fail-under=85 -n 4 -q
                                 → 955 passed, 15 skipped — 92.48% total coverage
```

## Critérios de Aceitação

- [x] `_run_ingest_annotate` coberto via teste de CLI (happy path)
- [x] `--force` testado: sem force = skip; com force = overwrite
- [x] Arquivo inexistente: exit_code=1 + mensagem de erro
- [x] Todos os gates verdes (ruff, mypy, lint-imports, pytest ≥ 85%)

## Observações para Próximas Tarefas

Esta correção encerra a lacuna de cobertura CLI da TAREFA-402. O arquivo
`test_cli_annotate_export.py` agora cobre tanto `--export` (13 testes) quanto
`--ingest` (3 testes). Pronto para reauditoria Codex (402_B round 2).
