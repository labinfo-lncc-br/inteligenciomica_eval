# M1_TAREFA-021_B — Auditoria Gate de Integração M1

**Data**: 2026-05-29
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1+E2 — Gate de Integração
**Skill**: code-reviewer, test-engineer
**Prioridade / Tamanho**: P0 / M
**Resultado**: FAIL / Request changes

## Objetivo

Auditar a implementação da TAREFA-021-A contra o Prompt B das linhas 1088-1121 de
`docs/prompts_m1_tarefas_013_021_corrigido.md`, verificando o gate de integração M1:

- pipeline de uma pergunta passando pelos 8 adapters de M1 e `ParquetStorage`;
- Qdrant real com dados isolados por teste;
- vLLM mockado via `respx` para generator, judge e RAGAS;
- roundtrip Parquet com `final_score` finito, `row_id` correto e `batch_invariant=False`;
- smoke E2E com `isinstance` contra Protocols;
- CI com job `integration` e serviço Qdrant;
- ordem aleatória e cobertura global sem regressão.

## Arquivos Criados / Modificados

| Arquivo | Ação | Observação |
|---------|------|------------|
| `docs/dev-log/M1_TAREFA-021_B_auditoria-gate-integracao-m1.md` | Criado | Este relatório de auditoria |

Arquivos auditados:

- `docs/dev-log/M1_TAREFA-021_A_gate-integracao-m1.md`
- `docs/prompts_m1_tarefas_013_021_corrigido.md`
- `tests/integration/test_m1_pipeline_integration.py`
- `tests/e2e/test_m1_smoke_e2e.py`
- `tests/fixtures/integration_question.json`
- `.github/workflows/ci.yml`
- `pyproject.toml`
- `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py`
- `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py`
- `src/inteligenciomica_eval/domain/ports.py`

## Achados

### Bloqueador 1 — Job de integração falha por aplicar `fail_under=85` global

**Evidência**: `.github/workflows/ci.yml:87-94`, `pyproject.toml:152-153`.

O job `integration` executa:

```bash
uv run pytest -m integration --cov=src --cov-report=term-missing \
  --cov-report=xml:integration-coverage.xml -v tests/integration/
```

A intenção documentada em `.github/workflows/ci.yml:87-90` é não aplicar threshold ao
coverage isolado de integração. Porém `pytest-cov` continua lendo
`[tool.coverage.report] fail_under = 85` de `pyproject.toml:152-153`.

Ao executar localmente o comando exigido pelo Prompt B, o resultado foi:

```text
2 passed, 8 skipped, 32 deselected
ERROR: Coverage failure: total of 36 is less than fail-under=85
TOTAL 1349 stmts, 809 miss, 190 branch, 3 brpart, 36%
```

Mesmo com Qdrant disponível no CI, o job de integração isolado não deve ser obrigado a
atingir a cobertura global de 85%; a própria configuração do workflow diz isso. A correção
esperada é sobrescrever explicitamente o threshold nesse job, por exemplo com
`--cov-fail-under=0`, mantendo o threshold global no job `unit`.

### Bloqueador 2 — RAGAS não é mockado via `respx`; o caminho RAGAS→LLM é bypassado

**Evidência**: `tests/integration/test_m1_pipeline_integration.py:215-230`,
`tests/integration/test_m1_pipeline_integration.py:353-380`,
`src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py:95-116`.

O Prompt B pede verificar que `respx.mock` intercepta todas as chamadas HTTP ao vLLM:
generator, judge e chamadas internas do RAGAS ao LLM. O teste cria apenas duas rotas
`/chat/completions`, uma para generator e uma para judge
(`test_m1_pipeline_integration.py:355-363`), e instancia o adapter assim:

```python
ragas = RAGASLayer1Adapter(judge_url=_JUDGE_URL, _metrics=_ragas_metric_mocks())
```

Como `_metrics` é fornecido, `RAGASLayer1Adapter.__init__` não constrói
`LangchainLLMWrapper(ChatOpenAI(...))` nem métricas reais do RAGAS
(`ragas_metrics.py:95-116`). O teste exercita o loop do adapter sobre mocks de métrica,
mas não valida o caminho de integração RAGAS→LLM via vLLM/respx exigido pela TAREFA-021.

Esse desvio é documentado no relatório A, mas é uma divergência direta do item 3 do
Prompt B e do objetivo do gate de integração como substituição dos fakes de M0.

### Importante — Smoke E2E habilitado depende de cache/rede externa do HuggingFace

**Evidência**: `tests/e2e/test_m1_smoke_e2e.py:81-82`,
`src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py:105`.

Com `E2E_ENABLED=1`, o smoke falhou neste ambiente ao construir
`RAGASLayer1Adapter(judge_url=...)`, pois `HuggingFaceEmbeddings` tentou acessar:

```text
https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/adapter_config.json
```

Resultado executado:

```text
FAILED tests/e2e/test_m1_smoke_e2e.py::test_all_m1_adapters_instantiable_and_satisfy_protocols
RuntimeError: Cannot send a request, as the client has been closed.
Root cause logged: Temporary failure in name resolution while requesting HuggingFace
```

O teste fica `skip` sem `E2E_ENABLED`, então o job unit não quebra. Ainda assim, a
verificação manual do smoke E2E não é reprodutível em ambiente sem cache prévio do modelo
ou sem rede externa. Isso contradiz o relatório A, que afirma que o smoke passou com
"RAGAS real construído offline".

## Critérios do Prompt B

| Critério Prompt B | Evidência arquivo:linha | Gravidade / Resultado |
|-------------------|-------------------------|-----------------------|
| 1. Fluxo cobre os 8 adapters M1 em sequência; `VLLMServerManager` no smoke | Pipeline cobre Qdrant, Gold, VLLM, RAGAS, Prometheus, Deterministic, Annotation e Parquet em `test_m1_pipeline_integration.py:324-486`; `VLLMServerManagerAdapter` no smoke em `test_m1_smoke_e2e.py:86,96` | PASS parcial — todos aparecem, mas RAGAS usa `_metrics` mockado |
| 2. Qdrant com `testcontainers` session-scope e dados function-scope; sem persistência | Fixture `qdrant_url` em `test_m1_pipeline_integration.py:238-260`; `populated_collection` cria/apaga coleção por teste em `test_m1_pipeline_integration.py:263-306`; CI usa `QDRANT_URL` em `.github/workflows/ci.yml:61-69` | PASS estrutural; execução local pulou por falta de Qdrant/Docker |
| 3. `respx.mock` intercepta todas as chamadas HTTP ao vLLM, incluindo RAGAS | Apenas generator/judge têm rotas em `test_m1_pipeline_integration.py:355-363`; RAGAS recebe `_metrics` em `test_m1_pipeline_integration.py:353`, logo não faz chamada interna ao LLM | FAIL / Bloqueador |
| 4. `final_score` não-NaN e `batch_invariant=False` assertado no Parquet | `final_score` em `test_m1_pipeline_integration.py:408-409,473`; `batch_invariant` em `test_m1_pipeline_integration.py:477-486` | PASS por inspeção; teste não executou localmente sem Qdrant |
| 5. Linha do Parquet lida de volta com `row_id` correto | Roundtrip via `storage.load` e coluna Parquet em `test_m1_pipeline_integration.py:467-486` | PASS por inspeção; teste não executou localmente sem Qdrant |
| 6. Smoke E2E verifica `isinstance` contra Protocol, com `@e2e` e skipif | Marcadores em `test_m1_smoke_e2e.py:60-66`; asserts em `test_m1_smoke_e2e.py:89-98` | FAIL manual com `E2E_ENABLED=1` por dependência de HuggingFace/cache |
| 7. CI atualizado com job `integration`, serviço `qdrant/qdrant:v1.9`, cobertura >=85 sem regressão | Serviço em `.github/workflows/ci.yml:57-69`; unit threshold em `.github/workflows/ci.yml:42-48`; `pyproject.toml:152-153` aplica `fail_under=85` também ao job integration | FAIL / Bloqueador |
| 8. Testes paralelizáveis e `pytest-randomly` não quebra | `pytest-randomly` em `pyproject.toml:57-59`; `pytest -m "not integration" ... -n 4` passou com seed aleatória | PASS para suíte não-integração; integração local pulou Qdrant |

## Probes Executados

### Protocols com instanciação controlada

Para isolar a verificação de `@runtime_checkable` sem baixar embeddings, rodei um probe com
`RAGASLayer1Adapter(..., _metrics=...)`. Resultado:

```text
QdrantRetrieverAdapter->RetrieverPort=True
GoldChunkReaderAdapter->GoldChunkReaderPort=True
VLLMGeneratorAdapter->GeneratorPort=True
PrometheusJudgeAdapter->RubricJudgePort=True
RAGASLayer1Adapter->MetricSuitePort=True
DeterministicMetricsAdapter->DeterministicMetricPort=True
AnnotationReaderAdapter->AnnotationReaderPort=True
VLLMServerManagerAdapter->VLLMServerManagerPort=True
ParquetStorage->ResultWriterPort=True
ParquetStorage->ResultReaderPort=True
```

Esse probe confirma a conformidade estrutural dos Protocols, mas não substitui o smoke E2E
real, que falhou com `E2E_ENABLED=1`.

## Validação (DoD)

| Comando / Probe | Resultado |
|-----------------|-----------|
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` | PASS — `All checks passed!` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .` | PASS — `84 files already formatted` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src` | PASS — `Success: no issues found in 30 source files` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict tests/integration/test_m1_pipeline_integration.py tests/e2e/test_m1_smoke_e2e.py` | PASS — `Success: no issues found in 2 source files` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` | PASS — 69 files, 178 dependencies, 4 contracts kept, 0 broken |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m "integration" --cov=src --cov-report=term-missing -v tests/integration/` | FAIL — 2 passed, 8 skipped, 32 deselected; coverage 36% abaixo de `fail_under=85` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m "integration" --cov=src --cov-report=term-missing --cov-fail-under=0 -v tests/integration/` | PASS técnico — 2 passed, 8 skipped; usado apenas para capturar cobertura sem quebrar no threshold global |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/e2e/test_m1_smoke_e2e.py` | PASS esperado por skip — 2 skipped |
| `UV_CACHE_DIR=/tmp/uv-cache E2E_ENABLED=1 uv run pytest -q tests/e2e/test_m1_smoke_e2e.py` | FAIL — 1 failed, 1 passed; falha ao construir RAGAS por tentativa de acesso ao HuggingFace |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m "not integration" --cov=src --cov-report=term-missing --cov-fail-under=85 -n 4` | PASS — 695 passed, 2 skipped, 96.82% |
| Probe de Protocols com RAGAS `_metrics` injetado | PASS estrutural — todos `isinstance(..., Port)` retornaram `True` |

### Cobertura de `infrastructure/adapters/` no comando de integração

Com Qdrant/Docker indisponível localmente, os testes que exercitariam os adapters reais
foram pulados. O output de cobertura do comando de integração ficou:

```text
annotation_reader.py          28%
deterministic_metrics.py      47%
prometheus_judge.py           33%
qdrant_retriever.py           64%
ragas_metrics.py              54%
vllm_generator.py             41%
vllm_server_manager.py         0%
TOTAL                         36%
```

Warnings observados:

- `pytest-benchmark` avisa que benchmarks são desabilitados sob `xdist`.
- `ragas_metrics.py` emite `DeprecationWarning` de `langchain-community`.
- `bert_score` emite `UserWarning` de NumPy array não gravável.
- `qdrant_client` avisa no smoke/probe que não conseguiu obter versão do servidor local.

## Conclusão

Veredito: **FAIL / Request changes**.

Os gates estáticos e a suíte não-integração estão verdes, mas o Gate M1 ainda não pode ser
aprovado. O job `integration` falha por herdar o `fail_under=85` global, e o teste de
integração não valida o caminho RAGAS→LLM via `respx` exigido pelo Prompt B. Além disso, o
smoke E2E habilitado não foi reprodutível neste ambiente por dependência de cache/rede
externa do HuggingFace.

Correções recomendadas:

1. No job `integration`, sobrescrever explicitamente o threshold de cobertura isolada
   (`--cov-fail-under=0`) ou separar a configuração de coverage do job.
2. Ajustar o teste de integração para exercitar o `RAGASLayer1Adapter` com o caminho de LLM
   mockado via `respx`, ou atualizar formalmente a especificação se `_metrics` injetado for
   a decisão aceita para o Gate M1.
3. Tornar o smoke E2E reprodutível sem cache implícito do HuggingFace, ou documentar e
   validar explicitamente o pré-requisito de cache/rede quando `E2E_ENABLED=1`.
