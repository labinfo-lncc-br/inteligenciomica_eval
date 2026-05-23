# M0_TAREFA-006_A — FinalScoreCalculator (domain service)

**Data**: 2026-05-23
**Milestone**: M0 — Bootstrap e Domínio Core
**Épico**: E0
**Skill**: ml-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Implementar `FinalScoreCalculator` como serviço de domínio puro em
`src/inteligenciomica_eval/domain/services/final_score.py`, aplicando a
fórmula §7.1 do documento-base com pesos configuráveis, propagação de NaN
(ADR-007) e suíte de testes (unit + golden + property-based).

---

## Arquivos Criados / Modificados

| Arquivo | Papel |
|---|---|
| `src/inteligenciomica_eval/domain/services/final_score.py` | Implementação do serviço |
| `src/inteligenciomica_eval/domain/services/__init__.py` | Export de `FinalScoreCalculator` e `DEFAULT_WEIGHTS` |
| `tests/unit/domain/services/__init__.py` | Inicialização do subpacote de testes |
| `tests/unit/domain/services/test_final_score.py` | 40 testes unitários |
| `tests/golden/final_score_cases.json` | 7 casos golden com valores calculados à mão |

---

## Decisões Técnicas

### Fórmula e pesos canônicos

Implementados como constante `DEFAULT_WEIGHTS` (não hardcode inline no `compute`):

```
FinalScore = 0.45*answer_correctness + 0.20*faithfulness
           + 0.15*rubric_biomed_score + 0.10*context_recall
           + 0.05*context_precision + 0.05*answer_relevancy
```

`answer_similarity` e `bertscore_f1` **não** estão em `DEFAULT_WEIGHTS` —
métricas auxiliares, fora da fórmula (§7.1, anti-double-counting). Como não
aparecem no mapeamento de pesos, jamais chegam ao loop de cálculo.

### Tolerância de pesos

`_WEIGHTS_TOLERANCE = 1e-9` (conforme spec). Qualquer `|sum(weights) - 1.0| > 1e-9`
levanta `WeightsDoNotSumToOneError`. Valores a 1e-10 da unidade são aceitos
(distingue "erro de arredondamento vs. configuração errada").

### NaN propagation (ADR-007)

- Pesos `== 0.0` são pulados antes de ler o campo — evita `0 * NaN = NaN` do Python.
- Pesos `> 0.0` com campo NaN → retorno imediato de `FinalScore(NaN)`.
- Pesos `< 0.0` incluídos na soma sem verificação especial (caso fora de escopo; NaN
  propagaria naturalmente, comportamento seguro/conservador).

### `cast(float, getattr(...))` para mypy strict

`getattr(metrics, field_name)` retorna `Any`; `cast(float, ...)` mantém o
contrato de tipos sem `# type: ignore` direto na linha de cálculo. Válido
porque a construção já garante que `field_name ∈ _METRIC_VECTOR_FIELDS`.

### Cópia defensiva de `weights` no `__init__`

`self._weights = dict(weights)` isola o estado interno de mutações externas.
Testado em `test_construction_stores_defensive_copy`.

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|---|---|
| `_GOLDEN_PATH` usando `parents[4]` apontava para raiz do projeto em vez de `tests/` | Corrigido para `parents[3]` (tests/unit/domain/services → tests/) |
| Test parametrizado com `0.9999999999` esperava raise, mas valor está dentro de `_WEIGHTS_TOLERANCE=1e-9` (diferença = 1e-10) | Valores substituídos por `0.99999999` e `1.00000001` (diferença ≈ 1e-8 > 1e-9) |
| Ruff C408: `dict(k=v, ...)` em teste de monotonidade | Reescrito como literal `{"k": v, ...}` |

---

## Validação (DoD)

| Gate | Resultado |
|---|---|
| `uv run ruff check .` | ✅ All checks passed |
| `uv run ruff format --check .` | ✅ 33 files already formatted |
| `uv run mypy --strict src` | ✅ Success: no issues found in 16 source files |
| `uv run lint-imports` | ✅ 4 kept, 0 broken |
| `uv run pytest ... -n auto` (257 testes) | ✅ 257 passed |
| Coverage `final_score.py` (line + branch) | ✅ **100%** |
| Coverage total do projeto | ✅ **95.6%** (acima de 85%) |

---

## Critérios de Aceitação

| Critério | Status | Evidência |
|---|---|---|
| Pesos não somando 1.0 ⇒ `WeightsDoNotSumToOneError` na construção | ✅ | `test_construction_weights_not_sum_to_one_raises` (7 casos) |
| Métrica desconhecida ⇒ `ConfigValidationError` na construção | ✅ | `test_construction_unknown_metric_raises_config_error` |
| Golden: ≥ 5 casos numéricos com tolerância 1e-9 | ✅ | 7 casos (`case_01` … `case_07`); todos passing |
| Borda: todas métricas = 1.0 ⇒ 1.0 | ✅ | `case_01_all_ones` / `test_compute_all_ones_returns_one` |
| Borda: todas métricas = 0.0 ⇒ 0.0 | ✅ | `case_02_all_zeros` / `test_compute_all_zeros_returns_zero` |
| Borda: métrica com peso > 0 = NaN ⇒ NaN | ✅ | `case_06_nan_faithfulness` + parametrize 6 campos |
| Cobertura line+branch ≥ 95% do módulo | ✅ | 100% |
| Property-based: métricas em [0,1] + pesos válidos → resultado ∈ [0,1] | ✅ | `test_hypothesis_result_in_unit_interval` (300 exemplos) |
| Property-based: monotonicidade fraca em `answer_correctness` | ✅ | `test_hypothesis_monotone_answer_correctness` (300 exemplos) |
| Serviço puro — `import-linter` OK | ✅ | 4 contratos kept, 0 broken |

---

## Observações para Próximas Tarefas

- `DEFAULT_WEIGHTS` está exportado de `domain/services/__init__.py`; adaptadores de
  configuração podem sobrescrever via `Mapping[str, float]` sem alterar o domínio.
- O tratamento de peso negativo não foi especificado; se necessário no futuro,
  adicionar validação `min(weights.values()) >= 0.0` no `__init__`.
- Caso a fórmula §7.1 mude (ex.: inclusão de `bertscore_f1`), basta atualizar
  `DEFAULT_WEIGHTS` — o loop em `compute` é genérico.
