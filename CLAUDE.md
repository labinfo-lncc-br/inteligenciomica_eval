# CLAUDE.md — Guia de Desenvolvimento InteligenciÔmica Eval

Este arquivo é lido automaticamente pelo Claude Code em cada sessão. Contém padrões,
decisões de arquitetura e convenções que devem ser respeitadas em **todas** as tarefas.

---

## 1. Stack e Ferramentas

| Categoria       | Ferramenta / Decisão                                       |
|-----------------|------------------------------------------------------------|
| Gerenciador pkg | **uv** — NUNCA usar pip install diretamente                |
| Build backend   | **hatchling** (configurado em `pyproject.toml`)            |
| Lint + format   | **ruff** (lint e format unificados)                        |
| Type checker    | **mypy --strict** (apenas em `src/`, não em `tests/`)      |
| Contratos arq.  | **import-linter** (`.importlinter` com 4 contratos)        |
| Testes          | **pytest** + **pytest-cov** + **pytest-xdist** + **pytest-asyncio** |
| Async tests     | `asyncio_mode = "auto"` no `pyproject.toml` — `async def` basta |
| HTTP mock       | **AsyncMock** (stdlib) para adapters com SDK; **respx** para httpx direto |
| Pre-commit      | ruff-lint · ruff-format · mypy (via hook `local`)          |
| Python          | **3.11+** (runtime); ambiente local usa 3.12               |

### Dependências de runtime relevantes

| Pacote | Versão mínima | Uso |
|--------|--------------|-----|
| `qdrant-client` | `>=1.7.1` | `AsyncQdrantClient` no `QdrantRetrieverAdapter` |
| `openai` | `>=1.0` | `AsyncOpenAI` no `VLLMGeneratorAdapter` |
| `httpx` | `>=0.27` | `AsyncClient` no polling `/health` do `VLLMServerManagerAdapter` |
| `tenacity` | `>=8.0` | Retry com `AsyncRetrying` nos adapters de rede |
| `structlog` | `>=24.0` | Logging estruturado em toda a infraestrutura |
| `pydantic` | `>=2.0` | Validação de configuração YAML (apenas infra) |

### Dev deps adicionais (M1)

| Pacote | Uso |
|--------|-----|
| `testcontainers[qdrant]>=4.3` | Testes de integração do `QdrantRetrieverAdapter` e gate M1 |
| `pytest-asyncio>=0.23` | Suporte a `async def` em testes |
| `respx>=0.20` | Mock de chamadas httpx diretas e do SDK OpenAI (via `respx.mock` global — TAREFA-021) |
| `pytest-randomly>=3.15` | Ordenação aleatória de testes (detecta acoplamento de ordem — gate M1) |

### Ordem obrigatória de validação (antes de qualquer commit)

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src
uv run lint-imports
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n auto
```

---

## 2. Layout do Projeto

```
src/inteligenciomica_eval/   ← pacote principal (src layout)
  __init__.py                ← expõe __version__
  cli.py                     ← Typer app (entry point: ielm-eval)
  domain/                    ← regras puras, sem I/O
    errors.py                ← hierarquia de exceções de domínio
    entities.py              ← EvaluationResult, GeneratedAnswer, Question
    value_objects.py         ← LLMId, BaseId, Seed, MetricVector, FinalScore, ...
    ports.py                 ← Protocols @runtime_checkable (GeneratorPort async)
    services/
      final_score.py         ← FinalScoreCalculator (pesos configuráveis)
      rank_score.py          ← RankScoreCalculator
      aggregation.py         ← AggregationService (ConfigAggregate)
  application/               ← use cases orquestrando domain (vazio em M0/M1)
  infrastructure/            ← adapters, repos, config, prompts
    adapters/
      qdrant_retriever.py    ← QdrantRetrieverAdapter + GoldChunkReaderAdapter ✅ M1
      vllm_generator.py      ← VLLMGeneratorAdapter ✅ M1
    config/
      schema.py              ← RoundConfig Pydantic (YAML de rodada)
      settings.py            ← AppSettings (pydantic-settings)
      provenance.py          ← ProvenanceInfo (hashes, versões)
    prompts/                 ← templates Jinja2 (a preencher em TAREFA-015)
    repositories/
      parquet_storage.py     ← ParquetStorage (ResultWriterPort + ResultReaderPort)
  visualization/             ← helpers de renderização (vazio)

tests/
  conftest.py
  unit/                      ← ≥ 70% dos testes, < 10 ms cada
    domain/                  ← espelha src/domain/
    infrastructure/adapters/ ← testes unitários dos adapters (AsyncMock / respx)
  integration/               ← adapters reais, containers
    adapters/                ← QdrantRetrieverAdapter com testcontainers
  e2e/                       ← fluxos fim-a-fim (harness async desde TAREFA-014)
  fakes/                     ← implementações in-memory das ports
  factories/                 ← builders de dados de teste
  golden/                    ← datasets de referência (ML/RAG)

docs/
  adr/                       ← Architecture Decision Records
  dev-log/                   ← relatórios de execução por tarefa
  prompts_m0_tarefas_001_006.md
  prompts_m0_tarefas_007_012.md
  prompts_m1_tarefas_013_021_corrigido.md ← Nota de operacionalização M1 + prompts A/B (v1.1 — corrigido após auditoria 26/05/2026)
```

---

## 3. Contratos de Importação (import-linter)

Quatro contratos declarados em `.importlinter` (root_package = inteligenciomica_eval):

1. **domain-forbidden**: `domain` NÃO importa `application`, `infrastructure`, `cli` nem libs de I/O (pandas, polars, pyarrow, sqlalchemy, httpx, requests, boto3, qdrant_client, openai, ragas, deepeval, statsmodels).
2. **application-forbidden**: `application` NÃO importa `infrastructure`, `cli` nem libs de I/O (mesma lista).
3. **infrastructure-forbidden**: `infrastructure` NÃO importa `cli`.
4. **architecture-layers** (tipo `layers`): enforce hierarquia estrita `domain < application < infrastructure` — `application` só pode importar `domain`.

Ao adicionar uma nova lib de I/O, atualizar `forbidden_modules` nos contratos 1 e 2.

---

## 4. Padrões de Código

- `from __future__ import annotations` **no topo de todo arquivo Python** (sem exceções).
- Type hints em todas as assinaturas públicas.
- Docstrings Google-style nas funções/classes públicas.
- Zero `Any` sem comentário justificando.
- `# pragma: no cover` no bloco `if __name__ == "__main__":` de todo CLI/script.
- Nenhum `print()` em código de produção — usar `structlog` ou `rich.Console`.

---

## 5. CLI (Typer)

**Decisão crítica**: Typer ≥ 0.9 colapsa um app com um único `@app.command()` fazendo
o app ser o próprio comando (sem subcomandos). Isso quebra `ielm-eval version`.

**Regra**: sempre adicionar `@app.callback()` antes do primeiro `@app.command()` para
forçar o modo de grupo (multi-subcomando). Extrair também uma função `main()` para
permitir testes do caminho de `KeyboardInterrupt`:

```python
@app.callback()
def _main() -> None:
    """Texto de ajuda do grupo."""

@app.command()
def meu_comando() -> None:
    ...

def main() -> None:
    """Entry point wrapper — testável via mocker.patch."""
    try:
        app()
    except KeyboardInterrupt:
        _err_console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)

if __name__ == "__main__":  # pragma: no cover
    main()
```

---

## 6. Cobertura de Testes

- `branch = true`, `source = ["src/inteligenciomica_eval"]`. O gate de **85%** é imposto pelo
  flag explícito `--cov-fail-under=85` (job `unit` + comando de gate local), **não** por
  `fail_under` no `[tool.coverage.report]` — assim runs de suíte única (job `integration`) não
  falham pela porcentagem menor (decisão TAREFA-021).
- `pytest-cov` é um pacote **separado** de `coverage[toml]` — ambos devem estar em `dev` deps.
- Dev deps ficam em `[dependency-groups] dev` (PEP 735), **não** em `[project.optional-dependencies]`.
  Com `[dependency-groups]`, `uv sync --frozen` instala runtime + dev por padrão — não precisa de `--all-extras`.
- Módulos de esqueleto (`__init__.py` vazios) precisam ser importados em algum teste para
  entrarem na contagem. Ver `tests/unit/test_imports.py`.
- `exclude_lines` inclui `if __name__ == .__main__.:` e `if TYPE_CHECKING:`.

---

## 7. Versionamento de Dependências

**Decisão**: `pyproject.toml` usa faixas mínimas (`>=`) para runtime e dev deps;
`uv.lock` é a fonte de verdade para reprodutibilidade.

- **Faixas mínimas no pyproject** declaram a intenção semântica (versão mínima compatível)
  sem bloquear atualizações de segurança em ambientes que não usam o lock.
- **`uv.lock` commitado** garante builds byte-a-byte idênticos em todos os ambientes
  que executam `uv sync --frozen` — CI, containers, máquinas de dev.
- Pins estritos em `pyproject.toml` (ex: `pandas==2.0.3`) seriam redundantes com o lock
  e dificultariam bumps de versão.

**Quando revisar**: executar `uv lock --upgrade` periodicamente (ou por dependabot/renovate)
e commitar o `uv.lock` atualizado após validar os gates.

---

## 8. Dev Log — Padrão de Nomes de Relatórios

Localização: `docs/dev-log/`

### Formato do nome de arquivo

```
M{N}_TAREFA-{NNN}_{parte}_{slug}.md
```

| Campo    | Descrição                                              | Exemplo     |
|----------|--------------------------------------------------------|-------------|
| `M{N}`   | Número do milestone (sem padding)                      | `M0`        |
| `TAREFA-{NNN}` | Identificador da tarefa com zero-padding 3 dígitos | `TAREFA-001` |
| `{parte}` | Letra do prompt (A = implementação, B = revisão, etc.) | `A`         |
| `{slug}` | Kebab-case descritivo, max 40 chars                    | `bootstrap-repositorio` |

**Exemplos válidos**:
```
M0_TAREFA-001_A_bootstrap-repositorio.md
M0_TAREFA-002_A_dominio-core.md
M1_TAREFA-013_A_qdrant-gold-chunk-adapters.md
M1_TAREFA-014_D_async-first-fix.md
```

### Estrutura interna do relatório

```markdown
# {M}_TAREFA-{NNN}_{parte} — {Título da Tarefa}

**Data**: YYYY-MM-DD
**Milestone**: M{N} — {Nome do Milestone}
**Épico**: E{N}
**Skill**: {skill usada}
**Prioridade / Tamanho**: P{N} / {S|M|L|XL}

## Objetivo
## Arquivos Criados / Modificados
## Decisões Técnicas
## Problemas Encontrados e Soluções
## Validação (DoD)
## Critérios de Aceitação
## Observações para Próximas Tarefas
```

---

## 9. Instalação e Comandos Rápidos

```bash
uv sync --frozen          # instala dependências (usa uv.lock)
uv run ielm-eval --help   # verifica entry point
uv run ielm-eval version  # imprime versão
uv run pre-commit install # instala hooks
uv run pre-commit run --all-files  # roda hooks em todos os arquivos
```

---

## 10. CI

Arquivo: `.github/workflows/ci.yml` — **dois jobs** desde TAREFA-021:

- **`unit`**: checkout → setup-uv → setup-python 3.11 → `uv sync --frozen` →
  `ruff check` → `ruff format --check` → `mypy --strict src` → `lint-imports` →
  `pytest -m "not integration" --cov=src --cov-report=xml:unit-coverage.xml --cov-fail-under=85 -n auto`
  → upload Codecov (flag `unit`). É o guardião do gate de 85%.
- **`integration`**: `services.qdrant` (`qdrant/qdrant:v1.9`, porta 6333) + env `QDRANT_URL=http://localhost:6333`
  → `uv sync --frozen` → `pytest -m integration --cov ... --cov-report=xml:integration-coverage.xml -v tests/integration/`
  → upload Codecov (flag `integration`). **Sem** `--cov-fail-under` (uma suíte de integração não
  atinge 85% sozinha; o job `unit` guarda o limiar).

`pytest-randomly` está ativo por padrão em ambos os jobs (ordenação aleatória).

---

## 11. Async-First — Política de Adapters de Rede (Nota M1 item 1)

> **Regra**: todos os adapters que realizam chamadas de rede usam `async/await` como
> interface pública. Adapters síncronos por natureza (BERTScore, ROUGE-L,
> `AnnotationReaderAdapter`) permanecem síncronos.

### Estado atual dos ports

| Port | Assinatura pública | Adapter | Observação |
|------|--------------------|---------|------------|
| `GeneratorPort.generate()` | `async def` ✅ | `VLLMGeneratorAdapter` | Async-first desde TAREFA-014-D |
| `RetrieverPort.search()` | `async def` ✅ | `QdrantRetrieverAdapter` | Promovido a async em TAREFA-013-F (correção spec v1.1) |
| `RubricJudgePort.score()` | `async def` ✅ | `PrometheusJudgeAdapter` | Promovido a async em TAREFA-016-D |
| `MetricSuitePort.score()` | `async def` ✅ | `RAGASLayer1Adapter` | Promovido a async em TAREFA-017 (PR retroativo) |
| `DeterministicMetricPort.score()` | `def` (síncrono) ✅ | `DeterministicMetricsAdapter` | Síncrono por natureza (TAREFA-018) — BERTScore/ROUGE são CPU-bound, sem I/O de rede |
| `VLLMServerManagerPort.start/wait_healthy/stop()` | `async def` ✅ | `VLLMServerManagerAdapter` | Promovido a async em TAREFA-019 (PR retroativo); `close()` é extensão fora do port |

### Padrão para testes de adapters que usam SDK OpenAI

**DECISÃO FINAL (TAREFA-014-G)**: mockar no nível do SDK, não no nível HTTP.

`httpx.MockTransport(respx_mock.handler)` injetado via `openai.AsyncOpenAI(http_client=...)`
pode não interceptar chamadas em ambientes sandboxed/containers onde a política do
event-loop ou anyio/sniffio se comporta de forma diferente. O SDK v2 usa `asyncify` (que
chama `asyncio.to_thread`) na primeira chamada, o que pode interferir com o transporte
injetado dependendo do ambiente.

**Padrão correto** — mockar diretamente em `adapter._client.chat.completions.create`:

```python
from unittest.mock import AsyncMock, MagicMock

def _mock_completion(text="...", tokens_in=128, tokens_out=16) -> MagicMock:
    comp = MagicMock()
    comp.choices = [MagicMock()]
    comp.choices[0].message.content = text
    comp.usage = MagicMock()
    comp.usage.prompt_tokens = tokens_in
    comp.usage.completion_tokens = tokens_out
    return comp

def _make_adapter(create_mock: AsyncMock | None = None) -> VLLMGeneratorAdapter:
    adapter = VLLMGeneratorAdapter(url=..., model=...,
                                   _retry_stop=stop_after_attempt(3),
                                   _retry_wait=wait_none())
    if create_mock is not None:
        adapter._client.chat.completions.create = create_mock  # type: ignore[method-assign]
    return adapter

# Para erros: instanciar com objetos httpx mínimos (não chegam à rede)
_DUMMY_REQUEST = httpx.Request("POST", _ENDPOINT)
exc = openai.APIConnectionError(message="conn refused", request=_DUMMY_REQUEST)
mock_create = AsyncMock(side_effect=exc)
# call_count valida retries; call_args.kwargs["extra_body"]["seed"] valida parâmetros
```

Este padrão:
- Não usa `respx`, `httpx.MockTransport` nem `http_client` para testes
- É 100% determinístico e independente de versão de anyio/sniffio/httpx
- Testa o adapter no nível correto de abstração (SDK, não transporte HTTP)

### Padrão de retry com tenacity (adapters de rede)

```python
_RETRYABLE = (openai.APIConnectionError, openai.RateLimitError)  # erros transitórios

async for attempt in AsyncRetrying(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(_RETRYABLE),
    reraise=True,
):
    with attempt:
        response = await client.chat.completions.create(...)
```

Setar `max_retries=0` no `AsyncOpenAI` — o SDK v2 tem retry próprio (default 2 tentativas);
sem isso, cada tentativa do tenacity faria até 3 chamadas HTTP (3 × 3 = 9).

---

## 12. Estado Atual do Desenvolvimento

### M0 — Fundação do Domínio ✅ CONCLUÍDO (TAREFA-001 a 012)

| Tarefa | Descrição | Status |
|--------|-----------|--------|
| 001 | Bootstrap do repositório (uv, ruff, mypy, import-linter, CI) | ✅ |
| 002 | Hierarquia de exceções de domínio | ✅ |
| 003 | Value objects de domínio (LLMId, BaseId, Seed, MetricVector, FinalScore, …) | ✅ |
| 004 | Entidades de domínio (Question, GeneratedAnswer, EvaluationResult) | ✅ |
| 005 | Ports/Protocols @runtime_checkable (GeneratorPort, RetrieverPort, …) | ✅ |
| 006 | FinalScoreCalculator (pesos configuráveis, NaN propagation ADR-007) | ✅ |
| 007 | RankScoreCalculator | ✅ |
| 008 | AggregationService (ConfigAggregate, NaN exclusion) | ✅ |
| 009 | ParquetStorage (ResultWriterPort + ResultReaderPort, two-pass §3.4) | ✅ |
| 010 | Config YAML (RoundConfig Pydantic, AppSettings, ProvenanceInfo, dry-run) | ✅ |
| 011 | Fakes e factories de teste (FakeGenerator, FakeMetricSuite, StubRetriever, …) | ✅ |
| 012 | E2E stub — round mínimo em CPU (harness §3.4 duas passadas, golden values) | ✅ |

### M1 — Adapters de Infraestrutura ✅ CONCLUÍDO (TAREFA-013 a 021)

| Tarefa | Descrição | Status |
|--------|-----------|--------|
| 013 | `QdrantRetrieverAdapter` + `GoldChunkReaderAdapter` | ✅ |
| 014 | `VLLMGeneratorAdapter` (async-first, openai SDK, tenacity, AsyncMock) | ✅ |
| 015 | `PromptRegistry` (templates Jinja2 versionados, `PackageLoader`) | ✅ |
| 016 | `PrometheusJudgeAdapter` (rubrica biomédica, NaN-or-retry ADR-007) | ✅ |
| 017 | `RAGASLayer1Adapter` (RAGAS apontando para vllm-judge determinístico) | ✅ |
| 018 | `DeterministicMetricsAdapter` (BERTScore + ROUGE-L, síncrono) | ✅ |
| 019 | `VLLMServerManagerAdapter` (subprocess local, polling /health) | ✅ |
| 020 | `AnnotationReaderAdapter` (JSONL de anotações críticas) | ✅ |
| 021 | Gate de integração M1 (pipeline adapter end-to-end + smoke E2E) | ✅ |

### M3 — Orquestração das 4 GPUs ✅ CONCLUÍDO (TAREFA-301 a 316)

| Tarefa | Descrição | Status |
|--------|-----------|--------|
| 301 | `WaveSchedulerService` — escalonamento de ondas de geração | ✅ |
| 302 | `VLLMServerManager` real (subprocess, GPU partition, regime-by-flag) | ✅ |
| 303 | `WaveSchedulerService` + CLI `--dry-run` + `RoundConfigView` Protocol | ✅ |
| 304 | `RunGenerationPassUseCase` (orquestra geração por onda) | ✅ |
| 305 | `RunMetricsPassUseCase` + PR retroativo `score_batch` | ✅ |
| 306 | `RunJudgePassUseCase` (rubrica por resultado) | ✅ |
| 307 | `RunExperimentUseCase` + `GeneratorFactory` | ✅ |
| 308 | `AnnotationWorkflowUseCase` + CLI `annotate` (Camada 3) | ✅ |
| 309 | DI Wiring + CLI `run` + `BenchmarkLoader` | ✅ |
| 310 | Gate E2E ciclo completo M3 | ✅ |
| 311 | `ExternalVLLMServerManager` + probes de proveniência (ADR-014) | ✅ |
| 312 | Gate de integração 309/310/311/606 (retrocompat log + spec §4.3/§5.3 + `determinism_verified`) | ✅ |
| 313 | Contrato benchmark — validação de `BenchmarkLoader` + batch de perguntas | ✅ |
| 314 | Observabilidade — `mask_url` centralizado + probes mascarados + payload juiz logado | ✅ |
| 316 | Fidelidade do prompt de geração + bundle versionado `v1_production` (ADR-015) | ✅ |

### M4 — Decisão Executiva ✅ CONCLUÍDO (TAREFA-401 a 409)

| Tarefa | Descrição | Status |
|--------|-----------|--------|
| 401 | CLI `annotate --export` (exportação JSONL para revisão humana) | ✅ |
| 402 | `IngestHumanAnnotationUseCase` + CLI `--ingest`/`--force` | ✅ |
| 403 | `AggregateResultsUseCase` (ConfigAggregate multi-run) | ✅ |
| 404 | `StatsPort` adapters (Wilcoxon, Friedman+Nemenyi, MLM) | ✅ |
| 405 | `StatisticalAnalysisUseCase` + `StatsReport` VO | ✅ |
| 406 | `FigurePath`/`ReportPath` VOs + `VisualizationPort`/`ReportPort` | ✅ |
| 407 | `MatplotlibVisualizationAdapter` (6 plots canônicos) | ✅ |
| 408 | `HTMLReportAdapter` + CLI `analyze`/`report`/`status`/`show-config` | ✅ |
| 409 | Gate E2E M4 (pipeline completo até relatório HTML) | ✅ |

### M6 — Qualidade e Segurança ✅ CONCLUÍDO (TAREFA-601 a 607)

| Tarefa | Descrição | Status |
|--------|-----------|--------|
| 601 | Mutation testing `domain/services` (mutmut; 94.8% score) | ✅ |
| 602 | Cohen's κ — validação do juiz (κ golden=0.5 moderada) | ✅ |
| 603 | Property-based tests hypothesis (4 targets, 15 testes) | ✅ |
| 604 | Manual de operação final + smoke-test (7 subcomandos) | ✅ |
| 605 | Revisão de segurança final (S1–S9, ADR-003 template fix) | ✅ |
| 606 | Emenda manual de operação + `validate_manual.py` (smoke-test 7 subcomandos) | ✅ |
| 607 | Doc-sync: arquitetura v1.2 + visão v1.1 (pós-M3 311/312/314/316) | ✅ |
| 315 | Acurácia documental: ADR-014 fix + manual + `validate_manual.py` alinhados | ✅ |

### Cobertura atual

```
1342 passed, 16 skipped — 89.66% total coverage
external_vllm_server_manager.py: 100% | endpoint_probe.py: 100% | vllm_server_manager.py: 100%
deterministic_metrics.py: 100% | prometheus_judge.py: 100% | vllm_generator.py: 96%
annotation_reader.py: 100% | ragas_metrics.py: 87% | qdrant_retriever.py: 96%
```

> Os 16 skips locais = 5 testes Qdrant (sem Docker) + 1 pipeline M1 (sem Docker) + skips de golden/integração.
> Smoke E2E agora roda com `E2E_ENABLED` — não contam mais como skip frequente.
> No CI o job `integration` executa os de Qdrant.
> `ragas_metrics.py` em 87% local: o ramo de construção real (embeddings + LLM) é coberto
> apenas pelo teste de integração, que roda no job `integration` do CI.
> `vllm_generator.py` em 96%: linhas 33–37 (`_default_render_fn` lazy import) não são exercidas
> pelos testes unitários (que injetam `render_fn`); cobertas pelos testes de integração M1.

> **Gate de cobertura local**: usar `-n 4` (não `-n auto`) — a máquina de dev tem 20 núcleos
> mas só 15 GB de RAM; com `-n auto`, os 20 workers importam torch (`bert_score` +
> `sentence-transformers`/ragas) em tempo de coleta e estouram a RAM → swap → timeout.
> CI permanece com `-n auto` (RAM suficiente).

---

## 13. Decisões de Design Relevantes para M1

### VLLMGeneratorAdapter

- `url` deve incluir `/v1` (ex: `"http://localhost:8000/v1"`) — `AsyncOpenAI(base_url=url)` anexa `/chat/completions` sem reintroduzir `/v1`.
- `seed` vai em `extra_body={"seed": seed}` (não em campo padrão da API) — comportamento vLLM-specific (§9.3, ADR-003).
- `batch_invariant=False` sempre — constante neste adapter (§9.2.4).
- `_retry_stop` e `_retry_wait` são injetáveis para testes (parâmetro `_` prefixo).

### QdrantRetrieverAdapter

- Embedding feito **pelo servidor Qdrant** (Inference API) — o adapter não carrega modelo local.
- `collection_map: Mapping[str, str]` mapeia `BaseId.value → nome da coleção Qdrant`.
- Testes de integração usam `testcontainers[qdrant]` (Docker); marcados com `@_skip_no_docker` pois WSL2 local não tem Docker disponível.
- Imagem testcontainers (`qdrant/qdrant:v1.9`) não inclui FastEmbed — testes de integração fazem monkeypatch de `_search_async` para usar vetores densos diretos.

### GoldChunkReaderAdapter

- Arquivo JSONL em `tests/fixtures/gold_chunks.jsonl` — uma linha por question_id.
- Carregamento lazy + cache interno (`_ensure_loaded()`).
- Levanta `StorageError` em arquivo ausente ou question_id não encontrado.

### PromptRegistry (TAREFA-015 + TAREFA-316 — concluídas)

- Templates em `src/inteligenciomica_eval/infrastructure/prompts/*.j2` (rubrica) e `prompts/rag/<versão>/` (bundles RAG).
- `jinja2.Environment(loader=PackageLoader(...))`.
- `prompt_version` = `git describe --tags --dirty` capturado na inicialização (usado pela rubrica).
- `get_default_registry() -> PromptRegistry` via `functools.cache` — singleton por processo.
- `render_rag_generation(question, contexts, version) -> tuple[str, str]`: devolve `(system, user)` do bundle especificado.
- `list_rag_versions() -> list[str]`: lista bundles disponíveis em `prompts/rag/`; usado por `load_round_config` para validar `generation_prompt_version`.
- Versão inexistente em `render_rag_generation` → `ValueError` com lista de disponíveis.

### PrometheusJudgeAdapter (TAREFA-016 — concluída)

- Implementa `RubricJudgePort` com `async def score(sample: EvaluationSample) -> RubricResult`.
- `batch_invariant=True` constante (ADR-003, `DeterminismRegime.JUDGE`) — nunca configurável.
- `temperature=0.0`, `seed=42` em `extra_body` — determinismo do juiz (§9.3).
- Política NaN-or-retry: tenacity 3 tentativas em `_ParseFailureError`; NaN ao esgotar (ADR-007).
- `JudgeUnavailableError` em `APIConnectionError`/`APITimeoutError` — não retentável.
- `PromptRegistry` injetado no construtor (não instanciado internamente).
- Log `prometheus_judge_completed` inclui `question_id` de `EvaluationSample` (Nota M1 item 11).

### RAGASLayer1Adapter (TAREFA-017 — concluída)

- Implementa `MetricSuitePort` com `async def score(sample: EvaluationSample) -> Layer1Metrics`.
- LLM-juiz via `LangchainLLMWrapper(ChatOpenAI(base_url=judge_url, temperature=0.0, api_key=SecretStr("EMPTY")))` — nunca usa `OPENAI_API_KEY` do ambiente.
- Embeddings via `LangchainEmbeddingsWrapper(HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2"))` — CPU, sem chamada de rede para embeddings.
- 6 métricas calculadas **individualmente** via `await metric.single_turn_ascore(ragas_sample)` — nunca via `ragas.evaluate()` batch.
- **`answer_correctness` precisa de `answer_similarity` wirado explicitamente** (`AnswerCorrectness(llm=…, embeddings=…, answer_similarity=AnswerSimilarity(embeddings=…))`): o RAGAS só seta `answer_similarity` em `init(run_config)`, que `single_turn_ascore` **não** chama — sem isso, `answer_correctness` é **sempre NaN** (`AssertionError: AnswerSimilarity must be set`, weights[1]=0.25). Bug de produção mascarado pelos unit tests (que injetam `_metrics`) e revelado pelo gate de integração (TAREFA-021-C).
- Isolamento de NaN por campo (ADR-007): exceção em uma métrica → `float("nan")` só nela; as outras 5 continuam.
- `_metrics: dict[str, Any]` injetável no construtor (`_` prefixo) — mesma convenção dos `_retry_stop`/`_retry_wait`.
- Testes mocam `single_turn_ascore` via `AsyncMock` no dict injetado — padrão CLAUDE.md §11 (sem respx).
- Log `ragas_layer1_computed` inclui `judge_url`, 6 valores de métrica, `nan_fields: list[str]`, `latency_ms`.
- Dependências adicionadas: `ragas>=0.3`, `langchain-openai`, `langchain-community`, `sentence-transformers`, `langchain-google-vertexai` (shim de compatibilidade ragas 0.3.1 + langchain-community 0.4.x), `pillow` (requisito transitivo do ragas).

### MetricSuitePort.score — promoção a async (TAREFA-017 PR retroativo)

- `MetricSuitePort.score` promovido de `def` para `async def` (Nota M1 item 1 / I4).
- Callers atualizados: `FakeMetricSuite.score`, `_StubMetricSuite.score`, harness e2e (`await metric_suite.score(sample)` ×2), `test_fakes_satisfy_ports.py` (5 testes → `async def` + `await`), `test_ports_contract.py` (1 teste).

### EvaluationSample — extensão question_id (Nota M1 item 11 / I6)

- Campo `question_id: str` adicionado como **primeiro campo obrigatório** do DTO.
- PR retroativo aplicado em TAREFA-016-B (2026-05-28): atualiza `domain/ports.py`,
  harness e2e, `test_ports_contract.py`, `test_fakes_satisfy_ports.py`,
  `test_prometheus_judge.py`.
- Motivação: `question_id` é obrigatório no schema §5.3 — ausência era lacuna de proveniência.

### DeterministicMetricsAdapter (TAREFA-018 — concluída)

- Implementa `DeterministicMetricPort` com `def score(self, *, answer: str, ground_truth: str) -> AuxMetrics` — **síncrono** (Nota M1 item 1; sem I/O de rede).
- Calcula **BERTScore-F1** (`bert_score.BERTScorer`, `lang="pt"`, `rescale_with_baseline=True` → modelo `bert-base-multilingual-cased`) e **ROUGE-L** (`RougeScorer(["rougeL"], use_stemmer=False)`, `fmeasure`).
- `batch_invariant` é **irrelevante** aqui (sem LLM/GPU) — documentado na docstring; resultado é função pura de `(answer, ground_truth)`.
- **Carga única + CPU fixo** (correção auditoria 018-B): `_bert_scorer` é uma instância de `bert_score.BERTScorer(lang=..., rescale_with_baseline=..., device="cpu")` cacheada via `functools.cached_property` — a **classe** retém os pesos em memória (carga única), ao contrário da API funcional `bert_score.score`, que recarregaria o modelo a cada chamada. `device="cpu"` (parâmetro configurável, default) impede uso acidental de GPU em CUDA. `_rouge_scorer` instancia o `RougeScorer` sob demanda — modelo de ~700 MB nunca carrega no `__init__`.
- `RougeScorer.score(target, prediction)`: `ground_truth` é o *target*, `answer` é a *prediction*. `BERTScorer.score(cands, refs)`: `answer` é *cand*, `ground_truth` é *ref*.
- NaN absorvido **por campo** (DoD §14.2): `_compute_bertscore`/`_compute_rouge_l` têm `try/except` independentes → `float("nan")` só no campo que falhou + WARNING (`bertscore_failed`/`rouge_failed`); nunca propaga exceção.
- Log `deterministic_metrics_computed` inclui `bertscore_f1`, `rouge_l`, `latency_ms`.
- Testes golden em `tests/golden/det_metrics_golden.json` (3 pares PT-biomédicos calibrados). ROUGE roda sempre (puro Python); BERTScore golden usa o adapter real, pulado se o modelo/rede indisponível (probe `bertscore_available`, mesma filosofia dos testcontainers). Testes mockam `bert_score.BERTScorer` via pytest-mock com **alvo string** (`_patch_bert`) — cobertura 100% mesmo com BERTScore golden pulado; `TestModelLoadedOnce` é a regressão que comprova carga única (`BERTScorer` instanciado 1×, `.score` chamado 2×).
- Dependências adicionadas: `bert-score>=0.3.13`, `rouge-score>=0.1.2` + override mypy `ignore_missing_imports` para `bert_score.*`/`rouge_score.*`.

### AuxMetrics — extensão rouge_l (PR retroativo TAREFA-018)

- `AuxMetrics` (definido em M0/TAREFA-005) estendido com `rouge_l: float` — spec linha 737 exige `AuxMetrics(bertscore_f1, rouge_l)`.
- **`rouge_l` é campo de log, NÃO de schema** (Nota M1 item 10): o `ParquetStorage`/`MetricVector` (§5.3) persistem apenas `bertscore_f1`; `rouge_l` é logado via structlog para sanity check.
- Callers atualizados: `FakeDeterministicMetric` (`tests/fakes/metrics.py`), `_StubDeterministicMetric` + `test_aux_metrics` (`test_ports_contract.py`), `test_fakes_satisfy_ports.py`.

### VLLMServerManagerAdapter (TAREFA-019 — concluída)

- Implementa `VLLMServerManagerPort` orquestrando processos vLLM locais via `asyncio.create_subprocess_exec` (Nota M1 item 9 — **sem Docker SDK**, reservado para M3). Nunca inicia vLLM real em CI.
- **Métodos async-first** (Nota M1 item 1): `async start/wait_healthy/stop`. `async close()` é extensão de ciclo de vida — **fora do port** (análogo a `QdrantRetrieverAdapter.close`); rastreia handles vivos em `_handles`/`_processes`.
- **Juiz vs. gerador visível no código (§9.2, bloqueador Prompt B)**: `ServerHandle.batch_invariant = "VLLM_BATCH_INVARIANT" in model.extra_env`. As envs `VLLM_BATCH_INVARIANT`/`VLLM_ENABLE_V1_MULTIPROCESSING` **nunca** são hardcoded no `start()` — só aparecem se o caller as colocou no `ModelSpec.extra_env`.
- **Saneamento de env de regime (correção auditoria 019-C)**: `_build_env` remove `_RESERVED_REGIME_ENV = {VLLM_BATCH_INVARIANT, VLLM_ENABLE_V1_MULTIPROCESSING}` do `os.environ` herdado **antes** de aplicar `extra_env`. Assim um gerador (`extra_env={}`) nunca herda o regime do juiz de um orquestrador que por acaso tenha essas envs no ambiente; e o juiz **sobrescreve** valores "errados" do pai. O regime fica decidido exclusivamente por `extra_env` (env real coerente com `handle.batch_invariant`).
- `start`: comando como **lista de args** (`sys.executable -m vllm.entrypoints.openai.api_server --model … --port … --tensor-parallel-size … --max-model-len … [--quantization …]`), `shell=False`; ambiente via `_build_env` (`os.environ` saneado + `extra_env`). `url` retornada com sufixo `/v1`.
- `wait_healthy`: polling `GET {url sem /v1}/health` via `httpx.AsyncClient` a cada `_poll_interval_s` (default 2 s) até deadline; `httpx.HTTPError` (servidor subindo) tratado como "não saudável"; timeout → `_force_kill` (SIGKILL) + **`ServerStartTimeoutError`** (erro de domínio, não `TimeoutError` genérico).
- `stop`: `SIGTERM` → `asyncio.wait_for(process.wait(), _sigterm_timeout_s=30s)` → `SIGKILL` em timeout (nunca SIGKILL direto). `ProcessLookupError` absorvido. Log `vllm_server_stopped` com `forced: bool`.
- `_poll_interval_s`, `_sigterm_timeout_s`, `_clock` injetáveis (convenção `_`) → testes de timeout determinísticos e instantâneos (relógio falso via `itertools.count`, sem espera real).
- Testes (Nota M1 item 7): `asyncio.create_subprocess_exec` mockado via pytest-mock (alvo string → mypy limpo no teste); **`respx`** para `/health` (intercepta `httpx.AsyncClient` direto — a ressalva do §11 era específica do SDK OpenAI + `asyncify`); `os.kill` mockado. 21 testes, adapter 100%.
- Dependência adicionada: `httpx>=0.27` (promovida de transitiva a direta de runtime).

### ModelSpec / ServerHandle — redesenho + VLLMServerManagerPort async (PR retroativo TAREFA-019)

- **PR retroativo em `domain/ports.py`** (mesmo padrão dos ports async de M0/M1):
  - `ModelSpec`: `model`, `port`, `quantization: str | None`, `tensor_parallel_size`, `max_model_len`, `extra_env: dict[str, str]` (antes: `model_id`, `tensor_parallel_size`, `gpu_memory_utilization`).
  - `ServerHandle`: `pid`, `url`, `model`, `batch_invariant: bool` (antes: `process_id`, `base_url`, `model_id`).
  - `VLLMServerManagerPort.start/wait_healthy/stop` promovidos de `def` para `async def` (Prompt A exige `await asyncio.create_subprocess_exec`/`httpx.AsyncClient`; Nota M1 item 1 lista o adapter como async-first).
- Callers atualizados: `FakeVLLMServerManager` (`tests/fakes/servers.py` — async + novos campos), `_StubVLLMServerManager` + `test_model_spec`/`test_server_handle`/`test_stub_vllm_manager_lifecycle` (`test_ports_contract.py`), `TestFakeVLLMServerManager` (`test_fakes_satisfy_ports.py`).
- `isinstance(adapter, VLLMServerManagerPort)` permanece válido — `runtime_checkable` verifica presença de método, não sincronicidade.

### AnnotationReaderAdapter (TAREFA-020 — concluída)

- Implementa `AnnotationReaderPort` com `def read(run_id: str) -> list[CriticalAnnotation]` — **síncrono** (Nota M1 item 1; leitura local de arquivo, sem I/O de rede). Camada 3 / ADR-010.
- **Carga ansiosa na construção** (ao contrário do `GoldChunkReaderAdapter`, que é lazy): JSONL → índice `dict[str, list[CriticalAnnotation]]` no `__init__`. Erros de formato aparecem cedo (construção), não em `read()`.
- **Arquivo ausente = Camada 3 desabilitada** (estado normal em M1): loga `INFO "annotation file not found, Camada 3 disabled"` + dict vazio → `read()` retorna `[]`. **Não** é erro (distinção do GoldChunk, onde arquivo ausente é `StorageError`).
- `read` sempre devolve `list` (cópia fresca via `list(self._by_run.get(run_id, []))`), nunca `None`; `[]` para run_id inexistente.
- **Validação → domínio**: `row_id` (hex) → `RowId` (`RowId.__post_init__` exige SHA-256 64-hex; `ValueError` vira `StorageError`); `flag ∈ {0,1}` senão `StorageError` (uniforme para linha malformada — não usa `InvalidCriticalFailureFlagError`); `note` opcional (`record.get("note")` → ausente/`null` = `None`). `StorageError` em `JSONDecodeError`/`KeyError`/`TypeError`/`ValueError`, com `lineno` + nome do arquivo.
- `reload(annotation_file: Path | None = None) -> int`: recarrega (ou troca de) arquivo; retorna a contagem total de anotações.
- Fixture: `tests/fixtures/annotations.jsonl` (3 anotações, uma com `note: null`). Casos de erro escrevem arquivos via `tmp_path`. 18 testes, adapter 100%.

### Gate de Integração M1 (TAREFA-021 — concluída)

- **Dois arquivos**: `tests/integration/test_m1_pipeline_integration.py` (pipeline E2E de 1 pergunta pelos 8 adapters) e `tests/e2e/test_m1_smoke_e2e.py` (instanciação + `isinstance` por Protocol; gated `E2E_ENABLED`). Fixture: `tests/fixtures/integration_question.json`.
- **Mock — respx para os 3 (generator, judge, RAGAS)**: probe confirmou que `respx.mock` global **intercepta** `AsyncOpenAI.chat.completions.create` (a ressalva do §11 era do padrão `http_client=MockTransport`, não do `respx.mock` global). O RAGAS é construído **real** (sem `_metrics`) numa URL própria (`_RAGAS_URL`); suas chamadas LLM são roteadas por uma rota respx com *side-effect* (`_ragas_llm_route`) que devolve, **por métrica**, o JSON que o parser interno espera — discriminando pelos tokens do schema no prompt (`noncommittal`→relevancy; `"TP"`→correctness; `attributed`→recall; `statements`+`verdict`→faithfulness NLI; `statements`→geração; `verdict`→precision). Uma rota estática deixaria correctness/faithfulness/precision em NaN → `final_score` NaN. Embeddings ficam locais (HuggingFace, sem HTTP). `assert_all_called` garante que generator, judge e RAGAS foram chamados (decisão 021-C, resolvendo o item 3 do Prompt B).
- **Qdrant**: fixture `qdrant_url` session-scoped resolve `QDRANT_URL` (serviço CI) → testcontainers (local) → `pytest.skip`. Coleção function-scoped (sem persistência entre testes). `query_points` redirecionado p/ vetor denso (Qdrant vanilla sem Inference API). Retrieval roda **fora** do `respx.mock` (senão respx interceptaria o httpx do Qdrant).
- **Leitura do Parquet bruto**: usar `pq.ParquetFile(path).read()`, **nunca** `pq.read_table(path)` dentro da árvore Hive (`round_id=…`) — esta dispara auto-detecção de partição e conflita `round_id` string × dictionary (`ArrowTypeError`).
- **`read_by_run_id` da spec não existe**: usar `load(round_id=, phase=)` (API real do `ResultReaderPort`). `EvaluationResult` persistido com `DeterminismRegime.GENERATOR` → `batch_invariant=False` no Parquet.
- **CI** (§10): jobs `unit` (guarda 85%) e `integration` (serviço `qdrant/qdrant:v1.9`). `pytest-randomly` adicionado p/ `pytest --randomly` (item 8). Validação local via probe com `AsyncQdrantClient(location=":memory:")` (teste em si é skipado sem Docker).

---

## 14. Decisões de Design Relevantes para M3

### ExternalVLLMServerManager (TAREFA-311 — concluída)

- Implementa `VLLMServerManagerPort` **sem subprocess** — para vLLM pré-existente (clusters LNCC).
- `ServerHandle.pid: int | None` (PR retroativo): `None` em modo external, `int` em modo managed. `_fail`/`_force_kill` no `VLLMServerManagerAdapter` fazem assert `pid is not None` antes de SIGTERM/SIGKILL.
- `stop()` no-op (loga `vllm_server_external_skipped`); `start()` valida endpoint via `/health` sem criar processo; `wait_healthy()` chama `start()` internamente.
- `RoundConfig.server_mode: Literal["managed", "external"]`; `ModelEntry.endpoint_env: dict[str, str]` para override de URL por gerador em modo external.
- Wiring seleciona adapter via `server_mode`; helper `_build_external_server_manager()` instancia `ExternalVLLMServerManager`.

### Probes de proveniência (TAREFA-311 — concluída)

- `infrastructure/provenance/endpoint_probe.py`: 3 probes HTTP via `httpx.AsyncClient`.
  - `probe_served_model(url) -> str | None` — `GET /v1/models` → primeiro `id` da lista.
  - `probe_vllm_version(url) -> str | None` — `GET /version` → campo `version`.
  - `probe_judge_determinism(url, model) -> bool` — 2 completions com `seed=42, temperature=0.0`; `True` se tokens idênticos.
- `collect_provenance(config: RoundConfig) -> ProvenanceInfo` — SHA-256 canônico de `config.model_dump()` (não de `round_id`).
- `_mask_url(url) -> str` — mantém `scheme://host:port/***`; oculta path para audit de topologia sem vazar paths internos.
- `endpoints_provenance` no `ExperimentReport` inclui: `config_hash`, `topology` (managed/external), `endpoint_masked`, `healthy`, `vllm_version` por gerador, `judge_det`.

### Semântica de `determinism_verified` (TAREFA-311 — concluída)

- **`False` por default** — sem prova, sem `True` (ADR-014). Só vira `True` se `probe_judge_determinism` executar e confirmar tokens idênticos.
- Fallback de exceção em `_run_endpoint_probes()` retorna `({}, False, {...})` — nunca assume determinismo em caso de falha de probe.
- CLI `--require-verified-determinism`: aborta o run se `determinism_verified=False` ao final dos probes.

### `config_hash` canônico (TAREFA-311 — concluída)

- Calculado em `wiring.build_container()` via `collect_provenance(config)` — SHA-256 de `json.dumps(config.model_dump(), sort_keys=True, default=str)`.
- Propagado para: `_ExperimentConfig.config_hash`, `ExperimentConfigView.config_hash` (Protocol), `ParquetStorage` (campo `RowProvenance`), `ExperimentReport.config_hash`, log `endpoints_provenance`.
- `run_experiment.py` usa `self._config.config_hash[:8]` diretamente — não recalcula internamente.

### `judge_url` em modo external (TAREFA-311 — concluída)

- Em modo `managed`: `judge_url = settings.VLLM_JUDGE_URL` (env global).
- Em modo `external`: `judge_url = _judge_url_probe` (URL validada via probe do registry) se disponível; fallback para `settings.VLLM_JUDGE_URL`.
- Ambos `PrometheusJudgeAdapter` e `RAGASLayer1Adapter` recebem o mesmo `judge_url` — consistência garantida no wiring.

### Testes de wiring offline-safe (TAREFA-311 — concluída)

- `RAGASLayer1Adapter.__init__` chama `_build_embeddings(config)` (carrega HuggingFace) na construção.
- Testes de wiring em `test_wiring_external.py` usam fixture `autouse=True` que faz patch de `_build_embeddings` → `MagicMock()` — sem downloads de modelo em CI offline.
- Testes de CLI em `test_run_external.py` usam `_make_asyncio_run_mock()` com `side_effect` que fecha coroutines (`coro.close()`) — elimina `RuntimeWarning: coroutine was never awaited`.

### Bundle de prompt versionado e fidelidade de geração (TAREFA-316 — concluída)

- **ADR-015**: bundle versionado `{system.txt, user.j2}` em `infrastructure/prompts/rag/<versão>/`.
  - `system.txt` = texto puro (sem variáveis Jinja2), carregado via `loader.get_source()`.
  - `user.j2` = template Jinja2 com `{{ context }}` e `{{ question }}`.
  - Contexto formatado como `"\n\n".join(f"[PMID:{c.source or 'N/A'}] {c.text}" for c in contexts)`.
  - Bundle `v1_production` = cópia verbatim do `system_prompt.txt` de produção.
- **`render_fn` substitui `prompt_fn`**: `VLLMGeneratorAdapter.__init__` aceita
  `render_fn: Callable[[str, Sequence[Chunk]], tuple[str, str]] | None`; default é
  `_default_render_fn` (lazy import do registry, bundle `v1_production`). Injeção para testes:
  `render_fn=lambda q, ctx: ("SYS", "USER")`.
- **Mensagens system+user**: `VLLMGeneratorAdapter` envia `messages=[{"role": "system", ...}, {"role": "user", ...}]` — não mais prompt única.
- **Strip de `<think>`**: `_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)` aplicado à saída bruta ANTES de montar `GenerationOutput` (mesmo comportamento do `orchestrator_service.py` de produção).
- **`Chunk.source: str = ""`**: campo aditivo adicionado em `domain/ports.py`; `QdrantRetrieverAdapter` preenche de `payload["source"]`; ausente → `""` (sem erro).
- **`RoundConfig.generation_prompt_version`**: campo com default `"v1_production"`; `load_round_config` valida contra `registry.list_rag_versions()` após parse Pydantic — versão inválida levanta `ConfigValidationError` com lista de disponíveis.
- **`prompt_version` no Parquet = `config.generation_prompt_version`** (ex.: `"v1_production"`), não mais `git describe` — proveniência diretamente ligada ao bundle usado.
- **Log `vllm_generation_completed`** inclui `system_len`, `user_len`, `num_chunks`; system/user NÃO logados crus (ADR-008 / política TAREFA-314).
- **Adicionar novo bundle**: criar `infrastructure/prompts/rag/<nova_versão>/system.txt` + `user.j2`; setar `generation_prompt_version: <nova_versão>` no YAML da rodada.
