# M1_TAREFA-021_D — Reauditoria Gate de Integração M1

**Data**: 2026-05-29
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1+E2 — Gate de Integração
**Skill**: code-reviewer, test-engineer
**Prioridade / Tamanho**: P0 / M
**Resultado**: PASS / Approve

## Objetivo

Reauditar a correção TAREFA-021-C contra os achados de
`M1_TAREFA-021_B_auditoria-gate-integracao-m1.md` e contra o Prompt B das linhas
1088-1121 de `docs/prompts_m1_tarefas_013_021_corrigido.md`.

Foco da reauditoria:

- `fail_under=85` não pode quebrar o job/comando isolado de integração;
- o teste do Gate M1 deve exercitar `RAGASLayer1Adapter` real, com LLM via `respx`;
- smoke E2E deve verificar `isinstance` dos adapters sem depender de rede/cache externo;
- o ajuste de produção no RAGAS (`AnswerCorrectness.answer_similarity`) não pode quebrar
  os testes da TAREFA-017;
- gates estáticos, cobertura e ordem aleatória continuam verdes.

## Arquivos Criados / Modificados

| Arquivo | Ação | Observação |
|---------|------|------------|
| `docs/dev-log/M1_TAREFA-021_D_reauditoria-gate-integracao-m1.md` | Criado | Este relatório de reauditoria |

Arquivos auditados:

- `docs/dev-log/M1_TAREFA-021_C_correcao-auditoria-gate-m1.md`
- `docs/prompts_m1_tarefas_013_021_corrigido.md`
- `tests/integration/test_m1_pipeline_integration.py`
- `tests/e2e/test_m1_smoke_e2e.py`
- `.github/workflows/ci.yml`
- `pyproject.toml`
- `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py`
- `tests/unit/infrastructure/adapters/test_ragas_layer1.py`
- `src/inteligenciomica_eval/domain/ports.py`

## Achados

Nenhum bloqueador ou achado importante foi identificado nesta reauditoria.

Os três bloqueadores da auditoria 021-B foram resolvidos:

1. `fail_under=85` foi removido de `[tool.coverage.report]`; o threshold global fica no
   flag explícito `--cov-fail-under=85` do job unit/gate local.
2. O teste de integração instancia `RAGASLayer1Adapter` real, sem `_metrics`, e cria rota
   `respx` dedicada para as chamadas internas do RAGAS ao LLM.
3. O smoke E2E separa conformidade estrutural de construção real do RAGAS; a conformidade
   roda sem cache/rede, e a construção real pula quando o modelo local não está disponível.

## Critérios do Prompt B

| Critério Prompt B | Evidência arquivo:linha | Gravidade / Resultado |
|-------------------|-------------------------|-----------------------|
| 1. Fluxo cobre todos os 8 adapters M1 em sequência; `VLLMServerManager` no smoke | Pipeline: `QdrantRetrieverAdapter` em `test_m1_pipeline_integration.py:362-369`; `GoldChunkReaderAdapter` em `:377-383`; `VLLMGeneratorAdapter`, `PrometheusJudgeAdapter`, `RAGASLayer1Adapter` em `:391-426`; `DeterministicMetricsAdapter` em `:444-447`; `AnnotationReaderAdapter` em `:463-480`; `ParquetStorage` em `:504-538`. `VLLMServerManagerAdapter` no smoke em `test_m1_smoke_e2e.py:92,102` | PASS |
| 2. Qdrant usa `testcontainers` session-scope e dados function-scope; sem persistência | `qdrant_url` session-scoped em `test_m1_pipeline_integration.py:276-298`; dados function-scoped em `populated_collection` `:301-344`; coleção apagada no teardown `:337-344`; CI usa `QDRANT_URL` em `.github/workflows/ci.yml:67-69` | PASS estrutural; local sem Docker/Qdrant pulou os testes dependentes |
| 3. `respx.mock` intercepta chamadas HTTP ao vLLM: generator, judge e RAGAS | RAGAS real sem `_metrics` em `test_m1_pipeline_integration.py:396`; `respx.mock(assert_all_called=True)` em `:398`; rotas generator/judge/RAGAS em `:399-409`; `ragas_route.called` em `:431-433`; side-effect por métrica em `:217-268` | PASS |
| 4. `final_score` não-NaN e `batch_invariant=False` assertados no Parquet | `final_score` calculado/assertado em `test_m1_pipeline_integration.py:449-461` e no roundtrip em `:519-525`; `batch_invariant=False` na coluna Parquet em `:529-538` | PASS |
| 5. Linha do Parquet lida de volta com `row_id` correto | `storage.load(round_id=..., phase=...)` em `test_m1_pipeline_integration.py:519`; `row_id` em `:522`; coluna Parquet `row_id` em `:533-537` | PASS |
| 6. Smoke E2E verifica `isinstance` contra Protocol, com `@e2e` e skipif sem env var | Marcadores em `test_m1_smoke_e2e.py:60-66`; asserts de `isinstance` em `:95-104`; construção real do RAGAS guardada em `:107-118` | PASS |
| 7. CI com job `integration`, serviço `qdrant/qdrant:v1.9`; cobertura global não regride abaixo de 85% | Serviço Qdrant em `.github/workflows/ci.yml:57-69`; job integration em `:87-94`; gate unit com `--cov-fail-under=85` em `:42-48`; ausência de `fail_under` global em `pyproject.toml:152-157` | PASS |
| 8. Testes paralelizáveis / `pytest-randomly` não quebra | `pytest-randomly` em `pyproject.toml:57-59`; comandos com seeds aleatórias passaram (`not integration` e suíte completa, ambos com `-n 4`) | PASS |

## Correção RAGAS

O ajuste em `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py:107-124`
cria explicitamente `AnswerSimilarity(embeddings=embeddings)` e injeta a instância em
`AnswerCorrectness(..., answer_similarity=answer_similarity)`, reutilizando-a como métrica
standalone. Isso resolve o bug relatado na correção C, em que `single_turn_ascore` não chamava
`init(run_config)` e `AnswerCorrectness` podia gerar NaN por falta de `answer_similarity`.

Os testes unitários existentes da TAREFA-017 continuam cobrindo isolamento de NaN, logging,
construção de `SingleTurnSample` e conformidade de Protocol via `_metrics` injetado.

## Validação (DoD)

| Comando / Probe | Resultado |
|-----------------|-----------|
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` | PASS — `All checks passed!` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .` | PASS — `84 files already formatted` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src` | PASS — `Success: no issues found in 30 source files` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict tests/integration/test_m1_pipeline_integration.py tests/e2e/test_m1_smoke_e2e.py` | PASS — `Success: no issues found in 2 source files` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` | PASS — 69 files, 178 dependencies, 4 contracts kept, 0 broken |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m "integration" --cov=src --cov-report=term-missing -v tests/integration/` | PASS — 2 passed, 8 skipped, 32 deselected, cobertura 36%, exit 0 |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/unit/infrastructure/adapters/test_ragas_layer1.py` | PASS — 16 passed |
| `UV_CACHE_DIR=/tmp/uv-cache E2E_ENABLED=1 uv run pytest -q tests/e2e/test_m1_smoke_e2e.py` | PASS — 2 passed, 1 skipped; construção real do RAGAS pulou por falta de modelo/cache neste ambiente |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m "not integration" --cov=src --cov-report=term-missing --cov-fail-under=85 -n 4` | PASS — 695 passed, 3 skipped, 96.75% |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n 4` | PASS — 697 passed, 11 skipped, 96.75% |

### Cobertura de `infrastructure/adapters/` no comando de integração

Como este ambiente local não tem Qdrant/Docker disponível, os testes que exigem backend
Qdrant foram coletados e pulados. O comando exato do Prompt B agora passa e reporta:

```text
annotation_reader.py          28%
deterministic_metrics.py      47%
prometheus_judge.py           33%
qdrant_retriever.py           64%
ragas_metrics.py              53%
vllm_generator.py             41%
vllm_server_manager.py         0%
TOTAL                         36%
```

Na suíte completa com cobertura, os adapters ficam:

```text
annotation_reader.py         100%
deterministic_metrics.py     100%
prometheus_judge.py          100%
qdrant_retriever.py           96%
ragas_metrics.py              87%
vllm_generator.py            100%
vllm_server_manager.py       100%
TOTAL                         96.75%
```

Warnings observados:

- `pytest-benchmark` avisa que benchmarks são desabilitados sob `xdist`.
- `ragas_metrics.py` emite `DeprecationWarning` de `langchain-community`.
- `HuggingFaceEmbeddings` emite `LangChainDeprecationWarning` no smoke E2E.
- `bert_score` emite `UserWarning` de array NumPy não gravável.
- `qdrant_client` avisa no smoke que não conseguiu obter versão do servidor local.

Nenhum warning acima é bloqueador para a TAREFA-021.

## Observações

- Não havia Docker/Qdrant local nesta sessão, então o pipeline M1 completo foi validado por
  inspeção do teste e pela configuração do CI com `services.qdrant`. O comando local exigido
  pelo Prompt B foi executado e passou, com skips esperados.
- A construção real do RAGAS no smoke E2E foi pulada localmente por indisponibilidade do
  modelo/cache; isso é comportamento intencional da correção C e evita dependência de rede
  externa no smoke de conformidade.

## Conclusão

Veredito: **PASS / Approve**.

Com esta reauditoria, os bloqueadores da TAREFA-021-B estão resolvidos. Considerando também
os PASS das TAREFAS 013 a 020, o Gate M1 está aprovado do ponto de vista desta auditoria.
