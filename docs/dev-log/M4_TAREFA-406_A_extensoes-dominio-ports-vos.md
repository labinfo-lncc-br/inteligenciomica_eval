# M4_TAREFA-406_A — Extensões de Domínio M4: novos ports e VOs para visualização

**Data**: 2026-06-02
**Milestone**: M4 — Decisão executiva da Rodada 1
**Épico**: E8 — Visualização
**Skill**: python-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Adicionar os dois novos Value Objects (`FigurePath`, `ReportPath`) e os dois novos ports
(`VisualizationPort`, `ReportPort`) ao domínio, desbloqueando TAREFA-407 (adapter de
visualização) e TAREFA-408 (HTMLReportAdapter + CLI). Sem quebrar nenhum contrato existente.

---

## Arquivos Criados / Modificados

| Arquivo | Tipo | Mudança |
|---------|------|---------|
| `src/inteligenciomica_eval/domain/value_objects.py` | Modificado | Import `Path`; adicionados `FigurePath` e `ReportPath` (frozen dataclasses, `slots=True`) |
| `src/inteligenciomica_eval/domain/ports.py` | Modificado | Import `Path`, `ConfigAggregate`, `FigurePath`, `ReportPath`, `StatsReport`; adicionados `VisualizationPort` e `ReportPort` (`@runtime_checkable`) |
| `tests/unit/domain/test_ports_contract.py` | Modificado | Imports dos novos tipos; stubs `_StubVisualization` e `_StubReport`; helpers `_make_figure_path` e `_make_stats_report`; 6 novos testes |

---

## Decisões Técnicas

### 1. `FigurePath` e `ReportPath` com `slots=True`
A spec exige apenas `frozen=True`. Foi adicionado `slots=True` por consistência com todos
os outros frozen dataclasses não-dict do projeto (`Chunk`, `RetrievalResult`, `ModelSpec`,
etc.). `StatsReport` e `MLMReport` não usam `slots=True` por conterem campos `dict`;
`FigurePath` e `ReportPath` só contêm `Path` e `str`, sem problema.

### 2. Import de `ConfigAggregate` em `ports.py`
`ConfigAggregate` está em `domain/services/aggregation.py` — dentro da camada `domain`.
O import-linter proíbe apenas imports de `application`, `infrastructure`, `cli` e libs de I/O
em `domain/`. O import intra-domain é permitido. Verificado: 4 contratos KEPT.

### 3. Re-export explícito de `ConfigAggregate`
`ConfigAggregate` é importado com alias `as ConfigAggregate` em `ports.py`, seguindo o
padrão já existente para `FriedmanReport`, `MLMReport`, `NemenyiPair` e `WilcoxonReport`,
facilitando o import direto via `from inteligenciomica_eval.domain.ports import ConfigAggregate`
nos callers de TAREFA-407 e TAREFA-408.

### 4. `StatsReport` agora exportado explicitamente de `ports.py`
`StatsReport` foi adicionado ao import direto de `value_objects` em `ports.py` (sem alias),
tornando-o acessível a callers que importam tudo de `domain.ports`.

### 5. Assinaturas keyword-only nos métodos dos ports
Todos os parâmetros após `self` e `aggregates`/`results` nos métodos de `VisualizationPort`
são keyword-only (`*`), conforme exigido pela spec. `ReportPort.generate_html` tem todos os
parâmetros keyword-only. Validado por mypy --strict.

---

## Problemas Encontrados e Soluções

### `RUF002` — símbolo multiplicação `×` em docstring
ruff sinalizou o caractere Unicode `×` (MULTIPLICATION SIGN, U+00D7) como ambíguo em duas
docstrings. Substituído por `x` (LATIN SMALL LETTER X) para conformidade com ruff RUF002.

---

## Validação (DoD)

```
uv run ruff check       → All checks passed (3 files)
uv run ruff format --check → 3 files already formatted
uv run mypy --strict src/ → Success: no issues found in 48 source files
uv run lint-imports     → 4 contracts KEPT, 0 broken
uv run pytest tests/unit/domain/test_ports_contract.py -v → 47 passed in 0.23s
uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4
    → 1024 passed, 5 skipped, 92.91% total coverage (gate 85% OK)
```

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| `VisualizationPort` com 6 métodos, assinaturas exatas, `@runtime_checkable` | ✅ |
| `ReportPort.generate_html` com todos kwargs, retorna `ReportPath`, `@runtime_checkable` | ✅ |
| `FigurePath` e `ReportPath` são frozen dataclasses sem Pydantic | ✅ |
| `isinstance` com stubs passa para ambos os ports | ✅ |
| import-linter: 4 contratos KEPT, 0 broken | ✅ |
| mypy --strict: 48 arquivos, 0 erros | ✅ |
| Suíte unit: 1024 passed, 92.91% cobertura (gate 85%) | ✅ |

---

## Observações para Próximas Tarefas

- **TAREFA-407** (`MatplotlibVisualizationAdapter`): implementar os 6 métodos de
  `VisualizationPort` em `src/inteligenciomica_eval/visualization/matplotlib_adapter.py`.
  Lembrar de `matplotlib.use("Agg")` como primeira linha (Nota M4 item 4 — bloqueador).
- **TAREFA-408** (`HTMLReportAdapter`): implementar `ReportPort.generate_html` em
  `infrastructure/adapters/`. Relatório autocontido sem URLs externas (Nota M4 item 5).
- `ConfigAggregate` e `StatsReport` são acessíveis via `from inteligenciomica_eval.domain.ports import ...`
  facilitando imports nos adapters de infraestrutura de TAREFA-407 e TAREFA-408.
