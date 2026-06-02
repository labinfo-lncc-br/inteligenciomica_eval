# M4_TAREFA-403_D — Reauditoria AggregateResultsUseCase

**Data**: 2026-06-01
**Milestone**: M4 — Decisão executiva da Rodada 1
**Épico**: E6 — Agregação
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Reauditar a TAREFA-403 após as correções dos dois bloqueadores apontados na
auditoria B: JSON inválido com tokens `NaN` e falha com `IndexError` para
seleção vazia.

## Arquivos Inspecionados

- `src/inteligenciomica_eval/application/aggregate_results.py`
- `tests/unit/application/test_aggregate_results_use_case.py`

## Validações Executadas

- `uv run pytest tests/unit/application/test_aggregate_results_use_case.py -v` → `12 passed`
- `uv run mypy --strict src` → `Success: no issues found in 46 source files`
- `uv run lint-imports` → `4 kept, 0 broken`

## Verificações dos Bloqueadores

### 1. JSON RFC 8259

Confirmado o uso de `_nan_to_null()` antes da persistência do sumário:

- `src/inteligenciomica_eval/application/aggregate_results.py:22-35`
- `src/inteligenciomica_eval/application/aggregate_results.py:144-147`

Reproduzi localmente um cenário com `iqr=NaN`, `critical_failure_rate=NaN` e
`rank_score.value=NaN`. O arquivo gerado:

- não contém o token `NaN`
- é parseável com `json.loads`
- serializa esses campos como `null`

O comportamento também está coberto por
`tests/unit/application/test_aggregate_results_use_case.py::test_json_nan_serialized_as_null`.

### 2. Caso vazio

Confirmada a guarda explícita para agregado vazio:

- `src/inteligenciomica_eval/application/aggregate_results.py:124-139`

Agora `execute()` levanta `ValueError` determinístico com `run_id`, `round_id`
e `phase` na mensagem, em vez de falhar com `IndexError`. O comportamento está
coberto por
`tests/unit/application/test_aggregate_results_use_case.py::test_empty_results_raises_value_error`.

## Parecer

Nenhum novo achado. Os dois bloqueadores foram corrigidos adequadamente e a
implementação segue consistente com o prompt da TAREFA-403.

**Resultado final da reauditoria:** PASS
