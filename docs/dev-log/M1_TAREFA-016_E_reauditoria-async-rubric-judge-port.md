# M1_TAREFA-016_E - Reauditoria do RubricJudgePort async

**Data**: 2026-05-28  
**Milestone**: M1 - Adapters de Infraestrutura  
**Prompt**: E - Reauditoria apos correcao D  
**Papel**: code-reviewer, test-engineer, ml-engineer  
**Resultado**: **PASS**

---

## Escopo

Reauditar a TAREFA-016 apos a correcao registrada em
`docs/dev-log/M1_TAREFA-016_D_async-rubric-judge-port.md`.

Pontos principais verificados:

- `RubricJudgePort.score` promovido para `async def`.
- `PrometheusJudgeAdapter` compatível estaticamente com `RubricJudgePort`.
- Fakes, stubs e harness e2e atualizados para `await rubric.score(...)`.
- Logs do adapter cobertos por testes com todos os campos relevantes.
- Gates de lint, formatacao, typing, import-linter e testes.

Referencias:

- `docs/prompts_m1_tarefas_013_021_corrigido.md`, TAREFA-016, Prompt A/B.
- `docs/arquitetura_detalhada_validacao_inteligenciomica.md`, secao 5.1 e regime do juiz.
- Nota M1 itens 1, 3, 4 e 11.
- `CLAUDE.md`, decisao TAREFA-014-G sobre `AsyncMock` no SDK OpenAI.

---

## Passos Executados

1. Reli as skills aplicaveis: `code-reviewer`, `test-engineer`, `ml-engineer`.
2. Reli o dev-log D e os arquivos alterados.
3. Inspecionei o contrato em `src/inteligenciomica_eval/domain/ports.py`.
4. Inspecionei o adapter em `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py`.
5. Inspecionei fakes, stubs e harness e2e:
   - `tests/fakes/metrics.py`
   - `tests/unit/domain/test_ports_contract.py`
   - `tests/unit/fakes/test_fakes_satisfy_ports.py`
   - `tests/e2e/_harness.py`
6. Inspecionei os testes de logging e typing em
   `tests/unit/infrastructure/adapters/test_prometheus_judge.py`.
7. Procurei chamadas sincronas remanescentes para `FakeRubricJudge.score`.
8. Executei gates locais e prova estatica adicional com `mypy`.

---

## Comandos e Resultados

Todos os comandos com `uv` foram executados com `UV_CACHE_DIR=/tmp/uv-cache`.

| Comando | Resultado |
|---|---|
| `uv run ruff check .` | PASS - `All checks passed!` |
| `uv run ruff format --check .` | PASS - `74 files already formatted` |
| `uv run mypy --strict src/` | PASS - `Success: no issues found in 26 source files` |
| `uv run lint-imports` | PASS - 4 contracts kept, 0 broken |
| `mypy --strict --config-file=/dev/null -c '<RubricJudgePort assignment probe>'` | PASS - `judge: RubricJudgePort = PrometheusJudgeAdapter(...)` aceito |
| `mypy --strict --config-file=/dev/null tests/unit/infrastructure/adapters/test_prometheus_judge.py` | PASS - teste com atribuicao estatica tambem tipa |
| `pytest -v tests/unit/infrastructure/adapters/test_prometheus_judge.py tests/unit/fakes/test_fakes_satisfy_ports.py tests/e2e/test_min_round_stub.py` | PASS - 86 passed |
| `pytest --cov --cov-fail-under=85` | PASS - 621 passed, 7 skipped, cobertura total 96.66%, `prometheus_judge.py` 100% |

---

## Achados

### Bloqueadores

Nenhum.

### Importantes

Nenhum.

### Waiver Mantido

| Criterio | Evidencia | Gravidade |
|---|---|---|
| Prompt B menciona `respx`, mas os testes usam `AsyncMock` no SDK OpenAI | Decisao vigente em `CLAUDE.md:271-313`. O body da chamada e verificado via `call_args.kwargs` em `tests/unit/infrastructure/adapters/test_prometheus_judge.py:164-185` e `:187-196`. | Waiver aceito, nao bloqueia |

### Observacao Fora do Escopo

| Tema | Evidencia | Impacto |
|---|---|---|
| `MetricSuitePort.score` ainda e sincronico | `src/inteligenciomica_eval/domain/ports.py:324-340`; `FakeMetricSuite.score` permanece sync em `tests/fakes/metrics.py:38-65`. | Nao bloqueia TAREFA-016. Pode impactar TAREFA-017 se `RAGASLayer1Adapter` tambem for async-first. |

---

## Checklist Prompt B

| # | Criterio | Status | Evidencia |
|---|---|---|---|
| 1 | Assinatura `.score(self, sample: EvaluationSample) -> RubricResult`; metodo `.score()`, nao `.judge()` | PASS | `RubricJudgePort.score` e `async def` em `src/inteligenciomica_eval/domain/ports.py:343-362`; adapter implementa `async def score` em `prometheus_judge.py:97-171`; prova `judge: RubricJudgePort = PrometheusJudgeAdapter(...)` passa em mypy. |
| 2 | `temperature=0.0` e `seed` constante no body | PASS | Constantes em `prometheus_judge.py:30-32`; chamada em `:130-135`; testes em `test_prometheus_judge.py:164-185`. |
| 3 | `batch_invariant=True` constante, nunca parametrizavel, com justificativa ADR-003 | PASS | Justificativa no docstring `prometheus_judge.py:46-48`; literal `True` nos logs em `:154` e `:168`; teste em `test_prometheus_judge.py:322-328`. |
| 4 | NaN-or-retry: 3 tentativas com tenacity antes de retornar NaN; JSON mal-formado nao levanta excecao | PASS | `AsyncRetrying` em `prometheus_judge.py:121-127`; retorno NaN em `:145-156`; testes em `test_prometheus_judge.py:204-233`. |
| 5 | `JudgeUnavailableError` apenas em falha de servidor, nao em parse failure | PASS | Conversao de `APIConnectionError`/`APITimeoutError` em `prometheus_judge.py:136-140`; parse failure retorna NaN em `:145-156`; testes em `test_prometheus_judge.py:268-315`. |
| 6 | Score validado em `[0.0, 1.0]`; fora do intervalo tratado como parse failure | PASS | Validacao em `prometheus_judge.py:201-207`; teste em `test_prometheus_judge.py:224-233`. |
| 7 | `PromptRegistry` injetado no construtor, nao instanciado internamente | PASS | Construtor recebe `registry: PromptRegistry` em `prometheus_judge.py:68-78`; uso em `:111-116`. |
| 8 | Logging com `batch_invariant=True` e campos corretos; body da chamada verificado | PASS com waiver | Codigo loga campos no sucesso em `prometheus_judge.py:161-169` e no NaN em `:147-155`; testes assertam campos em `test_prometheus_judge.py:330-371`; body verificado por `AsyncMock`, nao `respx`, conforme waiver. |
| 9 | `mypy --strict`; cobertura >= 80%; happy + NaN cobertos | PASS | `mypy --strict src/` passou; suite completa passou com 96.66%; `prometheus_judge.py` 100%; happy path e NaN cobertos em `test_prometheus_judge.py:126-147` e `:204-233`. |

---

## Verificacoes Especificas da Correcao D

| Verificacao | Status | Evidencia |
|---|---|---|
| `RubricJudgePort.score` async | PASS | `src/inteligenciomica_eval/domain/ports.py:352` |
| `PrometheusJudgeAdapter` satisfaz `RubricJudgePort` estaticamente | PASS | Prova mypy com atribuicao `judge: RubricJudgePort = PrometheusJudgeAdapter(...)`; teste em `test_prometheus_judge.py:104-112` tambem tipa quando rodado com mypy explicitamente. |
| `FakeRubricJudge.score` async | PASS | `tests/fakes/metrics.py:86-95` |
| `_StubRubricJudge.score` async | PASS | `tests/unit/domain/test_ports_contract.py:163-165` |
| Harness e2e usa `await rubric.score(...)` | PASS | `tests/e2e/_harness.py:245-251` |
| Testes de fakes usam `await FakeRubricJudge.score(...)` | PASS | `tests/unit/fakes/test_fakes_satisfy_ports.py:261-274` e `:571-574` |
| Testes de log cobrem campos obrigatorios | PASS | `tests/unit/infrastructure/adapters/test_prometheus_judge.py:330-371` |

---

## Recomendacao

**Approve para TAREFA-016.**

O bloqueador de contrato async foi resolvido, a correcao de `question_id` permanece
valida, os testes de observabilidade foram fortalecidos e os gates locais passaram.
Para a TAREFA-017, avaliar antes do inicio se `MetricSuitePort.score` tambem deve ser
promovido para `async def`, pelo mesmo criterio de adapter I/O-bound.
