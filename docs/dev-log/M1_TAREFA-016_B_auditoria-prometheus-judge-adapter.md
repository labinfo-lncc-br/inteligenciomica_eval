# M1_TAREFA-016_B - Auditoria do PrometheusJudgeAdapter

**Data**: 2026-05-28  
**Milestone**: M1 - Adapters de Infraestrutura  
**Prompt**: B - Verificacao / auditoria  
**Papel**: code-reviewer, test-engineer, ml-engineer  
**Resultado**: **FAIL**

---

## Escopo

Auditar a implementacao da TAREFA-016 contra:

- `docs/prompts_m1_tarefas_013_021_corrigido.md`, TAREFA-016, Prompt B.
- `docs/arquitetura_detalhada_validacao_inteligenciomica.md`, secao 5.1 e regime do juiz.
- `docs/visao_alto_nivel_validacao_inteligenciomica.md`, secao 9.
- Nota de operacionalizacao M1, especialmente itens 1, 3, 4 e 11.
- Dev-log da parte A: `docs/dev-log/M1_TAREFA-016_A_prometheus-judge-adapter.md`.

A auditoria nao reescreveu a implementacao.

---

## Passos Executados

1. Li as skills aplicaveis:
   - `code-reviewer`
   - `test-engineer`
   - `ml-engineer`
2. Li o Prompt A/B da TAREFA-016 em `docs/prompts_m1_tarefas_013_021_corrigido.md`.
3. Li os documentos de arquitetura/visao nas secoes relevantes:
   - `RubricJudgePort.score(self, sample: EvaluationSample) -> RubricResult`
   - Prometheus-2 como juiz deterministico
   - `VLLM_BATCH_INVARIANT=1`
   - Nota M1 item 11 (`EvaluationSample.question_id`)
4. Inspecionei:
   - `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py`
   - `tests/unit/infrastructure/adapters/test_prometheus_judge.py`
   - `src/inteligenciomica_eval/domain/ports.py`
   - fixtures em `tests/fixtures/prometheus_judge_response_*.json`
   - `CLAUDE.md` para a decisao vigente de `AsyncMock` no SDK OpenAI.
5. Executei os gates locais com `UV_CACHE_DIR=/tmp/uv-cache`, porque o primeiro `uv run`
   tentou escrever cache em `/prj/prjatrv/lgonzaga/.cache/uv` e falhou por sandbox
   read-only.

---

## Comandos e Resultados

| Comando | Resultado |
|---|---|
| `uv run ruff check .` | Falhou por sandbox: `Could not acquire lock ... Read-only file system ... /prj/prjatrv/lgonzaga/.cache/uv` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` | PASS - `All checks passed!` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .` | PASS - `74 files already formatted` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src/` | PASS - `Success: no issues found in 26 source files` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` | PASS - 4 contracts kept, 0 broken |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -v tests/unit/infrastructure/adapters/test_prometheus_judge.py` | PASS - 21 passed |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest --cov --cov-fail-under=85` | PASS - 620 passed, 7 skipped, cobertura total 96.66%, `prometheus_judge.py` 100% |

---

## Achados

### Bloqueadores

| Criterio | Evidencia | Gravidade |
|---|---|---|
| Logging deve ter campos corretos, incluindo `sample.question_id` conforme Prompt A e Nota M1 item 11 | `prometheus_judge_completed` loga `score`, `nan`, `feedback_len`, `latency_ms`, `batch_invariant`, mas nao loga `question_id`: `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py:160-167`. O evento NaN tambem nao loga `question_id`: `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py:147-154`. O DTO atual nem possui `question_id`: `src/inteligenciomica_eval/domain/ports.py:72-86`, apesar da Nota M1 item 11 exigir essa extensao antes da TAREFA-016. | Bloqueador |

### Importantes

| Criterio | Evidencia | Gravidade |
|---|---|---|
| Assinatura do adapter deve satisfazer `RubricJudgePort.score(self, sample: EvaluationSample) -> RubricResult` | O `RubricJudgePort` continua sincronico em `src/inteligenciomica_eval/domain/ports.py:341-357`, enquanto o adapter implementa `async def score(...) -> RubricResult` em `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py:97`. Em typing, isso e `Callable[..., Coroutine[..., RubricResult]]`, nao `Callable[..., RubricResult]`. O teste `isinstance(adapter, RubricJudgePort)` em `tests/unit/infrastructure/adapters/test_prometheus_judge.py:97-101` nao prova compatibilidade estatica, pois `@runtime_checkable` so verifica presenca do atributo. | Importante |
| Testes de logging nao verificam todos os campos requeridos | Os testes validam somente `batch_invariant` nos logs de sucesso/NaN: `tests/unit/infrastructure/adapters/test_prometheus_judge.py:319-348`. Nao ha assert para `question_id`, `score`, `nan`, `feedback_len` ou `latency_ms`. Isso permitiu a regressao de observabilidade acima passar com 100% de cobertura do adapter. | Importante |

### Waiver Aceito

| Criterio | Evidencia | Gravidade |
|---|---|---|
| Prompt B menciona `respx` para verificar body da request | Os testes usam `AsyncMock` no nivel `adapter._client.chat.completions.create`, nao `respx`: `tests/unit/infrastructure/adapters/test_prometheus_judge.py:1-9`, `69-89`. Isso diverge do Prompt B literal, mas segue a decisao vigente em `CLAUDE.md:271-313` e a auditoria anterior `M1_TAREFA-014_H`, que aceitou o waiver porque `respx`/`httpx.MockTransport` travavam ou nao interceptavam o SDK OpenAI neste ambiente. Os parametros criticos sao verificados via `call_args.kwargs`: temperatura em `tests/unit/infrastructure/adapters/test_prometheus_judge.py:163-173`, seed em `:175-184`, model em `:186-195`. | Waiver, nao bloqueia |

### Sugestoes

| Criterio | Evidencia | Gravidade |
|---|---|---|
| Fixtures entregues devem ser exercitadas por pelo menos um teste | As fixtures existem em `tests/fixtures/prometheus_judge_response_valid.json` e `tests/fixtures/prometheus_judge_response_malformed.json`, mas os testes usam JSON inline em `tests/unit/infrastructure/adapters/test_prometheus_judge.py:116-126` e `:203-221`. Isso nao quebra a implementacao, mas deixa as fixtures sem protecao contra drift. | Sugestao |

---

## Checklist Prompt B

| # | Criterio | Status | Evidencia |
|---|---|---|---|
| 1 | Assinatura `.score(self, sample: EvaluationSample) -> RubricResult`; nao `.judge()` | FAIL parcial | Nome e parametros existem em `prometheus_judge.py:97`; porem o adapter e `async def` enquanto o `RubricJudgePort` atual e `def` em `domain/ports.py:347`. Isso quebra compatibilidade estatica quando o adapter for usado como `RubricJudgePort`. |
| 2 | `temperature=0.0` e `seed` constante no body | PASS | Constantes em `prometheus_judge.py:30-32`; chamada OpenAI em `:130-135`; testes em `test_prometheus_judge.py:163-184`. |
| 3 | `batch_invariant=True` constante e nao parametrizavel, com justificativa ADR-003 | PASS | Justificativa no docstring `prometheus_judge.py:46-48`; sem parametro de construtor; logs usam literal `True` em `:153` e `:166`; teste em `test_prometheus_judge.py:311-348`. |
| 4 | NaN-or-retry: 3 tentativas com tenacity antes de retornar NaN; parse failure nao levanta excecao | PASS | `AsyncRetrying(stop=..., retry_if_exception_type(_ParseFailureError), reraise=True)` em `prometheus_judge.py:121-127`; retorno `RubricResult(score=float("nan"), feedback="parse_failure")` em `:145-155`; testes em `test_prometheus_judge.py:203-221`. |
| 5 | `JudgeUnavailableError` apenas em falha de servidor, nao em parse failure | PASS | `APIConnectionError` e `APITimeoutError` convertidos em `JudgeUnavailableError` em `prometheus_judge.py:136-140`; parse failure vira `_ParseFailureError` e depois NaN em `:188-205` e `:145-155`; testes em `test_prometheus_judge.py:267-304`. |
| 6 | Score validado em `[0.0, 1.0]`; fora do intervalo tratado como parse failure | PASS | Validacao em `prometheus_judge.py:199-205`; teste em `test_prometheus_judge.py:223-232`. |
| 7 | `PromptRegistry` injetado no construtor, nao instanciado internamente | PASS | Construtor recebe `registry: PromptRegistry` em `prometheus_judge.py:68-78`; uso em `:111-116`. |
| 8 | Logging com `batch_invariant=True` e campos corretos; body da chamada verificado | FAIL | `batch_invariant=True` esta presente nos logs, mas `question_id` esta ausente em `prometheus_judge.py:147-167`, e `EvaluationSample` nao possui o campo em `domain/ports.py:72-86`. Body e verificado por AsyncMock com waiver aceito, nao por `respx`. |
| 9 | `mypy --strict`; cobertura >= 80%; happy + NaN cobertos | PASS | `mypy --strict src/` passou; suite completa passou com 96.66% total e 100% em `prometheus_judge.py`; testes cobrem happy path e NaN em `test_prometheus_judge.py:115-126` e `:203-221`. |

---

## Recomendacao

**Request changes.**

Antes de considerar a TAREFA-016 aprovada, recomendo um Prompt C com escopo pequeno:

1. Estender `EvaluationSample` com `question_id: str` conforme Nota M1 item 11, ajustando fakes/testes impactados.
2. Incluir `question_id=sample.question_id` nos eventos `prometheus_judge_completed` e `prometheus_judge_nan`.
3. Atualizar testes de logging para validar `question_id`, `score`, `nan`, `feedback_len`, `latency_ms` e `batch_invariant`.
4. Resolver explicitamente a divergencia `RubricJudgePort.score` sync vs adapter async: promover o port para `async def score(...) -> RubricResult` agora, ou documentar um waiver formal equivalente ao feito para `GeneratorPort`/`RetrieverPort`.

Os itens 4 e 5 do Prompt B, marcados como bloqueadores diretos se errados, estao corretos nesta implementacao.
