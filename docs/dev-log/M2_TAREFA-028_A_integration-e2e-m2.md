# M2_TAREFA-028_A — Integration + E2E M2 (gate de saída do milestone)

**Data**: 2026-05-29
**Milestone**: M2 — Avaliação automática (Camadas 1+2, juiz determinístico)
**Épico**: E2
**Skill**: test-engineer
**Prioridade / Tamanho**: P0 / M
**Referência arquitetural**: TAREFA-207 (§14.5 — go/no-go do M2) · §11 (estratégia de testes) · ADR-003/007/009

## Objetivo

Fechar o M2 com a fronteira de teste de integração + E2E que exercita o
`ComputeMetricsUseCase` (TAREFA-026) fiado aos adapters **reais** de M2 (023/024/025)
e aos decorators de retry (TAREFA-027), validando: os 4 cenários da passada de
julgamento (normal / NaN parcial / retry / NaN-sentinel), idempotência (ADR-009),
`batch_invariant=True` ponta-a-ponta (§4.3), propagação de `n_nan_excluded` até o
`ConfigAggregate`, e o schema §5.3 completo no Parquet.

## Arquivos Criados / Modificados

### Criados
- `tests/integration/test_metrics_pipeline_m2.py` — parte (a): 2 testes async
  (`@pytest.mark.integration`), pipeline real sobre `InMemory{Reader,Writer}`.
- `tests/e2e/test_full_pipeline_m2.py` — parte (b): 2 testes async (`@pytest.mark.e2e`
  + `skipif(not E2E_ENABLED)`), pipeline real sobre `ParquetStorage` (tmp_path) +
  `AggregationService` + `RankScoreCalculator`.
- `tests/golden/metrics_pipeline_m2_expected.json` — golden da integração (FinalScore
  de q1/q3 = 0.809, recomputação, contagens do relatório).
- `tests/golden/e2e_m2_expected.json` — golden do E2E (FinalScore 0.809, RankScore
  0.6545, win_rate 1/3, agregados por config + recomputação manual).

### Modificados
- `tests/e2e/_harness.py` — novo helper `run_m2_metrics_pass(...)` (use case real +
  agregação) que dá suporte M2 ao harness; `run_min_round` (M0) intacto.
- `tests/unit/application/test_compute_metrics_use_case.py` — **incidental**: 1 linha
  colapsada pelo `ruff format` (drift pré-existente do commit da 026, sem mudança de
  comportamento) para o gate `ruff format --check .` ficar verde.

## Decisões Técnicas

1. **Mock no nível SDK, NÃO respx (CLAUDE.md §11 + memória + FAIL da TAREFA-024).**
   A spec pede `respx.MockRouter` para o vllm-judge, mas respx **trava** (timeout/exit
   124) com o SDK OpenAI no sandbox do auditor (asyncify→`asyncio.to_thread`). O gate
   M1 (TAREFA-021) usava respx mas é **Qdrant-gated** → *pulado* no sandbox; já a parte
   (a) **roda** em `pytest -m integration` sem Docker, então respx aqui reproduziria o
   FAIL. Substituição §11-compatível: `PrometheusRubricJudgeAdapter` real com
   `_client.chat.completions.create = AsyncMock(...)`; `RAGASLayer1Adapter` real com
   `_metrics` injetado (`single_turn_ascore` = AsyncMock). "Sem `respx.NetworkNotMocked`"
   fica satisfeito por construção (nenhuma chamada HTTP é emitida).
2. **Contagem de chamadas de Camada 1 = `call_args_list` do AsyncMock de
   `answer_correctness.single_turn_ascore`** — como é a 1ª métrica do laço RAGAS, é
   chamado exatamente 1× por tentativa de `RAGASLayer1Adapter.score()`. Equivalente
   §11-compatível de `len(respx.calls)` (Prompt B item 3 admite "ou equivalente").
3. **Falha de Camada 1 = `APIConnectionError`, não HTTP 500.** O `RAGASLayer1Adapter`
   trata 500 como falha de parsing (NaN por campo); só `APIConnectionError`/
   `APITimeoutError` viram `MetricComputationError` (`_IO_FAILURE_TYPES`,
   ragas_metrics.py:67) → única falha que aciona o retry. q3/q4 disparam
   `APIConnectionError` — fiel ao contrato do adapter (TAREFA-023).
4. **`RetryConfig(max_retries=2, initial_wait_s=0.0)`.** `max_retries=2` ⟹ até **3
   tentativas** (1 + 2 retries) → q4 esgota na 3ª (NaN-sentinel), batendo a "contagem de
   3 chamadas" da spec. `initial_wait_s=0.0` ⟹ `await asyncio.sleep(0)` (instantâneo,
   sem espera real). Reconcilia com TAREFA-027 (lá `max_retries=3` ⟹ 4 chamadas).
5. **Idempotência: linhas NaN reprocessam por design.** A spec textual diz
   `n_skipped == 4` (integração) / `== 5` (E2E), mas `_needs_processing` reprocessa
   linhas com `final_score` NaN ("incompletas", docstring do `ComputeMetricsUseCase`).
   Logo só as linhas **finitas** são puladas: integração `n_skipped == 2`; E2E
   `n_skipped == 4`. **Mesmo precedente do E2E M0** (TAREFA-012,
   `test_idempotency_second_run_does_not_duplicate_rows`). Demonstro o contrato com
   cenários limpos (todas finitas) + espião de `update_metrics` (call_count == 0 na 2ª).
6. **BERTScore real, sem mock (asserção 7).** `bertscore_f1` tem peso 0 em §7.1 → seu
   NaN não afeta o `final_score`; é NaN só se o modelo estiver indisponível offline.
   Asserção `not isnan ⟹ > 0.0` (real positivo quando carregado). Localmente o modelo
   carrega e `bertscore_f1 > 0`.
7. **E2E gated por `E2E_ENABLED`** (igual ao smoke M1) — carrega BERTScore. Sem a env,
   `pytest -m e2e` coleta e **pula** (rápido/seguro no sandbox). Validado localmente
   com `E2E_ENABLED=1`.
8. **Leitura do Parquet por arquivo** (`pq.ParquetFile(f).read()`), nunca
   `pd.read_parquet` sobre a árvore Hive (conflito `round_id` string × dictionary →
   `ArrowTypeError`, decisão TAREFA-021).

## Recomputação manual dos golden (para o auditor)

**FinalScore normal** (§7.1, `DEFAULT_WEIGHTS`; `answer_similarity`/`bertscore_f1` peso 0):
```
0.45*0.80 + 0.20*0.90 + 0.15*0.75 + 0.10*0.70 + 0.05*0.85 + 0.05*0.88
= 0.360 + 0.180 + 0.1125 + 0.070 + 0.0425 + 0.044 = 0.809
```
(rubrica bruta 4 → normalizada (4-1)/4 = 0.75.)

**RankScore por config** (§7.3; pesos 0.50/0.20/0.15/0.15):
```
win_rate: all_qids={q01,q02,q03_nan}, n_questions=3. q01/q02: empate alpha/beta → 0.5
cada; q03_nan: alpha NaN (excluído), beta não tem → sem vencedor. wins=1.0 cada →
win_rate = 1.0/3.
RankScore = 0.50*0.809 + 0.20*(1-0.0) + 0.15*(1/3) - 0.15*0.0
          = 0.4045 + 0.20 + 0.05 - 0.0 = 0.6545  (idêntico p/ alpha e beta)
```

## Problemas Encontrados e Soluções

- **`respx` × sandbox do auditor**: ver Decisão 1 — substituído por mock SDK.
- **Spec × contrato real do RAGAS (500 vs APIConnectionError)**: ver Decisão 3.
- **Spec × idempotência (n_skipped)**: ver Decisão 5 — reconciliado com o precedente M0.
- **`RUF002`** (`×` ambíguo em docstrings) → trocado por `x`.
- **Drift de formatação pré-existente** em `test_compute_metrics_use_case.py` (1 linha)
  → formatado para o gate `ruff format --check .` passar.

## Validação (DoD §14.2)

```
ruff check .                 → All checks passed
ruff format --check .        → 98 files already formatted
mypy --strict src            → Success (34 source files)
lint-imports                 → 4 kept, 0 broken
pytest tests/integration/test_metrics_pipeline_m2.py → 2 passed (9.06s < 30s)
pytest tests/e2e/test_full_pipeline_m2.py            → 2 skipped (sem E2E_ENABLED)
  └─ com E2E_ENABLED=1       → 2 passed (11.02s < 60s)
pytest (full, -n 4)          → 761 passed, 15 skipped — 97.10% cobertura
pytest (full, randomly)      → 761 passed, 15 skipped — 97.10% (sem acoplamento de ordem)
```

## Critérios de Aceitação (TAREFA-028)

### Parte (a) — Integration
- [x] Testes async (`asyncio_mode="auto"`); 4 cenários presentes e corretos.
- [x] Contagem de Camada 1: q3 → 2 tentativas; q4 → 3 (equivalente §11 de `respx.calls`).
- [x] Idempotência: 2ª execução → `n_skipped == 2` (finitas); `update_metrics` NÃO
      chamado (spy call_count == 0); Camadas 1/2 não reinvocadas.
- [x] `batch_invariant=True` em todos os resultantes (regime JUDGE).
- [x] `n_processed == 2`, `n_nan_excluded == 2`.
- [x] Golden inline do FinalScore de q1/q3 == 0.809.
- [x] BERTScore real (sem mock); `bertscore_f1 > 0.0` quando o modelo carrega.

### Parte (b) — E2E M2
- [x] Adapters reais M2 (023/024/025) com mock SDK; BERTScore real; Parquet tmp_path.
- [x] Schema §5.3: 8 campos de métrica + `rubric_feedback` presentes (sem null por bug).
- [x] `batch_invariant=True` em TODAS as 5 linhas (lido do Parquet por arquivo).
- [x] `n_nan_excluded` propagado até `ConfigAggregate.n_excluded_nan` (alpha = 1).
- [x] FinalScore (0.809) e RankScore (0.6545) batem o golden.
- [x] Idempotência: 2ª execução → `n_skipped == 4` (finitas; NaN reprocessa).
- [x] Tempo < 60s; nenhuma chamada de rede real (por construção).
- [x] `lint-imports` OK; `mypy --strict src` OK.

## Observações para Próximas Tarefas (M3)

- **Wiring de `rubric_feedback`**: o `RubricResult.feedback` ainda não é persistido na
  coluna `rubric_feedback` (`update_metrics` não a cobre; fica `""`). A coluna está
  **presente e não-null** (satisfaz §5.3); fiar feedback→coluna fica para um PR futuro
  (evoluir `update_metrics` ou append do resultado completo) — fora do escopo deste
  teste.
- **respx no CI integration job**: como os adapters de M2 usam o SDK OpenAI, o padrão
  de mock SDK (§11) deve ser reusado em M3 — nunca respx para o juiz.
- **Gate de saída M2**: todos os itens do Apêndice (DAG/§14.5) verdes — M2 fechado.
