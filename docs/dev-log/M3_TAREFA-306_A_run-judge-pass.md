# M3_TAREFA-306_A — RunJudgePassUseCase (Passada 3 do Juiz)

**Data**: 2026-05-30
**Milestone**: M3 — Orquestração experimental
**Épico**: E3
**Skill**: ml-engineer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Implementar `RunJudgePassUseCase` em
`src/inteligenciomica_eval/application/use_cases/run_judge_pass.py` — Passada 3 da
arquitetura de 3 passadas (ADR-004): avalia cada linha via rubrica biomédica
(`RubricJudgePort`, Prometheus) em ordem estável por `row_id`, persiste
`rubric_biomed_score` + `FinalScore` recalculado via `writer.update_metrics` com
`regime=DeterminismRegime.JUDGE` (ADR-003).

## Arquivos Criados / Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/.../application/use_cases/run_judge_pass.py` | **Novo**: `RunJudgePassUseCase`, `JudgePassConfig`, `JudgePassReport`. |
| `tests/unit/application/use_cases/test_run_judge_pass.py` | **Novo**: 17 testes (7 classes). |

## Decisões Técnicas

1. **`config: JudgePassConfig` (dataclass de aplicação), NÃO `RoundConfig`.**
   `RoundConfig` é infrastructure (import-linter Contract 2/4). Os campos necessários
   (`max_judge_retries`, `retry_backoff_s`, `log_progress_every`) não existem em
   `RoundConfig` — são parâmetros de orquestração da passada.
   `JudgePassConfig` é frozen dataclass com defaults sensatos (max=3, backoff=5 s).

2. **`score_calc: FinalScoreCalculator` adicionado ao construtor.**
   Não está na spec, mas é necessário para recompute do `FinalScore` após preencher
   `rubric_biomed_score` via `dataclasses.replace`. `FinalScoreCalculator` pertence a
   `domain.services` — importação permitida pela application.

3. **Linhas com `final_score=NaN` são PROCESSADAS.**
   O juiz avalia `(question + answer)` diretamente, independente do RAGAS. Bloquear
   Passada 3 por falha da Passada 2 seria contrário à independência de passadas (ADR-004).
   Linhas com `final_score=NaN` entram na lista elegível; `_log.info` registra o
   processamento com `judge_processing_nan_final_score`.

4. **Processamento SEQUENCIAL e ORDEM ESTÁVEL por `row_id` (ADR-003).**
   O juiz Prometheus é configurado com `VLLM_BATCH_INVARIANT=1` (juiz batch-invariant).
   Para garantir reprodutibilidade de submissão em re-runs, `eligible.sort(key=lambda
   r: r.answer.row_id.value)` é aplicado antes do loop de julgamento.

5. **Retry em `JudgeUnavailableError` com backoff configurável.**
   `_judge_with_retry` tenta até `max_judge_retries` vezes (não "max_retries extras" —
   1 tentativa inicial + N-1 retries). Ao esgotar, retorna `_NAN_RUBRIC` (ADR-007:
   NaN é estado legítimo). `asyncio.sleep(retry_backoff_s=0.0)` em testes para
   velocidade.

6. **`n_judged` vs `n_nan` baseado em `rubric.score`, não em `FinalScore`.**
   O contador `n_judged` incrementa quando `not math.isnan(rubric.score)` — o FinalScore
   pode ficar NaN por outros motivos (métricas RAGAS ausentes com peso > 0), e isso
   não é responsabilidade desta passada. `n_nan` conta retries esgotados ou resposta NaN
   do juiz.

7. **`enumerate(eligible, start=1)` em vez de variável manual.**
   Corrigido por ruff SIM113 — `enumerate` é idiomático e elimina a variável extra.

8. **`JudgePassReport.batch_invariant_assumed=True`.**
   Campo documentado: o use case ASSUME que o servidor do juiz foi configurado com
   `VLLM_BATCH_INVARIANT=1` pelo `VLLMServerManager`. Auditoria deve confirmar o
   wiring no orquestrador (TAREFA-309/310).

## Problemas Encontrados e Soluções

- **`JudgeUnavailableError` exige dois argumentos `(judge_id, reason)`:** `_SpyRubricJudge`
  no arquivo de testes usava `JudgeUnavailableError("simulated judge unavailable")` com
  apenas um argumento. Corrigido para `JudgeUnavailableError("spy-judge", "simulated
  unavailable")`.
- **ruff SIM113** (`enumerate` para variável de índice): variável `judged_count = 0`
  substituída por `enumerate(eligible, start=1)`, eliminando também a inicialização.

## Validação (DoD §14.3)

```text
ruff check .                    -> All checks passed!
ruff format --check .           -> 112 files already formatted
mypy --strict src               -> Success: no issues found in 41 source files
lint-imports                    -> Contracts: 4 kept, 0 broken
pytest -n 4 --cov --cov-fail-under=85
  -> 879 passed, 15 skipped — coverage 96.94%
  -> run_judge_pass.py: 96% (229 progress log ≥10 linhas, 305 type guard inalcançável)
```

## Critérios de Aceitação (tabela TAREFA-306)

| Critério | Estado | Evidência |
|----------|--------|-----------|
| Linhas já julgadas puladas (idempotência por rubric_biomed_score não-NaN) | ✅ | `TestIdempotency::test_already_judged_row_is_skipped` |
| JudgeUnavailableError: 3 retries → NaN aceito e persistido (ADR-007) | ✅ | `TestJudgeRetry::test_judge_nan_persisted_after_exhaustion` |
| Ordem estável por row_id (garante submissão idêntica em re-runs) | ✅ | `TestStableOrdering::test_judge_called_in_row_id_sorted_order` |
| Linhas com final_score=NaN são processadas (ADR-004: passadas independentes) | ✅ | `TestNanFinalScoreRows::test_nan_final_score_rows_are_processed` |
| rubric_biomed_score persistido = valor do juiz | ✅ | `TestPersistence::test_rubric_score_persisted_from_judge` |
| update_metrics com regime=DeterminismRegime.JUDGE | ✅ | `TestPersistence::test_update_metrics_called_with_judge_regime` |
| FinalScore recalculado com rubric preenchido | ✅ | `TestPersistence::test_final_score_recomputed_after_judging` |
| JudgePassReport com batch_invariant_assumed=True | ✅ | `TestJudgePassReport::test_report_fields_populated` |
| application NÃO importa infrastructure | ✅ | `lint-imports` 4/0 |

## Observações para Próximas Tarefas

- **Desvios conscientes a sinalizar ao Codex (Prompt B)**:
  1. `config: JudgePassConfig` (dataclass de aplicação) em vez de `RoundConfig`
     (infrastructure — import-linter Contract 2/4). Campos necessários não existem em
     `RoundConfig`.
  2. `score_calc: FinalScoreCalculator` adicionado ao construtor (não na spec) —
     necessário para recompute do FinalScore com `rubric_biomed_score` preenchido.
  3. Linhas com `final_score=NaN` são processadas (decisão de design documentada):
     o juiz avalia `(question + answer)` independente do RAGAS, permitindo diagnóstico
     parcial sem bloquear Passada 3 por falha da Passada 2.

- **Linhas sem cobertura (96%)**:
  - 229: progress log (`judged_count % log_progress_every == 0` — sem teste com ≥10 linhas)
  - 305: type guard inalcançável pós-retry (satisfaz type-checker apenas)

- **TAREFA-307 (ComputeMetricsUseCase/WaveOrchestrator)**: injetar `RunJudgePassUseCase`
  com `FinalScoreCalculator` que inclua `rubric_biomed_score` com peso > 0 para Passada 3.
- **TAREFA-309/310 (Orquestrador)**: ao configurar `VLLMServerManager`, garantir que o
  servidor do juiz receba `VLLM_BATCH_INVARIANT=1` em `extra_env` (ADR-003 §9.2).
  `JudgePassReport.batch_invariant_assumed=True` é um lembrete para auditoria.
