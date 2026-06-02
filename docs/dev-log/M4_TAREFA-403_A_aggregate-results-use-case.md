# M4_TAREFA-403_A — AggregateResultsUseCase

**Data**: 2026-06-01
**Milestone**: M4 — Decisão executiva da Rodada 1
**Épico**: E6 — Agregação
**Skill**: data-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Implementar `AggregateResultsUseCase` em `application/aggregate_results.py`: orquestrador
que lê resultados do Parquet via `ResultReaderPort`, delega 100% da agregação ao
`AggregationService` injetado (domínio M0/TAREFA-008), ordena por `rank_score` descrescente
e persiste um sumário JSON.

---

## Arquivos Criados / Modificados

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `src/inteligenciomica_eval/application/aggregate_results.py` | Criado | Use case + DTOs |
| `tests/unit/application/test_aggregate_results_use_case.py` | Criado | 10 testes unitários |
| `tests/golden/aggregate_results_expected.json` | Criado | Golden file (2 ConfigAggregates) |

---

## Decisões Técnicas

### 1. Filtro por `run_id` via `ResultReaderPort.load`

O spec sugeria carregar sem `run_id` e filtrar manualmente. Porém, `EvaluationResult`
não expõe `run_id` (embutido no hash SHA-256 do `RowId`), tornando a filtragem
in-memory impossível. A solução canônica é passar `run_id=inp.run_id` diretamente ao
`ResultReaderPort.load`, que já suporta o parâmetro. O teste `test_filter_by_run_id`
valida o comportamento com dois runs distintos.

### 2. NaN em `rank_score` — posição no final da ordenação

`float('nan')` não é comparável em Python. Para garantir comportamento determinístico,
a chave de ordenação substitui NaN por `float('-inf')`, enviando configs sem rank_score
computável para o final da lista descendente.

### 3. Serialização JSON com `dataclasses.asdict`

`dataclasses.asdict` produz dicts aninhados para sub-dataclasses (`BaseId`, `LLMId`,
`RankScore`), resultando em `{"base": {"value": "IDx_400k"}, ...}`. `json.dumps` com
`allow_nan=True` para compatibilidade com `critical_failure_rate=NaN` (Camada 3
não executada).

### 4. Cenário golden

- Config A (IDx_400k/llama3-8b): 5 scores válidos de 0.80 (q03-s42 = NaN excluído),
  1 anotação flag=0 → rank_score=0.75
- Config B (ID_230K/mistral-7b): 6 scores de 0.50, failure_rate=1.0, 1 anotação flag=0
  → rank_score=0.25

Valores calculados independentemente, confirmados pelo teste `test_golden_aggregate_values`.

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| `make_generated_answer()` não aceita `run_id` | Passar `row_id=make_row_id(run_id=..., ...)` explicitamente |
| `_build_golden_results` complexo com ternário NaN | Refatorado em estrutura linear clara (loop simples + `make_evaluation_result(final_score=nan)`) |

---

## Validação (DoD)

| Critério | Status |
|----------|--------|
| `AggregationService` injetado — verificado via mock | ✅ `test_aggregation_service_is_injected_not_instantiated` |
| Zero lógica de agregação no use case | ✅ verificado via inspeção + mock que captura chamada |
| `best_config` = maior `rank_score` | ✅ `test_best_config_is_highest_rank_score` |
| `n_nan_excluded` correto | ✅ `test_n_nan_excluded_is_sum_of_all_configs` |
| Ordenação desc por `rank_score` | ✅ `test_aggregates_ordered_descending_by_rank_score` |
| NaN vai para o final | ✅ `test_nan_rank_score_goes_to_end` |
| JSON criado com campos corretos | ✅ `test_json_summary_created_with_correct_fields` |
| `dataclasses.asdict` (estrutura aninhada) | ✅ `test_json_uses_dataclasses_asdict_structure` |
| Filtro por `run_id` | ✅ `test_filter_by_run_id_ignores_other_runs` |
| Golden confirma valores independentes | ✅ `test_golden_aggregate_values` |
| `mypy --strict` | ✅ 0 erros |
| `ruff check` + `ruff format` | ✅ 0 erros |
| `lint-imports` (4 contratos) | ✅ KEPT |
| Cobertura do módulo ≥ 90% | ✅ 100% |
| Suite completa (`-n 4`, `not integration`) | ✅ 957 passed, 92.59% total |

---

## Critérios de Aceitação

Todos os critérios da TAREFA-403 (tabela §14.7) atendidos:
- `AggregationService` injetado (não instanciado internamente)
- Zero lógica de agregação no use case
- `best_config` é o de maior `rank_score`
- `n_nan_excluded` correto
- JSON de sumário criado e legível
- Golden confirma valores independentes
- `mypy --strict`; `lint-imports`; cobertura ≥ 90%

---

## Observações para Próximas Tarefas

- TAREFA-404 (`StatsPort` adapters) é a próxima dependência no DAG.
- O JSON de sumário usa `allow_nan=True` — se for necessário JSON válido (RFC 8259),
  substituir NaN por `null` com um encoder customizado (decisão para TAREFA-408
  `HTMLReportAdapter`).
- O `data_dir` do use case pode ser wired via `AppSettings.data_dir` no CLI
  (TAREFA-408 `analyze` command).
