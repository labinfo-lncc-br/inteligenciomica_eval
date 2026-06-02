# M4_TAREFA-407_D — Reauditoria do MatplotlibVisualizationAdapter

**Data**: 2026-06-02
**Milestone**: M4 — Decisão executiva da Rodada 1 (Camada 3 + Agregação + Estatística + Relatório)
**Épico**: E8
**Skill**: code-reviewer, ml-engineer
**Prioridade / Tamanho**: P1 / M

## Objetivo
Reauditar a TAREFA-407 após a iteração 2 do desenvolvedor, confirmando a correção do bloqueador no `plot_radar`, o saneamento do lint nos testes e a manutenção dos gates exigidos pelo Prompt B.

## Arquivos Criados / Modificados
- `src/inteligenciomica_eval/visualization/matplotlib_adapter.py`
- `tests/unit/visualization/test_matplotlib_adapter.py`
- `tests/integration/visualization/test_matplotlib_adapter_integration.py`
- `docs/dev-log/M4_TAREFA-407_D_reauditoria-matplotlib-visualization-adapter.md`

## Decisões Técnicas
- A reauditoria foi limitada aos achados da rodada anterior e aos gates mandatórios do Prompt B.
- O gate de cobertura foi reexecutado sobre a suíte global do repositório para validar o critério do projeto, não apenas a subárvore de visualização.

## Problemas Encontrados e Soluções
- O uso de `plt.figure(...)` no radar foi removido; agora o método usa `plt.subplots(..., subplot_kw={"projection": "polar"})`, conforme o prompt.
- Os problemas de `ruff` nos testes foram corrigidos; `ruff check` agora está verde nos arquivos tocados.

## Validação (DoD)
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src/inteligenciomica_eval/visualization tests/unit/visualization tests/integration/visualization` → `All checks passed!`
- `uv run pytest tests/unit/visualization tests/integration/visualization -v` → `28 passed`
- `uv run mypy --strict src` → `Success: no issues found in 49 source files`
- `uv run lint-imports` → `4 kept, 0 broken`
- `uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -q` → `1068 passed, 15 skipped`, cobertura total `93.25%`

## Critérios de Aceitação

**Veredito**: PASS

| Critério | Evidência | Resultado |
|---|---|---|
| `matplotlib.use("Agg")` antes de `pyplot`/`seaborn` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:15-23` | PASS |
| 6 métodos com assinaturas do `VisualizationPort` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:108`, `:196`, `:275`, `:323`, `:391`, `:448` | PASS |
| `plot_radar` segue a regra global com `plt.subplots(...)` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:352-355` | PASS |
| `plt.close(fig)` após cada `fig.savefig()` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:79-83`; todos os 6 métodos retornam via `_save(...)` | PASS |
| Ausência de `plt.show` / `plt.clf` / `plt.cla` | grep vazio | PASS |
| Mock de `plt.close` para cada um dos 6 métodos | `tests/unit/visualization/test_matplotlib_adapter.py:118`, `:160`, `:184`, `:215`, `:253`, `:291` | PASS |
| SVG válido via `xml.etree.ElementTree` | `tests/integration/visualization/test_matplotlib_adapter_integration.py:61-138` | PASS |
| `plot_failure_breakdown` com zero falhas gera arquivo sem exceção | `tests/unit/visualization/test_matplotlib_adapter.py:278-289`; `tests/integration/visualization/test_matplotlib_adapter_integration.py:129-138` | PASS |
| `seaborn.set_theme(..., palette="colorblind")` no `__init__` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:97-102` | PASS |
| Sem imports de `qdrant_client`, `openai`, `ragas`, `statsmodels` em `visualization/` | inspeção local + `lint-imports` verde | PASS |
| `mypy --strict`, `ruff`, cobertura ≥ 85% | checks reexecutados acima | PASS |

## Tabela de Divergências

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| Nenhuma divergência encontrada | N/A | N/A |

## Evidências Solicitadas pelo Prompt B

### Grep item 1

```text
4:Nota de operacionalização M4 item 4: matplotlib.use("Agg") ANTES de qualquer
17:matplotlib.use("Agg")  # BLOQUEADOR: deve preceder qualquer import de pyplot/seaborn
21:import matplotlib.pyplot as plt
23:import seaborn as sns
236:            import seaborn as _sns
```

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
| `plot_radar` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:386` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:83` |
| `plot_per_question_ranking` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:443` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:83` |
| `plot_failure_breakdown` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:519` | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py:83` |

## Observações para Próximas Tarefas
- Há um `RuntimeWarning: More than 20 figures have been opened` durante os testes unitários quando `matplotlib.pyplot.close` é mockado; isso decorre da própria estratégia de teste e não de ausência de fechamento no código de produção.
- A TAREFA-407 está aprovada nesta reauditoria.
