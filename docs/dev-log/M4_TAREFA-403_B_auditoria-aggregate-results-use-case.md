# M4_TAREFA-403_B — Auditoria AggregateResultsUseCase

**Data**: 2026-06-01
**Milestone**: M4 — Decisão executiva da Rodada 1
**Épico**: E6 — Agregação
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Auditar a implementação da TAREFA-403 contra o prompt B, verificando injeção do
`AggregationService`, ausência de lógica de agregação no use case, ordenação,
filtro por `run_id`, persistência JSON, golden e gates locais.

## Arquivos Inspecionados

- `src/inteligenciomica_eval/application/aggregate_results.py`
- `tests/unit/application/test_aggregate_results_use_case.py`
- `tests/golden/aggregate_results_expected.json`
- `src/inteligenciomica_eval/domain/services/aggregation.py`
- `src/inteligenciomica_eval/domain/ports.py`
- `docs/m4_tarefa_403.md`

## Validações Executadas

- `uv run pytest tests/unit/application/test_aggregate_results_use_case.py -v` → `10 passed`
- `uv run lint-imports` → `4 kept, 0 broken`
- `uv run mypy --strict src` → `Success: no issues found in 46 source files`

## Recomputação Manual do Golden

Config A (`IDx_400k` / `llama3-8b`) tem 5 scores válidos de `0.80` e threshold `0.70`.
Logo, `failure_rate = 0 / 5 = 0.0`. O valor confere com
`tests/golden/aggregate_results_expected.json`.

## Divergências Encontradas

| Critério | Arquivo:linha | Gravidade | Observação |
|---|---|---|---|
| JSON de sumário criado e legível | `src/inteligenciomica_eval/application/aggregate_results.py:121-123` | Bloqueador | O use case grava `json.dumps(..., allow_nan=True)`. Como `AggregationService` retorna `NaN` em cenários normais (`iqr`, `critical_failure_rate`, `rank_score` sem anotação suficiente), o arquivo persistido contém tokens `NaN`, que não são JSON válido RFC 8259. Reproduzido localmente com 1 resultado sem anotação humana. |
| `best_config` = primeiro da lista | `src/inteligenciomica_eval/application/aggregate_results.py:116` | Bloqueador | Quando `reader.load(...)` retorna zero resultados para o `run_id`/`phase`, `aggregate_all()` devolve `()`, e o acesso `aggregates[0]` explode com `IndexError`. Reproduzido localmente com `run_id` inexistente. Não há teste cobrindo o caso vazio. |

## Observações

- A injeção de `AggregationService` está correta via `__init__`.
- Não há reimplementação indevida de média/mediana/IQR/failure_rate/win_rate no use case.
- A ordenação por `rank_score` descrescente com `NaN` ao final está correta.
- O filtro por `run_id` foi implementado via `ResultReaderPort.load(..., run_id=...)`.
  Embora difira do passo literal do prompt, o contrato atual do port já suporta esse
  filtro e o teste cobre o comportamento observado.

## Recomendação

**FAIL** até:

1. serializar `NaN`/`Infinity` para uma forma JSON válida (`null` ou encoder explícito),
2. tratar seleção vazia de forma determinística no use case, com teste dedicado.
