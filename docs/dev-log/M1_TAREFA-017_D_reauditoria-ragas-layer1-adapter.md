# M1_TAREFA-017_D - Reauditoria do RAGASLayer1Adapter

**Data**: 2026-05-28  
**Milestone**: M1 - Adapters de Infraestrutura  
**Prompt**: D - reauditoria apos correcao C  
**Papel**: code-reviewer, test-engineer, rag-engineer  
**Resultado**: **PASS**

---

## Escopo

Reauditar a correcao da TAREFA-017-C contra o bloqueador registrado em
`docs/dev-log/M1_TAREFA-017_B_auditoria-ragas-layer1-adapter.md` e contra os
criterios do Prompt B da TAREFA-017:

- `docs/prompts_m1_tarefas_013_021_corrigido.md`, TAREFA-017, Prompt A/B.
- `docs/arquitetura_detalhada_validacao_inteligenciomica.md`, secao 5.1/5.2 e ADR-007.
- Dev-log da correcao: `docs/dev-log/M1_TAREFA-017_C_reauditoria-ragas-layer1-adapter.md`.
- Baseline das skills `code-reviewer`, `test-engineer` e `rag-engineer`.

A auditoria nao reescreveu a implementacao.

---

## Passos Executados

1. Li novamente o Prompt A/B da TAREFA-017.
2. Li o dev-log da correcao C.
3. Inspecionei a implementacao corrigida em:
   - `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py`
   - `tests/unit/infrastructure/adapters/test_ragas_layer1.py`
   - `src/inteligenciomica_eval/domain/ports.py`
   - `src/inteligenciomica_eval/domain/services/final_score.py`
   - `pyproject.toml` e `.importlinter`
4. Verifiquei se o shim manual havia sido removido de `.venv`.
5. Verifiquei se o shim versionado e aplicado antes dos imports de `ragas`.
6. Executei probes de importacao em processo limpo e em venv temporario criado com
   `uv run --frozen`.
7. Reexecutei gates de lint, formatacao, mypy, import-linter, testes focados e suite
   completa com cobertura.

---

## Comandos e Resultados

Todos os comandos com `uv` foram executados com `UV_CACHE_DIR=/tmp/uv-cache`.

| Comando | Resultado |
|---|---|
| `uv run ruff check .` | PASS - `All checks passed!` |
| `uv run ruff format --check .` | PASS - `76 files already formatted` |
| `uv run mypy --strict src/` | PASS - `Success: no issues found in 27 source files` |
| `uv run lint-imports` | PASS - 4 contracts kept, 0 broken |
| `MYPYPATH=src mypy --strict --config-file=/dev/null -c '<MetricSuitePort assignment probe>'` | PASS - `suite: MetricSuitePort = RAGASLayer1Adapter(...)` aceito |
| `uv run mypy --strict tests/unit/infrastructure/adapters/test_ragas_layer1.py` | PASS - teste tipado aceito com os overrides do projeto |
| `uv run pytest -v tests/unit/infrastructure/adapters/test_ragas_layer1.py tests/unit/fakes/test_fakes_satisfy_ports.py tests/e2e/test_min_round_stub.py` | PASS - 80 passed, 1 warning |
| `uv run pytest --cov --cov-fail-under=85` | PASS - 637 passed, 7 skipped, cobertura total 96.29%, `ragas_metrics.py` 89% |
| `uv run python -c '<verifica .venv/.../vertexai.py>'` | PASS - `manual_shim_exists=False` |
| `uv run python -c '<adapter import + sys.modules probe>'` | PASS - adapter importa, shim entra em `sys.modules`, `ChatVertexAI` existe, `module_file=None` |
| `uv run python -c '<ragas-style from langchain_community.chat_models.vertexai import ChatVertexAI>'` apos importar adapter | PASS - importa a classe de `langchain_google_vertexai.chat_models.ChatVertexAI` |
| `UV_PROJECT_ENVIRONMENT=/tmp/inteligenciomica_eval_audit_017d_venv uv run --frozen python -c '<import RAGASLayer1Adapter>'` | PASS - venv limpo importou o adapter; `manual_shim_exists=False` |
| `uv run python -c 'import ragas'` | FAIL esperado fora do caminho do adapter - `ModuleNotFoundError: langchain_community.chat_models.vertexai` |

Observacao operacional: a primeira tentativa do venv temporario falhou por DNS ao baixar
`scipy`; o comando foi reexecutado com rede permitida e passou. Isso confirma o caso
que importava para a auditoria: um ambiente recriado a partir de `uv.lock`, sem patch
manual em `.venv`, consegue importar o adapter.

---

## Achados

### Bloqueadores

Nenhum bloqueador remanescente.

O bloqueador da auditoria B foi resolvido: o arquivo manual
`.venv/lib/python3.13/site-packages/langchain_community/chat_models/vertexai.py` nao
existe mais, e o adapter importou em venv temporario sem esse arquivo.

### Importantes

| Criterio | Evidencia | Gravidade |
|---|---|---|
| O shim resolve o caminho do adapter, mas nao torna `import ragas` globalmente funcional | `RAGASLayer1Adapter` importa com sucesso porque `ragas_metrics.py:18-29` injeta `langchain_community.chat_models.vertexai` antes dos imports de RAGAS em `ragas_metrics.py:35-38`. Um processo que execute `import ragas` diretamente, sem passar pelo adapter, ainda falha com `ModuleNotFoundError`. Como o projeto usa RAGAS apenas no adapter (`rg "from ragas\|import ragas"` retorna somente `ragas_metrics.py` e um import local de teste apos importar o adapter), isso nao bloqueia TAREFA-017, mas deve ser considerado em futuras integracoes. | Importante / risco residual |
| O Prompt A pede NaN como `null` no JSON de log; a implementacao passa `float("nan")` ao structlog | O log `ragas_layer1_computed` inclui todos os 6 campos, `nan_fields`, `latency_ms` e `judge_url` em `ragas_metrics.py:156-166`, mas nao ha conversao explicita `NaN -> None` antes do log. Como o criterio do Prompt B pede principalmente "Logging com todos os 6 valores e `nan_fields`", isso fica como ressalva, nao bloqueador. | Importante / nao bloqueador |

### Waiver Mantido

| Criterio | Evidencia | Gravidade |
|---|---|---|
| Prompt A menciona `respx.mock`, mas os testes usam `AsyncMock` no nivel dos objetos RAGAS | Os testes injetam `_metrics` e verificam `single_turn_ascore` sem rede/modelo em `test_ragas_layer1.py:65-90`, `test_ragas_layer1.py:138-157` e `test_ragas_layer1.py:165-242`. Mantem-se o waiver aceito na auditoria B por ser o nivel correto de mock para este adapter. | Waiver aceito |

---

## Checklist Prompt B

| # | Criterio | Status | Evidencia |
|---|---|---|---|
| 1 | RAGAS usa `LangchainLLMWrapper(ChatOpenAI(base_url=judge_url, ..., api_key="EMPTY"))`; sem `OPENAI_API_KEY`; `judge_url`/`judge_model` do construtor | PASS | `ragas_metrics.py:86-103`; `judge_url` e `judge_model` entram pelo construtor; `api_key=SecretStr("EMPTY")`; nao ha uso de `OPENAI_API_KEY`/`os.environ`. |
| 2 | Metricas calculadas individualmente via `single_turn_ascore`; nao `ragas.evaluate(dataset)`; metodo `.score()` | PASS | `RAGASLayer1Adapter.score` em `ragas_metrics.py:118`; loop individual em `ragas_metrics.py:141-152`; busca por `ragas.evaluate` nao encontrou uso de producao; teste em `test_ragas_layer1.py:148-157`. |
| 3 | `SingleTurnSample` com `user_input`, `response`, `reference`, `retrieved_contexts` | PASS | `ragas_metrics.py:130-135`; teste em `test_ragas_layer1.py:324-347`. |
| 4 | NaN por metrica individual; excecao em uma metrica nao afeta as outras; sem `return NaN_vector` total em catch de topo | PASS | Catch por campo em `ragas_metrics.py:141-152`; retorno final monta `Layer1Metrics` com cada campo em `ragas_metrics.py:169-176`; testes em `test_ragas_layer1.py:165-242`. |
| 5 | `Layer1Metrics` tem os 6 campos corretos; `answer_similarity` e `bertscore_f1` nao entram no `FinalScore` | PASS | DTO em `domain/ports.py:92-112`; `FinalScoreCalculator.DEFAULT_WEIGHTS` exclui `answer_similarity` e `bertscore_f1` em `final_score.py:20-29`, documentado em `final_score.py:44-45`. |
| 6 | Logging com todos os 6 valores e `nan_fields` | PASS com ressalva | Codigo loga os 6 valores, `nan_fields`, `latency_ms` e `judge_url` em `ragas_metrics.py:156-166`; testes em `test_ragas_layer1.py:250-316`. Ressalva: nao ha conversao explicita de `float("nan")` para `None` no log JSON. |
| 7 | `mypy --strict`; import-linter OK; cobertura dos paths happy + NaN isolado | PASS | `mypy --strict src/` PASS; `lint-imports` PASS; suite completa PASS com 96.29%; happy path e NaN isolado cobertos em `test_ragas_layer1.py:119-157` e `test_ragas_layer1.py:165-242`. |

---

## Verificacao do Bloqueador B

| Verificacao | Resultado | Evidencia |
|---|---|---|
| Shim manual removido do `.venv` | PASS | Probe retornou `manual_shim_exists=False` para `.venv/lib/python3.13/site-packages/langchain_community/chat_models/vertexai.py`. |
| Shim versionado roda antes de RAGAS | PASS | Bloco de compatibilidade em `ragas_metrics.py:18-29`, imports de RAGAS somente depois em `ragas_metrics.py:35-38`. |
| Caminho usado pelo RAGAS resolve `ChatVertexAI` | PASS | Probe apos importar adapter aceitou `from langchain_community.chat_models.vertexai import ChatVertexAI` e retornou `<class 'langchain_google_vertexai.chat_models.ChatVertexAI'>`. |
| Ambiente novo sem patch manual importa o adapter | PASS | `UV_PROJECT_ENVIRONMENT=/tmp/inteligenciomica_eval_audit_017d_venv uv run --frozen ...` importou `RAGASLayer1Adapter`; `manual_shim_exists=False`. |

---

## Conclusao

A TAREFA-017-C corrige o bloqueador da auditoria B. O shim deixou de depender de
arquivo manual dentro de `.venv`, esta versionado no adapter e foi validado em venv
temporario criado por `uv --frozen`. Os criterios funcionais do Prompt B continuam
atendidos: LLM-juiz configurado via construtor, metricas calculadas individualmente,
NaN isolado por campo, DTO correto, logging presente e gates verdes.

Recomendacao: **Approve / PASS** para a TAREFA-017.

Riscos residuais para acompanhamento:

1. `import ragas` direto ainda falha sem passar pelo adapter; futuras tarefas devem
   evitar imports diretos ou centralizar o shim em modulo de compatibilidade mais geral.
2. Se a exigencia de log JSON com NaN como `null` for tratada como obrigatoria em uma
   tarefa futura, sera necessario converter `float("nan")` para `None` antes do log.
