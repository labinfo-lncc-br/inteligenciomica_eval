# M3_TAREFA-308_A — AnnotationWorkflowUseCase + CLI `annotate` (Camada 3)

**Data**: 2026-05-30
**Milestone**: M3 — Passadas de Execução
**Épico**: E3
**Skill**: implementação
**Prioridade / Tamanho**: P1 / M

## Objetivo

Implementar o use case `AnnotationWorkflowUseCase` (Camada 3, ADR-010) com:

- Fila priorizada de revisão humana (`get_review_queue`) — filtra respostas não anotadas
  abaixo dos limiares de `final_score` ou `rubric_biomed_score`, ordena ASC com NaN primeiro.
- Persistência de anotação individual (`annotate`) — valida flag, chama `with_human_annotation`
  (imutabilidade ADR-010), persiste via `update_metrics` com kwargs de Camada 3.
- Processamento em lote a partir de CSV (`batch_annotate_from_csv`) — tolera erros por linha.
- CLI `ielm-eval annotate` com modo interativo (Rich) e modo batch (`--csv`).

Antecipa TAREFA-401/402 do M4 (§14.7): M4 deve referenciar e, se necessário, estender sem
reimplementar.

## Arquivos Criados / Modificados

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `src/inteligenciomica_eval/application/use_cases/annotation_workflow.py` | **NOVO** | `AnnotationConfig` (dataclass), `AnnotationSummary`, `AnnotationWorkflowUseCase`, `_sort_key` |
| `src/inteligenciomica_eval/cli.py` | MODIFICADO | Comando `annotate`, helpers `_run_batch_annotate` / `_run_interactive_annotate`, `AnnotationWorkflowUseCase` no `TYPE_CHECKING` |
| `src/inteligenciomica_eval/domain/ports.py` | MODIFICADO | `ResultWriterPort.update_metrics` — kwargs keyword-only `critical_failure_flag` e `critical_failure_note` (backward-compatible) |
| `src/inteligenciomica_eval/infrastructure/config/schema.py` | MODIFICADO | `AnnotationConfig` (Pydantic) + campo `annotation: AnnotationConfig \| None = None` em `RoundConfig` |
| `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py` | MODIFICADO | `ParquetStorage.update_metrics` — persiste colunas de anotação quando fornecidas |
| `tests/fakes/storage.py` | MODIFICADO | `InMemoryResultWriter.update_metrics` — aceita kwargs e chama `with_human_annotation` |
| `tests/unit/application/use_cases/test_annotation_workflow.py` | **NOVO** | 21 testes em 3 classes (`TestGetReviewQueue`, `TestAnnotate`, `TestBatchAnnotateFromCSV`) |

## Decisões Técnicas

### 1. `AnnotationConfig` duplicado (application vs. infrastructure)

`application` não pode importar `infrastructure` (Contract 2/4 do import-linter). Por isso:

- **`application/use_cases/annotation_workflow.py`**: `AnnotationConfig` é um `dataclass(frozen=True)`
  com `round_id`, `score_threshold`, `rubric_threshold`, `max_to_review`.
- **`infrastructure/config/schema.py`**: `AnnotationConfig` é um `BaseModel` Pydantic com
  `score_threshold`, `rubric_threshold`, `max_to_review` (sem `round_id` — virá do `RoundConfig`).

O wiring (TAREFA-309) converte o Pydantic para o dataclass, injetando `round_id` de `RoundConfig.round_id`.

### 2. `ResultWriterPort.update_metrics` — PR retroativo backward-compatible

Os quatro callers existentes (`RunGenerationPassUseCase`, `RunMetricsPassUseCase`,
`RunJudgePassUseCase`, `RunExperimentUseCase`) passam `metrics`, `final_score` e `regime`
como posicionais. Os dois novos args de Camada 3 foram adicionados como **keyword-only**
(após `*`) com default `None` — nenhum caller existente precisa ser atualizado.

### 3. Tratamento de NaN na fila

`NaN < threshold` é `False` em Python. Portanto:

- Linha com `final_score=NaN` E `rubric_biomed_score=NaN` → **não entra** na fila (ambas as
  condições são False) — interpretação literal da spec.
- Linha com `final_score=NaN` mas `rubric_biomed_score < threshold` → **entra** via rubric.
- `_sort_key`: NaN recebe `(0, 0.0)` vs. `(1, fs)` para valores finitos → NaN sempre primeiro.

### 4. `ScoreOutOfRangeError` vs. `InvalidCriticalFailureFlagError`

`annotate` valida `flag ∈ {0, 1}` antes de chamar `with_human_annotation`. Dupla validação
intencional: `ScoreOutOfRangeError` é o contrato público do use case; `with_human_annotation`
é o invariante ADR-010 da entidade.

### 5. CLI com lazy import e TYPE_CHECKING

`AnnotationWorkflowUseCase` referenciado na assinatura dos helpers `_run_batch_annotate` /
`_run_interactive_annotate` está sob `TYPE_CHECKING`. Com `from __future__ import annotations`
presente, a anotação é avaliada como string em runtime — nenhum import real no load do módulo.
Import real acontece apenas dentro do corpo do comando `annotate` (lazy).

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| `StorageError` importado mas não usado no body do `annotate` (cli.py) | Removido; já é lazy via `_run_batch_annotate` / `_run_interactive_annotate` |
| `FinalScore` importado mas não usado no test | Removido |
| `RUF059` — variáveis desempacotadas de `_make_uc()` nunca usadas | Renomeadas para `_store` / `_writer` onde o valor não é referenciado no corpo |
| Sed global renomeou `store` para `_store` mesmo em testes que usam o valor | Revertido para `store` nos 5 testes que criam `InMemoryResultReader(store)` |

## Validação (DoD)

```
uv run ruff check .                                          → 0 errors
uv run ruff format --check .                                 → 0 files would change
uv run mypy --strict src                                     → Success: no issues found in 43 source files
uv run lint-imports                                          → 4 kept, 0 broken
uv run pytest --cov=src --cov-fail-under=85 -n 4             → 924 passed, 15 skipped, 93.59% total
```

## Critérios de Aceitação

- [x] `AnnotationWorkflowUseCase` implementado com `get_review_queue`, `annotate`, `batch_annotate_from_csv`
- [x] `AnnotationConfig` dataclass de aplicação (sem importar infrastructure)
- [x] Contratos de importação: 4/4 KEPT
- [x] `update_metrics` retrocompatível — callers existentes não precisam de atualização
- [x] CLI `ielm-eval annotate` com modo interativo e `--csv`
- [x] 21 testes unitários cobrindo fila, anotação individual e batch
- [x] Gate 85% de cobertura: 93.59%
- [x] mypy --strict: PASS

## Observações para Próximas Tarefas

- **TAREFA-309 (wiring)** deve converter `schema.AnnotationConfig` + `RoundConfig.round_id`
  para `application.use_cases.annotation_workflow.AnnotationConfig` ao instanciar o use case.
- `ParquetStorage` precisa garantir que as colunas `critical_failure_flag` e
  `critical_failure_note` existam no schema Parquet antes do `update_metrics` ser chamado;
  isso pode exigir migração do schema ou criação das colunas com default `None` no `append`.
- O modo interativo do CLI usa `typer.prompt` — testes de CLI que cobrem o caminho interativo
  precisarão de mock do stdin (fora do escopo desta tarefa).
