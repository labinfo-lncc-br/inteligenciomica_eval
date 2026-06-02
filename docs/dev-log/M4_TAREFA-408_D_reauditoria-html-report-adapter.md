# M4_TAREFA-408_D — Reauditoria: correção dos 3 achados do Codex

**Data**: 2026-06-02
**Milestone**: M4 — Decisão executiva da Rodada 1
**Épico**: E8
**Skill**: backend-engineer, python-engineer
**Prioridade / Tamanho**: P1 / S (correção pós-auditoria)

---

## Objetivo

Corrigir os 3 achados do Codex na auditoria _B_ da TAREFA-408:
1. 🛑 **[Arquitetura]**: `cli.py` importava `HTMLReportAdapter` de `infrastructure/adapters/` diretamente
2. 🛑 **[Correção]**: `status` não implementava "melhor config (se aggregates disponíveis)"
3. ⚠️ **[Tipagem/Contrato]**: factories retornavam `object` em vez de tipos concretos

---

## Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/inteligenciomica_eval/infrastructure/factories.py` | Retornos tipados; `build_report_adapter` retorna `ReportPort`; `build_analysis_from_config` retorna `StatisticalAnalysisUseCase`; `build_visualization_adapter` retorna `MatplotlibVisualizationAdapter`; importes em `TYPE_CHECKING` |
| `src/inteligenciomica_eval/cli.py` | Removido import direto de `HTMLReportAdapter` e `assert isinstance`; `status` agora calcula e exibe melhor config |

---

## Correções Implementadas

### Achado 1 + 3: Factories tipadas, CLI sem import de adapters

**Causa**: `build_report_adapter` retornava `object`, forçando o CLI a importar
`HTMLReportAdapter` para fazer `assert isinstance`. Isso violava a restrição arquitetural.

**Solução**:
- `factories.py` usa `TYPE_CHECKING` para importar os tipos de retorno:
  - `build_analysis_from_config() -> StatisticalAnalysisUseCase`
  - `build_visualization_adapter() -> MatplotlibVisualizationAdapter`
  - `build_report_adapter() -> ReportPort` — typed como Protocol de domínio, não como adapter concreto
- `cli.py` removeu todos os `assert isinstance(...)` e importações diretas de `infrastructure/adapters/`
- O duck typing via `ReportPort` satisfaz mypy sem expor a classe concreta ao CLI

**Verificação pós-correção**:
```
grep -n "from.*adapters import" src/inteligenciomica_eval/cli.py  → sem saída (OK)
```

### Achado 2: `status` exibe melhor config

**Causa**: A implementação só exibia contagens; a spec exige "melhor config (se aggregates disponíveis)".

**Solução**: Bloco `try/except` que instancia `AggregationService` + `RankScoreCalculator`
com `DEFAULT_WEIGHTS`, chama `aggregate_all(results, threshold=cfg.scoring.failure_threshold)`,
ordena por `rank_score.value` descendente e exibe a melhor na tabela do `rich`.
Em qualquer exceção (dados insuficientes, lista vazia), exibe "N/A" — degradação graciosa
sem quebrar o `status` (exit_code=0 mantido).

---

## Validação (DoD)

### Gates verificados

```
uv run ruff check .                        → OK
uv run ruff format --check .               → OK
uv run mypy --strict src/                  → OK (50 arquivos, 0 issues)
uv run lint-imports                        → OK (4 contratos KEPT)
uv run pytest -m "not integration" -n 4   → 1068 passed, 5 skipped
Coverage: 90.97% (gate 85% ✓)
```

### Greps de auditoria (Prompt B itens 4 e 8)

```bash
grep -in "http" infrastructure/prompts/report_template.html.j2  → sem saída ✅
grep -n "from.*adapters import" cli.py                          → sem saída ✅
```

### Testes específicos

```
tests/unit/adapters/test_html_report.py     → 11 passed
tests/unit/test_cli_m4_subcommands.py       → 13 passed
Total: 24 passed
```

---

## Observações para Próximas Tarefas

- `build_report_adapter` retorna `ReportPort` (Protocol de domínio) — garante que CLI
  nunca dependa de nenhum adapter concreto de relatório futuro (PDF, etc.)
- A "melhor config" no `status` usa `DEFAULT_WEIGHTS` do `RankScoreCalculator` —
  mesma ponderação usada no pipeline principal. Se pesos configuráveis forem necessários
  em M5, extrair do `cfg.scoring` (já presente no schema).
