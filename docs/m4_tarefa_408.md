# Prompts M4 — TAREFA-401 a 409 (Claude Code ↔ ChatGPT Codex)

**Milestone:** M4 — Decisão executiva da Rodada 1 (Camada 3 + Agregação + Estatística + Relatório)
**Documentos de referência:**
- `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1, §§ 5.1, 6, 7.2–7.3, 8, 11.4–11.5, 14.7)
- `visao_alto_nivel_validacao_inteligenciomica.md` (v1.0, §§ 5, 7, 8, 11, 13)
**Continuação de:** M3 (TAREFA-301–310 — orquestração das 4 GPUs, Rodada 1 completa)
**Formato:** para cada tarefa, um **Prompt A (implementação — Claude Code)** e um
**Prompt B (verificação — ChatGPT Codex)**, conforme seção 16 do documento de arquitetura.
**Uso:** o desenvolvedor sênior cola o Prompt A no Claude Code; ao receber o PR, cola o
Prompt B no Codex; arbitra PASS/FAIL; itera até PASS; só então parte para a próxima
tarefa **respeitando o DAG do Apêndice**.

> Pressupõe que **M0 (001–012), M1 (013–021), M2 (022–028) e M3 (301–310) já estão
> mergeados e verdes**: domínio completo, adapters de infraestrutura, pipeline de
> métricas (Camadas 1 e 2), Rodada 1 executada, Parquet com `generated_answer` +
> métricas + `rubric_biomed_score` + `final_score` disponível para leitura.
>
> **Skills esperadas no Claude Code:** `python-clean-architecture`, `test-engineer`,
> `python-engineer`, `ml-engineer`, `data-engineer`, `backend-engineer`.
>
> **Nota de rastreabilidade:** TAREFA-4xx mapeia diretamente para a tabela do §14.7.
>
> | §14.7 (arquitetura) | Prompt M4 | Descrição |
> |---|---|---|
> | TAREFA-401 | **TAREFA-401** | CLI `annotate` (export estratificado) |
> | TAREFA-402 | **TAREFA-402** | `IngestHumanAnnotationUseCase` |
> | TAREFA-403 | **TAREFA-403** | `AggregateResultsUseCase` |
> | TAREFA-404 | **TAREFA-404** | `StatsPort` adapters (Wilcoxon + Friedman+Nemenyi + MLM) |
> | TAREFA-405 | **TAREFA-405** | `StatisticalAnalysisUseCase` + correção múltipla |
> | TAREFA-406 | **TAREFA-406** | Extensões de domínio M4 (ports, VOs) |
> | TAREFA-407 | **TAREFA-407** | `MatplotlibVisualizationAdapter` (7 plots canônicos) |
> | TAREFA-408 | **TAREFA-408** | `HTMLReportAdapter` + CLI `analyze`/`report`/`status` |
> | TAREFA-409 | **TAREFA-409** | Gate M4: E2E decisão executiva completa |

---

## Nota de operacionalização M4 — decisões que estes prompts fixam

As decisões abaixo são complementares às de M0–M3 e valem para todos os prompts de M4.
Devem ser confirmadas pela equipe (vetáveis antes da TAREFA-401).

### 1. `GoldChunkReaderPort` — delta de contrato declarado

A arquitetura §5.1 declara `gold_for(question_id: str) -> list[str]`. M1 (TAREFA-013)
implementou o adapter com `read_gold_chunks(question_id: str) -> tuple[str, ...]`.
**Resolução:** manter `read_gold_chunks` como nome canônico (delta em relação ao §5.1,
declarado e aprovado implicitamente pela conclusão do M1 sem auditoria contrária).
Qualquer uso novo do port em M4 usa `read_gold_chunks`. Uma correção futura de §5.1
para `gold_for` seria tratada como PR de renomeação isolado. **Este delta está
registrado aqui como decisão explícita.**

### 2. `RetrieverPort` — uso assíncrono

A arquitetura §5.1 declara `search(...)` como método síncrono. M1 (TAREFA-013)
implementou `QdrantRetrieverAdapter` como async. **Resolução para M4:** qualquer
chamada ao `RetrieverPort` em M4 usa `await retriever.search(...)`. Esta é uma extensão
do contrato, não uma quebra. Documentar na **Nota de operacionalização M5** (quando M5
for escrito) para rastrear o delta formalmente.

### 3. Visualização — `visualization/matplotlib_adapter.py` (ADR inline)

A arquitetura §8 prevê arquivos separados por tipo de plot. **Decisão M4:** implementar
todos os 7 plots em um único `visualization/matplotlib_adapter.py`. **Justificativa:**
cada método tem ~20–40 linhas de código; criar 7 arquivos com 1 função cada aumenta
overhead de importação e fragmentação. **Reversibilidade:** se algum plot crescer (>100
linhas), extrai-se o método para `visualization/<tipo>.py` sem alterar a interface do
adapter. Esta decisão não altera os contratos de domínio.

### 4. Matplotlib — `Agg` backend antes de qualquer import gráfico (bloqueador se violado)

`import matplotlib; matplotlib.use("Agg")` **ANTES** de qualquer
`import matplotlib.pyplot` ou `import seaborn` — linha 1 ou 2 do módulo. CI sem display
falha silenciosamente sem isso. É critério de aceitação verificado pelo Codex.

### 5. Relatório HTML — autocontido, sem dependências externas (bloqueador se violado)

O HTML gerado por `HTMLReportAdapter` deve ser um arquivo único, sem URLs http/https
externas (fontes, scripts, CDN). Plots embutidos como `data:image/svg+xml;base64,...`.
Verificado por `assert "http" not in html_content.lower()` no teste.

### 6. Análise estatística — `StatsPort` implementado via adapters, `StatsReport` como VO agregado

Os três adapters de TAREFA-404 (`WilcoxonAdapter`, `FriedmanNemenyiAdapter`,
`MixedLinearModelAdapter`) implementam `StatsPort` (§5.1) individualmente.
`StatisticalAnalysisUseCase` (TAREFA-405) os orquestra e produz um `StatsReport` (novo
VO de M4, declarado em TAREFA-406) com todos os resultados consolidados + p-values
corrigidos. O `StatsReport` é o input do `HTMLReportAdapter` (TAREFA-408).

### 7. Anotação humana — workflow export→edit→ingest (ADR-010)

O subcomando `annotate` **exporta** respostas priorizando scores baixos para um arquivo
JSONL editável pelo especialista. Após a edição offline, `annotate --ingest` faz o
merge por `row_id` via `IngestHumanAnnotationUseCase`. Esta separação é mandatória
(ADR-010). **Não há prompt interativo em sessão** — o especialista biomédico edita
o arquivo externamente, no seu tempo.

### 8. `AggregationService` (M0/TAREFA-008) vs `AggregateResultsUseCase` (M4/TAREFA-403)

`AggregationService` (domínio puro, TAREFA-008) já existe e produz `ConfigAggregate`
dado um conjunto de `EvaluationResult` em memória. `AggregateResultsUseCase`
(application, TAREFA-403) é o orquestrador que: lê o Parquet via `ResultReaderPort`,
converte para `EvaluationResult`, injeta no `AggregationService` existente, e persiste
o sumário. Não reimplementar lógica de agregação — **delegar 100% ao `AggregationService`**.

---

## TAREFA-408 — `HTMLReportAdapter` + CLI `analyze`/`report`/`status`/`show-config`

**Épico:** E8 · **Skills:** backend-engineer, python-engineer
**Prioridade:** P1 · **Tamanho:** L
**Dependências:** TAREFA-406 (`ReportPort`, `ReportPath`), TAREFA-407 (plots),
TAREFA-405 (`StatsReport`), TAREFA-403 (`AggregateResultsOutput`);
TAREFA-309 (CLI + factories) — M3
**ADRs:** ADR-001, ADR-008 · **Camadas:** infrastructure/adapters + cli + infrastructure/factories

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (§11.5 CLI completa, §11.4 relatório).
Skills: backend-engineer, python-engineer. TAREFA-406/407 concluídas. "Nota M4" itens 5 e 7.

TAREFA: TAREFA-408 — dois entregáveis:
(a) `HTMLReportAdapter` em `infrastructure/adapters/html_report.py`.
(b) Extensão da CLI com subcomandos `analyze`, `report`, `status`, `show-config`.

ESPECIFICAÇÃO — (a) `HTMLReportAdapter`:

Implementa `ReportPort.generate_html(*, run_id, aggregates, results, stats_report,
figure_paths, output_path) -> ReportPath`.

Pipeline (ordem obrigatória):
1. Para cada `FigurePath` com `format="svg"`: ler bytes, encodar base64 UTF-8,
   montar `"data:image/svg+xml;base64," + b64_str`.
   Arquivo ausente → placeholder `[Figura indisponível: {plot_type}]` (sem exceção).
2. Montar contexto Jinja2:
   - `aggregates_table`: lista de dicts ordenada por `rank_score.value` descrescente;
     campos: `config` (f"{base}/{llm}"), `rank_score`, `median_score`, `failure_rate`,
     `win_rate`, `critical_failure_rate`. Valores com `f"{v:.3f}"`.
   - `stats_summary`: campos do `StatsReport`. Campo ausente → `"N/A"`.
   - `figures`: `[{"plot_type": ..., "src": ..., "available": True/False}]`.
   - `generation_ts`: UTC ISO-8601.
3. Renderizar `infrastructure/prompts/report_template.html.j2`.
4. Escrever HTML em `output_path` (criar dir pai se necessário).
5. Retornar `ReportPath(path=output_path, format="html", run_id=run_id)`.

Template `report_template.html.j2` — 5 seções obrigatórias (por `id`):
1. `<section id="cabecalho">` — run_id, data, N configs, N perguntas.
2. `<section id="ranking-executivo">` — `<table id="ranking-table">`;
   melhor config com `class="best-config"`.
3. `<section id="visualizacoes">` — loop sobre figuras; `<img src="data:...">` ou
   placeholder de ausência.
4. `<section id="resultados-estatisticos">` — tabela com `stats_summary`.
5. `<section id="nota-metodologica">` — texto fixo sobre OFAT, n=13, determinismo
   do juiz (VLLM_BATCH_INVARIANT=1), geradores em modo realista.

Requisitos do template (Nota M4 item 5 — BLOQUEADORES):
- `<!DOCTYPE html><html lang="pt-BR"><meta charset="UTF-8">`.
- CSS inline em `<style>` (zero links externos, zero CDN, zero fontes web).
- ZERO referências a URLs http/https externas.
- HTML5 semântico; zero JavaScript.

ESPECIFICAÇÃO — (b) Novos subcomandos CLI (adicionando ao cli.py + factories.py):

(1) `ielm-eval analyze --run-id TEXT [--round-id TEXT] [--tests wilcoxon|friedman|mlm|all]
                       [--metric final_score|answer_correctness|...]`:
    - Delega a `StatisticalAnalysisUseCase` via `build_analysis_from_config`.
    - Imprime `StatsReport` via `rich.table` (p-values, significâncias, top_llm).
    - Informa onde o JSON de stats foi salvo.

(2) `ielm-eval report --run-id TEXT [--round-id TEXT] [--format html] [--output-dir PATH]`:
    - Gera os 6 plots via `MatplotlibVisualizationAdapter` em `output_dir/plots/`.
    - Gera HTML via `HTMLReportAdapter` em `output_dir/{run_id}_report.html`.
    - `--format pdf`: mensagem amigável "formato PDF reservado para versão futura".
    - Imprime via `rich.panel`: caminho do HTML + lista de figuras geradas.

(3) `ielm-eval status --run-id TEXT`:
    - Lê Parquet via `ResultReaderPort`.
    - run_id inexistente → mensagem amigável via `rich.print("[yellow]...[/yellow]")`,
      `typer.Exit(0)` (SEM traceback).
    - Imprime via `rich.table`: N total, N com `final_score` não-NaN, N NaN,
      N com `critical_failure_flag` anotado, N sem anotar, melhor config (se aggregates
      disponíveis).

(4) `ielm-eval show-config --config PATH`:
    - Carrega e valida o YAML via `ExperimentConfig` (TAREFA-010 M0).
    - Imprime via `rich.pretty.pprint`.
    - `ConfigValidationError` → mensagem amigável, `typer.Exit(1)`.

Factories em `infrastructure/factories.py` (novas):
```python
def build_analysis_from_config(config_path: Path) -> StatisticalAnalysisUseCase: ...
def build_visualization_adapter(config_path: Path) -> MatplotlibVisualizationAdapter: ...
def build_report_adapter(config_path: Path) -> HTMLReportAdapter: ...
```

ENTREGÁVEL:
- `src/inteligenciomica_eval/infrastructure/adapters/html_report.py`
- `infrastructure/prompts/report_template.html.j2`
- Extensão de `src/inteligenciomica_eval/cli.py` (4 subcomandos)
- Extensão de `infrastructure/factories.py` (3 novas factories)
- `tests/unit/adapters/test_html_report.py`
  a) 6 figuras SVG → HTML com 6 `data:image/svg+xml;base64,`.
  b) Figura ausente → placeholder sem exceção.
  c) Campo ausente em `StatsReport` → "N/A" no HTML, sem exceção.
  d) Tabela ordenada: melhor config na linha 1 com `class="best-config"`.
  e) `assert "http" not in html_content.lower()`.
  f) HTML parseable via `html.parser`.
- `tests/unit/test_cli_m4_subcommands.py` (via CliRunner)
  a) `--help` de cada subcomando: exit_code=0.
  b) `status --run-id inexistente`: exit_code=0, sem traceback.
  c) `show-config --config valid.yaml`: exit_code=0.
  d) `show-config --config invalid.yaml`: exit_code=1, mensagem amigável.
  e) `report --format pdf`: exit_code=0, mensagem informativa (sem crash).

RESTRIÇÕES (DoD §14.2 + Nota M4 item 5):
- Template em arquivo separado (.j2). Zero string inline de HTML no .py.
- HTML gerado: ZERO URLs externas — testado com assert.
- `cli.py` NÃO importa de `infrastructure/adapters/` diretamente.
- `from __future__ import annotations`; type hints; mypy --strict; import-linter OK.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-408):
- 5 section IDs no HTML — testado.
- 6 figuras embutidas como base64 — testado.
- `"http" not in html_content.lower()` — testado.
- HTML parseable — testado.
- 4 subcomandos com `--help` funcionando — testado.
- `status` com run_id inexistente: exit_code=0, sem traceback — testado.
- mypy --strict; lint-imports; cobertura ≥ 80%.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer (skill backend-engineer). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-408 + §11.5 (CLI spec) + "Nota M4" item 5 +
TAREFA-406 (ReportPort assinatura exata).

VERIFIQUE, item a item, citando arquivo:linha:
1. Assinatura de `generate_html` bate EXATAMENTE com `ReportPort` (TAREFA-406)?
   Todos os parâmetros keyword-only? Retorno `ReportPath`?
2. Template em arquivo separado `.j2`? Zero string HTML inline no .py?
3. 5 seções com IDs: `cabecalho`, `ranking-executivo`, `visualizacoes`,
   `resultados-estatisticos`, `nota-metodologica` — todas presentes no template?
4. HTML autocontido: execute `grep -i "http"
   src/inteligenciomica_eval/infrastructure/prompts/report_template.html.j2`
   (deve ser vazio — qualquer URL externa é BLOQUEADOR). Cole o output.
5. `assert "http" not in html_content.lower()` no teste — presente e passando?
6. Tabela de ranking ordenada por `rank_score` descrescente? Melhor config com
   `class="best-config"` — testado com aggregates propositalmente desordenados?
7. 4 subcomandos (`analyze`, `report`, `status`, `show-config`) com `--help` = exit 0?
   `status` com run_id inexistente: exit_code=0, SEM traceback?
8. `cli.py` NÃO importa adapters: `grep -n "from.*adapters import"
   src/inteligenciomica_eval/cli.py` deve ser vazio?
9. mypy --strict; lint-imports; cobertura ≥ 80%? DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Cole outputs dos greps dos itens 4 e 8.
Confirme `pytest tests/unit/adapters/test_html_report.py
tests/unit/test_cli_m4_subcommands.py -v` e `lint-imports`.
~~~

---

