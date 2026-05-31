# M4_TAREFA-401_B — Auditoria CLI `annotate --export`

**Data**: 2026-05-31
**Milestone**: M4 — Workflow de Anotação Offline
**Épico**: E5
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Auditar a entrega da TAREFA-401A contra `docs/prompts_m4_tarefas_401_409_corrigido.md`
(Prompt B), ADR-010, §14.7 e a Nota de operacionalização M4 item 7.

## Arquivos Inspecionados

| Arquivo | Papel |
|---------|-------|
| `src/inteligenciomica_eval/cli.py` | implementação do subcomando `annotate --export` |
| `src/inteligenciomica_eval/infrastructure/factories.py` | factory `build_annotation_reader` |
| `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py` | evidência de persistência/leitura do `run_id` |
| `src/inteligenciomica_eval/domain/value_objects.py` | contrato de `RowId` |
| `tests/unit/test_cli_annotate_export.py` | testes unitários da 401A |
| `docs/dev-log/M4_TAREFA-401_A_cli-annotate-export.md` | relatório produzido pela implementação |

## Resultado

**Veredito geral: FAIL**

### Divergências

| Critério | Arquivo:linha | Gravidade | Evidência |
|---------|---------------|-----------|-----------|
| Filtrar pelo `run_id` antes de exportar | `src/inteligenciomica_eval/cli.py:442-456` | **Bloqueador** | O código faz `reader.load(round_id=cfg.round_id, phase=None)` e exporta candidatos sem qualquer filtro por `run_id`. A spec da 401 exige explicitamente "Filtrar pelo `run_id`". |
| `run_id` existe no armazenamento, mas é descartado na leitura para o domínio | `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:189-190`, `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:254-270`, `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:567-589` | **Bloqueador** | O Parquet serializa `run_id`, porém `from_row()` não o preserva em `EvaluationResult`; `load()` devolve apenas `results`. O relatório da 401A assume "aceitável para rodadas com um único run", mas isso contradiz a especificação do prompt. |
| `KeyboardInterrupt` não gera log `structlog INFO` | `src/inteligenciomica_eval/cli.py:338-340` | **Importante** | O DoD da 401 exige "KeyboardInterrupt tratado → structlog INFO + typer.Exit(130)". A implementação apenas imprime em `rich` e sai com 130. |
| Cobertura específica do subcomando não está demonstrada por evidência reproduzível | `tests/unit/test_cli_annotate_export.py:138-279`, `src/inteligenciomica_eval/cli.py:425-447` | **Importante** | Os testes novos passam, mas não cobrem branches de erro de `--sort-by`, falhas de config/storage ou `KeyboardInterrupt`. Medindo a suíte dedicada sobre `inteligenciomica_eval.cli`, a cobertura do módulo fica em 27%, então o critério "cobertura ≥ 80% do subcomando" não fica objetivamente comprovado. |

## Verificação Item a Item

| Item do Prompt B | Status | Evidência |
|------------------|--------|-----------|
| 1. `annotate --export` e flags `--run-id`, `--threshold`, `--max-items`, `--sort-by` | PASS | `src/inteligenciomica_eval/cli.py:232-302` |
| 2. Filtro `final_score < threshold` OU NaN | PASS | `src/inteligenciomica_eval/cli.py:451-456`; `tests/unit/test_cli_annotate_export.py:138-169` |
| 3. `sort-by finalscore` asc e `random` com seed=42 | PASS | `src/inteligenciomica_eval/cli.py:459-477`; `tests/unit/test_cli_annotate_export.py:171-217`, `452-486` |
| 4. JSONL com `critical_failure_flag = null` | PASS | `src/inteligenciomica_eval/cli.py:489-500`; `tests/unit/test_cli_annotate_export.py:378-405` |
| 5. `--export + --ingest` mutuamente exclusivos com `typer.BadParameter` | PASS | `src/inteligenciomica_eval/cli.py:320-325`; `tests/unit/test_cli_annotate_export.py:251-279` |
| 6. `cli.py` sem import direto de adapters | PASS | grep vazio, ver seção abaixo |
| 7. `KeyboardInterrupt` tratado e zero `print()` nu | PARCIAL | Sem `print()` cru; `KeyboardInterrupt` sem `structlog INFO`: `src/inteligenciomica_eval/cli.py:338-340` |
| 8. `mypy --strict`, `lint-imports`, cobertura ≥ 80% | PARCIAL | `mypy`, `lint-imports`, `ruff` e `pytest` da suíte nova passaram; cobertura específica do subcomando não ficou comprovada |

## Saída do grep do item 6

Comando:

```bash
grep -n "from.*adapters import" src/inteligenciomica_eval/cli.py
```

Saída: vazia (`exit_code=1`), como esperado.

## Validação Executada

```bash
/bin/bash -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_cli_annotate_export.py -v'
→ 10 passed in 0.21s

/bin/bash -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports'
→ 4 kept, 0 broken

/bin/bash -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src'
→ Success: no issues found in 44 source files

/bin/bash -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .'
→ All checks passed!

/bin/bash -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_cli_annotate_export.py --cov=inteligenciomica_eval.cli --cov-report=term-missing -q'
→ 10 passed; cobertura do módulo `cli.py`: 27%
```

## Próxima Iteração Requerida

1. Corrigir o contrato de exportação para realmente isolar o `run_id` solicitado.
2. Preservar ou disponibilizar `run_id` na leitura do Parquet sem violar a arquitetura.
3. Adicionar `structlog INFO` no caminho de `KeyboardInterrupt`.
4. Expandir os testes para cobrir branches de erro e deixar a evidência de cobertura do subcomando inequívoca.

## Observações para Próximas Tarefas

- O arquivo orientador existe como `CLAUDE.md`; a referência do pedido a `CLAUDE.pm` parece ser um lapsus nominal.
- Não houve edição de código nesta etapa; apenas auditoria e geração do relatório B.
