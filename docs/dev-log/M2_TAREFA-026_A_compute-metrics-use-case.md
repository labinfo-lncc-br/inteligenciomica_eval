# M2_TAREFA-026_A — `ComputeMetricsUseCase` (passada de julgamento, §5.4)

**Data**: 2026-05-29
**Milestone**: M2 — Avaliação automática (Camadas 1+2, juiz determinístico)
**Épico**: E2
**Skill**: python-engineer, data-engineer
**Prioridade / Tamanho**: P0 / M
**Referência arquitetural**: TAREFA-206 (§14.5) · §5.4 (contrato entre passadas) · §3.4 · ADR-007/009

## Objetivo

Implementar a **primeira tarefa da camada `application`**: o `ComputeMetricsUseCase`
que orquestra a passada 2 (julgamento) do fluxo §3.4 — lê linhas geradas, avalia cada
uma pelas Camadas 1 (RAGAS), 1-aux (BERTScore/ROUGE) e 2 (rubrica), agrega o
`FinalScore` (§7.1) e persiste de forma idempotente (ADR-009).

## Arquivos Criados / Modificados

### Criados
- `src/inteligenciomica_eval/application/compute_metrics_use_case.py` — use case +
  `ComputeMetricsInput`/`ComputeMetricsReport`/`ComputeMetricsConfig` (frozen dataclasses).
- `tests/unit/application/test_compute_metrics_use_case.py` — 12 testes.
- `tests/golden/compute_metrics_expected.json` — 4 linhas + relatórios esperados (default/force).

### Modificados — PR retroativo `ResultWriterPort.update_metrics` (previsto na TAREFA-022)
- `src/inteligenciomica_eval/domain/ports.py` — `update_metrics(row_id, metrics,
  final_score, regime)` (antes só `row_id, metrics`); imports `FinalScore`/`DeterminismRegime`.
- `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py` —
  `update_metrics` agora grava também as colunas `final_score` e `batch_invariant`
  (derivado de `regime is JUDGE`, §4.3).
- `tests/fakes/storage.py` — `InMemoryResultWriter.update_metrics` via `with_metrics`.
- `tests/unit/domain/test_ports_contract.py` — stub writer.
- `tests/unit/fakes/test_fakes_satisfy_ports.py` — 3 callers; `test_update_metrics_preserves_other_fields`
  → `test_update_metrics_updates_score_and_preserves_answer` (final_score AGORA muda).
- `tests/integration/repositories/test_parquet_storage.py` — 5 callers;
  `test_update_does_not_change_other_columns` → `test_update_writes_final_score_and_preserves_answer`.
- `tests/e2e/_harness.py` — caller da passada 2 passa `final_score` + regime.

## Decisões Técnicas

1. **PR retroativo de `update_metrics` (Option A — params obrigatórios).** A spec (step viii)
   exige `update_metrics(row_id, metrics, final_score, regime)`. Promovi o método (e o
   `ParquetStorage`) para gravar `final_score` + `batch_invariant`, em vez de deixar a
   antiga semântica "só métricas". Mudança de comportamento documentada e refletida em 2
   testes (a antiga asserção "final_score não muda" virou "final_score É gravado").
2. **`update_metrics` permanece SÍNCRONO; o use case NÃO o aguarda.** A spec escreve
   `await writer.update_metrics(...)`, mas `ResultWriterPort` é armazenamento local (não
   adapter de rede) e a Nota M2 item 1 lista como async-canônicos **apenas** os ports de
   métrica (`metric_suite`, `rubric_judge`). Mantive `append/exists/load/update_metrics`
   síncronos (consistência) e chamo `self._writer.update_metrics(...)` sem `await`. O
   checklist do Prompt B (item 1) exige apenas que **metric_suite/rubric_judge** sejam
   awaited e que **aux_metrics** seja síncrono — satisfeito.
3. **Idempotência: `None` ⟷ NaN.** No domínio `FinalScore` nunca é `None`; "ainda não
   computado" (Parquet NULL) vira NaN na leitura. Logo `_needs_processing = force or
   math.isnan(final_score.value)`. Linha NaN-sentinel (ADR-007) é "incompleta" e será
   reprocessada num run futuro.
4. **`with_metrics` + `update_metrics` (ambos da spec).** Crio `updated =
   result.with_metrics(metrics, final_score, JUDGE)` e persisto via `update_metrics` com
   os campos de `updated` — `regime=JUDGE` ⟹ `batch_invariant=True` (§4.3, TAREFA-022).
5. **Concorrência serial (M2).** `await` sequencial em ordem determinística (`sort` por
   `row_id`). `asyncio.gather` deliberadamente adiado para M3 (documentado na docstring).
6. **Exceção inesperada por linha** (bug escapando do `RetryableMetricAdapter`): `except
   Exception` → log ERROR + `n_failed_terminal++` + `failed_row_ids` + **continua** o loop.
7. **`failure_threshold`** (config): usado no summary final — WARNING
   `compute_metrics_high_failure_rate` se a fração de falhas terminais o exceder (sanity
   check operacional; não aborta).

## Problemas Encontrados e Soluções

- **Rubrica em escala bruta estouraria o FinalScore.** O fake `_DEFAULT_RUBRIC` usa
  `score=4.0` (escala 1-5 de M1); com peso 0.15 isso levaria o `FinalScore` acima de 1.0
  (`ScoreOutOfRangeError`). Nos testes/golden uso `RubricResult(score=0.80)` — a rubrica
  **normalizada [0,1]** que o `PrometheusRubricJudgeAdapter` (TAREFA-024) realmente entrega.
- **Golden com cenários distintos exige fakes roteados.** Os fakes de TAREFA-011 retornam
  valor fixo; criei `_RoutedMetricSuite` (NaN por `question_id`) e `_RoutedAux` (NaN por
  texto da resposta) para diferenciar normal / NaN-parcial / NaN-sentinel.
- **"NaN parcial" vs "NaN-sentinel":** `bertscore_f1` tem peso 0 em §7.1 → NaN nele deixa
  o `final_score` computável (`n_processed`); `answer_correctness` (peso 0.45) NaN ⟹
  `final_score` NaN (`n_nan_excluded`). É a distinção testada no golden.

## Validação (DoD §14.2)

```
ruff check / format          → OK
mypy --strict src            → Success (33 source files)
lint-imports                 → 4 kept, 0 broken (application não importa infrastructure)
pytest test_compute_metrics_use_case → 12 passed
pytest (full, -n 4)          → 749 passed, 13 skipped — 97.01% cobertura
compute_metrics_use_case.py  → 100% | parquet_storage.py → 93%
```

## Critérios de Aceitação (TAREFA-026)

- [x] `execute` é `async def`; `metric_suite`/`rubric_judge` awaited; `aux_metrics` síncrono.
- [x] Use case em `application`, sem importar `infrastructure`; ports por DI (lint-imports OK).
- [x] `DeterminismRegime.JUDGE` passado ao `update_metrics` — `test_judge_regime_passed_to_update_metrics` (spy).
- [x] Idempotência: skip por final_score não-NaN; `force=True` reprocessa — 2 testes.
- [x] Exceção inesperada por linha → `n_failed_terminal++` + continua — `TestTerminalFailure`.
- [x] NaN propagado → `n_nan_excluded++` + `update_metrics` chamado — `TestNaNPropagation`.
- [x] Ordem determinística (sort por `row_id`) — `test_rows_processed_in_row_id_order` (spy).
- [x] `ComputeMetricsReport` (5 campos); golden 4 linhas confere (default + force) — `TestGolden`.
- [x] Concorrência serial documentada; sem `asyncio.gather`.
- [x] Cobertura 100% ≥ 90%; mypy --strict; import-linter OK.

## Observações para Próximas Tarefas

- **TAREFA-027 (`RetryableMetricAdapter`)**: os ports `metric_suite`/`rubric_judge`
  injetados no use case devem chegar **já decorados** — o use case injeta sempre o adapter
  envolvido, nunca o nu (Nota M2 item 4). O use case já trata o NaN-sentinel resultante.
- **TAREFA-028 (Integração/E2E M2)**: fiará `ComputeMetricsUseCase` com os adapters reais
  (RAGAS + rubrica decorados pelo retryable + determinístico) sobre o `ParquetStorage`.
- O campo `rubric_feedback` do schema §5.3 ainda recebe `""` no `to_row`; a fiação do
  `RubricResult.feedback` → coluna `rubric_feedback` pode ser endereçada na 028.
