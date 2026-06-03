# Relatório de Validação do Juiz LLM — Cohen's κ

**Data de geração:** 2026-06-03 03:11:43 UTC
**run_id:** `round_1_20260601`
**round_id:** `A`

---

## 1. Metadados do Juiz

| Campo | Valor |
|---|---|
| Modelo do juiz | `prometheus-2-8x7b-rc (simulado)` |
| Determinismo confirmado (`batch_invariant`) | ✅ Sim |
| Threshold de binarização | `0.5` |

> **Semântica da binarização:** `judge_binary = 1` quando `rubric_biomed_score < 0.5`
> (juiz concorda com falha crítica quando atribui score baixo).

---

## 2. Tamanhos Amostrais

| Descrição | N |
|---|---|
| Total de linhas no Parquet | 52 |
| Linhas com anotação humana | 20 |
| Linhas válidas (anotadas + score não-NaN) | 18 |
| Excluídas por NaN do juiz (`n_excluded_nan`) | 2 |


> ⚠️ **Atenção:** 2 linha(s) com anotação humana foram excluídas porque o juiz retornou NaN (ADR-007).


---

## 3. Cohen's κ

**Cohen's κ = 0.6842 (substancial)**

### Interpretação — escala de Landis & Koch


0.60 ≤ κ < 0.80 — **substancial** — suporte forte ao uso como métrica de avaliação.
A concordância é robusta; o juiz é adequado para uso em produção com monitoramento ocasional.


---

## 4. Matriz de Confusão

> Referência = anotação humana (`critical_failure_flag`); Predição = juiz binarizado.

|  | **Juiz: Falha (1)** | **Juiz: OK (0)** |
|---|---|---|
| **Humano: Falha (1)** | TP = 7 | FN = 1 |
| **Humano: OK (0)** | FP = 1 | TN = 9 |

---

## 5. Primeiras Discordâncias (até 20)


| row_id | rubric_biomed_score | judge_binary | critical_failure_flag |
|---|---|---|---|

| `abc123def456789012345678901234567890123456789012345678901234` | 0.5200 | 0 | 1 |

| `def456abc789012345678901234567890123456789012345678901234567` | 0.4800 | 1 | 0 |




---

_Relatório gerado automaticamente por `ielm-eval validate-judge`._
