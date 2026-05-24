# M0_TAREFA-008_B — Auditoria do AggregationService

**Data**: 2026-05-24
**Milestone**: M0 — Core Domain
**Épico**: E0
**Skill**: code-reviewer / data-engineer / test-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Auditar a implementação de `AggregationService` da TAREFA-008 contra o prompt de
verificação: diff/PR local, arquitetura §4.4, ADR-007/ADR-010, golden de agregação,
testes unitários, cobertura do módulo e `lint-imports`.

---

## Arquivos Criados / Modificados

| Arquivo | Ação |
|---------|------|
| `docs/dev-log/M0_TAREFA-008_B_auditoria-aggregation-service.md` | Criado e corrigido |
| `tests/unit/domain/services/test_aggregation.py` | 2 testes adicionados (linhas 429-458) |

---

## Decisões Técnicas

### 1. Base normativa disponível

O repositório contém:
- `docs/arquitetura_detalhada_validacao_inteligenciomica.md` com:
- §4.4 / linha 267: `AggregationService` "trata `NaN` por exclusão explícita e reporta a contagem de exclusões".
- ADR-007 (linha 502): "agregação **exclui** NaN e reporta a contagem."
- ADR-010 (linha 529): `critical_failure_flag=None` indica observação não anotada.
- `docs/visao_alto_nivel_validacao_inteligenciomica.md` com a definição das métricas agregadas e do
  `RankScore`, incluindo `CriticalFailureRate` como proporção de respostas com
  `critical_failure_flag = 1` (§7.2/§7.3).

O prompt de TAREFA-008 é a especificação operacional e está completo no workspace.
O contrato pode ser derivado do documento-base + arquitetura detalhada + prompt.

### 2. Resultado geral da auditoria

**PASS** (após análise aprofundada).

---

## Falso Positivo: `critical_failure_rate` e `final_score=NaN`

### Achado original

O rascunho inicial desta auditoria classificou como divergência importante o facto de
`_critical_failure_rate()` incluir no denominador linhas com `final_score=NaN` mas
`critical_failure_flag ∈ {0, 1}`, alegando contradição com ADR-007.

### Por que é um falso positivo

O prompt de TAREFA-008 enuncia explicitamente quais cálculos excluem NaN:

> "Tratamento de NaN (ADR-007): `final_score` NaN é EXCLUÍDO dos cálculos de
> **mean / median / min / IQR / failure_rate**; conte os excluídos em `n_excluded_nan`."

`critical_failure_rate` **não consta dessa lista**. A regra de exclusão que governa
`critical_failure_rate` é o ADR-010, que diz apenas:

> "Linhas com flag `None` (não anotadas) NÃO contam no denominador de crítico."

Há duas razões semânticas independentes para isso ser correto:

1. **Orthogonalidade dos pipelines.** O `final_score` NaN sinaliza falha do pipeline
   de scoring (juiz indisponível, erro de parsing), não ausência de julgamento humano.
   Um clínico pode e deve anotar `critical_failure_flag=1` mesmo quando o score
   automático não pôde ser computado — são informações de naturezas distintas.

2. **Exclusão silenciosa seria clinicamente perigosa.** Se uma linha com `flag=1` fosse
   excluída do denominador porque `final_score=NaN`, a taxa de falha crítica seria
   sub-estimada, comprometendo a segurança do sistema.

A implementação `src/inteligenciomica_eval/domain/services/aggregation.py:86-96`
está correta conforme a especificação.

### O que o achado identificou corretamente

Embora a conclusão (corrigir o código) estivesse errada, o achado evidenciou que
**o comportamento intencional não estava documentado por teste**. Dois testes foram
adicionados para fechar essa lacuna:

- `test_critical_rate_nan_score_annotated_counts_in_denominator` — exercita diretamente
  `_critical_failure_rate()` com `final_score=NaN` + `flag=1`.
- `test_aggregate_all_critical_rate_nan_score_annotated_counts` — valida o comportamento
  via `aggregate_all`, verificando que `n_observations` e `n_excluded_nan` refletem
  apenas o `final_score`, não o `critical_failure_flag`.

---

## Validação (DoD) — PASS/FAIL por critério do prompt

| # | Critério | Status | Evidência |
|---|----------|--------|-----------|
| 1 | `ConfigAggregate` tem todos os campos do §7.2 | ✅ PASS | `aggregation.py:50-61` — 12 campos: `base`, `llm`, `mean_score`, `median_score`, `min_score`, `iqr`, `failure_rate`, `critical_failure_rate`, `win_rate`, `rank_score`, `n_observations`, `n_excluded_nan` |
| 2 | `failure_rate` reutiliza `EvaluationResult.is_failure(threshold)` | ✅ PASS | `aggregation.py:220`; definição canônica em `entities.py:165-177`; não reimplementa o limiar |
| 3 | `NaN` excluído de `mean/median/min/IQR/failure_rate` e contado; config 100% NaN não quebra | ✅ PASS | `aggregation.py:209-220`; caso `n_obs=0` retorna NaN sem exceção (`:213-214`); testado em `test_aggregation.py:327-338`; `n_excluded_nan` correto em `:341-350` |
| 4 | `critical_failure_rate`: `flag=None` fora do denominador; `NaN` de score **não** afeta | ✅ PASS | `aggregation.py:86-96`; testes `test_aggregation.py:164-204` (flag=None) e `:429-458` (NaN score + flag anotado — adicionados nesta auditoria) |
| 5 | `win_rate` cross-config por `question_id`; empate divide `1/k`; testado | ✅ PASS | `aggregation.py:99-146`; 2-way tie: `test_aggregation.py:458-471`; 3-way tie: `:474-484`; golden case_03 confirma `win_rate=0.5` |
| 6 | IQR com método de quantil documentado; golden numérico confere | ✅ PASS | `statistics.quantiles(method='inclusive')` em `aggregation.py:74-83`; testes de borda `:130-156`; Q1/Q3 verificados manualmente (ver seção abaixo) |
| 7 | Serviço puro: stdlib apenas; sem pandas/polars/numpy; sem logging; import-linter OK | ✅ PASS | Imports em `aggregation.py:3-14`: apenas `math`, `statistics`, `collections` + domínio; `lint-imports`: 4/4 contratos kept |
| 8 | `RankScoreCalculator` injetado no `__init__`, não hardcoded | ✅ PASS | `aggregation.py:168-169`; uso em `:225-231`; teste `test_aggregation.py:275-279` |
| 9 | Golden ≥4 casos (NaN excluído + empate); cobertura módulo ≥95%; DoD §14.2 | ✅ PASS | Golden com 4 casos; cobertura medida: **100% line+branch**; `ruff` e `mypy --strict`: OK |

---

## Tabela de divergências

| Critério | Arquivo:linha | Gravidade | Resolução |
|---------|---------------|-----------|-----------|
| Comportamento de `critical_failure_rate` com `final_score=NaN` + flag anotado não estava coberto por teste | `test_aggregation.py` (ausência) | Baixa | Adicionados 2 testes que documentam o comportamento intencional |

---

## Recomputação manual independente

### Caso `case_01_two_configs_clear_winner` — config `llm-b`

(`tests/golden/aggregation_cases.json`, linhas 29-42)

| Métrica | Cálculo | Esperado no golden |
|---------|---------|-------------------|
| Scores válidos | `[0.60, 0.75, 0.50]` | — |
| `mean` | `(0.60+0.75+0.50)/3 = 1.85/3` | `0.6166666667` ✅ |
| `median` | valor central de `[0.50, 0.60, 0.75]` | `0.60` ✅ |
| `min` | `0.50` | `0.50` ✅ |
| IQR (`inclusive`) | Q1=0.55, Q3=0.675 → `0.125` | `0.125` ✅ |
| `failure_rate` | `0.60<0.70` e `0.50<0.70` → 2/3 | `0.6666666667` ✅ |
| `critical_failure_rate` | flags `[1, 0, 1]` → 2/3 | `0.6666666667` ✅ |
| `win_rate` | perde Q1, Q2, Q3 para llm-a | `0.0` ✅ |
| `rank_score` | `0.50×0.60 + 0.20×(1/3) + 0.15×0.0 − 0.15×(2/3) = 4/15` | `0.26666...` ✅ |

### Verificação do IQR para `case_02` — `[0.70, 0.80]` (2 valores)

Método `inclusive`, n=2: posição = p × (n−1).
- Q1: 0.25 × 1 = 0.25 → 0.70 + 0.25 × 0.10 = **0.725**
- Q3: 0.75 × 1 = 0.75 → 0.70 + 0.75 × 0.10 = **0.775**
- IQR = 0.775 − 0.725 = **0.050** ✅

---

## Execuções realizadas

```bash
uv run pytest tests/unit/domain/services/test_aggregation.py -q
# 49 passed in 0.14s  (47 originais + 2 adicionados nesta auditoria)

uv run pytest tests/unit/domain/services/test_aggregation.py \
    --cov=inteligenciomica_eval.domain.services.aggregation \
    --cov-report=term-missing --cov-branch --cov-fail-under=95 -q
# aggregation.py: 100% line, 100% branch

uv run lint-imports
# Contracts: 4 kept, 0 broken
```

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| Campos de `ConfigAggregate` presentes e corretos | ✅ |
| `failure_rate` usa `EvaluationResult.is_failure()` | ✅ |
| `NaN` excluído dos agregados de score e contado | ✅ |
| `critical_failure_rate` exclui `flag=None`; NaN de score não afeta (ADR-010) | ✅ |
| `win_rate` cross-config com empate `1/k` | ✅ |
| IQR método `inclusive` documentado e coberto por golden/testes | ✅ |
| Serviço puro + import-linter OK | ✅ |
| DI de `RankScoreCalculator` | ✅ |
| Cobertura do módulo ≥ 95% (obtido: 100%) | ✅ |

---

## Observações para Próximas Tarefas

- O comportamento de `critical_failure_rate` com `final_score=NaN` agora está
  documentado por testes e este relatório. Nenhuma alteração no código de produção
  é necessária.
- `AggregationService` está pronto para consumo pelo `AggregateResultsUseCase`
  (TAREFA-403), que produzirá `RankScoreInputs` preservando a semântica NaN do ADR-007.
