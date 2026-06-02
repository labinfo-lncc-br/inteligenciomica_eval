# M4_TAREFA-407_A — MatplotlibVisualizationAdapter (6 plots canônicos)

**Data**: 2026-06-02
**Milestone**: M4 — Decisão executiva da Rodada 1
**Épico**: E8
**Skill**: ml-engineer, python-engineer
**Prioridade / Tamanho**: P1 / M

---

## Objetivo

Implementar `MatplotlibVisualizationAdapter` em
`src/inteligenciomica_eval/visualization/matplotlib_adapter.py`,
implementando `VisualizationPort` com 6 métodos de visualização canônicos (§11.4).
Nota de operacionalização M4 itens 3 e 4.

---

## Arquivos Criados / Modificados

| Ação      | Arquivo |
|-----------|---------|
| Criado    | `src/inteligenciomica_eval/visualization/matplotlib_adapter.py` |
| Modificado | `src/inteligenciomica_eval/infrastructure/config/adapter_configs.py` |
| Modificado | `pyproject.toml` (dependências + mypy overrides) |
| Criado    | `tests/unit/visualization/__init__.py` |
| Criado    | `tests/unit/visualization/test_matplotlib_adapter.py` |
| Criado    | `tests/integration/visualization/__init__.py` |
| Criado    | `tests/integration/visualization/test_matplotlib_adapter_integration.py` |

---

## Decisões Técnicas

### 1. `matplotlib.use("Agg")` — posição exata (BLOQUEADOR M4 item 4)

```python
import matplotlib
matplotlib.use("Agg")  # linha 16 do módulo

# isort: split
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
```

O `# isort: split` isola o bloco pós-`use("Agg")` evitando falha de ruff I001
sem sacrificar a posição do bloqueador. O `matplotlib.use("Agg")` está na
linha 16, antes de qualquer `import matplotlib.pyplot` ou `import seaborn`.

### 2. Eixos do radar chart — adaptação de ConfigAggregate

`ConfigAggregate` (M0) armazena apenas campos de `FinalScore` agregados
(`mean_score`, `median_score`, `min_score`, `iqr`, `failure_rate`, etc.),
não métricas RAGAS individuais. Os 6 eixos do radar usam campos disponíveis:
`median_score`, `failure_rate`, `critical_failure_rate`, `win_rate`,
`mean_score`, `min_score`. Os eixos RAGAS originais da §11.4
(`answer_correctness`, `faithfulness`, etc.) requerem extensão do VO em M5+.
Documentado no docstring `_RADAR_AXES` e no docstring de `plot_radar`.

### 3. Boxplot aproximado (sem ResultFrame)

Quando `results=None`, `plot_finalscore_boxplots` usa `ax.bxp()` do matplotlib
com box stats construídas a partir de `median_score`, `iqr` e `min_score` do
`ConfigAggregate`. Documentado como aproximação no docstring do método.

### 4. `VisualizationAdapterConfig` — `field(default_factory=lambda: ["svg"])`

Frozen dataclass com campo `list` mutável usa `field(default_factory=...)`.
Não usa `__post_init__` (incompatibilidade com `slots=True`).

### 5. Tipos Any para matplotlib — sem stubs mypy

`plt.Figure` e o `PolarAxes` polar não têm stubs mypy. Solução:
- `_save(fig: Any, ...)` — tipo anotado como `Any` com comentário explicando
- `polar_ax: Any = fig.add_subplot(111, projection="polar")` — cast local

### 6. BaseId válidos nos testes

Os IDs de base válidos são `"IDx_400k"`, `"ID_230K"`, `"fixed"` (definidos em
`_VALID_BASE_IDS` no domain). Uso `"IDx_400k"` + `"ID_230K"` para cobrir
dois bases distintas nos testes.

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| ruff I001: import block unsorted (matplotlib.use antes de pyplot) | `# isort: split` entre o bloco de setup e o bloco de imports restantes |
| ruff RUF002/RUF001: caracteres `×` ambíguos | Substituído por `x` em títulos/docstrings |
| ruff RUF005: concatenação de listas | Substituído por `[*angles, angles[0]]` |
| mypy: `plt.Figure` não definido (sem stubs) | Tipo `Any` com comentário explicativo |
| mypy: `ax.set_thetagrids` não existe em `Axes` | `polar_ax: Any = fig.add_subplot(...)` |
| `InvalidBaseIdError: IDx_800k` | Substituído por `"ID_230K"` (valor válido) |
| `ModuleNotFoundError: tests` | Import `from factories.factories import ...` (sem prefixo `tests.`) |

---

## Correções Pós-Auditoria Codex (iteração 2)

| Achado Codex | Correção aplicada |
|---|---|
| **BLOQUEADOR**: `plot_radar` usa `plt.figure()` + `add_subplot(projection="polar")` em vez de `fig, ax = plt.subplots(...)` | Substituído por `fig, polar_ax_raw = plt.subplots(..., subplot_kw={"projection": "polar"})` |
| **Lint I001**: imports desordenados nos dois arquivos de teste | `ruff check --fix` + `ruff format` aplicados; `factories` agora no grupo correto (third-party) |
| **Lint F401**: `xml.etree.ElementTree` não usado em `test_matplotlib_adapter.py` | Import removido |
| **Lint RUF002**: caractere `×` ambíguo no docstring de fixture | Substituído por `x` |

---

## Validação (DoD)

### Gate de lint e formatação

```
uv run ruff check src/inteligenciomica_eval/visualization/ → All checks passed!
uv run ruff format --check src/inteligenciomica_eval/visualization/ → 3 files already formatted
```

### Gate mypy

```
uv run mypy --strict src/inteligenciomica_eval/visualization/ → Success: no issues found in 3 source files
```

### Gate import-linter

```
uv run lint-imports → Contracts: 4 kept, 0 broken.
```

### Gate de testes

```
uv run pytest tests/unit/visualization/ -v → 20 passed
uv run pytest tests/integration/visualization/ -v -m integration → 8 passed
uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4 →
  1044 passed, 5 skipped
  matplotlib_adapter.py: 99%
  Total: 93.25% (gate de 85% atingido)
```

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| 6 métodos retornam `FigurePath` e criam SVG com `st_size > 0` | ✅ 20 testes unitários PASS |
| `plt.close(fig)` confirmado por mock em cada método (6 assertivas) | ✅ cada classe tem `test_plt_close_chamado` |
| SVG é XML válido (`xml.etree.ElementTree.fromstring`) | ✅ 8 testes de integração PASS |
| `matplotlib.use("Agg")` na linha correta (antes de pyplot/seaborn) | ✅ linha 16, antes dos imports gráficos |
| `plot_failure_breakdown` com 0 falhas → arquivo criado sem exceção | ✅ `test_zero_falhas_arquivo_criado_sem_excecao` PASS |
| `plot_rankscore_heatmap` metric_name inválido → `ConfigValidationError` | ✅ `test_metric_name_invalido` PASS |
| `visualization/` não importa qdrant/openai/ragas/statsmodels | ✅ import-linter OK |
| mypy --strict OK | ✅ 0 erros |
| Cobertura ≥ 85% | ✅ 93.25% total; 99% do adapter |

---

## Observações para Próximas Tarefas

- **TAREFA-408** (`HTMLReportAdapter`): receberá `list[FigurePath]` e embutirá SVGs
  como `data:image/svg+xml;base64,...` no HTML. A leitura do arquivo SVG via
  `path.read_bytes()` e encode base64 é o padrão — nenhuma extensão de `FigurePath`
  necessária.
- **Eixos radar M5+**: extensão do `ConfigAggregate` com métricas RAGAS individuais
  (`answer_correctness`, `faithfulness`, etc.) permitirá substituir os 6 eixos
  atuais pelo conjunto original do §11.4.
- **Seaborn DeprecationWarning**: `seaborn.boxplot` emite
  `PendingDeprecationWarning: vert: bool` ao chamar `ax.bxp`. Será resolvido
  quando seaborn ≥0.14 (API `orientation`) estiver disponível. Não é bloqueador.
