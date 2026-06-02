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

## TAREFA-407 — `MatplotlibVisualizationAdapter` (6 plots canônicos)

**Épico:** E8 · **Skills:** ml-engineer, python-engineer
**Prioridade:** P1 · **Tamanho:** M
**Dependências:** TAREFA-406 (`VisualizationPort`, `FigurePath`, `ConfigAggregate`) —
TAREFA-403 para dados reais em testes de integração
**ADRs:** ADR-001 · **Camadas:** visualization/

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (§11.4 visualizações canônicas).
Skills: ml-engineer, python-engineer. TAREFA-406 concluída: `VisualizationPort`
disponível. "Nota de operacionalização M4" itens 3 e 4.

TAREFA: TAREFA-407 — implementar `MatplotlibVisualizationAdapter` em
`src/inteligenciomica_eval/visualization/matplotlib_adapter.py`,
implementando `VisualizationPort` (6 métodos, conforme TAREFA-406).

REGRA GLOBAL (Nota M4 item 4 — BLOQUEADOR se violada):
- `import matplotlib; matplotlib.use("Agg")` ANTES de qualquer
  `import matplotlib.pyplot as plt` ou `import seaborn`. TOPO DO MÓDULO.
- Cada método: `fig, ax = plt.subplots(...)`.
  Após `fig.savefig(path, dpi=config.dpi, bbox_inches="tight")`: `plt.close(fig)`.
- ZERO: `plt.show()`, `plt.clf()`, `plt.cla()`, `plt.figure()` sem captura da variável.
- `seaborn.set_theme(style="whitegrid", palette="colorblind")` no `__init__` (1×).
- Salvar sempre em SVG (`format="svg"`); PNG adicional se `"png" in config.formats`.
- Paleta `"colorblind"` ou `"muted"` (suporte a daltonismo obrigatório).

ESPECIFICAÇÃO — 6 métodos (assinaturas exatas do `VisualizationPort`):

(1) `plot_rankscore_heatmap(aggregates, *, output_dir, metric_name="rank_score")`:
    - Pivot: linhas=bases, colunas=LLMs, valores=métrica.
    - Métricas suportadas: `"rank_score"`, `"median_score"`, `"failure_rate"`,
      `"win_rate"`, `"critical_failure_rate"`.
    - `seaborn.heatmap(data, annot=True, fmt=".3f", cmap="RdYlGn", vmin=0, vmax=1,
       ax=ax, linewidths=0.5)`.
    - Borda preta na célula máxima (via `ax.add_patch(Rectangle(...))`).
    - Arquivo: `output_dir / f"{metric_name}_heatmap.svg"`.

(2) `plot_finalscore_boxplots(aggregates, *, output_dir, results=None)`:
    - Se `results` (ResultFrame) fornecido: boxplot real dos FinalScore.
    - Fallback (results=None): boxplot aproximado a partir de `median_score`, `iqr`
      do `ConfigAggregate` (documentado no docstring como aproximação).
    - Ordenar configs por `rank_score` descrescente (melhor à esquerda).
    - Arquivo: `output_dir / "finalscore_boxplot.svg"`.

(3) `plot_interaction(aggregates, *, output_dir)`:
    - Interaction plot: x=base (2 pontos), y=`median_score`, linha por LLM.
    - `ax.legend(title="LLM", bbox_to_anchor=(1.05,1))`.
    - Arquivo: `output_dir / "interaction_plot.svg"`.

(4) `plot_radar(aggregates, *, output_dir, top_n=5)`:
    - Top-N configs por `rank_score` em radar (spider chart).
    - 6 eixos: `answer_correctness`, `faithfulness`, `context_recall`,
      `context_precision`, `answer_relevancy`, `rubric_biomed_score`
      (valores de `ConfigAggregate.mean_score` por métrica, se disponíveis, ou de
      `AggregationService` por métrica — documentar a fonte).
    - NOTA: `ConfigAggregate` (M0) armazena agregados de `FinalScore`, não de cada
      métrica individualmente. Se os campos por métrica não existirem no VO atual,
      usar os campos disponíveis (ex.: `median_score`, `failure_rate`) como eixos
      alternativos e documentar a adaptação no docstring.
    - `ax = fig.add_subplot(111, projection="polar")`.
    - Arquivo: `output_dir / f"radar_top{top_n}.svg"`.

(5) `plot_per_question_ranking(results, *, output_dir)`:
    - Heatmap question × config com `FinalScore` por célula.
    - Construir matriz de `ResultFrame` — iterar sobre `EvaluationResult`.
    - `seaborn.heatmap(matrix, annot=True, fmt=".2f", cmap="YlOrRd")`.
    - Arquivo: `output_dir / "per_question_ranking.svg"`.

(6) `plot_failure_breakdown(aggregates, *, output_dir)`:
    - Stacked bar: `failure_rate` (amarelo) + `critical_failure_rate` (vermelho) por config.
    - Se nenhuma config com `failure_rate > config.failure_threshold`: figura vazia com
      texto "Sem falhas acima do threshold". Arquivo gerado igualmente (sem exceção).
    - Arquivo: `output_dir / "failure_breakdown.svg"`.

`VisualizationAdapterConfig` (Pydantic):
```python
formats: list[str] = ["svg"]
dpi: int = 150
figure_width: float = 10.0
figure_height: float = 6.0
failure_threshold: float = 0.20
top_n_radar: int = 5
```

ENTREGÁVEL:
- `src/inteligenciomica_eval/visualization/matplotlib_adapter.py`
- Extensão de `infrastructure/config/adapter_configs.py`
- `tests/unit/visualization/test_matplotlib_adapter.py`
  Para CADA um dos 6 métodos:
  a) Arquivo SVG criado em `tmp_path` com `st_size > 0`.
  b) `plt.close` chamado 1× por método (via `mocker.patch("matplotlib.pyplot.close")`).
  c) `plot_failure_breakdown` com FailureRate=0 → arquivo criado sem exceção.
  d) `plot_rankscore_heatmap` com `metric_name` inválido → `ConfigValidationError`.
- `tests/integration/visualization/test_matplotlib_adapter_integration.py`
  (gera SVGs reais sem mock; `xml.etree.ElementTree.fromstring` sem exceção em cada SVG;
   marcado `@pytest.mark.integration`)

RESTRIÇÕES (DoD §14.2 + Nota M4 itens 3 e 4 — cada item é potencial bloqueador):
- `matplotlib.use("Agg")` ANTES dos imports — BLOQUEADOR.
- `plt.close(fig)` após CADA `fig.savefig()` em TODOS os 6 métodos — BLOQUEADOR.
- ZERO `plt.show()` / `plt.clf()` / `plt.cla()`.
- `visualization/` NÃO importa `qdrant_client`, `openai`, `ragas`, `statsmodels`.
- `from __future__ import annotations`; type hints; mypy --strict; import-linter OK.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-407):
- 6 métodos retornam `FigurePath` e criam SVG válido.
- `plt.close(fig)` confirmado por mock em cada método (6 assertivas).
- SVG é XML válido (teste de integração).
- `matplotlib.use("Agg")` na linha correta — verificado pelo Codex (item 1 do Prompt B).
- `plot_failure_breakdown` com 0 falhas → arquivo criado sem exceção.
- import-linter OK; mypy --strict; cobertura ≥ 85%.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer (skill ml-engineer). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-407 + §11.4 + "Nota M4" itens 3 e 4 + TAREFA-406
(VisualizationPort, assinaturas exatas).

VERIFIQUE, item a item, citando arquivo:linha:
1. `matplotlib.use("Agg")` está NA LINHA CORRETA: ANTES de qualquer
   `import matplotlib.pyplot` ou `import seaborn`? Se ausente OU depois: BLOQUEADOR.
2. 6 métodos com assinaturas EXATAS do `VisualizationPort` (TAREFA-406)?
   Liste os 6 nomes encontrados.
3. `plt.close(fig)` APÓS CADA `fig.savefig()` em TODOS os 6 métodos?
   Liste arquivo:linha de cada ocorrência. Se algum método não tiver: BLOQUEADOR.
4. Execute: `grep -n "plt.show\|plt.clf\|plt.cla"
   src/inteligenciomica_eval/visualization/matplotlib_adapter.py` (deve ser vazio).
5. Testes unitários: mock de `plt.close` para CADA um dos 6 métodos, com assertiva
   de `call_count >= 1`? 6 assertivas independentes?
6. SVG XML válido via `xml.etree.ElementTree` no teste de integração?
7. `plot_failure_breakdown` com FailureRate=0 → arquivo criado sem exceção — testado?
8. Paleta `"colorblind"` ou `"muted"`; `seaborn.set_theme` no `__init__`?
9. import-linter: `visualization/` NÃO importa qdrant/openai/ragas/statsmodels?
10. mypy --strict; cobertura ≥ 85%; DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Cole os outputs dos greps dos itens 1 (confirmar linha) e 4 (deve ser vazio).
Liste os 6 `plt.close` com suas linhas.
Confirme `pytest tests/unit/visualization/ tests/integration/visualization/ -v`.
~~~

---

