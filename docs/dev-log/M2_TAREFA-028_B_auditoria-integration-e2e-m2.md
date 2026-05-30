# M2_TAREFA-028_B_auditoria-integration-e2e-m2

## Prompt auditado

- TAREFA-028 — Prompt B
- Data: 2026-05-29
- Auditor: ChatGPT Codex (`code-reviewer`)

## Veredito

- PASS / Approve

## Resumo executivo

O gate de Integração + E2E do M2 está aderente ao contrato funcional do milestone.
Os testes usam adapters reais de M2 com mocking no nível correto do SDK OpenAI,
preservam `DeterministicMetricsAdapter` real em CPU, exercitam a passagem completa
de julgamento até agregação e validam o schema Parquet, `batch_invariant`,
idempotência e propagação de `n_nan_excluded`.

## Evidências por critério

| Critério | Evidência | Status |
|---|---|---|
| Integration async + `pytest-asyncio` | `asyncio_mode = "auto"` em `pyproject.toml`; testes `async def` em `tests/integration/test_metrics_pipeline_m2.py:306` e `:372` | OK |
| 4 cenários da integration | `q1_normal`, `q2_nan_parcial`, `q3_retry`, `q4_exhaust` em `tests/integration/test_metrics_pipeline_m2.py:309-364` | OK |
| Contagem exata de tentativas L1 | `_attempts("q3_retry") == 2` e `_attempts("q4_exhaust") == 3` em `tests/integration/test_metrics_pipeline_m2.py:342-352` | OK |
| Idempotência integration | `n_skipped == 2`, `update_metrics`/Camada1/Camada2 não reinvocados em `tests/integration/test_metrics_pipeline_m2.py:394-408` | OK |
| `batch_invariant=True` integration | verificado em `tests/integration/test_metrics_pipeline_m2.py:354-357` | OK |
| BERTScore real na integration | `DeterministicMetricsAdapter()` real em `tests/integration/test_metrics_pipeline_m2.py:287`; assert `bertscore_f1 > 0.0` em `:359-364` | OK |
| `n_processed == 2` e `n_nan_excluded == 2` | `tests/integration/test_metrics_pipeline_m2.py:320-325` | OK |
| E2E com adapters reais M2 + Parquet `tmp_path` | `tests/e2e/test_full_pipeline_m2.py:159-174` e `:263-279` | OK |
| Schema §5.3 completo no Parquet | verificação dos 8 campos + `rubric_feedback` em `tests/e2e/test_full_pipeline_m2.py:290-309` | OK |
| `batch_invariant=True` em todas as linhas do Parquet | `tests/e2e/test_full_pipeline_m2.py:300-301` | OK |
| `n_nan_excluded` até `ConfigAggregate` | `tests/e2e/test_full_pipeline_m2.py:326-343` | OK |
| Idempotência E2E | re-run com `n_skipped == 4` em `tests/e2e/test_full_pipeline_m2.py:351-395` | OK* |
| Tempo de E2E < 60s | assert em `tests/e2e/test_full_pipeline_m2.py:345-348` | OK |
| Harness M2 usa `ComputeMetricsUseCase` real | `tests/e2e/_harness.py:313-368` | OK |

\* Reconciliação aceita: a spec textual fala `n_skipped == 5`, mas o contrato real do
projeto reprocessa linhas com `final_score = NaN` por design; portanto apenas as 4
linhas finitas são efetivamente "skipped" no rerun. Isso está coerente com o
`ComputeMetricsUseCase` e com o precedente do E2E M0, sem impacto negativo no gate.

## Recomputação manual

### FinalScore — integration / E2E

Pesos canônicos em `src/inteligenciomica_eval/domain/services/final_score.py:22-29`:

- `answer_correctness = 0.45`
- `faithfulness = 0.20`
- `rubric_biomed_score = 0.15`
- `context_recall = 0.10`
- `context_precision = 0.05`
- `answer_relevancy = 0.05`

Valores normais do golden:

- `answer_correctness = 0.80`
- `faithfulness = 0.90`
- `rubric_biomed_score = 0.75`
- `context_recall = 0.70`
- `context_precision = 0.85`
- `answer_relevancy = 0.88`

Recomputação:

`0.45*0.80 + 0.20*0.90 + 0.15*0.75 + 0.10*0.70 + 0.05*0.85 + 0.05*0.88`

`= 0.36 + 0.18 + 0.1125 + 0.07 + 0.0425 + 0.044`

`= 0.809`

Confere com:

- `tests/golden/metrics_pipeline_m2_expected.json`
- `tests/golden/e2e_m2_expected.json`
- asserções em `tests/integration/test_metrics_pipeline_m2.py:332-338`
- asserções em `tests/e2e/test_full_pipeline_m2.py:311-324`

### RankScore — E2E

Pesos canônicos em `src/inteligenciomica_eval/domain/services/rank_score.py:22-27`:

- `median = 0.50`
- `one_minus_failure = 0.20`
- `win_rate = 0.15`
- `critical_failure_penalty = 0.15`

Valores do golden:

- `median_score = 0.809`
- `failure_rate = 0.0`
- `win_rate = 1/3`
- `critical_failure_rate = 0.0`

Recomputação:

`0.50*0.809 + 0.20*(1-0.0) + 0.15*(1/3) - 0.15*0.0`

`= 0.4045 + 0.20 + 0.05 - 0`

`= 0.6545`

Confere com `tests/golden/e2e_m2_expected.json` e com asserções em
`tests/e2e/test_full_pipeline_m2.py:326-343`.

## Execução realizada

```text
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/test_metrics_pipeline_m2.py -q
-> 2 passed in 6.81s

UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/e2e/test_full_pipeline_m2.py -q
-> 2 skipped in 5.75s

E2E_ENABLED=1 UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/e2e/test_full_pipeline_m2.py -q
-> 2 passed in 7.18s

UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports
-> Contracts: 4 kept, 0 broken

UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src
-> Success: no issues found in 34 source files
```

## Observações

- A substituição `respx -> AsyncMock` no SDK OpenAI é adequada aqui e segue a regra
  operacional já consolidada na TAREFA-024; não há perda de cobertura material porque
  o contrato verificado é o do adapter real, não do transporte HTTP.
- Não encontrei ausência de colunas do schema §5.3 no E2E.
- Os warnings observados (`langchain-community` deprecation e `bert_score`/NumPy
  non-writable) não bloqueiam o merge desta tarefa.
