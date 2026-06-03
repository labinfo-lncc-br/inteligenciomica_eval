# M6_TAREFA-602_B — Correções Pós-Auditoria Codex (Cohen's κ)

**Data**: 2026-06-03
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: ml-engineer
**Prioridade / Tamanho**: P0 / S

## Objetivo

Corrigir os três achados da auditoria Codex (Prompt B) sobre a TAREFA-602.

## Achados e Correções

### Bloqueador — `judge_model` incorreto

**Problema:** `JudgeValidationUseCase` montava `judge_model` a partir de
`r.answer.llm.value`, que é o **modelo avaliado** (ex.: `llama3-8b`), não o modelo
juiz (ex.: `prometheus-2-8x7b-rc`). Isso contradiz o contrato de
`JudgeValidationResult.judge_model` ("lido do Parquet — modelo do juiz").

**Causa raiz:** `EvaluationResult` não carrega proveniência do juiz via
`ResultReaderPort`. O campo `judge_model` existe no Parquet (`EVAL_SCHEMA` linha 50
de `parquet_storage.py`), mas não é exposto via `ResultFrame`.

**Solução:** Adicionado `judge_model: str = "unknown"` a `JudgeValidationConfig`.
O chamador (CLI) injeta o valor a partir de `cfg.judge.endpoint_env` do round config.
O use case usa `self._config.judge_model` diretamente — sem derivar do modelo avaliado.
Alternativa descartada: estender `ResultReaderPort` quebraria todas as implementações
existentes (Protocol `@runtime_checkable` verifica presença de método).

### Importante — sklearn fora de `infrastructure/stats/`

**Problema:** `_FakeKappa` em `tests/unit/application/test_judge_validation.py` fazia
`from sklearn.metrics import cohen_kappa_score` dentro do método `compute`. Embora o
import-linter não cubra `tests/`, viola o espírito da Nota M6 item 5 (sklearn restrito
a `infrastructure/stats/`).

**Solução:** `_FakeKappa` reescrita com implementação matemática pura:
```python
po = sum(a == b for a, b in zip(y_true, y_pred, strict=True)) / n
pe = p_true_pos * p_pred_pos + (1 - p_true_pos) * (1 - p_pred_pos)
kappa = (po - pe) / (1.0 - pe)
```
Sem nenhum import de sklearn nos testes de application/. A implementação real com
sklearn permanece exclusivamente em `infrastructure/stats/cohen_kappa_adapter.py`.

### Importante — WARNING de `batch_invariant` não verificado no teste

**Problema:** O teste `test_confirmed_false_when_any_generator` verificava apenas o
valor de retorno (`batch_invariant_confirmed is False`), mas não que o WARNING estruturado
`"judge_validation_non_deterministic"` foi realmente emitido pelo logger.

**Problema secundário:** structlog não usa o pipeline `logging` padrão do Python —
`caplog.records` fica vazio. Usar `caplog.at_level` não captura eventos structlog.

**Solução:** Novo teste `test_warning_logged_when_non_deterministic` que mocka
`inteligenciomica_eval.application.judge_validation._log.warning` via pytest-mock e
verifica que o evento `"judge_validation_non_deterministic"` está entre os args da
chamada.

**Adicional:** Adicionado `test_judge_model_from_config_not_from_evaluated_llm` que
verifica que `result.judge_model == "prometheus-2-8x7b-rc"` e que `"llama3-8b"` (llm
avaliado — default do factory) **não** aparece no campo.

## Arquivos Modificados

| Arquivo | Mudança |
|---|---|
| `src/inteligenciomica_eval/application/judge_validation.py` | `JudgeValidationConfig.judge_model: str = "unknown"`; use case usa `self._config.judge_model` |
| `src/inteligenciomica_eval/cli.py` | `validate-judge` passa `cfg.judge.endpoint_env` como `judge_model` |
| `tests/unit/application/test_judge_validation.py` | `_FakeKappa` sem sklearn; `_make_uc` aceita `judge_model`; 2 testes novos |

## Validação (DoD)

```
ruff check .                          → All checks passed!
ruff format --check .                 → 147 files already formatted
mypy --strict src/                    → Success: no issues found in 54 source files
lint-imports                          → 4 contracts KEPT, 0 broken
pytest -m "not integration" -n 4      → 1116 passed, 6 skipped — 90.43% coverage
```

## Critérios de Aceitação (pós-ciclo)

- [x] `judge_model` vem de `JudgeValidationConfig`, não de `r.answer.llm.value`
- [x] sklearn ausente de todos os testes fora de `infrastructure/stats/`
- [x] WARNING `judge_validation_non_deterministic` verificado por mock de `_log.warning`
- [x] Teste `test_judge_model_from_config_not_from_evaluated_llm` confirma semântica correta
- [x] Todos os gates verdes — 1116 passed, 90.43%

## Observações para Próximas Tarefas

- Se futuramente o `ResultReaderPort` for estendido com acesso a proveniência (campo
  `judge_model` do Parquet), o `JudgeValidationConfig.judge_model` pode ser descontinuado
  em favor de leitura direta do store.
- A solução atual (judge_model via config) é semanticamente correta: o nome do juiz é
  um dado de configuração da rodada, não de cada linha avaliada.
