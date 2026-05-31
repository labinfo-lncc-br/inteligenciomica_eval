# M4_TAREFA-401_A — CLI `annotate --export` (Exportação Estratificada)

**Data**: 2026-05-31
**Milestone**: M4 — Workflow de Anotação Offline
**Épico**: E4
**Skill**: Claude Code
**Prioridade / Tamanho**: P1 / M

---

## Objetivo

Implementar o subcomando `ielm-eval annotate --export PATH` que exporta
`EvaluationResult` estratificados para um arquivo JSONL destinado à anotação
offline por especialistas biomédicos (ADR-010). A seleção é por
`final_score < threshold` **ou** `math.isnan(final_score)` (NaN = prioridade
máxima). Modos de ordenação: `finalscore`, `rubric`, `random` (seed=42).

---

## Arquivos Criados / Modificados

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `src/inteligenciomica_eval/infrastructure/factories.py` | **NOVO** | `build_annotation_reader(config_path)` — factory injetável |
| `src/inteligenciomica_eval/cli.py` | **MODIFICADO** | `annotate` estendido: `--export`, `--ingest`, `--threshold`, `--max-items`, `--sort-by`; `data_dir` tornado opcional |
| `tests/unit/test_cli_annotate_export.py` | **NOVO** | 10 testes unitários com `InMemoryResultReader` |

---

## Decisões Técnicas

### 1. Factory `build_annotation_reader` (injetabilidade)

A CLI chama `build_annotation_reader(config)` em vez de instanciar
`ParquetStorage` diretamente, tornando o leitor substituível em testes via
`mocker.patch("inteligenciomica_eval.infrastructure.factories.build_annotation_reader")`.
Convenção de diretório de dados: `config_path.parent / "data"`.

### 2. `run_id` não filtrado

`EvaluationResult` não possui campo `run_id` no domínio (é proveniência do
Parquet). A implementação carrega todos os resultados do `round_id` sem
filtro por `run_id` — aceitável para rodadas com um único run por fase.

### 3. `rubric_feedback` sempre `""`

Campo presente na spec do JSONL mas ausente no modelo de domínio
(`EvaluationResult`). Preenchido com string vazia na exportação; será
populado pelo especialista no fluxo de ingestão (TAREFA-402).

### 4. `data_dir` opcional na CLI

O parâmetro `--data-dir` era obrigatório no modo M3 interativo/CSV. Tornado
`Optional[Path] = None` para compatibilidade retroativa; modo M3 ainda exige
`data_dir` e levanta `typer.BadParameter` se ausente.

### 5. Serialização de NaN → `null`

`math.isnan(value)` antes de serializar; `None` em Python → `null` em JSON
(RFC 8259 compliant). Nunca `float("nan")` no JSON.

### 6. Mutualidade exclusiva `--export` / `--ingest`

`typer.BadParameter` levanta saída com código 2 (padrão de erro de parâmetro
do Typer), exibindo mensagem amigável "mutuamente exclusivas".

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| `B904`: `raise typer.Exit(130)` dentro de `except` sem `from` | Alterado para `raise typer.Exit(130) from None` |
| `N806`: `_VALID_SORT_BY` uppercase em escopo de função | Renomeado para `_valid_sort_by` (lowercase local) |
| `RUF001`: EN DASH `–` em string `"0.5–0.7"` | Substituído por hífen-minus `"0.5-0.7"` |
| `B905`: `zip()` sem `strict=` | Adicionado `strict=True` na fixture `result_reader` |
| `E741`: variável `l` ambígua em list comprehensions | Renomeado para `line` em todos os pontos (6 ocorrências) |

### Correções pós-auditoria Codex (iteração 2)

| Item Codex | Problema | Solução |
|------------|----------|---------|
| 1+2 | `run_id` não filtrado; perdido no `from_row()` | Adicionado `run_id: str \| None = None` a `ResultReaderPort.load()`, `ParquetStorage.load()` (filtro PyArrow `pc.equal`), `InMemoryResultReader.load()` e `_StoredRow` + `InMemoryResultWriter` |
| 3 | `KeyboardInterrupt` sem log structlog | Adicionado `_log.info("export_annotate_interrupted", run_id=run_id)` antes do rich print |
| 4 | Branches `cli.py:425`, `:433`, `:445` descobertos | Adicionados 3 testes: `test_run_id_filters_results`, `test_invalid_sort_by_exits_with_error`, `test_storage_error_exits_with_error` |

---

## Validação (DoD) — após correções pós-auditoria Codex (iteração 2)

```
uv run ruff check .          → All checks passed!
uv run mypy --strict src     → Success: no issues found in 44 source files
uv run lint-imports          → 4 contracts kept, 0 broken
uv run pytest tests/unit/test_cli_annotate_export.py -v
                             → 13 passed in 0.29s
uv run pytest --cov=src --cov-fail-under=85 -n 4 -q
                             → 938 passed, 15 skipped — 92.89% coverage
```

---

## Critérios de Aceitação

- [x] `ielm-eval annotate --export PATH --run-id ID --config CFG` exporta JSONL estratificado
- [x] `--threshold 0.70` (default): inclui `final_score < threshold` e NaN
- [x] `--sort-by finalscore`: NaN primeiro, depois ASC por `final_score`
- [x] `--sort-by rubric`: NaN primeiro, depois ASC por `rubric_biomed_score`
- [x] `--sort-by random`: embaralha com `random.Random(42)` (reprodutível)
- [x] `--max-items N`: limita a N linhas após ordenação
- [x] `--export` + `--ingest` juntos: `typer.BadParameter` (exit ≠ 0)
- [x] Diretório pai criado automaticamente (`mkdir(parents=True, exist_ok=True)`)
- [x] Cada linha é JSON válido com todos os campos obrigatórios
- [x] `critical_failure_flag: null` (especialista preenche na ingestão)
- [x] NaN serializado como `null` (RFC 8259)
- [x] `mypy --strict` limpo
- [x] `lint-imports` 4 contratos satisfeitos
- [x] Cobertura ≥ 85% (92.77%)

---

## Observações para Próximas Tarefas

- **TAREFA-402**: implementar `--ingest PATH` — leitura do JSONL anotado e
  persistência de `CriticalAnnotation` via `AnnotationWorkflowUseCase`.
- `factories.py` em 44% de cobertura: corpo da factory não é coberto pelos
  testes unitários (mock total). Testes de integração (M4 gate) cobrirão.
- `--ingest` já levanta `typer.Exit(1)` com mensagem "será implementado na
  TAREFA-402" — placeholder explícito.
