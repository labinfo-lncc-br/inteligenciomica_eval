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

## TAREFA-405 — `StatisticalAnalysisUseCase` + correção para múltiplos testes

**Épico:** E7 · **Skill:** ml-engineer
**Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-404 (adapters de stats), TAREFA-403 (aggregates), TAREFA-005
(`StatsPort`, `ResultReaderPort`) — M0
**ADRs:** ADR-011, ADR-007 · **Camadas:** application

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §14.7 TAREFA-407,
doc-base §8.1–8.5). Padrão: python-clean-architecture §2 (use case de application).
Skills: ml-engineer. TAREFA-404 concluída: adapters de stats disponíveis.
"Nota de operacionalização M4" item 6.

TAREFA: TAREFA-405 — implementar `StatisticalAnalysisUseCase` em
`src/inteligenciomica_eval/application/statistical_analysis.py`.

ESPECIFICAÇÃO:

DTOs:
```python
@dataclass(frozen=True)
class StatisticsInput:
    run_id: str
    round_id: str
    metrics: tuple[str, ...] = ("final_score",)     # métricas a testar
    tests: tuple[str, ...] = ("all",)               # "wilcoxon"|"friedman"|"mlm"|"all"
    alpha: float = 0.05
    correction_method: str = "benjamini-hochberg"

@dataclass(frozen=True)
class StatsReport:
    """Relatório consolidado — input do HTMLReportAdapter."""
    run_id: str
    round_id: str
    wilcoxon_reports: tuple[WilcoxonReport, ...]       # por métrica
    friedman_reports: tuple[FriedmanReport, ...]       # por métrica
    mlm_reports: tuple[MLMReport, ...]                 # por fórmula
    correction_method: str
    alpha: float
    # Síntese executiva (derivada dos reports)
    base_difference_significant: bool    # qualquer Wilcoxon com p_corrected < alpha
    llm_difference_significant: bool    # qualquer Friedman com p_corrected < alpha
    interaction_significant: bool       # MLM interação p < alpha
    top_llm_by_friedman: str | None     # LLM com mais vitórias no Nemenyi (ou None)
```

Lógica do use case:
1. `results_frame = reader.load(round_id=inp.round_id, phase="A")`
   (estatística é sobre Experimento A — Experimento B é diagnóstico complementar;
   documentar esta decisão no docstring).
2. Filtrar por `run_id`.
3. Para cada `metric` em `inp.metrics`:
   a. Se "wilcoxon" em `tests` ou "all": `wilcoxon_report = wilcoxon_adapter.wilcoxon_paired(frame, metric)`
   b. Se "friedman" em `tests` ou "all": `friedman_report = friedman_adapter.friedman_nemenyi(frame, metric)`
   c. Se "mlm" em `tests` ou "all": `mlm_report = mlm_adapter.mixed_linear_model(frame, formula)`
      onde `formula = f"{metric} ~ base * llm + (1 | question_id)"`.
4. Correção para múltiplos testes (Benjamini-Hochberg ou Holm, conforme `correction_method`):
   - Coletar TODOS os p-values não-NaN dos Wilcoxon + Friedman reports.
   - Aplicar correção via `statsmodels.stats.multitest.multipletests`.
   - Atualizar `p_value_corrected` e `significant` em cada report.
   - NOTA: a correção é aplicada DENTRO do use case, não nos adapters individuais.
     Os adapters retornam p_values brutos; o use case faz a correção.
5. Derivar campos de síntese (`base_difference_significant`, etc.).
6. Persistir `StatsReport` em JSON: `{data_dir}/{run_id}_{round_id}_stats.json`.
7. Retornar `StatsReport`.

ENTREGÁVEL:
- `src/inteligenciomica_eval/application/statistical_analysis.py`
- `tests/unit/application/test_statistical_analysis.py`
  a) Correção BH: 3 p-values [0.04, 0.03, 0.02] → p-values corrigidos calculados
     manualmente e conferem.
  b) `tests=("wilcoxon",)`: apenas Wilcoxon chamado; Friedman/MLM NÃO chamados
     (verificado via mock).
  c) `base_difference_significant=True` quando pelo menos 1 Wilcoxon corrigido < alpha.
  d) `top_llm_by_friedman`: LLM com mais vitórias no Nemenyi identificado corretamente.
  e) Persistência JSON: arquivo criado com campos de síntese.
- `tests/golden/stats_report_expected.json`
  (StatsReport sintético para o E2E M4)

RESTRIÇÕES (DoD §14.2):
- `statsmodels.stats.multitest.multipletests` usado SOMENTE no use case (não nos adapters).
- Use case NÃO importa `scipy`/`statsmodels` diretamente — via adapters injetados.
- `from __future__ import annotations`; type hints; mypy --strict; import-linter OK.
- Cobertura ≥ 90%.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-405):
- Correção BH: p-values corrigidos conferem com cálculo manual — testado.
- `tests=("wilcoxon",)`: Friedman/MLM não chamados — testado via mock.
- `StatsReport` JSON persistido — testado.
- `top_llm_by_friedman` correto — testado.
- mypy --strict; import-linter OK; cobertura ≥ 90%.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer (skill ml-engineer). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-405 + doc-base §8.1–8.5 + ADR-011 + TAREFA-404 (VOs).

VERIFIQUE, item a item, citando arquivo:linha:
1. `StatsReport` é frozen dataclass em `domain/value_objects.py`?
   Campos `wilcoxon_reports`, `friedman_reports`, `mlm_reports`, e campos de síntese
   presentes com tipos corretos?
2. Correção múltipla (`multipletests`) aplicada NO USE CASE (não nos adapters)?
   Import de `statsmodels.stats.multitest` SOMENTE em application — NÃO em adapters?
3. `tests=("wilcoxon",)` → adapters Friedman/MLM NÃO chamados — testado via mock?
4. Correção BH: recalcule você mesmo os p-values corrigidos para o caso de teste
   [0.04, 0.03, 0.02] com BH e compare com o resultado do código. Cite os valores.
5. `base_difference_significant` derivado corretamente de `any(r.significant for r in wilcoxon_reports)`?
6. Use case não importa `scipy`/`statsmodels` diretamente (apenas via adapters)?
   Execute: `grep -n "import scipy\|import statsmodels"
   src/inteligenciomica_eval/application/statistical_analysis.py` (deve ter só
   `multipletests` — aceitável pois é utilitário de correção, não análise estatística)?
7. JSON de StatsReport criado e parseable? Campos de síntese presentes?
8. mypy --strict; import-linter OK; cobertura ≥ 90%? DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Inclua os p-values corrigidos recalculados do item 4.
Confirme `pytest tests/unit/application/test_statistical_analysis.py -v` e `lint-imports`.
~~~

---

