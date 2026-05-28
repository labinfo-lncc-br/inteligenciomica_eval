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
| `tenacity` | `>=8.0` | Retry com `AsyncRetrying` nos adapters de rede |
| `structlog` | `>=24.0` | Logging estruturado em toda a infraestrutura |
| `pydantic` | `>=2.0` | Validação de configuração YAML (apenas infra) |

### Dev deps adicionais (M1)

| Pacote | Uso |
|--------|-----|
| `testcontainers[qdrant]>=4.3` | Testes de integração do `QdrantRetrieverAdapter` |
| `pytest-asyncio>=0.23` | Suporte a `async def` em testes |
| `respx>=0.20` | Mock de chamadas httpx diretas (adapters sem SDK intermediário) |

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
  prompts_m1_tarefas_013_021.md ← Nota de operacionalização M1 + prompts A/B
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

- `branch = true`, `source = ["src/inteligenciomica_eval"]`, `fail_under = 85`.
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

Arquivo: `.github/workflows/ci.yml`

Passos em ordem: checkout → setup-uv → setup-python 3.11 → `uv sync --frozen` →
`ruff check` → `ruff format --check` → `mypy --strict src` → `lint-imports` →
`pytest --cov=src --cov-report=xml --cov-fail-under=85 -n auto`

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

### M1 — Adapters de Infraestrutura (TAREFA-013 a 021)

| Tarefa | Descrição | Status |
|--------|-----------|--------|
| 013 | `QdrantRetrieverAdapter` + `GoldChunkReaderAdapter` | ✅ |
| 014 | `VLLMGeneratorAdapter` (async-first, openai SDK, tenacity, AsyncMock) | ✅ |
| 015 | `PromptRegistry` (templates Jinja2 versionados, `PackageLoader`) | 🔲 próxima |
| 016 | `PrometheusJudgeAdapter` (rubrica biomédica, NaN-or-retry ADR-007) | 🔲 |
| 017 | `RAGASLayer1Adapter` (RAGAS apontando para vllm-judge determinístico) | 🔲 |
| 018 | `DeterministicMetricsAdapter` (BERTScore + ROUGE-L, síncrono) | 🔲 |
| 019 | `VLLMServerManagerAdapter` (subprocess local, polling /health) | 🔲 |
| 020 | `AnnotationReaderAdapter` (JSONL de anotações críticas) | 🔲 |
| 021 | Gate de integração M1 (pipeline adapter end-to-end) | 🔲 |

### Cobertura atual

```
579 passed, 7 skipped — 96.39% total coverage
vllm_generator.py: 98% | qdrant_retriever.py: 95%
```

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

### PromptRegistry (TAREFA-015 — a implementar)

- Templates em `src/inteligenciomica_eval/infrastructure/prompts/*.j2`.
- `jinja2.Environment(loader=PackageLoader(...))`.
- `prompt_version` = `git describe --tags --dirty` capturado na inicialização.
- `VLLMGeneratorAdapter` já aceita `prompt_fn: Callable[[str, Sequence[Chunk]], str]` para injeção — substituir `_default_prompt_fn` inline pelo `PromptRegistry`.
