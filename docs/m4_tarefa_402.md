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

## TAREFA-402 — `IngestHumanAnnotationUseCase`

**Épico:** E5 · **Skill:** python-engineer
**Prioridade:** P0 · **Tamanho:** S
**Dependências:** TAREFA-401 (formato JSONL de anotação), TAREFA-009 (ParquetStorage) — M0
**ADRs:** ADR-010, ADR-009 (idempotência) · **Camadas:** application + cli

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, ADR-010,
§14.7 TAREFA-402). Padrão: python-clean-architecture §2 (use case de application).
TAREFA-401 concluída: formato JSONL conhecido. "Nota de operacionalização M4" item 7.

TAREFA: TAREFA-402 — implementar `IngestHumanAnnotationUseCase` em
`src/inteligenciomica_eval/application/ingest_annotation.py` e o flag `--ingest`
no subcomando `annotate` da CLI.

ESPECIFICAÇÃO:

DTOs (frozen dataclasses, sem Pydantic):
```python
@dataclass(frozen=True)
class IngestAnnotationInput:
    annotations_path: Path      # arquivo JSONL editado pelo especialista
    run_id: str
    force: bool = False         # reingerir linhas já anotadas

@dataclass(frozen=True)
class IngestAnnotationOutput:
    n_ingested: int         # critical_failure_flag atualizado com sucesso
    n_skipped: int          # já anotadas e force=False
    n_invalid: int          # linhas com flag diferente de 0, 1 ou null
    n_missing_row_id: int   # row_id do JSONL não encontrado no Parquet
```

Lógica do use case:
1. Ler o JSONL linha por linha via `AnnotationReaderPort.read(run_id)` OU diretamente
   do `path` (preferir leitura direta do path para simplicidade — não criar adapter
   desnecessário para leitura de arquivo local, use `pathlib.Path.open`).
2. Para cada linha:
   a. Validar `critical_failure_flag ∈ {0, 1, null}`. Se inválido: contar em `n_invalid`,
      logar WARNING, pular — NÃO abortar.
   b. Se `flag` é `null`: pular silenciosamente (especialista ainda não decidiu).
   c. Verificar se `row_id` existe via `ResultWriterPort.exists(row_id)`.
      Se não existir: contar `n_missing_row_id`, logar WARNING, pular.
   d. Verificar idempotência (ADR-009): se linha já tem `critical_failure_flag` não-null
      e `force=False`: contar `n_skipped`, pular.
   e. Persistir via `ResultWriterPort.update_annotation(row_id, flag, note)`.
      NOTA: `update_annotation` é um NOVO método que deve ser adicionado ao
      `ResultWriterPort` NESTA tarefa (extensão de contrato). Declarar na Nota de M4
      como delta explícito. Implementar o método real em `ParquetStorage` (substituir
      o stub `NotImplementedError` que poderá existir).
3. Retornar `IngestAnnotationOutput`.

`update_annotation` no `ResultWriterPort`:
```python
# Extensão de contrato M4 — delta de §5.1 declarado na Nota de M4
def update_annotation(
    self,
    row_id: RowId,
    *,
    critical_failure_flag: int,         # 0 ou 1
    critical_failure_note: str = "",
) -> None: ...
```

Implementação em `ParquetStorage`: localizar a partição que contém `row_id`, ler a
partição, atualizar `critical_failure_flag` e `critical_failure_note`, reescrever a
partição. Logar `annotation_updated` (structlog, row_id, flag).

CLI: adicionar `--ingest PATH` ao subcomando `annotate`:
```
ielm-eval annotate --run-id TEXT --ingest PATH [--force]
```
Ao final: `rich.table` com `n_ingested`, `n_skipped`, `n_invalid`, `n_missing_row_id`.

ENTREGÁVEL:
- `src/inteligenciomica_eval/application/ingest_annotation.py`
- Extensão de `ResultWriterPort` em `domain/ports.py` (`update_annotation`)
- Implementação de `update_annotation` em `infrastructure/repositories/parquet_storage.py`
- Extensão do subcomando `annotate` em `cli.py` (flag `--ingest`)
- `tests/unit/application/test_ingest_annotation.py`
  a) Ingestão normal: 3 linhas com flag 0/1 → `n_ingested=3`.
  b) Flag inválido (2): `n_invalid=1`, não aborta, demais ingeridas.
  c) `flag=null`: linha pulada silenciosamente, não conta em inválido.
  d) `force=False`, linha já anotada: `n_skipped=1`.
  e) `force=True`, linha já anotada: `n_ingested=1` (sobrescreve).
  f) `row_id` inexistente: `n_missing_row_id=1`, sem exceção.
- `tests/integration/repositories/test_parquet_annotation.py`
  (tmp_path; append de EvaluationResult; update_annotation; load de volta; flag correto)

RESTRIÇÕES (DoD §14.2):
- Use case em `application/` NÃO importa de `infrastructure/` diretamente.
- `update_annotation` como extensão de port documentada explicitamente nesta tarefa.
- `from __future__ import annotations`; type hints; mypy --strict; import-linter OK.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-402):
- Flag inválido: WARNING + pular, sem abortar — testado.
- `flag=null`: pulado silenciosamente — testado.
- Idempotência (ADR-009): `force=False` pula anotada — testado.
- `update_annotation` no `ResultWriterPort` declarado como delta de contrato.
- Roundtrip: `update_annotation` → `load` → `critical_failure_flag` correto — testado.
- `mypy --strict`; `lint-imports`; cobertura ≥ 85%.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-402 + ADR-010 + ADR-009 + §5.1 (ResultWriterPort) +
"Nota de operacionalização M4" item 7.

VERIFIQUE, item a item, citando arquivo:linha:
1. `IngestHumanAnnotationUseCase` em `application/ingest_annotation.py`?
   NÃO importa de `infrastructure/` diretamente?
2. Flag inválido (ex: 2) → WARNING + pular, sem abortar + `n_invalid` correto — testado?
3. `flag=null` → pular silenciosamente (não conta em inválido) — testado?
4. Idempotência (ADR-009): `force=False` pula linha já anotada → `n_skipped` — testado?
   `force=True` sobrescreve → `n_ingested` — testado?
5. `row_id` inexistente → `n_missing_row_id`, sem exceção — testado?
6. `update_annotation` adicionado ao `ResultWriterPort` em `domain/ports.py` declarado
   como delta de contrato M4? Implementação real em `ParquetStorage` (sem NotImplementedError)?
7. Roundtrip integration: `update_annotation` → `load` → campo `critical_failure_flag`
   correto no Parquet — testado?
8. `mypy --strict`; `lint-imports`; cobertura ≥ 85%? DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Confirme `pytest tests/unit/application/test_ingest_annotation.py
tests/integration/repositories/test_parquet_annotation.py -v` e `lint-imports`.
~~~

---

