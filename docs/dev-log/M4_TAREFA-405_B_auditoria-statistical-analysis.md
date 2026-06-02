# M4_TAREFA-405_B — Auditoria do StatisticalAnalysisUseCase

**Data**: 2026-06-01
**Milestone**: M4 — Análise Estatística e Publicação
**Tarefa auditada**: M4-TAREFA-405A
**Resultado**: **FAIL**
**Auditor**: Codex (Prompt B)

---

## Achados

### 1. Bloqueador — o prompt exige `multipletests`, mas o use case implementa um algoritmo próprio

**Arquivo**: `src/inteligenciomica_eval/application/statistical_analysis.py:76-147`

O prompt A da TAREFA-405 fixa explicitamente: “Aplicar correção via
`statsmodels.stats.multitest.multipletests`”. O prompt B também pede verificar que a
correção múltipla é aplicada com `multipletests` no use case. A implementação atual
não importa nem usa `multipletests`; em vez disso, introduz `_bh_correction`,
`_holm_correction` e `_correct_pvalues`.

Os testes mostram que o algoritmo local está coerente para os cenários cobertos, mas
isso continua sendo um desvio objetivo da especificação do prompt. Sem aprovação
explícita dessa mudança de abordagem, a tarefa não pode ser considerada conforme.

### 2. Bloqueador — `top_llm_by_friedman` não calcula “vitórias”; ele conta aparições em pares significativos

**Arquivos**:
- `src/inteligenciomica_eval/application/statistical_analysis.py:153-180`
- `src/inteligenciomica_eval/domain/value_objects.py:406-409`
- `tests/unit/application/test_statistical_analysis.py:330-381`

O contrato funcional pede “LLM com mais vitórias no Nemenyi”. A implementação atual
incrementa contadores para **ambos** os lados de cada par significativo:

```python
wins[pair.llm_a] += 1
wins[pair.llm_b] += 1
```

Isso mede frequência de participação em diferenças significativas, não vitórias. Como
`NemenyiPair` só carrega `(llm_a, llm_b, p_value, significant)` e não contém direção,
o algoritmo atual pode marcar como “top” um LLM apenas por aparecer em muitos pares,
inclusive se ele for o pior modelo. O próprio docstring do VO admite isso como
“proxy”, o que confirma o desvio da semântica pedida.

Os testes também validam essa heurística de aparição, então a lacuna de modelagem
permanece sem cobertura de um conceito real de “vitória”.

---

## Verificações confirmadas

- `StatsReport` é frozen dataclass e contém os campos exigidos.
- `tests=("wilcoxon",)` chama apenas o adapter de Wilcoxon; Friedman/MLM não são chamados.
- `base_difference_significant` é derivado com `any(r.significant for r in wilcoxon_reports)`.
- O JSON de `StatsReport` é criado, parseável e serializa `NaN` como `null`.
- `application/statistical_analysis.py` não importa `scipy` nem `statsmodels`.

---

## Recomputação manual do caso BH pedido no prompt B

Para os p-values `[0.04, 0.03, 0.02]` com Benjamini-Hochberg:

1. Ordenados: `[0.02, 0.03, 0.04]`
2. Ajustes brutos: `[0.02*3/1, 0.03*3/2, 0.04*3/3] = [0.06, 0.045, 0.04]`
3. Monotonicidade da direita para a esquerda: `[0.04, 0.04, 0.04]`

Resultado esperado:

```text
0.04, 0.04, 0.04
```

Os testes da implementação batem com esses valores.

---

## Comandos executados

### Grep pedido no prompt B (item 6)

Comando:

```text
grep -n "import scipy\|import statsmodels" src/inteligenciomica_eval/application/statistical_analysis.py
```

Saída:

```text
(sem saída)
```

### Testes unitários

```text
uv run pytest tests/unit/application/test_statistical_analysis.py -v
28 passed
```

### Import-linter

```text
uv run lint-imports
Contracts: 4 kept, 0 broken.
```

### Type check

```text
uv run mypy --strict src
Success: no issues found in 48 source files
```

---

## Conclusão

Os gates estão verdes e a correção BH/Holm está matematicamente consistente nos testes,
mas a tarefa ainda falha por dois desvios materiais do prompt: não usar
`multipletests` como especificado e expor `top_llm_by_friedman` com semântica de
“proxy por aparição” em vez de vitórias reais.
