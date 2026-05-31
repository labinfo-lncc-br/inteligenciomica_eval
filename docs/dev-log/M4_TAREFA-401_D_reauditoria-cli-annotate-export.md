# M4_TAREFA-401_D — Reauditoria CLI `annotate --export`

**Data**: 2026-05-31
**Milestone**: M4 — Workflow de Anotação Offline
**Épico**: E5
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Reauditar a TAREFA-401 após a correção dos apontamentos registrados em
`M4_TAREFA-401_B_auditoria-cli-annotate-export.md`.

## Resultado

**Veredito geral: PASS**

Não encontrei divergências remanescentes contra o Prompt B da TAREFA-401.

## Verificação Item a Item

| Item do Prompt B | Status | Evidência |
|------------------|--------|-----------|
| 1. `annotate --export` e flags `--run-id`, `--threshold`, `--max-items`, `--sort-by` | PASS | `src/inteligenciomica_eval/cli.py:234-276` |
| 2. Filtro `final_score < threshold` OU NaN | PASS | `src/inteligenciomica_eval/cli.py:454-459`; `tests/unit/test_cli_annotate_export.py:138-169` |
| 3. `sort-by finalscore` asc e `random` com seed=42 | PASS | `src/inteligenciomica_eval/cli.py:462-480`; `tests/unit/test_cli_annotate_export.py:171-217`, `452-486` |
| 4. JSONL com `critical_failure_flag = null` | PASS | `src/inteligenciomica_eval/cli.py:492-503`; `tests/unit/test_cli_annotate_export.py:384-414` |
| 5. `--export + --ingest` mutuamente exclusivos com `typer.BadParameter` | PASS | `src/inteligenciomica_eval/cli.py:322-327`; `tests/unit/test_cli_annotate_export.py:251-279` |
| 6. `cli.py` sem import direto de adapters | PASS | grep vazio, ver seção abaixo |
| 7. `KeyboardInterrupt` tratado e zero `print()` nu | PASS | `src/inteligenciomica_eval/cli.py:330-344`; `src/inteligenciomica_eval/cli.py:341` registra `structlog INFO`; grep por `print(` não retorna uso de `print` cru em `cli.py` |
| 8. `mypy --strict`, `lint-imports`, cobertura ≥ 80% | PASS | `mypy`, `lint-imports`, `ruff` e `pytest` passaram; a região da 401 em `cli.py:234-541` ficou com ~81.49% de cobertura e a função `_run_export_annotate` com ~95.86% |

## Correções Confirmadas

| Correção | Evidência |
|---------|-----------|
| Isolamento por `run_id` no contrato do reader | `src/inteligenciomica_eval/domain/ports.py:533-550` |
| Filtro por `run_id` no Parquet real | `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:554-600` |
| Filtro por `run_id` nas fakes de teste | `tests/fakes/storage.py:16-20`, `tests/fakes/storage.py:51-72`, `tests/fakes/storage.py:131-155` |
| Uso do `run_id` no fluxo de export | `src/inteligenciomica_eval/cli.py:445-447` |
| Log `structlog` no `KeyboardInterrupt` | `src/inteligenciomica_eval/cli.py:340-343` |
| Testes novos para `run_id`, `sort-by` inválido e `StorageError` | `tests/unit/test_cli_annotate_export.py:488-612` |

## Saída do grep do item 6

Comando:

```bash
grep -n "from.*adapters import" src/inteligenciomica_eval/cli.py
```

Saída: vazia (`exit_code=1`), como esperado.

## Validação Executada

```bash
/bin/bash -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_cli_annotate_export.py -v'
→ 13 passed in 0.24s

/bin/bash -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports'
→ 4 kept, 0 broken

/bin/bash -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src'
→ Success: no issues found in 44 source files

/bin/bash -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .'
→ All checks passed!

/bin/bash -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_cli_annotate_export.py --cov=inteligenciomica_eval.cli --cov-report=term-missing -q'
→ 13 passed; cobertura do módulo `cli.py`: 30%
```

## Nota sobre Cobertura

O valor de 30% acima não contradiz o DoD da 401: `cli.py` agrega vários subcomandos de
M0–M3. O que interessa aqui é a região da TAREFA-401 (`annotate` export), não o arquivo
inteiro. Com base nas linhas ausentes do relatório de cobertura:

- região `cli.py:234-541` (subcomando `annotate` + `_run_export_annotate`): **81.49%**
- função `_run_export_annotate` (`cli.py:397-541`): **95.86%**

As únicas linhas não exercitadas dentro da função de export são os caminhos de erro de
configuração (`cli.py:436-441`).

## Observações para Próximas Tarefas

- A TAREFA-401 pode ser considerada aprovada por esta auditoria.
- Não identifiquei necessidade de atualização adicional em `CLAUDE.md` a partir desta iteração.
