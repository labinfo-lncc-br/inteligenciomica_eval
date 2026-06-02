# M4_TAREFA-408_D — Reauditoria HTMLReportAdapter + CLI analyze/report/status/show-config

**Data**: 2026-06-02
**Milestone**: M4 — Decisão executiva da Rodada 1
**Épico**: E8
**Skill**: code-reviewer
**Prioridade / Tamanho**: P1 / L

## Objetivo

Reauditar a TAREFA-408 após as correções da iteração anterior, verificando:
- remoção do acoplamento da CLI ao adapter concreto
- correção das signatures das factories
- exibição de "melhor config" no subcomando `status`
- manutenção dos gates e restrições da Nota M4

## Arquivos Criados / Modificados

- `docs/dev-log/M4_TAREFA-408_D_reauditoria-html-report-cli-subcommands.md`

## Decisões Técnicas

- A reauditoria foi focada nos três achados da auditoria B.
- O parecer considera o estado real do workspace e a execução dos gates solicitados no prompt B.

## Problemas Encontrados e Soluções

### Correções confirmadas

1. `cli.py` não importa mais adapters concretos de `infrastructure/adapters/`.
2. `build_analysis_from_config`, `build_visualization_adapter` e `build_report_adapter`
   agora expõem retornos tipados, eliminando os `assert isinstance(...)` anteriores.
3. `status` agora calcula e imprime `Melhor config`, com degradação graciosa para `N/A`.

### Risco residual não bloqueador

- O arquivo `tests/unit/test_cli_m4_subcommands.py` ainda não cobre explicitamente o
  caminho de sucesso de `status` com `Melhor config` exibida. Há cobertura para os
  caminhos de `--help`, config ausente/inválida, run inexistente e `report --format pdf`,
  mas não para esse novo ramo específico.
- Como o comportamento foi confirmado por inspeção do código e os gates estão verdes,
  isso não bloqueia aprovação nesta iteração.

## Validação (DoD)

### Greps exigidos pelo prompt B

`grep -in "http" src/inteligenciomica_eval/infrastructure/prompts/report_template.html.j2`

```text
(sem saída)
```

`grep -n "from.*adapters import" src/inteligenciomica_eval/cli.py`

```text
(sem saída)
```

### Gates reexecutados

- `uv run pytest tests/unit/adapters/test_html_report.py tests/unit/test_cli_m4_subcommands.py -v`
  - `24 passed`
- `uv run lint-imports`
  - `4 kept, 0 broken`
- `uv run mypy --strict src`
  - `Success: no issues found in 50 source files`
- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src/inteligenciomica_eval/cli.py src/inteligenciomica_eval/infrastructure/factories.py src/inteligenciomica_eval/infrastructure/adapters/html_report.py tests/unit/adapters/test_html_report.py tests/unit/test_cli_m4_subcommands.py`
  - `All checks passed!`
- `uv run pytest -m "not integration" --cov=src --cov-report=term-missing --cov-fail-under=85 -n 4`
  - `1068 passed, 5 skipped`
  - cobertura total `90.97%`

## Critérios de Aceitação

| Critério | Evidência | Status |
|---|---|---|
| Assinatura de `generate_html` bate com `ReportPort` | `html_report.py` + `domain/ports.py` | ✅ |
| Template `.j2` separado | `report_template.html.j2` | ✅ |
| 5 section IDs obrigatórios | template + testes | ✅ |
| Zero `http` no template | grep vazio + teste | ✅ |
| `cli.py` sem import direto de adapter | grep vazio + `cli.py` | ✅ |
| Factories com signatures conforme correção | `infrastructure/factories.py` | ✅ |
| `status` exibe melhor config quando possível | `cli.py` | ✅ |
| `status` com run inexistente: exit 0 sem traceback | teste unitário | ✅ |
| mypy/lint-imports/ruff/cobertura | gates reexecutados | ✅ |

## Observações para Próximas Tarefas

- Vale adicionar um teste unitário específico para o caminho de sucesso de `status`
  com `Melhor config`, para reduzir risco de regressão.

## Resultado

**PASS**
