# M4_TAREFA-403_D — Correção pós-auditoria: NaN→null e guarda vazio

**Data**: 2026-06-01
**Milestone**: M4 — Decisão executiva da Rodada 1
**Épico**: E6 — Agregação
**Skill**: data-engineer
**Prioridade / Tamanho**: P0 / S (correção de 2 bloqueadores identificados na auditoria Codex _B_)

---

## Problemas reportados pelo Codex (FAIL)

### Bloqueador 1 — JSON inválido com `allow_nan=True`

`json.dumps(..., allow_nan=True)` produz tokens `NaN` no arquivo quando campos como
`iqr`, `critical_failure_rate` ou `rank_score.value` são `float('nan')`. Isso não é
JSON válido RFC 8259 e quebra parsers não-permissivos.

**Arquivo:** `application/aggregate_results.py:121`

### Bloqueador 2 — `IndexError` quando resultado está vazio

`aggregates[0]` levantava `IndexError` quando `AggregationService.aggregate_all()`
retornava `()` (ex.: `run_id` inexistente). Sem tratamento determinístico e sem teste.

**Arquivo:** `application/aggregate_results.py:116`

---

## Correções aplicadas

### Fix 1 — Função `_nan_to_null` + `json.dumps` sem `allow_nan`

```python
def _nan_to_null(obj: Any) -> Any:
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: _nan_to_null(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_nan_to_null(v) for v in obj]
    return obj
```

Chamada antes de `json.dumps`: `_nan_to_null([dataclasses.asdict(a) for a in aggregates])`.
NaN serializado como `null` (válido RFC 8259). `allow_nan` removido.

### Fix 2 — Guarda determinística para resultado vazio

```python
if not aggregates:
    raise ValueError(
        f"No results found for run_id={inp.run_id!r}, "
        f"round_id={inp.round_id!r}, phase={inp.phase!r}. "
        "Cannot aggregate an empty result set."
    )
```

Lançado antes de `aggregates[0]`, com mensagem clara identificando os parâmetros.

---

## Testes adicionados

| Teste | Cobre |
|-------|-------|
| `test_empty_results_raises_value_error` | Bloqueador 2: `ValueError` com mensagem "No results found" |
| `test_json_nan_serialized_as_null` | Bloqueador 1: token NaN ausente; `null` no JSON; `json.loads` sem erro |

---

## Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/inteligenciomica_eval/application/aggregate_results.py` | `_nan_to_null()` + guarda vazio + `import Any` |
| `tests/unit/application/test_aggregate_results_use_case.py` | +2 testes (total: 12) |

---

## Validação pós-correção (DoD)

| Critério | Status |
|----------|--------|
| 12/12 testes PASS | ✅ |
| `mypy --strict` | ✅ 0 erros |
| `ruff check` + `ruff format` | ✅ 0 erros |
| `lint-imports` (4 contratos) | ✅ KEPT |
| Cobertura módulo | ✅ 100% |
| Suite total (`-n 4`, `not integration`) | ✅ 959 passed, 92.59% |
| JSON RFC 8259: `"NaN" not in raw` | ✅ verificado em teste |
| `json.loads(raw)` sem erro | ✅ verificado em teste |
| `ValueError` com mensagem descritiva para vazio | ✅ verificado em teste |
