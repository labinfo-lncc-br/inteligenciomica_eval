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

## TAREFA-409 — Gate M4: E2E decisão executiva completa

**Épico:** E9 — Gate M4 · **Skill:** test-engineer
**Prioridade:** P0 · **Tamanho:** L
**Dependências:** TODAS as TAREFA-401 a 408 mergeadas e verdes; M0–M3 green
**ADRs:** todos · **Camadas:** tests/e2e + docs

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica. Gate final do milestone M4.
Skill: test-engineer. TAREFA-401–408 mergeadas e verdes. Este é o ÚLTIMO PR de M4.

TAREFA: TAREFA-409 — criar o teste E2E de M4 e a documentação de fechamento do milestone.

ESPECIFICAÇÃO — PARTE A: `tests/e2e/test_full_pipeline_m4.py`

Fixtures (determinísticas, sem GPU nem vLLM real):
- 6 `ConfigAggregate` sintéticos (2 bases × 3 LLMs) — fixture JSON em
  `tests/fixtures/e2e_m4_aggregates.json`.
- `StatsReport` sintético — fixture JSON em `tests/fixtures/e2e_m4_stats_report.json`.
- `ResultFrame` com 5 `EvaluationResult` (4 com `final_score` válido, 1 NaN).
- Arquivo JSONL de anotação sintético com flags `0`, `1` e `null`.
- `respx.mock` para todo HTTP.
- Qdrant via `testcontainers.qdrant` (scope="session") com 5 chunks de fixture.
- `tmp_path` para todos os arquivos de saída.

Fluxo E2E — 5 etapas com componentes reais:

**ETAPA 1 — Anotação e ingestão:**
```python
# Export
runner.invoke(app, ["annotate", "--run-id", run_id, "--export", str(export_path),
                    "--threshold", "0.75"])
assert export_path.exists()
jsonl_lines = [json.loads(l) for l in export_path.read_text().splitlines() if l]
assert all("critical_failure_flag" in l for l in jsonl_lines)

# Ingestão (com arquivo JSONL pré-editado de fixture)
result = IngestHumanAnnotationUseCase(...).execute(IngestAnnotationInput(...))
assert result.n_ingested > 0
assert result.n_invalid == 0
```

**ETAPA 2 — Agregação:**
```python
agg_output = AggregateResultsUseCase(...).execute(AggregateResultsInput(
    run_id=run_id, round_id="round_1"
))
assert len(agg_output.aggregates) == 6  # 2 bases × 3 LLMs
assert agg_output.best_config is not None
assert agg_output.n_nan_excluded >= 1   # o resultado NaN da fixture
```
Verificar ordenação: `agg_output.aggregates[0].rank_score.value >= agg_output.aggregates[-1].rank_score.value`.

**ETAPA 3 — Análise estatística:**
```python
stats_uc = StatisticalAnalysisUseCase(
    reader=reader,
    wilcoxon_adapter=WilcoxonAdapter(config),
    friedman_adapter=FriedmanNemenyiAdapter(config),
    mlm_adapter=MixedLinearModelAdapter(config),
)
stats_output = stats_uc.execute(StatisticsInput(run_id=run_id, round_id="round_1"))
stats_json_path = tmp_path / f"{run_id}_round_1_stats.json"
assert stats_json_path.exists()
# Campos de síntese presentes
assert hasattr(stats_output, "base_difference_significant")
assert hasattr(stats_output, "llm_difference_significant")
assert hasattr(stats_output, "interaction_significant")
```

**ETAPA 4 — Visualização:**
```python
viz = MatplotlibVisualizationAdapter(VisualizationAdapterConfig())
plots_dir = tmp_path / "plots"
figure_paths = [
    viz.plot_rankscore_heatmap(agg_output.aggregates, output_dir=plots_dir),
    viz.plot_finalscore_boxplots(agg_output.aggregates, output_dir=plots_dir),
    viz.plot_interaction(agg_output.aggregates, output_dir=plots_dir),
    viz.plot_radar(agg_output.aggregates, output_dir=plots_dir, top_n=3),
    viz.plot_per_question_ranking(result_frame, output_dir=plots_dir),
    viz.plot_failure_breakdown(agg_output.aggregates, output_dir=plots_dir),
]
for fpath in figure_paths:
    assert fpath.path.exists() and fpath.path.stat().st_size > 0
    xml.etree.ElementTree.fromstring(fpath.path.read_text())  # SVG válido
```

**ETAPA 5 — Relatório HTML:**
```python
report_adapter = HTMLReportAdapter(HTMLReportAdapterConfig())
report_path = report_adapter.generate_html(
    run_id=run_id,
    aggregates=agg_output.aggregates,
    results=result_frame,
    stats_report=stats_output,
    figure_paths=figure_paths,
    output_path=tmp_path / "report_m4_e2e.html",
)
html = report_path.path.read_text(encoding="utf-8")
assert report_path.path.stat().st_size > 30_000
for section_id in ["cabecalho", "ranking-executivo", "visualizacoes",
                   "resultados-estatisticos", "nota-metodologica"]:
    assert f'id="{section_id}"' in html
assert html.count("data:image/svg+xml;base64,") == 6
assert "http" not in html.lower()
html_parser = html.parser.HTMLParser()
html_parser.feed(html)  # sem exceção

# CLI smoke (via CliRunner)
for subcmd in ["analyze", "report", "status", "show-config", "annotate"]:
    r = runner.invoke(app, [subcmd, "--help"])
    assert r.exit_code == 0, f"--help falhou: {subcmd}"
r = runner.invoke(app, ["status", "--run-id", "inexistente"])
assert r.exit_code == 0
assert "não encontrado" in r.output or "not found" in r.output
```

Critério de tempo: `pytest -m e2e tests/e2e/test_full_pipeline_m4.py` < 90s em CPU.

ESPECIFICAÇÃO — PARTE B: Documentação de fechamento do M4

(1) `CHANGELOG.md` — nova seção `## [M4] — TAREFA-401 a 409`:
    - Lista de entregáveis por tarefa.
    - Deltas de contrato declarados em M4: `update_annotation` no `ResultWriterPort`;
      `GoldChunkReaderPort.read_gold_chunks` como delta de §5.1;
      `RetrieverPort` uso async.
    - Breaking changes: nenhum (M4 é aditivo).

(2) `docs/adr/ADR-013-round2-funnel.md` — ADR para uso em M5:
    - **Título:** Funil de dois estágios para Rodada 2 (OFAT)
    - **Context:** custo de geração (LLM) é O(N_configs × N_perguntas × N_seeds);
      com 5 configs × 13 perguntas × 3 seeds = 195 chamadas por fase.
    - **Decision:** estágio 1 — métricas de retrieval puro (sem LLM, barato) filtra
      candidatos; estágio 2 — geração completa apenas para top-N por nDCG@k médio.
      `top_n=3` como default.
    - **Consequences:** reduz chamadas de LLM em ~60%; configs boas em geração mas
      ruins em retrieval podem ser descartadas (aceitável: retrieval ruim → contexto
      pobre → geração provavelmente ruim).

(3) Atualizar `README.md`:
    - Tabela de milestones com M4 marcado ✅.
    - Seção "Decisão executiva (M4)" com os comandos:
      ```bash
      ielm-eval analyze --run-id <run> --tests all
      ielm-eval report  --run-id <run> --output-dir reports/
      ```

(4) Atualizar `.github/workflows/ci.yml`:
    - Job `e2e` rodando `pytest -m e2e tests/e2e/test_full_pipeline_m4.py -v`
      com `services.qdrant` (image `qdrant/qdrant:v1.9`).
    - `needs: [unit, integration]`; `timeout-minutes: 10`.

ENTREGÁVEL:
- `tests/e2e/test_full_pipeline_m4.py`
- `tests/fixtures/e2e_m4_aggregates.json`
- `tests/fixtures/e2e_m4_stats_report.json`
- `tests/fixtures/e2e_m4_annotation.jsonl` (flags 0, 1, null para 3 itens)
- `CHANGELOG.md` (seção M4)
- `docs/adr/ADR-013-round2-funnel.md`
- `README.md` (atualizado)
- `.github/workflows/ci.yml` (job e2e adicionado)

RESTRIÇÕES (DoD §14.2 + test-engineer §9):
- Qdrant scope="session"; dados de fixture scope="function".
- `respx.mock` intercepta todo HTTP (confirmar ausência de `NetworkNotMocked`).
- Determinístico: fixtures fixas, seeds fixas.
- < 90s em CPU sem GPU.
- `from __future__ import annotations`; type hints; mypy --strict.

CRITÉRIO DE ACEITAÇÃO (Gate M4 — TAREFA-409):
- Etapa 1: export JSONL criado + ingestão `n_ingested > 0` — testado.
- Etapa 2: 6 agregados, `best_config` não None, `n_nan_excluded >= 1`, ordenação — testado.
- Etapa 3: `StatsReport` JSON criado; 3 campos de síntese presentes — testado.
- Etapa 4: 6 SVGs válidos (XML) criados — testado.
- Etapa 5: HTML com 5 section IDs + 6 figuras base64 + zero URLs externas + parseable + > 30KB — testado.
- CLI smoke: `--help` de 5 subcomandos = exit 0; `status` inexistente = exit 0, sem traceback — testado.
- `pytest -m e2e` verde em CI < 90s.
- CHANGELOG com deltas de contrato M4; ADR-013 com Context/Decision/Consequences.
- README com M4 ✅ e comandos de decisão executiva.
- CI job `e2e` com Qdrant service e timeout.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer (skill test-engineer). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-409 + todos os ADRs M0–M4 + §14.7 go/no-go +
skill test-engineer §9 (E2E enxuto).

VERIFIQUE, item a item, citando arquivo:linha:

PARTE A — Teste E2E:
1. Etapa 1 — Anotação: export JSONL com `critical_failure_flag: null` assertado?
   Ingestão: `n_ingested > 0`, `n_invalid == 0` assertados?
2. Etapa 2 — Agregação: `len(aggregates) == 6`? `n_nan_excluded >= 1`?
   Ordenação descrescente por `rank_score` verificada?
3. Etapa 3 — Stats: arquivo JSON criado? Campos `base_difference_significant`,
   `llm_difference_significant`, `interaction_significant` presentes?
4. Etapa 4 — Plots: exatamente 6 SVGs assertados com `st_size > 0`?
   XML válido para CADA um?
5. Etapa 5 — HTML:
   a) `st_size > 30_000` assertado?
   b) 5 section IDs (`cabecalho`, `ranking-executivo`, `visualizacoes`,
      `resultados-estatisticos`, `nota-metodologica`) assertados?
   c) `html.count("data:image/svg+xml;base64,") == 6` assertado?
   d) `"http" not in html.lower()` assertado?
      Execute também: `grep -i "http" tests/fixtures/e2e_m4_stats_report.json` e cole.
   e) HTML parseable assertado?
6. CLI smoke: `--help` dos 5 subcomandos testados? Liste os 5.
   `status --run-id inexistente`: exit_code=0, sem traceback?

PARTE B — Documentação:
7. CHANGELOG com seção M4 cobrindo TAREFA-401–408? Deltas de contrato documentados
   (`update_annotation`, `read_gold_chunks`, async `search`)?
8. `docs/adr/ADR-013-round2-funnel.md` (NÃO ADR-012) com Context, Decision,
   Consequences e `top_n=3` justificado?
9. README com M4 ✅ e comandos `analyze` / `report`?
10. CI job `e2e`: `needs: [unit, integration]`? `qdrant/qdrant:v1.9` como service?
    `timeout-minutes: 10`?

GATE M4: PASS nesta tarefa + PASS nas TAREFA-401–408 = milestone M4 concluído.
As 5 perguntas operacionais do §2.1 do doc-base devem ser respondíveis com os
artefatos de M4:
  H1 (Wilcoxon base×base) → `wilcoxon_reports` no `StatsReport`
  H2 (Friedman+Nemenyi LLMs) → `friedman_reports` + `nemenyi_pairs`
  H3 (interação base×LLM) → `mlm_reports.interaction_p_value`
  H4 (melhor = mais robusto) → `best_config` + `ConfigAggregate.failure_rate`
  (Origem dos erros) → `plot_failure_breakdown` + `rubric_feedback`

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Cole output do grep do item 5d. Liste os 5 subcomandos do item 6.
Confirme `pytest -m e2e tests/e2e/test_full_pipeline_m4.py -v --tb=short`
(cole as últimas 20 linhas) e `pytest -m "unit or integration" --cov=src
--cov-fail-under=85` (cole o resumo).

GATE M4: PASS nesta tarefa + PASS nas TAREFA-401–408 = milestone M4 concluído.
~~~

---

