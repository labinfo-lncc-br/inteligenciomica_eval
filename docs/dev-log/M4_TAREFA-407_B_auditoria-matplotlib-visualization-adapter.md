# M4_TAREFA-407_B — Auditoria do MatplotlibVisualizationAdapter

**Data**: 2026-06-02
**Milestone**: M4 — Decisão executiva da Rodada 1 (Camada 3 + Agregação + Estatística + Relatório)
**Épico**: E8
**Skill**: code-reviewer, ml-engineer
**Prioridade / Tamanho**: P1 / M

## Objetivo
Auditar a entrega da TAREFA-407A contra `docs/m4_tarefa_407.md`, com foco nos bloqueadores da Nota M4 itens 3 e 4, aderência ao contrato `VisualizationPort`, validade dos SVGs e gates obrigatórios.

## Arquivos Criados / Modificados
- `src/inteligenciomica_eval/visualization/matplotlib_adapter.py`
- `src/inteligenciomica_eval/infrastructure/config/adapter_configs.py`
- `tests/unit/visualization/test_matplotlib_adapter.py`
- `tests/integration/visualization/test_matplotlib_adapter_integration.py`
- `docs/dev-log/M4_TAREFA-407_B_auditoria-matplotlib-visualization-adapter.md`

## Decisões Técnicas
- A auditoria foi feita por inspeção de linha dos arquivos alterados e execução local de `pytest`, `mypy`, `lint-imports`, `ruff` e greps exigidos no Prompt B.
- O critério de cobertura foi validado com a suíte global do repositório, porque a cobertura da suíte isolada de visualização sobre `src/` inteiro não representa o gate do projeto.

## Problemas Encontrados e Soluções
- Encontrado um bloqueador de aderência ao prompt: `plot_radar` cria a figura com `plt.figure(...)`, contrariando a regra global que exigia `fig, ax = plt.subplots(...)` em cada método.
- Encontrado desvio nos gates reportados: `ruff check` falha nos testes adicionados, então a entrega não pode ser considerada verde no estado atual.

## Validação (DoD)
- `uv run pytest tests/unit/visualization tests/integration/visualization -v` → `28 passed`
- `uv run mypy --strict src` → `Success: no issues found in 49 source files`
- `uv run lint-imports` → `4 kept, 0 broken`
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src/inteligenciomica_eval/visualization tests/unit/visualization tests/integration/visualization` → `FAIL`
- `uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -q` → `1068 passed, 15 skipped`, cobertura total `93.25%`

## Critérios de Aceitação

**Veredito**: FAIL

| Critério | Evidência | Resultado |
|---|---|---|
| `matplotlib.use("Agg")` antes de qualquer `pyplot`/`seaborn` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:15-23` | PASS |
| 6 métodos com assinaturas do `VisualizationPort` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:108`, `:196`, `:275`, `:323`, `:391`, `:448` | PASS |
| `plt.close(fig)` após cada `fig.savefig()` | helper `_save` em `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:79-83`; usado por todos os 6 métodos | PASS |
| Ausência de `plt.show` / `plt.clf` / `plt.cla` | grep vazio | PASS |
| Mock de `plt.close` para cada um dos 6 métodos | `tests/unit/visualization/test_matplotlib_adapter.py:114`, `:152`, `:176`, `:207`, `:243`, `:283` | PASS |
| SVG válido via `xml.etree.ElementTree` | `tests/integration/visualization/test_matplotlib_adapter_integration.py:53-57`, `:60-129` | PASS |
| `plot_failure_breakdown` com zero falhas gera arquivo sem exceção | unit `tests/unit/visualization/test_matplotlib_adapter.py:270-281`; integration `tests/integration/visualization/test_matplotlib_adapter_integration.py:119-129` | PASS |
| `seaborn.set_theme(..., palette="colorblind")` no `__init__` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:97-102` | PASS |
| Sem imports de `qdrant_client`, `openai`, `ragas`, `statsmodels` em `visualization/` | inspeção do arquivo + `lint-imports` verde | PASS |
| `mypy --strict`, cobertura ≥ 85%, DoD §14.2 | `mypy` PASS, cobertura global PASS, `ruff` FAIL | FAIL |
| Regra global: cada método usa `fig, ax = plt.subplots(...)` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:352-355` usa `plt.figure(...)` | FAIL |

## Tabela de Divergências

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| `plot_radar` viola a regra global do prompt (`fig, ax = plt.subplots(...)` em cada método) ao usar `fig = plt.figure(...)` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:352` | Bloqueador |
| `ruff check` não está verde nos testes adicionados: imports desordenados e import não usado | `tests/unit/visualization/test_matplotlib_adapter.py:3`, `:5`; `tests/integration/visualization/test_matplotlib_adapter_integration.py:6` | Importante |
| Docstring com caractere ambíguo `×`, também reportado por `ruff` (`RUF002`) | `tests/unit/visualization/test_matplotlib_adapter.py:47` | Importante |

## Evidências Solicitadas pelo Prompt B

### Grep item 1

```text
4:Nota de operacionalização M4 item 4: matplotlib.use("Agg") ANTES de qualquer
17:matplotlib.use("Agg")  # BLOQUEADOR: deve preceder qualquer import de pyplot/seaborn
21:import matplotlib.pyplot as plt
23:import seaborn as sns
236:            import seaborn as _sns
```

Observação: a linha relevante do código é `17`, anterior aos imports gráficos nas linhas `21` e `23`.

### Grep item 4

```text
<vazio>
```

### `plt.close(fig)` por método

| Método | Chamada de `_save` | `plt.close(fig)` efetivo |
|---|---|---|
| `plot_rankscore_heatmap` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:190` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:83` |
| `plot_finalscore_boxplots` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:269` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:83` |
| `plot_interaction` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:317` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:83` |
| `plot_radar` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:385` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:83` |
| `plot_per_question_ranking` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:442` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:83` |
| `plot_failure_breakdown` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:518` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:83` |

## Observações para Próximas Tarefas
- Para aprovação, o radar deve ser ajustado à regra global do prompt e os testes precisam ser normalizados para `ruff`.
- A cobertura global do repositório permanece acima do gate (`93.25%`), então o bloqueio aqui não é de cobertura e sim de aderência de implementação e lint.
