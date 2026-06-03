# M6_TAREFA-602_C_reauditoria-pos-correcoes

Data: 2026-06-03
Commit auditado: `bc47ae1`
Prompt-base: `docs/m6_tarefas_602.md`
Resultado: **FAIL**

## Resumo

As correções de teste foram aplicadas corretamente: o import de `sklearn` saiu de `tests/unit/application/test_judge_validation.py`, e agora existe teste explícito verificando o `WARNING` de não determinismo. Os gates que reexecutei ficaram verdes: `validate-judge --help`, `44` testes do escopo 602, `mypy --strict src` e `import-linter`.

O bloqueador remanescente é que a correção de `judge_model` continua semanticamente incorreta: a CLI injeta `cfg.judge.endpoint_env`, que é o **nome da variável de ambiente do endpoint** (`VLLM_JUDGE_URL`), não o identificador do modelo juiz. O YAML da rodada já tem o campo correto em `cfg.judge.model`.

## Divergências

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| `judge_model` continua vindo da fonte errada. A correção trocou `r.answer.llm.value` por `cfg.judge.endpoint_env`, mas `endpoint_env` é o nome da env var do endpoint, não o modelo juiz. O schema define `judge.model` como identificador do modelo e `judge.endpoint_env` como referência de ambiente. Assim, o relatório pode exibir `VLLM_JUDGE_URL` em vez do juiz real. | [cli.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/cli.py:1172), [schema.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/config/schema.py:36), [experiment_round1.yaml](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/config/experiment_round1.yaml:43) | **BLOQUEADOR** |
| A docstring de `JudgeValidationResult` ainda afirma “modelo do juiz lido do Parquet”, mas a implementação passou a depender de config injetada. O contrato documentado segue inconsistente com o comportamento atual. | [judge_validation.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/application/judge_validation.py:53), [judge_validation.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/application/judge_validation.py:127) | **IMPORTANTE** |

## Correções confirmadas

- `_FakeKappa` foi reescrita sem `sklearn` em [test_judge_validation.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/application/test_judge_validation.py:18).
- O teste `test_warning_logged_when_non_deterministic` agora verifica o evento `judge_validation_non_deterministic` em [test_judge_validation.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/application/test_judge_validation.py:226).
- O relatório gerado continua presente e reporta **κ = 0.6842 (`substancial`)** em [docs/judge_validation_report.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/judge_validation_report.md:39).

## Validação executada

- `uv run --directory ... python -m inteligenciomica_eval.cli validate-judge --help` → OK
- `uv run --directory ... pytest tests/unit/application/test_judge_validation.py tests/unit/infrastructure/adapters/test_judge_validation_report.py tests/unit/infrastructure/stats/test_cohen_kappa_adapter.py -q` → `44 passed`
- `uv run --directory ... mypy --strict src` com `MYPY_CACHE_DIR=/tmp/mypy-cache` → `Success: no issues found in 54 source files`
- `uv run lint-imports` → `Contracts: 4 kept, 0 broken`

## Recomendação

**Request changes**.

Correção mínima esperada:
1. Em [cli.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/cli.py:1172), usar `cfg.judge.model` para `judge_model`, não `cfg.judge.endpoint_env`.
2. Alinhar a docstring/contrato de `JudgeValidationResult` ao comportamento real adotado.
