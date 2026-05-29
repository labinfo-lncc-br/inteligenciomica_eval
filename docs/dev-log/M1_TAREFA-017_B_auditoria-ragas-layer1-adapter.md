# M1_TAREFA-017_B - Auditoria do RAGASLayer1Adapter

**Data**: 2026-05-28  
**Milestone**: M1 - Adapters de Infraestrutura  
**Prompt**: B - Verificacao / auditoria  
**Papel**: code-reviewer, test-engineer, rag-engineer  
**Resultado**: **FAIL**

---

## Escopo

Auditar a implementacao da TAREFA-017 contra:

- `docs/prompts_m1_tarefas_013_021_corrigido.md`, TAREFA-017, Prompt A/B.
- `docs/arquitetura_detalhada_validacao_inteligenciomica.md`, secao 5.1/5.2 e ADR-007.
- Nota M1 itens 1, 3 e 5.
- Dev-log da parte A: `docs/dev-log/M1_TAREFA-017_A_ragas-layer1-adapter.md`.
- Baseline de RAG/RAGAS da skill `rag-engineer`.

A auditoria nao reescreveu a implementacao.

---

## Passos Executados

1. Li as skills aplicaveis: `code-reviewer`, `test-engineer`, `rag-engineer`.
2. Li o Prompt A/B da TAREFA-017 no arquivo corrigido de prompts.
3. Li o dev-log da parte A.
4. Inspecionei:
   - `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py`
   - `tests/unit/infrastructure/adapters/test_ragas_layer1.py`
   - `src/inteligenciomica_eval/domain/ports.py`
   - `tests/fakes/metrics.py`
   - `tests/e2e/_harness.py`
   - `pyproject.toml`, `.importlinter`, `uv.lock`
5. Verifiquei o shim manual citado no dev-log:
   - `.venv/lib/python3.13/site-packages/langchain_community/chat_models/vertexai.py`
   - `ragas.llms.base` importando `langchain_community.chat_models.vertexai`
   - `langchain-community` instalado sem esse arquivo no `RECORD` da distribuicao.
6. Executei os gates locais, testes focados, suite completa e uma prova mypy explicita
   de atribuicao `MetricSuitePort = RAGASLayer1Adapter`.

---

## Comandos e Resultados

Todos os comandos com `uv` foram executados com `UV_CACHE_DIR=/tmp/uv-cache`.

| Comando | Resultado |
|---|---|
| `uv run ruff check .` | PASS - `All checks passed!` |
| `uv run ruff format --check .` | PASS - `76 files already formatted` |
| `uv run mypy --strict src/` | PASS - `Success: no issues found in 27 source files` |
| `uv run lint-imports` | PASS - 4 contracts kept, 0 broken |
| `mypy --strict --config-file=/dev/null -c '<MetricSuitePort assignment probe>'` | PASS - `suite: MetricSuitePort = RAGASLayer1Adapter(...)` aceito |
| `mypy --strict --config-file=/dev/null tests/unit/infrastructure/adapters/test_ragas_layer1.py` | FAIL auxiliar - import nao tipado de `ragas.dataset_schema` e `type: ignore` inefetivo |
| `pytest -v tests/unit/infrastructure/adapters/test_ragas_layer1.py tests/unit/fakes/test_fakes_satisfy_ports.py tests/e2e/test_min_round_stub.py` | PASS - 80 passed, 1 warning |
| `pytest --cov --cov-fail-under=85` | PASS - 637 passed, 7 skipped, cobertura total 96.47%, `ragas_metrics.py` 91% |

---

## Achados

### Bloqueadores

| Criterio | Evidencia | Gravidade |
|---|---|---|
| Ambiente reprodutivel / CI verde apos `uv sync --frozen` | A implementacao depende de um shim criado manualmente dentro de `.venv`: `.venv/lib/python3.13/site-packages/langchain_community/chat_models/vertexai.py:1-5`. Esse diretorio e ignorado pelo Git em `.gitignore:8-10`, e o arquivo nao pertence ao pacote instalado: `langchain-community 0.4.2`, `chat_models/vertexai.py in RECORD: False`. Ao mesmo tempo, `ragas` 0.3.1 importa esse modulo incondicionalmente em `.venv/lib/python3.13/site-packages/ragas/llms/base.py:8`. O proprio dev-log confirma que ambientes CI que recriam o venv nao terao o shim em `docs/dev-log/M1_TAREFA-017_A_ragas-layer1-adapter.md:86-105` e `:170`. | Bloqueador |

### Importantes

| Criterio | Evidencia | Gravidade |
|---|---|---|
| O teste `test_static_typing_assignment` nao e exercitado pelo gate `mypy --strict src/` | A prova estatica direta do contrato passa via comando separado, mas rodar mypy no arquivo de teste falha antes por `ragas.dataset_schema` sem stubs e por `# type: ignore` posicionado de forma inefetiva em `tests/unit/infrastructure/adapters/test_ragas_layer1.py:327-329`. Como o gate oficial do projeto ainda tipa apenas `src/`, isso nao bloqueia a tarefa, mas reduz o valor do teste como detector automatico de regressao de typing. | Importante |

### Waiver Mantido

| Criterio | Evidencia | Gravidade |
|---|---|---|
| Prompt A menciona `respx.mock`, mas os testes usam `AsyncMock` no nivel de objetos RAGAS | O padrao segue a decisao vigente de `CLAUDE.md` para SDKs/adapters intermediarios. Os testes injetam `_metrics` e validam chamadas `single_turn_ascore` em `tests/unit/infrastructure/adapters/test_ragas_layer1.py:65-90`, `:138-157`. | Waiver aceito, nao bloqueia |

---

## Checklist Prompt B

| # | Criterio | Status | Evidencia |
|---|---|---|---|
| 1 | RAGAS usa `LangchainLLMWrapper(ChatOpenAI(base_url=judge_url, ..., api_key="EMPTY"))`; sem `OPENAI_API_KEY`; `judge_url`/`judge_model` do construtor | PASS | `ragas_metrics.py:58-74`; nao ha uso de `OPENAI_API_KEY`/`os.environ`; `api_key=SecretStr("EMPTY")` satisfaz o objetivo sem ler ambiente. |
| 2 | Metricas calculadas individualmente via `single_turn_ascore`; nao `ragas.evaluate(dataset)`; metodo `.score()` | PASS | `RAGASLayer1Adapter.score` em `ragas_metrics.py:90`; loop individual em `:113-116`; busca por `ragas.evaluate` nao encontrou uso; testes em `test_ragas_layer1.py:138-157`. |
| 3 | `SingleTurnSample` com `user_input`, `response`, `reference`, `retrieved_contexts` | PASS | `ragas_metrics.py:102-107`; teste em `test_ragas_layer1.py:325-349`. |
| 4 | NaN por metrica individual; excecao em uma metrica nao afeta as outras; sem `return NaN_vector` total em catch de topo | PASS | Catch por campo em `ragas_metrics.py:113-124`; retorno final monta `Layer1Metrics` com cada campo em `:141-148`; testes em `test_ragas_layer1.py:165-242`. |
| 5 | `Layer1Metrics` tem os 6 campos corretos; `answer_similarity` e `bertscore_f1` nao entram no `FinalScore` | PASS | DTO em `domain/ports.py:92-112`; `FinalScoreCalculator.DEFAULT_WEIGHTS` exclui `answer_similarity` e `bertscore_f1` em `src/inteligenciomica_eval/domain/services/final_score.py:20-29`, documentado em `:44-45`. |
| 6 | Logging com todos os 6 valores e `nan_fields` | PASS parcial | Codigo loga os 6 valores, `nan_fields`, `latency_ms` e `judge_url` em `ragas_metrics.py:128-139`; testes em `test_ragas_layer1.py:250-316`. Observacao: o Prompt A cita NaN como `null` no JSON de log; o codigo passa `float("nan")` diretamente, sem conversao explicita para `None`. |
| 7 | `mypy --strict`; import-linter OK; cobertura dos paths happy + NaN isolado | PASS local | Gates locais passaram: `mypy --strict src/`, `lint-imports`, suite completa com 96.47%; happy path e NaN isolado cobertos em `test_ragas_layer1.py:119-157` e `:165-242`. |

---

## Conclusao

Os criterios funcionais do Prompt B foram implementados corretamente: RAGAS esta apontando
para o juiz via `LangchainLLMWrapper`, as metricas sao calculadas individualmente, o NaN
e isolado por campo, e o contrato `MetricSuitePort` async foi promovido e validado.

Mesmo assim, a recomendacao e **Request changes** antes de aprovar a TAREFA-017, porque
a solucao atual depende de um patch manual dentro de `.venv`. Isso invalida a
reprodutibilidade do ambiente em CI/fresh clone, exatamente o fluxo que `uv.lock` e
`uv sync --frozen` deveriam garantir.

Correcoes aceitaveis:

1. Ajustar as versoes/pins de `ragas` e `langchain-community` para uma combinacao que nao
   precise do shim.
2. Versionar um modulo/patch de compatibilidade controlado pelo projeto e garantir que seja
   aplicado automaticamente no setup/CI.
3. Adicionar um passo formal de pos-instalacao no CI e documenta-lo como parte do ambiente
   reprodutivel, embora esta opcao seja menos limpa que corrigir as dependencias.

Depois disso, reexecutar os mesmos gates e uma importacao limpa de `ragas.llms.base`.
