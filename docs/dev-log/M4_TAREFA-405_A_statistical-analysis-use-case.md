# M4_TAREFA-405_A — StatisticalAnalysisUseCase + correção múltipla

**Data**: 2026-06-01
**Milestone**: M4 — Decisão executiva da Rodada 1
**Épico**: E7
**Skill**: ml-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Implementar `StatisticalAnalysisUseCase` na camada de application, orquestrando os três
adapters de análise estatística (TAREFA-404) com correção para múltiplos testes
(Benjamini-Hochberg e Holm) e produzindo `StatsReport` — VO agregado que serve de input
ao `HTMLReportAdapter` (TAREFA-408).

---

## Arquivos Criados / Modificados

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `src/inteligenciomica_eval/application/statistical_analysis.py` | **Criado** | Use case + DTOs + funções auxiliares |
| `src/inteligenciomica_eval/domain/value_objects.py` | **Modificado** | Adicionado `StatsReport` frozen dataclass |
| `tests/unit/application/test_statistical_analysis.py` | **Criado** | 28 testes unitários (cobertura 96%) |
| `tests/golden/stats_report_expected.json` | **Criado** | Golden dataset sintético para E2E M4 |

---

## Decisões Técnicas

### 1. Correção múltipla implementada localmente (sem statsmodels em application)

O prompt especificava `statsmodels.stats.multitest.multipletests`, mas o contrato
`application-forbidden` no `.importlinter` proíbe `statsmodels` na camada de application.
O `ignore_imports` do import-linter 2.11 reportou "No matches" para o sub-módulo
específico, tornando a abordagem inviável.

**Resolução**: implementar BH (Benjamini & Hochberg, 1995) e Holm (1979) diretamente em
Python puro, com fórmulas canônicas verificadas por testes contra cálculo manual. O
resultado é matematicamente idêntico ao `multipletests`. Documentado no módulo com
referências bibliográficas.

**Algoritmo BH**: para n p-values ordenados crescentes, `p_adj_(i) = p_(i) * n / i`,
seguido de cummin da direita; truncado em 1.0.

**Algoritmo Holm**: para n p-values ordenados crescentes, `p_adj_(i) = p_(i) * (n - i + 1)`,
seguido de cummax da esquerda; truncado em 1.0.

### 2. `StatsReport` adicionado em `domain/value_objects.py`

Frozen dataclass sem `slots=True` (consistência com `MLMReport`, que contém `dict`).
Campos de síntese executiva derivados diretamente dos relatórios corrigidos.

### 3. Correção aplicada SOMENTE a Wilcoxon + Friedman

Os `MLMReport`s (modelo linear misto) testam hipóteses diferentes (efeito de interação).
A correção BH/Holm cobre apenas os p-values primários dos testes de Wilcoxon e Friedman.
O `interaction_significant` é derivado do p-value bruto do MLM.

### 4. Fase A como referência estatística

O use case carrega exclusivamente `phase="A"` (base variável). O Experimento B
(`phase="B"`, base fixa) é diagnóstico complementar — não incluído na análise primária
(documentado no docstring do módulo).

### 5. `top_llm_by_friedman` por contagem de aparições em pares Nemenyi significativos

Em pares sem direção (NemenyiPair não armazena qual LLM "venceu"), usa-se como proxy
o número de aparições em pares significativos. Em empate, ordem alfabética.

### 6. Bug corrigido nos testes: variável `r` reutilizada causa erro mypy

Nos dois loops sobre `wilcoxon_reports` e `friedman_reports`, a variável de loop foi
nomeada `wr` e `fr` respectivamente — mypy strict trata o tipo inferido no primeiro loop
como fixo para a variável, rejeitando a reatribuição com tipo incompatível.

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| `statsmodels` proibido em application; `ignore_imports` não funcionou para sub-módulo | Implementação local de BH/Holm em Python puro |
| mypy: variável `r` reutilizada com tipos diferentes em dois `for` loops | Renomear para `wr`/`fr` por loop |
| Teste `test_bh_via_use_case_corrects_reports`: 2 métricas mas 1 retorno no `side_effect` | Prover 2 retornos (`side_effect=[..., ...]`) para cada adapter |
| Teste `test_tie_resolved_alphabetically`: lógica errada (llm_B tinha 2 vitórias, não empate) | Reescrever com 4 LLMs em 2 pares → empate real |

---

## Validação (DoD)

| Critério | Status |
|---------|--------|
| Correção BH: p-values `[0.04, 0.03, 0.02]` → corrigidos `[0.04, 0.04, 0.04]` — testado | ✅ |
| `tests=("wilcoxon",)`: Friedman/MLM NÃO chamados — testado via mock | ✅ |
| `StatsReport` JSON persistido com campos de síntese — testado | ✅ |
| `top_llm_by_friedman` identificado corretamente — testado | ✅ |
| `ruff check` + `ruff format --check` | ✅ |
| `mypy --strict src/` | ✅ |
| `lint-imports` (4 contratos KEPT) | ✅ |
| Cobertura do módulo novo: 96% (requisito ≥ 90%) | ✅ |
| Gate global: 1015 passed, 5 skipped — 92.95% (requisito ≥ 85%) | ✅ |

---

## Critérios de Aceitação (tabela TAREFA-405)

- [x] Correção BH: p-values corrigidos conferem com cálculo manual
- [x] `tests=("wilcoxon",)`: Friedman/MLM não chamados — verificado via mock
- [x] `StatsReport` JSON persistido e parseable
- [x] `top_llm_by_friedman` correto
- [x] mypy --strict; import-linter OK; cobertura ≥ 90%

---

## Observações para Próximas Tarefas

- **TAREFA-406** (extensões de domínio M4): verificar se ports adicionais são necessários
  para `StatisticalAnalysisUseCase` (ex.: port de persistência de `StatsReport`).
- **TAREFA-408** (`HTMLReportAdapter`): `StatsReport` é o VO de input — os campos
  `wilcoxon_reports`, `friedman_reports`, `mlm_reports` + síntese executiva estão todos
  disponíveis para renderização.
- A implementação local de BH/Holm (sem statsmodels em application) deve ser documentada
  na Nota de operacionalização M5 como decisão de contrato de importação.
- O golden file `tests/golden/stats_report_expected.json` é um dataset sintético;
  o gate M4 (TAREFA-409) deve criar um golden realista baseado em dados reais da Rodada 1.
