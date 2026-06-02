# Changelog — inteligenciomica-eval

Todas as mudanças notáveis são documentadas aqui por milestone.

---

## [M4] — TAREFA-401 a 409 (2026-06-02)

### Entregáveis por tarefa

| Tarefa | Descrição | Artefato principal |
|--------|-----------|--------------------|
| TAREFA-401 | CLI `annotate --export`: exportação estratificada JSONL | `cli.py:annotate`, `_run_export_annotate` |
| TAREFA-402 | `IngestHumanAnnotationUseCase`: ingestão de anotações offline | `application/use_cases/ingest_annotation.py` |
| TAREFA-403 | `AggregateResultsUseCase`: agregação por config {base, llm} | `application/aggregate_results.py` |
| TAREFA-404 | Adapters estatísticos: `WilcoxonAdapter`, `FriedmanNemenyiAdapter`, `MixedLinearModelAdapter` | `infrastructure/adapters/stats_adapters.py` |
| TAREFA-405 | `StatisticalAnalysisUseCase` + correção múltipla BH/Holm + `StatsReport` VO | `application/statistical_analysis.py` |
| TAREFA-406 | VOs de visualização: `FigurePath`, `ReportPath`; ports: `VisualizationPort`, `ReportPort` | `domain/ports.py`, `domain/value_objects.py` |
| TAREFA-407 | `MatplotlibVisualizationAdapter` com 6 plots canônicos (SVG, backend Agg) | `visualization/matplotlib_adapter.py` |
| TAREFA-408 | `HTMLReportAdapter` (HTML autocontido, SVGs embutidos base64); CLI `analyze`, `report`, `status`, `show-config` | `infrastructure/adapters/html_report.py`, `cli.py` |
| TAREFA-409 | Gate E2E M4: `test_full_pipeline_m4.py` — 5 etapas, < 90s CPU; ADR-013; CHANGELOG | `tests/e2e/test_full_pipeline_m4.py` |

### Deltas de contrato declarados em M4

Os itens abaixo representam desvios em relação à especificação de arquitetura
original (§5.1) aprovados implicitamente pela conclusão bem-sucedida dos milestones
anteriores. Estão aqui documentados de forma explícita para rastreabilidade.

#### 1. `ResultWriterPort.update_annotation` (M4 — TAREFA-402)

Método `update_annotation(row_id, *, critical_failure_flag, critical_failure_note)`
adicionado ao `ResultWriterPort` e implementado em `ParquetStorage`. Não estava
previsto no §5.1 original — adicionado como extensão aditiva (sem breaking change).

#### 2. `GoldChunkReaderPort.read_gold_chunks` (delta em relação ao §5.1)

O §5.1 declara `gold_for(question_id: str) -> list[str]`. A implementação em M1
(TAREFA-013) adotou `read_gold_chunks(question_id: str) -> tuple[str, ...]` como
nome canônico. Qualquer uso novo do port (M4+) usa `read_gold_chunks`. Uma
renomeação para `gold_for` seria tratada como PR isolado em M5+.

#### 3. `RetrieverPort.search` — uso assíncrono (delta em relação ao §5.1)

O §5.1 declara `search(...)` como método síncrono. M1 (TAREFA-013) implementou
`QdrantRetrieverAdapter` com `async def search(...)`. Qualquer chamada ao
`RetrieverPort` em M4+ usa `await retriever.search(...)`.

### Breaking changes

Nenhum. M4 é inteiramente **aditivo** — novos use cases, adapters e subcomandos
CLI. Todos os contratos existentes de M0–M3 permanecem inalterados.

### Cobertura ao fechar M4

- 1068 testes passando, 5 skipped, 90.97% de cobertura total
- Gate de 85% mantido no job CI `unit`

---

## [M3] — TAREFA-301 a 310 (2026-05-30)

Orquestração das 4 GPUs, `WaveSchedulerService`, `VLLMServerManagerAdapter` real,
pipeline completo de Rodada 1 (geração + métricas + julgamento + anotação).

---

## [M1] — TAREFA-013 a 021 (2026-05-28)

Adapters de infraestrutura: `QdrantRetrieverAdapter`, `VLLMGeneratorAdapter`,
`PrometheusJudgeAdapter`, `RAGASLayer1Adapter`, `DeterministicMetricsAdapter`,
`VLLMServerManagerAdapter`, `AnnotationReaderAdapter`. Gate de integração M1.

---

## [M0] — TAREFA-001 a 012 (2026-05-22)

Bootstrap do repositório, domínio completo: hierarquia de erros, value objects,
entidades, ports/protocols, serviços de domínio (`FinalScoreCalculator`,
`RankScoreCalculator`, `AggregationService`), `ParquetStorage`, config YAML,
fakes/factories, E2E stub.
