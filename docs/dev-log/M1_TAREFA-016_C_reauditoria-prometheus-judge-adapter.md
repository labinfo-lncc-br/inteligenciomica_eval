# M1_TAREFA-016_C - Reauditoria do PrometheusJudgeAdapter

**Data**: 2026-05-28  
**Milestone**: M1 - Adapters de Infraestrutura  
**Prompt**: C - Reauditoria apos correcao de `EvaluationSample.question_id`  
**Papel**: code-reviewer, test-engineer, ml-engineer  
**Resultado**: **FAIL**

---

## Escopo

Repetir integralmente a auditoria da TAREFA-016 apos a correcao reportada em
`docs/dev-log/M1_TAREFA-016_B_question-id-evaluation-sample.md`.

Referencias usadas:

- `docs/prompts_m1_tarefas_013_021_corrigido.md`, TAREFA-016, Prompt A/B.
- `docs/arquitetura_detalhada_validacao_inteligenciomica.md`, secao 5.1 e regime do juiz.
- `docs/visao_alto_nivel_validacao_inteligenciomica.md`, secao 9.
- Nota M1 itens 1, 3, 4 e 11.
- `CLAUDE.md`, decisao TAREFA-014-G sobre `AsyncMock` no SDK OpenAI.

A auditoria nao reescreveu a implementacao.

---

## Passos Executados

1. Reli as skills aplicaveis: `code-reviewer`, `test-engineer`, `ml-engineer`.
2. Reli o Prompt A/B da TAREFA-016 no arquivo corrigido de prompts.
3. Reli o dev-log de correcao `M1_TAREFA-016_B_question-id-evaluation-sample.md`.
4. Inspecionei os arquivos alterados:
   - `src/inteligenciomica_eval/domain/ports.py`
   - `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py`
   - `tests/unit/infrastructure/adapters/test_prometheus_judge.py`
   - `tests/unit/domain/test_ports_contract.py`
   - `tests/unit/fakes/test_fakes_satisfy_ports.py`
   - `tests/e2e/_harness.py`
   - `CLAUDE.md`
5. Executei os gates estaticos, unitarios e a suite completa.
6. Executei uma checagem estatica adicional com `mypy -c` atribuindo
   `PrometheusJudgeAdapter` a uma variavel tipada como `RubricJudgePort`.

---

## Comandos e Resultados

Todos os comandos com `uv` foram executados com `UV_CACHE_DIR=/tmp/uv-cache`.

| Comando | Resultado |
|---|---|
| `uv run ruff check .` | PASS - `All checks passed!` |
| `uv run ruff format --check .` | PASS - `74 files already formatted` |
| `uv run mypy --strict src/` | PASS - `Success: no issues found in 26 source files` |
| `uv run lint-imports` | PASS - 4 contracts kept, 0 broken |
| `uv run pytest -v tests/unit/infrastructure/adapters/test_prometheus_judge.py` | PASS - 21 passed |
| `uv run pytest --cov --cov-fail-under=85` | PASS - 620 passed, 7 skipped, cobertura total 96.66%, `prometheus_judge.py` 100% |
| `mypy --strict --config-file=/dev/null -c '<RubricJudgePort assignment probe>'` | FAIL esperado - incompatibilidade entre `PrometheusJudgeAdapter.score` async e `RubricJudgePort.score` sync |

Saida relevante da prova estatica adicional:

```text
Incompatible types in assignment (expression has type "PrometheusJudgeAdapter", variable has type "RubricJudgePort")
Expected:
    def score(self, sample: EvaluationSample) -> RubricResult
Got:
    def score(self, sample: EvaluationSample) -> Coroutine[Any, Any, RubricResult]
```

---

## Achados

### Bloqueadores

| Criterio | Evidencia | Gravidade |
|---|---|---|
| `PrometheusJudgeAdapter` deve implementar `RubricJudgePort.score(self, sample: EvaluationSample) -> RubricResult` conforme Prompt B item 1 e arquitetura secao 5.1 | O port segue sincronico em `src/inteligenciomica_eval/domain/ports.py:343-360`, com `def score(...) -> RubricResult`. O adapter implementa `async def score(...) -> RubricResult` em `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py:97`, o que para typing equivale a retorno `Coroutine[Any, Any, RubricResult]`. A prova `mypy -c` com `judge: RubricJudgePort = PrometheusJudgeAdapter(...)` falha. | Bloqueador |

### Importantes

| Criterio | Evidencia | Gravidade |
|---|---|---|
| Testes de logging ainda nao validam todos os campos requeridos | O codigo agora inclui `question_id` nos eventos em `prometheus_judge.py:147-169`, mas os testes de log continuam assertando apenas `batch_invariant`: `tests/unit/infrastructure/adapters/test_prometheus_judge.py:320-349`. Isso nao invalida a implementacao atual, mas deixa sem teste direto os campos `question_id`, `score`, `nan`, `feedback_len` e `latency_ms`. | Importante |

### Waiver Aceito

| Criterio | Evidencia | Gravidade |
|---|---|---|
| Prompt B menciona verificacao com `respx`, mas os testes usam `AsyncMock` no SDK | A divergencia segue a decisao vigente em `CLAUDE.md:271-313`. Os parametros criticos sao verificados por `call_args.kwargs`: temperatura em `tests/unit/infrastructure/adapters/test_prometheus_judge.py:164-174`, seed em `:176-185`, model em `:187-196`. | Waiver, nao bloqueia |

### Confirmado como Corrigido

| Criterio | Evidencia | Gravidade |
|---|---|---|
| `EvaluationSample.question_id` obrigatorio conforme Nota M1 item 11 | Campo adicionado como primeiro atributo em `src/inteligenciomica_eval/domain/ports.py:72-89`; construtores atualizados em `tests/unit/infrastructure/adapters/test_prometheus_judge.py:43-49`, `tests/unit/fakes/test_fakes_satisfy_ports.py:59-65`, `tests/unit/domain/test_ports_contract.py:309-318` e `tests/e2e/_harness.py:229-235`. | PASS |
| Logs do `PrometheusJudgeAdapter` incluem `question_id` | Evento NaN inclui `question_id=sample.question_id` em `prometheus_judge.py:147-155`; evento de sucesso inclui `question_id=sample.question_id` em `prometheus_judge.py:161-169`. | PASS |

---

## Checklist Prompt B

| # | Criterio | Status | Evidencia |
|---|---|---|---|
| 1 | Assinatura `score(self, sample: EvaluationSample) -> RubricResult`; metodo `.score()`, nao `.judge()` | FAIL | Nome e parametro estao corretos em `prometheus_judge.py:97`, mas o metodo e `async def`. O `RubricJudgePort` atual e sync em `domain/ports.py:350`. A prova estatica de atribuicao ao port falha com mypy. |
| 2 | `temperature=0.0` e `seed` constante no body | PASS | Constantes em `prometheus_judge.py:30-32`; chamada em `:130-135`; testes em `test_prometheus_judge.py:164-185`. |
| 3 | `batch_invariant=True` constante, nunca parametrizavel, com justificativa ADR-003 | PASS | Justificativa no docstring `prometheus_judge.py:46-48`; sem parametro de construtor; logs usam literal `True` em `:154` e `:168`. |
| 4 | NaN-or-retry: 3 tentativas com tenacity antes de retornar NaN; JSON mal-formado nao levanta excecao | PASS | `AsyncRetrying` em `prometheus_judge.py:121-127`; retorno `RubricResult(score=float("nan"), feedback="parse_failure")` em `:145-156`; testes em `test_prometheus_judge.py:204-222`. |
| 5 | `JudgeUnavailableError` apenas em falha de servidor, nao em parse failure | PASS | `APIConnectionError`/`APITimeoutError` convertidos em `JudgeUnavailableError` em `prometheus_judge.py:136-140`; parse failure vira NaN em `:193-207` e `:145-156`; testes em `test_prometheus_judge.py:268-304`. |
| 6 | Score validado em `[0.0, 1.0]`; fora do intervalo tratado como parse failure | PASS | Validacao em `prometheus_judge.py:201-207`; teste em `test_prometheus_judge.py:224-233`. |
| 7 | `PromptRegistry` injetado no construtor, nao instanciado internamente | PASS | Construtor recebe `registry: PromptRegistry` em `prometheus_judge.py:68-78`; uso em `:111-116`. |
| 8 | Logging com `batch_invariant=True` e campos corretos; body da chamada verificado | PASS com waiver | Codigo loga `question_id`, `score`, `nan`, `feedback_len`, `latency_ms`, `batch_invariant` no sucesso em `prometheus_judge.py:161-169`; NaN loga `question_id`, `nan_reason`, `raw_content`, `model`, `latency_ms`, `batch_invariant` em `:147-155`. Body verificado por `AsyncMock`, nao por `respx`, conforme waiver. |
| 9 | `mypy --strict`; cobertura >= 80%; happy + NaN cobertos | PASS | `mypy --strict src/` passou; suite completa passou com 96.66% total e 100% em `prometheus_judge.py`; happy path e NaN em `test_prometheus_judge.py:116-127` e `:204-222`. |

---

## Recomendacao

**Request changes.**

A correcao de `question_id` resolveu o bloqueador da auditoria anterior, mas a TAREFA-016
ainda nao esta conforme o Prompt B por causa do contrato `RubricJudgePort`.

Proximo ajuste recomendado:

1. Tornar `RubricJudgePort.score` async (`async def score(...) -> RubricResult`) e
   atualizar fakes/harness/chamadores correspondentes, ou formalizar um waiver de contrato
   que aceite `PrometheusJudgeAdapter` fora do `RubricJudgePort` estatico.
2. Fortalecer os testes de logging para assertar `question_id`, `score`, `nan`,
   `feedback_len`, `latency_ms` e `batch_invariant`.

Os pontos especialmente criticos do Prompt B, itens 4 e 5, continuam corretos.
