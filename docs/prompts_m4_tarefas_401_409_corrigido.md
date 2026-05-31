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

## TAREFA-401 — CLI `annotate`: export estratificado por score baixo

**Épico:** E5 — Camada 3 · **Skill:** python-engineer
**Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-005 (ResultReaderPort), TAREFA-009 (ParquetStorage) — M0;
TAREFA-309 (CLI + factories wiring) — M3
**ADRs:** ADR-010 (anotação offline), ADR-008 (config) · **Camadas:** cli + application

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §14.7 TAREFA-401,
ADR-010 "anotação humana offline com merge desacoplado"). Skills: python-engineer,
python-clean-architecture. M3 concluído: Parquet com `final_score` disponível;
CLI e DIContainer existentes (TAREFA-309). VER "Nota de operacionalização M4" item 7.

TAREFA: TAREFA-401 — implementar o subcomando CLI `annotate` com flag `--export`,
que exporta respostas priorizadas para JSONL que o especialista biomédico editará
offline. A ingestão será TAREFA-402.

ESPECIFICAÇÃO:

Subcomando Typer:
```
ielm-eval annotate --run-id TEXT --export PATH
                   [--threshold FLOAT]
                   [--max-items INT]
                   [--sort-by finalscore|rubric|random]
```

Comportamento de `--export`:
1. Ler `EvaluationResult` via `ResultReaderPort.load(round_id=..., phase=None)`.
   Filtrar pelo `run_id` (campo do resultado).
2. Estratificação prioritária (ADR-010: revisar o que pode ter erros graves):
   a. Primário: `final_score < threshold` (default 0.70) OU `final_score` é NaN.
   b. Secundário: ordenar pelo `sort_by` escolhido (`finalscore` asc = piores primeiro;
      `rubric` asc = menor `rubric_biomed_score` primeiro; `random` = permutação com
      seed=42 para reprodutibilidade).
   c. Aplicar `--max-items` se fornecido.
3. Serializar CADA item como uma linha JSON (JSONL), campos:
   ```json
   {
     "row_id": "...",
     "question_id": "...",
     "question": "...",
     "generated_answer": "...",
     "ground_truth": "...",
     "final_score": 0.61,
     "rubric_biomed_score": 0.55,
     "rubric_feedback": "...",
     "critical_failure_flag": null,
     "critical_failure_note": ""
   }
   ```
   `critical_failure_flag` permanece `null` — o especialista preenche com `0` ou `1`.
4. Escrever para `PATH` (criar diretório pai se necessário).
5. Imprimir via `rich.panel` um resumo: total de respostas no Parquet, total exportadas,
   breakdown por `final_score` bucket (<0.5, 0.5–0.7, ≥0.7).
6. `--export` e `--ingest` são mutuamente exclusivos (TAREFA-402 implementa `--ingest`).
   Usar `typer.BadParameter` se ambos fornecidos simultaneamente.

Adicionar ao `infrastructure/factories.py`:
```python
def build_annotation_reader(config_path: Path) -> ResultReaderPort: ...
```

ENTREGÁVEL:
- Extensão de `src/inteligenciomica_eval/cli.py` com subcomando `annotate --export`
- Extensão de `src/inteligenciomica_eval/infrastructure/factories.py`
- `tests/unit/test_cli_annotate_export.py`
  (CliRunner; fixtures de 10 EvaluationResult sintéticos — 4 com final_score<0.70,
   2 com final_score=NaN, 4 acima do threshold)
  a) `--export`: arquivo JSONL criado com 6 linhas (os 4 baixos + 2 NaN).
  b) `--sort-by finalscore`: primeiro item tem menor final_score.
  c) `--max-items 3`: exatamente 3 linhas exportadas.
  d) `--export + --ingest` juntos: exit_code != 0, mensagem de erro amigável.
  e) `--export` para diretório inexistente: diretório criado, sem exceção.
  f) JSONL é JSON válido linha por linha (`json.loads` sem exceção em cada linha).
  g) Todos os campos obrigatórios presentes em cada linha.

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings; mypy --strict.
- `cli.py` NÃO importa adapters diretamente — apenas via factories.
- Zero `print()` nu — apenas `rich.*`.
- `KeyboardInterrupt` tratado → structlog INFO + `typer.Exit(130)`.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-401):
- JSONL gerado com campos corretos e `critical_failure_flag: null` — testado.
- Estratificação correta (score < threshold + NaN primeiro) — testado.
- `--max-items` respeitado — testado.
- `--export + --ingest` mutuamente exclusivos — testado.
- `mypy --strict`; `ruff`; `lint-imports`; cobertura ≥ 80% do subcomando.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-401 + arquitetura ADR-010 + §14.7 (TAREFA-401 descrição) +
"Nota de operacionalização M4" item 7 + skill python-engineer.

VERIFIQUE, item a item, citando arquivo:linha:
1. Subcomando `annotate --export` presente? Flags `--run-id`, `--threshold`,
   `--max-items`, `--sort-by` declaradas?
2. Filtro correto: `final_score < threshold` OU `final_score` é NaN — ambos incluídos?
3. Ordenação `--sort-by finalscore` coloca piores primeiro (asc)?
   `--sort-by random` usa seed=42?
4. JSONL: `critical_failure_flag` exportado como `null` (não `0`)? Testado?
5. `--export + --ingest` mutuamente exclusivos com `typer.BadParameter`? Testado?
6. `cli.py` NÃO importa de `infrastructure/adapters/` — grep:
   `grep -n "from.*adapters import" src/inteligenciomica_eval/cli.py` (deve ser vazio)?
7. `KeyboardInterrupt` tratado? Zero `print()` nu?
8. `mypy --strict`; `lint-imports`; cobertura ≥ 80%? DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Cole o output do grep do item 6.
Confirme `pytest tests/unit/test_cli_annotate_export.py -v` e `lint-imports`.
~~~

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

## TAREFA-404 — Adapters `StatsPort`: Wilcoxon, Friedman+Nemenyi e Modelo Linear Misto

**Épico:** E7 — Estatística · **Skill:** ml-engineer
**Prioridade:** P0 · **Tamanho:** L
**Dependências:** TAREFA-005 (`StatsPort`, `ResultFrame`, VOs de output) — M0
**ADRs:** ADR-011 (statsmodels+scikit-posthocs, pymer4 opcional) · **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §5.1 StatsPort,
ADR-011, doc-base §8 análise estatística). Skills: ml-engineer, python-clean-architecture.
M0: `StatsPort` declarado com `WilcoxonReport`, `FriedmanReport`, `MLMReport` como VOs
de retorno (a serem definidos nesta tarefa se ainda não declarados em M0).

TAREFA: TAREFA-404 — três entregáveis:
(a) VOs de saída estatística em `domain/value_objects.py` (se não declarados em M0).
(b) Três adapters implementando `StatsPort` em `infrastructure/adapters/stats_adapters.py`.
(c) Testes unitários e de integração.

ESPECIFICAÇÃO — (a) VOs de saída (frozen dataclasses, sem Pydantic):

```python
@dataclass(frozen=True)
class WilcoxonReport:
    metric: str
    base_a: str
    base_b: str
    statistic: float
    p_value: float
    p_value_corrected: float | None       # após correção múltipla
    significant: bool                     # p_value_corrected < alpha (0.05)
    n_pairs: int
    effect_size_r: float | None           # r = Z / sqrt(N)

@dataclass(frozen=True)
class NemenyiPair:
    llm_a: str
    llm_b: str
    p_value: float
    significant: bool

@dataclass(frozen=True)
class FriedmanReport:
    metric: str
    chi2_statistic: float
    p_value: float
    p_value_corrected: float | None
    significant: bool
    n_groups: int
    n_blocks: int
    nemenyi_pairs: tuple[NemenyiPair, ...]    # post-hoc (só se significant=True)

@dataclass(frozen=True)
class MLMReport:
    formula: str
    base_effect_coef: float
    base_effect_p_value: float
    llm_effect_p_values: dict[str, float]     # por LLM (vs. referência)
    interaction_p_value: float
    interaction_significant: bool
    aic: float
    n_observations: int
    convergence_warning: bool
```

ESPECIFICAÇÃO — (b) Três adapters em `infrastructure/adapters/stats_adapters.py`:

**Adapter 1: `WilcoxonAdapter`** (implementa `StatsPort.wilcoxon_paired`):
- `scipy.stats.wilcoxon(x, y, alternative="two-sided", zero_method="wilcox")`
- `x` = `FinalScore` (ou `metric`) da base A por pergunta × seed.
- `y` = `FinalScore` da base B nas mesmas observações (pareamento por `question_id` + `seed`).
- Calcular `effect_size_r = Z / sqrt(N)` onde `Z = norm.ppf(1 - p/2)` e `N = n_pairs`.
- Logging: `metric`, `statistic`, `p_value`, `n_pairs`, `latency_ms`.
- Se `n_pairs < 5`: logar WARNING e retornar `WilcoxonReport` com `significant=False` e
  `p_value=1.0` (amostra insuficiente). NÃO levantar exceção.

**Adapter 2: `FriedmanNemenyiAdapter`** (implementa `StatsPort.friedman_nemenyi`):
- `scipy.stats.friedmanchisquare(*grupos)` onde cada grupo = array de FinalScore
  para um LLM, pareado por `(question_id, seed, base)`.
- Post-hoc (só se `p_value < 0.05`):
  `scikit_posthocs.posthoc_nemenyi_friedman(data_matrix)`.
- Montar `NemenyiPair` para cada par `(llm_a, llm_b)`.
- Logging: `metric`, `chi2_statistic`, `p_value`, `n_groups`, `n_blocks`, `latency_ms`.
- Se menos de 3 grupos: `significant=False`, `p_value=1.0`, `nemenyi_pairs=()`, WARNING.

**Adapter 3: `MixedLinearModelAdapter`** (implementa `StatsPort.mixed_linear_model`):
- Fórmula padrão: `"final_score ~ base * llm + (1 | question_id)"` mas recebe
  `formula: str` como parâmetro (§5.1).
- Usar `statsmodels.formula.api.mixedlm`:
  ```python
  import statsmodels.formula.api as smf
  model = smf.mixedlm(formula, data=df, groups=df["question_id"])
  result = model.fit(reml=True, method="lbfgs")
  ```
- `df` é construído do `ResultFrame` — converter para `pandas.DataFrame` **dentro do
  adapter** (pandas é permitido em infra).
- Extrair: `base_effect_coef` e `base_effect_p_value` (coeficiente de `base`);
  `llm_effect_p_values` (p-values das variáveis LLM); `interaction_p_value` (variável
  com `*` na fórmula, ex.: `base:llm`); `aic`; `n_observations = result.nobs`.
- `convergence_warning = not result.converged` (structlog WARNING se True).
- Se `statsmodels.mixedlm` não convergir OU lançar exceção numérica: retornar
  `MLMReport` com todos os p-values = `float("nan")` e `convergence_warning=True`.
  NÃO levantar exceção — degradação graceful.

**Config Pydantic** `StatsAdapterConfig` (em `adapter_configs.py`):
```python
alpha: float = 0.05
correction_method: str = "benjamini-hochberg"   # ou "holm"
min_pairs_wilcoxon: int = 5
reml: bool = True
```

ENTREGÁVEL:
- Extensão de `domain/value_objects.py` (VOs de stats)
- `src/inteligenciomica_eval/infrastructure/adapters/stats_adapters.py`
- Extensão de `infrastructure/config/adapter_configs.py`
- `tests/unit/adapters/test_stats_adapters.py`
  Para CADA adapter:
  a) Dataset sintético conhecido → valores p calculados manualmente conferem.
  b) Amostra insuficiente (n<5 para Wilcoxon; <3 grupos para Friedman) → `significant=False`,
     sem exceção, WARNING logado.
  c) Falha numérica no MLM → `convergence_warning=True`, `p_values=NaN`, sem exceção.
- `tests/integration/adapters/test_stats_integration.py`
  (marcado `@pytest.mark.integration`; dataset de 13 pares reais; valores verificados
  contra cálculo direto de scipy)
- `tests/golden/stats_wilcoxon_expected.json` + `stats_friedman_expected.json`
  (valores calculados independentemente via scipy notebook ou R)

RESTRIÇÕES (DoD §14.2):
- Adapters NUNCA levantam exceção em caso de amostra pequena ou falha numérica —
  degradação graceful para p=1.0/NaN com WARNING.
- `pandas` e `scipy`/`statsmodels`/`scikit-posthocs` usados **somente** em `infrastructure/`.
- `from __future__ import annotations`; type hints; docstrings; mypy --strict.
- import-linter: `domain/application` NÃO importam `scipy`/`statsmodels`/`pandas`.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-404):
- 3 VOs de output (`WilcoxonReport`, `FriedmanReport`, `MLMReport`) são frozen dataclasses.
- 3 adapters implementam `StatsPort` estruturalmente (`isinstance` com Protocol passa).
- Amostra insuficiente: `significant=False`, sem exceção — testado para cada adapter.
- MLM não convergente: `convergence_warning=True`, p-values NaN, sem exceção — testado.
- Golden de Wilcoxon e Friedman conferem valores calculados independentemente.
- import-linter OK; mypy --strict; cobertura ≥ 85%.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer (skill ml-engineer). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-404 + arquitetura §5.1 (StatsPort assinaturas) +
doc-base §8.1–8.5 + ADR-011 + "Nota de operacionalização M4" item 6.

VERIFIQUE, item a item, citando arquivo:linha:
1. VOs `WilcoxonReport`, `FriedmanReport` (com `NemenyiPair`), `MLMReport` são
   frozen dataclasses em `domain/value_objects.py`? Sem Pydantic?
2. Assinaturas dos 3 adapters batem com `StatsPort` de §5.1?
   `isinstance(adapter, StatsPort)` passa para cada um?
3. Wilcoxon: pareamento por `(question_id, seed)` correto?
   `effect_size_r = Z / sqrt(N)` calculado e testado?
   n<5 → `significant=False`, sem exceção, WARNING — testado?
4. Friedman: post-hoc Nemenyi só quando `p_value < 0.05`?
   < 3 grupos → degradação graceful — testado?
5. MLM: `statsmodels.formula.api.mixedlm` com `groups=question_id`?
   `convergence_warning=True` e p-values=NaN em falha numérica — testado?
6. `pandas` e `scipy`/`statsmodels`/`scikit-posthocs` usados SOMENTE em `infrastructure/`?
   Execute: `grep -rn "import scipy\|import statsmodels\|import pandas"
   src/inteligenciomica_eval/domain/ src/inteligenciomica_eval/application/`
   e reporte (deve ser vazio).
7. Golden de Wilcoxon: recalcule um p-value manualmente com os pares do arquivo JSON
   e confira — cite o resultado.
8. import-linter OK; cobertura ≥ 85%; DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Cole o output do grep do item 6. Inclua recomputação do p-value do item 7.
Confirme `pytest tests/unit/adapters/test_stats_adapters.py -v` e `lint-imports`.
~~~

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

## Apêndice — Gate M4 e preparação para M5

### DAG de M4 (401–409)

```
M3 gate (301–310) — pré-requisito obrigatório
    │
    ▼
401 (CLI annotate --export — P0) ─────────────────────────────────────────┐
    │                                                                      │
402 (IngestHumanAnnotationUseCase — P0; depende de 401 por formato JSONL) │
    │                                                                      │
403 (AggregateResultsUseCase — P0; depende de TAREFA-008/M0) ─────────────┤
    │                                                                      │
404 (StatsPort adapters — P0; independente de 401–403) ─────────────────  │
    │                                                                      │
405 (StatisticalAnalysisUseCase — P0; depende de 404 + 403) ──────────────┤
    │                                                                      │
406 (Extensões de domínio M4: ports/VOs — P0, BLOQUEADOR de 407+408) ─────┤
    │                                                                      │
407 (MatplotlibVisualizationAdapter — P1; depende de 406 + 403) ──────────┤
    │                                                                      │
408 (HTMLReportAdapter + CLI analyze/report/status — P1; depende de       │
     406 + 407 + 405) ────────────────────────────────────────────────────┤
                                                                           │
    (todas 401–408 mergeadas e verdes) ────────────────────────────────────▼
                                                                         409
                                                                  (Gate M4 ✓)
```

**Caminho crítico:** 406 → 405 → 408 → 409
(ports de domínio → estatística → relatório completo → gate)

### Sequência recomendada de PRs

1. **TAREFA-401** (CLI annotate export) — independente, desbloqueador de 402.
2. **TAREFA-402** (IngestHumanAnnotationUseCase) — após 401.
3. **TAREFA-403** (AggregateResultsUseCase) — independente de 401/402; pode ir em paralelo.
4. **TAREFA-404** (StatsPort adapters) — independente; pode ir em paralelo com 401–403.
5. **TAREFA-405** (StatisticalAnalysisUseCase) — após 403 + 404.
6. **TAREFA-406** (extensões de domínio) — após 403 + 405 (para ter os tipos todos definidos).
7. **TAREFA-407** (Visualização) + **TAREFA-408** (Report + CLI) — após 406; paralelizáveis.
8. **TAREFA-409** (Gate) — POR ÚLTIMO; todas as anteriores mergeadas.

### Paralelização (time com ≥ 2 engenheiros)

- **Engenheiro A:** 401 → 402 → auxilia 408 (CLI)
- **Engenheiro B:** 403 → 404 → 405 → 406
- **Engenheiro C:** 407 → 408 (Report) → (aguarda todos) → 409

### Gate de saída do M4 (go/no-go para M5)

Para avançar para M5 (Rodada 2 OFAT), todos os critérios abaixo devem estar
atendidos no CI:

- [ ] `mypy --strict src` verde (sem `# type: ignore` não justificado)
- [ ] `ruff check .` e `ruff format --check .` verdes
- [ ] `lint-imports` verde
- [ ] `pytest -m unit` verde; cobertura global ≥ 85%; `domain/` ≥ 95%
- [ ] `pytest -m integration` verde
- [ ] `pytest -m e2e tests/e2e/test_full_pipeline_m4.py` verde em CI < 90s
- [ ] `StatsReport` JSON com campos de síntese H1–H4 — evidência no E2E
- [ ] 6 SVGs válidos + HTML autocontido no E2E
- [ ] `critical_failure_flag` ingerido e propagado ao `ConfigAggregate.critical_failure_rate`
- [ ] `best_config` por `RankScore` identificada e presente no relatório HTML
- [ ] CHANGELOG M4 com deltas de contrato documentados
- [ ] ADR-013 (`docs/adr/ADR-013-round2-funnel.md`) criado (para uso em M5)

### Preparação para M5 — Rodada 2 (OFAT)

M5 (arquivo `prompts_m5_tarefas_501_507.md`) implementará:

- **TAREFA-501** — `GoldChunkReaderAdapter` real + validação de formato de chunks-ouro
- **TAREFA-502** — `RetrievalMetricsService` (precision@k, recall@k, MRR, nDCG@k) em
  `domain/services/retrieval_metrics.py` (puro, stdlib, sem third-party)
- **TAREFA-503** — `FunnelSelector` em `domain/services/funnel.py` (puro) —
  **NOTA:** §4.4 e §8 já preveem este serviço de domínio; deve ser implementado no M5
  como desbloqueador do funil.
- **TAREFA-504** — `RetrievalFunnelUseCase` em `application/retrieval_funnel.py`
  (nome canônico de §8) — orquestra TAREFA-502 + TAREFA-503
- **TAREFA-505** — Variação de chunking (fase 2a) + reindex parametrizado
- **TAREFA-506** — Variação de embedding (fase 2b) + reindex
- **TAREFA-507** — Gate M5: funil completo + top-3 promovidos para geração

> **Pré-requisito de M5:** curadoria de chunks-ouro entregue pelo especialista biomédico
> (Premissa P5 — §2.5 do documento de arquitetura). Sem os chunks-ouro das 13 perguntas,
> as métricas de retrieval puro não são calculáveis. ADR-013 (criado em M4) fundamenta
> a decisão do funil de 2 estágios.
