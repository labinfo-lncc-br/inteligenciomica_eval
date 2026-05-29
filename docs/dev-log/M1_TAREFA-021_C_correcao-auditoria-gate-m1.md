# M1_TAREFA-021_C — Correção pós-auditoria do Gate de Integração M1

**Data**: 2026-05-29
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1+E2
**Skill**: test-engineer, python-engineer
**Prioridade / Tamanho**: P0 / M
**Em resposta a**: `M1_TAREFA-021_B_auditoria-gate-integracao-m1.md` (FAIL / Request changes)

## Objetivo

Resolver os 3 bloqueadores da auditoria 021-B. Gates estáticos já estavam verdes.

## Bloqueadores e Resoluções

### Bloqueador 1 — `fail_under=85` herdado no job `integration`

**Achado**: o comando do Prompt B (`pytest -m integration --cov=src --cov-report=term-missing
-v tests/integration/`) falhava localmente com 36% porque `[tool.coverage.report] fail_under = 85`
do `pyproject.toml` é aplicado pelo `pytest-cov` mesmo sem `--cov-fail-under` na CLI.

**Correção**: removido `fail_under = 85` de `[tool.coverage.report]`. O gate de 85% passa a ser
imposto **exclusivamente** pelo flag explícito `--cov-fail-under=85` no job `unit` e no comando
de gate local documentado. Assim, runs de suíte única (job `integration` / comando do Prompt B)
reportam cobertura sem falhar pela porcentagem naturalmente menor.

**Evidência**: `pytest -m integration --cov=src --cov-report=term-missing -v tests/integration/`
→ **2 passed, 8 skipped, 32 deselected, 36% — exit 0** (sem erro de fail_under).

### Bloqueador 2 — RAGAS não validava o caminho RAGAS→LLM via respx

**Achado**: o teste injetava `_metrics` com `AsyncMock`, contornando o caminho exigido pelo item 3.

**Correção**: o teste agora constrói o `RAGASLayer1Adapter` **real** (sem `_metrics`). Suas 6 métricas
chamam o LLM-juiz numa URL própria (`_RAGAS_URL`), e essas chamadas HTTP são interceptadas por uma
rota respx com *side-effect* (`_ragas_llm_route`) que devolve, **por métrica**, o JSON que o parser
interno daquela métrica espera (discriminando pelos tokens do schema embutido no prompt:
`noncommittal` → answer_relevancy; `"TP"`/`true positive` → answer_correctness; `attributed` →
context_recall; `statements`+`verdict` → faithfulness NLI; `statements` → geração de statements;
`verdict` → context_precision). Os embeddings permanecem locais (HuggingFace, sem HTTP).
`assert_all_called` confirma que generator, judge e RAGAS foram todos chamados via respx.

**Bug de produção descoberto** (valor central do gate): com o adapter como estava
(`AnswerCorrectness(llm=llm, embeddings=embeddings)`), `answer_correctness` resultava **sempre NaN** —
o `answer_similarity` interno só é setado em `init(run_config)` do RAGAS, que `single_turn_ascore`
**não** chama, disparando `AssertionError: AnswerSimilarity must be set`. Os unit tests da 017
injetavam `_metrics` e nunca exercitaram o ramo de construção real (linhas `96-114`, ~87% cobertura).
**Correção no adapter** (`src/.../ragas_metrics.py`): wirar `answer_similarity=AnswerSimilarity(embeddings=embeddings)`
explicitamente no `AnswerCorrectness` (e reusar a mesma instância como métrica standalone). Com isso,
as 6 métricas retornam não-NaN.

**Evidência** (probe local com RAGAS real + callback respx): `ac=0.913, faith=1.0, cp=1.0, cr=1.0,
ar=1.0, similarity=0.68` → `nan_fields=[]` → `final_score=0.928` (finito).

### Bloqueador 3 — smoke E2E falhava ao construir RAGAS real sem cache/rede

**Achado**: `RAGASLayer1Adapter(judge_url=...)` no smoke tentava baixar o modelo HuggingFace, falhando
sem cache/rede.

**Correção**: o smoke separa as duas preocupações:
- `test_all_m1_adapters_instantiable_and_satisfy_protocols`: constrói o RAGAS com `_metrics={}`
  (sem carregar embeddings) — verifica instanciabilidade + `isinstance(MetricSuitePort)` de forma
  **independente de ambiente**.
- `test_ragas_real_construction_when_model_available`: tenta a construção **real**; **pula** (não
  falha) com `pytest.skip` se o modelo não estiver disponível (sem cache/rede). Verifica "config real"
  quando possível.

## Validação (DoD)

```
ruff check / format --check     → All checks passed! / 84 files
mypy --strict src               → Success (30 files)
mypy --strict (2 testes novos)  → Success
lint-imports                    → 4 kept, 0 broken
pytest -m integration ... tests/integration/  → 2 passed, 8 skipped, 36% — exit 0 (Prompt B, blocker 1)
pytest tests/unit/.../test_ragas_layer1.py     → 16 passed (017 intacto após fix do adapter)
E2E_ENABLED=1 pytest tests/e2e/test_m1_smoke_e2e.py → 3 passed (inclui construção real do RAGAS)
pytest -m "not integration" --cov -n 4 (job unit) → 695 passed, 3 skipped — 96.75% (≥85%)
pytest --cov -n 4 (completo, randomly)            → 697 passed, 11 skipped — 96.75%
probe full-integration (Qdrant :memory: + RAGAS real + respx) → final_score=0.928, batch_invariant=False
```

`ragas_metrics.py` em 87% local (ramo de construção real coberto só pelo teste de integração, que roda
no CI); cobertura global 96.75%.

## Arquivos Modificados nesta correção

| Arquivo | Mudança |
|---------|---------|
| `src/.../adapters/ragas_metrics.py` | Fix: `answer_similarity` wirado no `AnswerCorrectness` (bug de produção) |
| `tests/integration/test_m1_pipeline_integration.py` | RAGAS real + rota respx per-métrica (`_ragas_llm_route`); URL própria; asserções de não-NaN por campo |
| `tests/e2e/test_m1_smoke_e2e.py` | Conformidade com `_metrics={}` + teste guardado de construção real |
| `pyproject.toml` | Removido `fail_under = 85` de `[tool.coverage.report]` |

## Resposta item a item à auditoria 021-B

| Bloqueador | Resolução |
|------------|-----------|
| 1. `fail_under` herdado no integration | ✅ removido do config; gate via flag explícito no job `unit` |
| 2. RAGAS não passa pelo LLM via respx | ✅ RAGAS real + rota respx per-métrica; + fix do bug `answer_similarity` |
| 3. smoke falha sem cache/rede do HF | ✅ conformidade com `_metrics={}`; construção real guardada por `skip` |

## Observações

- O gate cumpriu seu papel: revelou um bug real (answer_correctness sempre NaN em produção) que os
  unit tests com mock haviam mascarado.
- Pronto para reauditoria. Com PASS aqui + 013–020, **M1 concluído**.
