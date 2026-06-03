# M6_TAREFA-602_C — Correção da Fonte de judge_model (Reauditoria Codex)

**Data**: 2026-06-03
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: ml-engineer
**Prioridade / Tamanho**: P0 / XS

## Objetivo

Corrigir o bloqueador remanescente apontado na reauditoria Codex (ciclo C):
`validate-judge` estava injetando `cfg.judge.endpoint_env` como `judge_model`
em vez de `cfg.judge.model`.

## Achado e Correção

### Bloqueador — `cfg.judge.endpoint_env` ≠ identificador do modelo

**Problema:** Na CLI (`cli.py:1175-1180`), o código corrigido no ciclo B passou a usar
`judge_model_name.endpoint_env`, que é o **nome da variável de ambiente** do endpoint
(ex.: `"VLLM_JUDGE_URL"`), não o identificador do modelo juiz.

O schema em `infrastructure/config/schema.py` define claramente:
- `JudgeConfig.model: str` → identificador do modelo (ex.: `"prometheus-8x7b-v2.0"`)
- `JudgeConfig.endpoint_env: str` → nome da env var do endpoint (ex.: `"VLLM_JUDGE_URL"`)

O YAML de exemplo (`config/experiment_round1.yaml`) confirma:
```yaml
judge:
  model: "prometheus-8x7b-v2.0"
  endpoint_env: "VLLM_JUDGE_URL"
```

**Solução:** Substituída a referência `judge_model_name.endpoint_env` por
`judge_cfg.model`. Uma linha alterada em `cli.py`:

```python
# Antes (incorreto):
judge_model_str = str(judge_model_name.endpoint_env) if judge_model_name is not None else "unknown"

# Depois (correto):
judge_cfg = getattr(cfg, "judge", None)
judge_model_str = str(judge_cfg.model) if judge_cfg is not None else "unknown"
```

## Arquivos Modificados

| Arquivo | Mudança |
|---|---|
| `src/inteligenciomica_eval/cli.py` | `validate-judge`: `.endpoint_env` → `.model` em `JudgeValidationConfig(judge_model=...)` |

## Validação (DoD)

```
ruff check .                          → All checks passed!
ruff format --check .                 → 147 files already formatted
mypy --strict src/                    → Success: no issues found in 54 source files
lint-imports                          → 4 contracts KEPT, 0 broken
pytest -m "not integration" -n 4      → 1116 passed, 6 skipped — 90.43% coverage
```

Testes específicos da TAREFA-602 (44 testes, todos PASSED):
```
pytest tests/unit/application/test_judge_validation.py \
       tests/unit/infrastructure/adapters/test_judge_validation_report.py \
       tests/unit/infrastructure/stats/test_cohen_kappa_adapter.py -v
44 passed in 0.81s
```

## Critérios de Aceitação (ciclo C)

- [x] `validate-judge` usa `cfg.judge.model` como `judge_model` (identificador do modelo)
- [x] `cfg.judge.endpoint_env` não aparece no campo `judge_model` do resultado
- [x] Todos os gates verdes — 1116 passed, 90.43%

## Observações

Esta correção resolve o único bloqueador remanescente após os ciclos A e B.
Os três achados da auditoria original (judge_model source, sklearn em test,
WARNING não verificado) estão agora todos resolvidos.
