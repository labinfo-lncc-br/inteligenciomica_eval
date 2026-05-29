# M2_TAREFA-027_A — `RetryableMetricAdapter` (decorators de retry, ADR-007)

**Data**: 2026-05-29
**Milestone**: M2 — Avaliação automática (Camadas 1+2, juiz determinístico)
**Épico**: E2
**Skill**: python-engineer
**Prioridade / Tamanho**: P0 / S
**Referência arquitetural**: TAREFA-205 (§14.5) · ADR-007 (retry máx → NaN explícito) · Nota M2 item 4

## Objetivo

Implementar os decorators de resiliência da passada de julgamento:
`RetryableMetricSuiteAdapter` e `RetryableRubricJudgeAdapter`. Cada um envolve o port
correspondente adicionando retry async com backoff exponencial e **degradação explícita
para NaN-sentinel** (ADR-007), sem nunca propagar `MetricComputationError` ao caller.

## Arquivos Criados

- `src/inteligenciomica_eval/infrastructure/adapters/retryable_metric_adapter.py` —
  `RetryConfig`, `_score_with_retry` (helper genérico), os 2 decorators + 2 factories.
- `tests/unit/infrastructure/adapters/test_retryable_metric_adapter.py` — 10 testes.

## Decisões Técnicas

1. **Helper genérico `_score_with_retry` (TypeVar `_T`).** A lógica de retry é idêntica
   nos dois ports; extraí um helper `Callable[[], Awaitable[_T]]` + `Callable[[int], _T]`
   (factory do sentinel) para não duplicar. Os decorators só diferem no `wrapped.score` e
   no sentinel. mypy --strict valida a inferência do `_T` a partir das lambdas.
2. **Semântica do contador (reconciliação da spec).** A pseudo-lógica do Prompt A
   (`tentativa < max_retries: sleep; senão sentinel`) com `max_retries=3` produz:
   **4 chamadas** ao adapter interno (índices 0–3) e **3 esperas** `[1.0, 2.0, 4.0]`
   (uma antes de cada retry). O sentinel é devolvido quando o índice atinge `max_retries`,
   então `feedback="[retry_exhausted:3]"` (n = índice esgotado = `max_retries`). A
   descrição "3 falhas" do Prompt A é o rótulo do cenário; o contrato testável vinculante
   é o backoff `[1,2,4]` + `feedback:3`, ambos satisfeitos. Documentado na docstring.
3. **NaN parcial NÃO é retryável.** Só `MetricComputationError` (falha total de I/O
   sinalizada pelo adapter interno) entra no `except`. Um resultado com campo NaN sem
   exceção (parsing falhou no adapter interno, ADR-007) cai no `return await call()` —
   devolvido como está, sem retry. Testado e visível no código (não só nos testes).
4. **Exceção inesperada propaga.** O `except` captura **apenas** `MetricComputationError`;
   qualquer outra (bug) sobe imediatamente — testado com `RuntimeError`.
5. **`await asyncio.sleep` (nunca `time.sleep`).** Espera não bloqueia o event loop.
   Backoff `initial_wait_s * 2**attempt`. Testes mockam `asyncio.sleep` via
   `patch("asyncio.sleep", new_callable=AsyncMock)` — determinísticos e instantâneos.
6. **NaN-sentinels.** Camada 1: `Layer1Metrics` com 6 campos `math.nan`. Rubrica:
   `RubricResult(score=nan, feedback="[retry_exhausted:N]")`.
7. **`jitter` wired (não campo morto).** `jitter=False` por default (backoff exato nos
   testes). `jitter=True` soma `random.uniform(0, wait)` à espera — testado com
   `patch("random.uniform")` (cobertura 100%, sem branch morto).
8. **Diretório de teste.** Spec escreve `tests/unit/adapters/`, mas a convenção do projeto
   (CLAUDE.md §2 + todos os testes de adapter) é `tests/unit/infrastructure/adapters/`.
   Segui a convenção do projeto.

## Validação (DoD §14.2)

```
ruff check / format          → OK
mypy --strict src            → Success (34 source files)
lint-imports                 → 4 kept, 0 broken
pytest test_retryable_metric_adapter → 10 passed
pytest (full, -n 4)          → 759 passed, 13 skipped — 97.10% cobertura
retryable_metric_adapter.py  → 100% (line + branch)
```

## Critérios de Aceitação (TAREFA-027)

- [x] 2 decorators async (`async def score`); `isinstance(MetricSuitePort/RubricJudgePort)` True — `TestProtocolConformance`.
- [x] `RetryConfig` frozen com 3 campos; `jitter=False` por default.
- [x] Só `MetricComputationError` é retryada; NaN parcial devolvido sem retry; exceção inesperada propaga — 3 testes.
- [x] Retries esgotados → NaN-sentinel SEM exceção; `feedback="[retry_exhausted:3]"` — `TestRetryExhausted`.
- [x] Backoff `[1.0, 2.0, 4.0]` via spy de `asyncio.sleep` — `test_backoff_sequence_is_1_2_4`.
- [x] Logging: tentativa fallida e NaN-sentinel como WARNING.
- [x] Puro Python/stdlib (`asyncio`, `math`, `random`); cobertura 100% ≥ 95%; mypy --strict; import-linter OK.

## Observações para Próximas Tarefas

- **TAREFA-028 (Integração/E2E M2)**: fiará `ComputeMetricsUseCase` com
  `make_retryable_metric_suite(RAGASLayer1Adapter)` e
  `make_retryable_rubric_judge(PrometheusRubricJudgeAdapter)` (Nota M2 item 4 — sempre o
  decorado). O cenário "Sample 3" (falha→sucesso) exercita o backoff; "Sample 4" (3 falhas
  HTTP 500) exercita o NaN-sentinel via este decorator (com `respx` para o HTTP do juiz).
- O `aux_metrics` (determinístico) **não** é decorado — não faz I/O de rede.
