# M4_TAREFA-408_B — Auditoria HTMLReportAdapter + CLI analyze/report/status/show-config

**Data**: 2026-06-02
**Milestone**: M4 — Decisão executiva da Rodada 1
**Épico**: E8
**Skill**: code-reviewer
**Prioridade / Tamanho**: P1 / L

## Objetivo

Auditar a implementação da TAREFA-408A contra `docs/m4_tarefa_408.md`, com foco em:
- `HTMLReportAdapter` e conformidade com `ReportPort`
- template HTML autocontido
- subcomandos CLI `analyze`, `report`, `status`, `show-config`
- restrições arquiteturais da Nota M4 e DoD da tarefa

## Arquivos Criados / Modificados

- `docs/dev-log/M4_TAREFA-408_B_auditoria-html-report-cli-subcommands.md`

## Decisões Técnicas

- A auditoria foi baseada no prompt B da TAREFA-408, no contrato de `ReportPort` da TAREFA-406 e nas regras de `CLAUDE.md`.
- O parecer considera não apenas gates verdes, mas também aderência literal às restrições arquiteturais e ao comportamento exigido pela CLI.

## Problemas Encontrados e Soluções

### 1. FAIL — `cli.py` ainda importa adapter concreto de infraestrutura

**Arquivo**: `src/inteligenciomica_eval/cli.py:980-985`

O prompt A fixa explicitamente: `cli.py NÃO importa de infrastructure/adapters/ diretamente`.
Mesmo usando factory, o comando `report` faz:

- `from inteligenciomica_eval.infrastructure.adapters.html_report import HTMLReportAdapter`
- `assert isinstance(reporter, HTMLReportAdapter)`

Isso reintroduz acoplamento ao adapter concreto e viola a restrição arquitetural do prompt.

**Correção esperada**:
- tipar `build_report_adapter()` com retorno concreto ou port adequado
- remover o import direto do adapter em `cli.py`
- remover a necessidade do `assert isinstance(...)`

### 2. FAIL — `status` não implementa “melhor config (se aggregates disponíveis)”

**Arquivo**: `src/inteligenciomica_eval/cli.py:1040-1067`

A spec do subcomando `status` exige imprimir:

- total
- total com `final_score` válido
- total `NaN`
- total com `critical_failure_flag`
- total sem anotação
- **melhor config (se aggregates disponíveis)**

O código atual só carrega o `ResultFrame` do Parquet e imprime contagens. Não calcula
agregados nem mostra a melhor configuração em nenhum cenário.

**Correção esperada**:
- derivar/agregar resultados para obter o melhor `ConfigAggregate`, ou carregar agregados persistidos se já existirem
- incluir a linha correspondente na `rich.table`
- adicionar teste cobrindo esse comportamento

### 3. IMPORTANTE — signatures das factories divergem da spec e forçam asserts de runtime

**Arquivo**: `src/inteligenciomica_eval/infrastructure/factories.py:55-57,97-99,119-121`

O prompt A especifica as assinaturas:

- `build_analysis_from_config(config_path: Path) -> StatisticalAnalysisUseCase`
- `build_visualization_adapter(config_path: Path) -> MatplotlibVisualizationAdapter`
- `build_report_adapter(config_path: Path) -> HTMLReportAdapter`

Na implementação, as três factories retornam `object`. Isso enfraquece o contrato,
oculta a API para o type checker e leva a asserts de runtime no `cli.py`.

**Correção esperada**:
- expor os retornos concretos declarados pela tarefa
- eliminar os `assert isinstance(...)` usados apenas para recuperar tipagem

## Validação (DoD)

### Conformidades confirmadas

- `generate_html` corresponde ao `ReportPort` com parâmetros keyword-only e retorno `ReportPath`
- template separado em `.j2`, sem HTML inline em `html_report.py`
- 5 seções obrigatórias presentes no template
- template sem referências externas `http/https`
- teste com `assert "http" not in html_content.lower()` presente e passando
- ranking ordenado por `rank_score` desc e `class="best-config"` testados
- `--help` dos 4 subcomandos retorna `exit_code=0`
- `status --run-id inexistente` retorna `exit_code=0` sem traceback
- `mypy --strict`, `lint-imports`, `ruff check` e cobertura global passaram

### Greps exigidos pelo prompt B

`grep -in "http" src/inteligenciomica_eval/infrastructure/prompts/report_template.html.j2`

```text
(sem saída)
```

`grep -n "from.*adapters import" src/inteligenciomica_eval/cli.py`

```text
(sem saída)
```

Observação: embora o grep solicitado tenha vindo vazio, a restrição arquitetural continua
violada por `from inteligenciomica_eval.infrastructure.adapters.html_report import HTMLReportAdapter`
em `cli.py`, pois o padrão do grep não captura imports de submódulo.

## Critérios de Aceitação

| Critério | Evidência | Status |
|---|---|---|
| Assinatura de `generate_html` bate com `ReportPort` | `src/inteligenciomica_eval/infrastructure/adapters/html_report.py` + `src/inteligenciomica_eval/domain/ports.py` | ✅ |
| Template `.j2` separado | `src/inteligenciomica_eval/infrastructure/prompts/report_template.html.j2` | ✅ |
| 5 section IDs obrigatórios | template + teste unitário | ✅ |
| Zero `http` no template | grep vazio + teste | ✅ |
| 6 figuras SVG embutidas como base64 | `tests/unit/adapters/test_html_report.py` | ✅ |
| CLI `status` sem traceback para run inexistente | `tests/unit/test_cli_m4_subcommands.py` | ✅ |
| `cli.py` sem import direto de adapter | `src/inteligenciomica_eval/cli.py:980-985` | ❌ |
| `status` mostra melhor config quando disponível | `src/inteligenciomica_eval/cli.py:1040-1067` | ❌ |
| Factories com signatures conforme prompt | `src/inteligenciomica_eval/infrastructure/factories.py:55-121` | ❌ |

## Observações para Próximas Tarefas

- Antes de avançar, a iteração seguinte deve remover o import direto do adapter em `cli.py`.
- O subcomando `status` precisa cumprir a spec completa, não só o caso de run inexistente.
- Vale acrescentar testes cobrindo:
  - `status` com dados válidos e melhor config exibida
  - ausência de import/acoplamento indevido na CLI via revisão de arquitetura ou smoke test estrutural

## Resultado

**FAIL**

Resumo:
- gates técnicos principais estão verdes
- porém há divergências objetivas com a spec/DoD da tarefa, suficientes para reprovar a auditoria nesta iteração
