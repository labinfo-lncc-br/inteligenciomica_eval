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

## TAREFA-406 — Extensões de domínio M4: novos ports e VOs para visualização

**Épico:** E8 — Visualização · **Skill:** python-engineer
**Prioridade:** P0 · **Tamanho:** S
**Dependências:** TAREFA-005 (ports existentes), TAREFA-403 (`ConfigAggregate`),
TAREFA-405 (`StatsReport`) — pré-requisito de tipos
**ADRs:** ADR-001 · **Camadas:** domain

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §5.1 ports,
§11.4 visualizações). Skills: python-engineer. TAREFA-405 concluída: `StatsReport`
disponível. "Nota de operacionalização M4" item 3.
Esta tarefa desbloqueador de TAREFA-407 e TAREFA-408.

TAREFA: TAREFA-406 — adicionar novos ports e VOs de M4 em `domain/ports.py` e
`domain/value_objects.py`, sem quebrar nenhum contrato existente.

ESPECIFICAÇÃO — VOs em `domain/value_objects.py`:

```python
@dataclass(frozen=True)
class FigurePath:
    path: Path
    format: str       # "svg" | "png"
    plot_type: str    # "rankscore_heatmap"|"finalscore_boxplot"|"interaction"|
                      # "radar"|"per_question_ranking"|"failure_breakdown"

@dataclass(frozen=True)
class ReportPath:
    path: Path
    format: str   # "html" em M4; "pdf" reservado para M5
    run_id: str
```

ESPECIFICAÇÃO — Ports em `domain/ports.py`:

(1) `VisualizationPort` (@runtime_checkable Protocol):
```python
class VisualizationPort(Protocol):
    def plot_rankscore_heatmap(
        self,
        aggregates: Sequence[ConfigAggregate],
        *,
        output_dir: Path,
        metric_name: str = "rank_score",
    ) -> FigurePath: ...

    def plot_finalscore_boxplots(
        self,
        aggregates: Sequence[ConfigAggregate],
        *,
        output_dir: Path,
        results: ResultFrame | None = None,
    ) -> FigurePath: ...

    def plot_interaction(
        self,
        aggregates: Sequence[ConfigAggregate],
        *,
        output_dir: Path,
    ) -> FigurePath: ...

    def plot_radar(
        self,
        aggregates: Sequence[ConfigAggregate],
        *,
        output_dir: Path,
        top_n: int = 5,
    ) -> FigurePath: ...

    def plot_per_question_ranking(
        self,
        results: ResultFrame,
        *,
        output_dir: Path,
    ) -> FigurePath: ...

    def plot_failure_breakdown(
        self,
        aggregates: Sequence[ConfigAggregate],
        *,
        output_dir: Path,
    ) -> FigurePath: ...
```

(2) `ReportPort` (@runtime_checkable Protocol):
```python
class ReportPort(Protocol):
    def generate_html(
        self,
        *,
        run_id: str,
        aggregates: Sequence[ConfigAggregate],
        results: ResultFrame,
        stats_report: StatsReport,
        figure_paths: Sequence[FigurePath],
        output_path: Path,
    ) -> ReportPath: ...
```

ENTREGÁVEL:
- Extensão de `src/inteligenciomica_eval/domain/ports.py`
- Extensão de `src/inteligenciomica_eval/domain/value_objects.py`
- Extensão de `tests/unit/domain/test_ports_contracts.py`
  (teste de `isinstance` com stub mínimo para `VisualizationPort` e `ReportPort`)

RESTRIÇÕES (DoD §14.2):
- Todos os novos ports: `@runtime_checkable`.
- VOs: frozen dataclasses SEM Pydantic.
- import-linter: `domain/` NÃO importa de `infrastructure/`.
- `mypy --strict`; `ruff`; `lint-imports` verdes.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-406):
- 2 novos ports com assinaturas exatas; `isinstance` com stub passa — testado.
- 2 novos VOs são frozen dataclasses sem Pydantic.
- import-linter OK; mypy --strict; DoD §14.2.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-406 + arquitetura §5.1 + §11.4 + "Nota M4" item 3.

VERIFIQUE, item a item, citando arquivo:linha:
1. `VisualizationPort` e `ReportPort` são `typing.Protocol` com `@runtime_checkable`?
2. Assinaturas dos 6 métodos do `VisualizationPort` batem EXATAMENTE com a spec?
   (parâmetros keyword-only, tipos de retorno `FigurePath`, `ReportPath`)
3. `generate_html` em `ReportPort`: todos os parâmetros keyword-only? Retorna `ReportPath`?
4. `FigurePath` e `ReportPath` são frozen dataclasses sem Pydantic?
5. Testes de `isinstance` com stub para ambos os ports — presentes e passando?
6. import-linter OK? mypy --strict? Sem imports de infra em domain? DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Confirme `pytest tests/unit/domain/test_ports_contracts.py -v` e `lint-imports`.
~~~

---

