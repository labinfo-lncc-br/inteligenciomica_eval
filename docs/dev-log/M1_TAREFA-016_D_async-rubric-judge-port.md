# M1_TAREFA-016_D — Correção: RubricJudgePort.score async + testes de log completos

**Data**: 2026-05-28
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E2 — Adapters de Avaliação
**Skill**: python-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Resolver os dois pontos levantados pela auditoria C
(`M1_TAREFA-016_C_reauditoria-prometheus-judge-adapter.md`, resultado **FAIL**):

**Bloqueador** — `RubricJudgePort.score` era `def score` (síncrono) enquanto
`PrometheusJudgeAdapter.score` é `async def`. O `isinstance()` passava em runtime,
mas mypy rejeitava a atribuição estática:

```
Incompatible types in assignment:
    expression has type "PrometheusJudgeAdapter"
    variable has type "RubricJudgePort"
Expected: def score(...) -> RubricResult
Got:      def score(...) -> Coroutine[Any, Any, RubricResult]
```

**Importante** — Testes de logging assertavam apenas `batch_invariant`, sem cobrir
`question_id`, `score`, `nan`, `feedback_len`, `latency_ms`.

Ações executadas:

1. Promover `RubricJudgePort.score` a `async def` em `domain/ports.py` (Nota M1 item 1 / I4).
2. Atualizar todos os implementadores: `FakeRubricJudge`, `_StubRubricJudge`.
3. Atualizar todos os callers: harness e2e e testes de `TestFakeRubricJudge` / `TestNaNInjection`.
4. Adicionar `test_static_typing_assignment` sem `# type: ignore` como detector de regressão.
5. Expandir testes de logging para assertar todos os campos dos dois eventos de log.

---

## Arquivos Criados / Modificados

| Arquivo | Ação | Descrição |
|---------|------|-----------|
| `src/inteligenciomica_eval/domain/ports.py` | Modificado | `RubricJudgePort.score`: `def` → `async def`; docstring atualizado com justificativa Nota M1 I4 |
| `tests/fakes/metrics.py` | Modificado | `FakeRubricJudge.score`: `def` → `async def` |
| `tests/unit/domain/test_ports_contract.py` | Modificado | `_StubRubricJudge.score`: `def` → `async def` |
| `tests/unit/fakes/test_fakes_satisfy_ports.py` | Modificado | `TestFakeRubricJudge` (3 testes) + `TestNaNInjection.test_rubric_judge_nan_score` → `async def` + `await` |
| `tests/e2e/_harness.py` | Modificado | `rubric.score(sample)` → `await rubric.score(sample)` (×2, linhas 247 e 251) |
| `tests/unit/infrastructure/adapters/test_prometheus_judge.py` | Modificado | `test_static_typing_assignment` sem `# type: ignore`; `TestBatchInvariant` substituído por `test_success_log_fields` e `test_nan_log_fields` com cobertura de todos os campos |
| `CLAUDE.md` | Modificado | Seção `EvaluationSample` e `PrometheusJudgeAdapter` atualizada; `RubricJudgePort` marcado como async |

---

## Decisões Técnicas

### `async def` no port, não wrapper síncrono

A alternativa seria manter o port síncrono e usar `asyncio.run()` ou
`asyncio.get_event_loop().run_until_complete()` no adapter. Isso seria incorreto:
o adapter é chamado dentro de contextos já assíncronos (use cases em M2);
`asyncio.run()` dentro de um loop ativo levanta `RuntimeError`. A Nota M1 item 1 /
correção I4 do arquivo corrigido é explícita: "M1 promove `async def` como delta
de contrato explícito."

### `FakeRubricJudge.score` como `async def` sem `await` interno

O fake não faz I/O — a coroutine retorna o valor imediatamente. `async def` sem
`await` é válido em Python e cria uma coroutine que resolve instantaneamente.
Nenhum overhead perceptível em testes.

### `test_static_typing_assignment` como detector de regressão de contrato

```python
judge: RubricJudgePort = _make_adapter()
```

Sem `# type: ignore`. mypy verifica compatibilidade estrutural (Protocol) e aceita
a atribuição pois ambos os `score` são agora `async def score(...) -> RubricResult`.
Se alguém regredir o port para `def score`, mypy rejeitará essa linha — o teste
funciona como alarme de regressão de contrato.

### Campos de log cobertos por testes

| Evento | Campos assertados |
|--------|------------------|
| `prometheus_judge_completed` | `question_id`, `score ≈ 0.9`, `nan is False`, `feedback_len > 0`, `latency_ms >= 0`, `batch_invariant is True` |
| `prometheus_judge_nan` | `question_id`, `nan_reason == "parse_failure_exhausted"`, `raw_content: str`, `latency_ms >= 0`, `batch_invariant is True` |

---

## Problemas Encontrados e Soluções

### `TestNaNInjection.test_rubric_judge_nan_score` — chamada síncrona não descoberta

**Problema**: além dos 3 testes em `TestFakeRubricJudge` (corrigidos na edição
inicial), havia um quarto teste em `TestNaNInjection` (linha 571) chamando
`.score()` de forma síncrona. O mapeamento inicial com
`grep "FakeRubricJudge.*score"` não o capturou porque o padrão de texto na linha
era diferente (`FakeRubricJudge(inject_nan=True).score(_SAMPLE)`).

**Solução**: detectado pela falha da suite na primeira execução.
`def test_rubric_judge_nan_score` → `async def` + `await`.

### Import `math as _math` não utilizado

**Problema**: importação inline `import math as _math` em `test_success_log_fields`
ficou sem uso após refatoração do teste.

**Solução**: auto-corrigido por `uv run ruff check --fix`.

---

## Validação (DoD)

| Gate | Resultado | Detalhe |
|------|-----------|---------|
| `ruff check .` | ✅ PASS | 0 erros |
| `ruff format --check .` | ✅ PASS | 74 arquivos |
| `mypy --strict src/` | ✅ PASS | 26 arquivos, zero issues |
| `lint-imports` | ✅ PASS | 4 contratos mantidos |
| `pytest --cov --cov-fail-under=85 -n auto` | ✅ PASS | **621 passed, 7 skipped — 96.66%** |
| `prometheus_judge.py` cobertura | ✅ PASS | **100%** |
| `judge: RubricJudgePort = PrometheusJudgeAdapter(...)` | ✅ mypy aceita sem `# type: ignore` |

---

## Critérios de Aceitação

Checklist completo do Prompt B de TAREFA-016 após esta correção:

| # | Critério | Status | Evidência |
|---|----------|--------|-----------|
| 1 | Assinatura `score(self, sample) -> RubricResult`; `.score()` não `.judge()`; port async | ✅ | `domain/ports.py:343`; `prometheus_judge.py:97`; `test_static_typing_assignment` sem ignore |
| 2 | `temperature=0.0` e `seed=42` constantes no body da chamada | ✅ | `prometheus_judge.py:30-32`; verificados em `test_temperature_zero_in_request` e `test_seed_constant_in_extra_body` |
| 3 | `batch_invariant=True` constante, não configurável, ADR-003 documentado | ✅ | Docstring `prometheus_judge.py:46-48`; literal `True` nos logs; `test_batch_invariant_true_is_constant` |
| 4 | NaN-or-retry: 3 tentativas tenacity antes de NaN; JSON mal-formado não levanta exceção | ✅ | `AsyncRetrying` em `prometheus_judge.py:121`; `test_three_attempts_made_on_malformed_response`; `test_nan_returned_after_three_malformed_responses` |
| 5 | `JudgeUnavailableError` apenas em falha de servidor, não em parse failure | ✅ | Captura de `APIConnectionError`/`APITimeoutError` em `prometheus_judge.py:136`; `test_connection_error_not_retried` |
| 6 | Score validado em `[0.0, 1.0]`; fora do intervalo é parse failure | ✅ | `prometheus_judge.py:201`; `test_nan_on_score_out_of_range` |
| 7 | `PromptRegistry` injetado no construtor, não instanciado internamente | ✅ | Parâmetro `registry: PromptRegistry` em `prometheus_judge.py:68` |
| 8 | Logging com todos os campos obrigatórios; body da chamada verificado | ✅ | `test_success_log_fields` e `test_nan_log_fields` com todos os campos; body via `call_args.kwargs` |
| 9 | `mypy --strict`; cobertura ≥ 80%; happy + NaN cobertos | ✅ | Gates acima; 100% em `prometheus_judge.py` |

---

## Observações para Próximas Tarefas

- **TAREFA-017 (RAGASLayer1Adapter)**: `MetricSuitePort.score` está atualmente síncrono
  (`def score`). Como `RAGASLayer1Adapter` realizará chamadas ao vllm-judge (I/O assíncrono),
  o mesmo bloqueador de typing se aplicará. Recomenda-se promover `MetricSuitePort.score` a
  `async def` como PR retroativo antes de iniciar TAREFA-017, seguindo o mesmo padrão desta
  correção.
- **Waiver aceito e mantido**: testes usam `AsyncMock` em vez de `respx`, conforme
  decisão registrada em `CLAUDE.md §11` (TAREFA-014-G). O Prompt B menciona `respx` para
  verificar o body da request, mas `call_args.kwargs` satisfaz o mesmo critério.
