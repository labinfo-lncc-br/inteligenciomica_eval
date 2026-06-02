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

## TAREFA-403 — `AggregateResultsUseCase`

**Épico:** E6 — Agregação · **Skill:** data-engineer
**Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-008 (`AggregationService`) — M0; TAREFA-009 (ParquetStorage) — M0;
TAREFA-402 (`IngestHumanAnnotationUseCase`) — upstream para `critical_failure_flag`
**ADRs:** ADR-007 (NaN), ADR-009 (idempotência) · **Camadas:** application

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §14.7 TAREFA-403,
§7.2 "Agregação por configuração", §4.4 `AggregationService`). Padrão:
python-clean-architecture §2. Skills: data-engineer. M0 concluído: `AggregationService`
em `domain/services/aggregation.py` e `ConfigAggregate` VO existem. "Nota M4" item 8.

TAREFA: TAREFA-403 — implementar `AggregateResultsUseCase` em
`src/inteligenciomica_eval/application/aggregate_results.py`.

ESPECIFICAÇÃO:

DTOs (frozen dataclasses, sem Pydantic):
```python
@dataclass(frozen=True)
class AggregateResultsInput:
    run_id: str
    round_id: str
    phase: str | None = None    # None = ambos A e B
    failure_threshold: float = 0.70

@dataclass(frozen=True)
class AggregateResultsOutput:
    run_id: str
    round_id: str
    aggregates: tuple[ConfigAggregate, ...]     # ordenado por rank_score desc
    n_total_results: int
    n_nan_excluded: int
    n_configs: int
    best_config: ConfigAggregate                # config com maior rank_score
```

Lógica do use case:
1. `results_frame = reader.load(round_id=inp.round_id, phase=inp.phase)`
2. Filtrar por `run_id` (o `ResultFrame` pode conter múltiplos runs).
3. Delegar 100% ao `AggregationService.aggregate_all(results, threshold=inp.failure_threshold)`
   — NENHUMA lógica de agregação reimplementada aqui.
4. Ordenar `ConfigAggregate` por `rank_score.value` descrescente (melhor primeiro).
5. `best_config` = primeiro da lista (rank_score máximo).
6. Contar `n_nan_excluded` = soma de `agg.n_excluded_nan` por config.
7. Persistir o sumário de agregados em JSON:
   `{data_dir}/{run_id}_{round_id}_aggregates.json` — serialização simples dos
   `ConfigAggregate` como dicts. Usar `json.dumps` + `dataclasses.asdict`.
8. Retornar `AggregateResultsOutput`.

Logging estruturado: `run_id`, `round_id`, `n_configs`, `n_nan_excluded`,
`best_config` (base + llm + rank_score), `latency_ms`.

ENTREGÁVEL:
- `src/inteligenciomica_eval/application/aggregate_results.py`
- `tests/unit/application/test_aggregate_results_use_case.py`
  a) 2 configs × 3 perguntas × 2 seeds = 12 resultados: agregados corretos.
  b) `best_config` é a config com maior rank_score — testado.
  c) NaN excluído: `n_nan_excluded` correto — testado.
  d) Ordenação desc por rank_score — testado.
  e) Persistência: arquivo JSON criado em `tmp_path` com campos corretos.
  f) Filtro por `run_id`: resultados de outro run_id são ignorados.
- `tests/golden/aggregate_results_expected.json`
  (2 ConfigAggregate esperados para 12 EvaluationResult sintéticos, calculados
  independentemente; incluir 1 NaN para testar n_excluded_nan)

RESTRIÇÕES (DoD §14.2):
- Use case em `application/` NÃO reimplementa lógica de agregação.
- NÃO importa `AggregationService` de forma acoplada — injetar via `__init__`.
- `from __future__ import annotations`; type hints; mypy --strict; import-linter OK.
- Cobertura ≥ 90% do módulo.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-403):
- `AggregationService` injetado (não instanciado internamente) — verificado via mock.
- Zero lógica de agregação no use case — verificado pelo Codex.
- `best_config` é o de maior `rank_score` — testado.
- `n_nan_excluded` correto — testado.
- JSON de sumário criado e legível — testado.
- Golden confirma valores independentes.
- `mypy --strict`; `lint-imports`; cobertura ≥ 90%.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-403 + arquitetura §4.4 (`AggregationService`) + §7.2 +
ADR-007/009 + "Nota de operacionalização M4" item 8.

VERIFIQUE, item a item, citando arquivo:linha:
1. `AggregateResultsUseCase` em `application/aggregate_results.py`?
   `AggregationService` INJETADO no `__init__` (não instanciado internamente)?
2. ZERO lógica de agregação (média, mediana, IQR, failure_rate, win_rate) reimplementada
   no use case — confirme buscando por `statistics.`, `sum(`, `len(` fora de chamadas
   a `AggregationService`?
3. Ordenação dos agregados por `rank_score.value` descrescente?
   `best_config` = primeiro da lista — testado?
4. Filtro por `run_id` correto — testado com 2 runs distintos?
5. `n_nan_excluded = sum(agg.n_excluded_nan for agg in aggregates)` correto?
   NaN excluído testado?
6. JSON de sumário criado (campo por campo verificável)? `dataclasses.asdict` usado?
7. Golden: recompute manualmente `failure_rate` de 1 config do caso de teste e
   compare com o JSON golden.
8. `mypy --strict`; `lint-imports`; cobertura ≥ 90%? DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Inclua recomputação de `failure_rate` de 1 config.
Confirme `pytest tests/unit/application/test_aggregate_results_use_case.py -v` e
`lint-imports`.
~~~

---

