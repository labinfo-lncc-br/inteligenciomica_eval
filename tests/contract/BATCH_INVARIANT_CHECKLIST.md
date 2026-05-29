# BATCH_INVARIANT_CHECKLIST — TAREFA-022

Contrato §4.3 / ADR-003: `batch_invariant is True` ⟺ a métrica veio do juiz
determinístico (`DeterminismRegime.JUDGE`); `False` para o gerador (`GENERATOR`).

Legenda de status: ✓ OK (já existia) · ✗ corrigido nesta tarefa · ⚠ ausente/manual.

| # | Item | Arquivo:linha | Status |
|---|------|---------------|--------|
| 1 | `DeterminismRegime.JUDGE` definido | `src/inteligenciomica_eval/domain/value_objects.py:27` | ✓ OK (M0/TAREFA-003) |
| 2 | `batch_invariant` derivado de `JUDGE` no `EvaluationResult` | `src/inteligenciomica_eval/domain/entities.py:166,184` | ✗ adicionado (property derivada) |
| 3 | `batch_invariant` incluído no schema pyarrow do Parquet | `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:58` | ✓ OK (M0/TAREFA-009) |
| 4 | `batch_invariant` gravado a partir da entidade em `to_row` | `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:205` | ✗ refatorado p/ usar `result.batch_invariant` (mesmo valor) |
| 5 | `PrometheusJudgeAdapter.determinism_regime == JUDGE` | `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py:87` | ✗ adicionado (atributo de instância) |

**Nenhum item marcado como `⚠ ausente`.**

## Notas de decisão

- **Item 2 — invariante estrutural, não validação em runtime.**
  `EvaluationResult.batch_invariant` é uma *property derivada* de
  `determinism_regime` (não um campo independente). A inconsistência do §4.3
  (`regime=JUDGE` com `batch_invariant=False`) é **irrepresentável**: não há
  atributo separado nem setter. Por isso a TAREFA-022 **não** levanta exceção de
  domínio nem loga WARNING no writer — o invariante é garantido por construção.
  Comprovado pelos testes do cenário (d) em
  `tests/contract/test_batch_invariant_contract.py::TestInvariantByConstruction`.

- **Item 1c do schema (não-nulo).** A coluna é
  `pa.field("batch_invariant", pa.bool_(), nullable=False)` — obrigatória, nunca
  NULL.

- **Item 4 — sem mudança de comportamento.** `to_row` antes calculava
  `result.determinism_regime == DeterminismRegime.JUDGE` inline; agora delega à
  property `result.batch_invariant`, que computa exatamente o mesmo booleano.
  Apenas a fonte única de verdade mudou (M1 não é afetado).

## Cenários de teste (todos passam)

| Cenário | Teste |
|---------|-------|
| (a) adapter expõe `JUDGE` sem rede | `TestAdapterRegime::test_prometheus_judge_regime_is_judge` |
| (b) `with_metrics(..., JUDGE)` → `True` (unit puro) | `TestWithMetricsRegime::test_with_metrics_judge_sets_batch_invariant_true` |
| (c) round-trip Parquet real `True` | `TestParquetRoundTrip::test_judge_round_trip_persists_batch_invariant_true` |
| (d) invariante §4.3 por construção | `TestInvariantByConstruction` (3 testes) |
| (e) round-trip Parquet real `False` (GENERATOR) | `TestParquetRoundTrip::test_generator_round_trip_persists_batch_invariant_false` |
