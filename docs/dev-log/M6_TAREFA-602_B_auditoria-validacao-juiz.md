# M6_TAREFA-602_B_auditoria-validacao-juiz

Data: 2026-06-03
Commit auditado: `1d8c96c`
Prompt-base: `docs/m6_tarefas_602.md`
Resultado: **FAIL**

## Resumo

O artefato gerado em [judge_validation_report.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/judge_validation_report.md:1) reporta **Cohen's κ = 0.6842 (substancial)** em [docs/judge_validation_report.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/judge_validation_report.md:39), e os checks executados localmente ficaram verdes para `validate-judge --help`, `pytest` dos 42 testes novos, `mypy --strict src` e `import-linter`.

Apesar disso, a tarefa **não passa** porque há divergências materiais em relação ao Prompt B: o `judge_model` do resultado não é lido do campo `judge_model` persistido no Parquet, e `sklearn` aparece fora de `infrastructure/stats/cohen_kappa_adapter.py`.

## Divergências

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| `JudgeValidationResult.judge_model` é documentado como "modelo do juiz lido do Parquet", mas o use case monta esse valor a partir de `r.answer.llm.value`, que representa o LLM avaliado. O schema do Parquet tem campo próprio `judge_model`, porém ele é descartado ao reconstruir `EvaluationResult`. O relatório final pode exibir o modelo errado. | [application/judge_validation.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/application/judge_validation.py:53), [application/judge_validation.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/application/judge_validation.py:137), [parquet_storage.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:50), [parquet_storage.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:289) | **BLOQUEADOR** |
| O prompt B item 2 pede `import sklearn` apenas em `infrastructure/stats/cohen_kappa_adapter.py`, mas há um segundo import em teste de aplicação, no fake `_FakeKappa`. Isso quebra a restrição literal de localização do uso de `sklearn`. | [test_judge_validation.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/application/test_judge_validation.py:18), [test_judge_validation.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/application/test_judge_validation.py:26), [cohen_kappa_adapter.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/stats/cohen_kappa_adapter.py:33) | **IMPORTANTE** |
| O prompt B item 7 exige verificar que `batch_invariant_confirmed=False` gera `WARNING`, mas os testes cobrem apenas o valor booleano no resultado; não há asserção do log emitido em `judge_validation_non_deterministic`. | [application/judge_validation.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/application/judge_validation.py:152), [test_judge_validation.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/application/test_judge_validation.py:193) | **IMPORTANTE** |

## Evidências positivas

- `InsufficientAnnotationError` foi adicionada na hierarquia de domínio em [domain/errors.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/domain/errors.py:346).
- `KappaCalculatorPort` está em `domain/ports.py` como `@runtime_checkable Protocol`, com docstring de delta M6, em [domain/ports.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/domain/ports.py:819).
- `JudgeValidationUseCase` injeta `KappaCalculatorPort`, não recebe `report_path`, retorna `JudgeValidationResult` puro e calcula `n_excluded_nan` corretamente em [application/judge_validation.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/application/judge_validation.py:104).
- O template está externalizado em [judge_validation_report.j2](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/prompts/judge_validation_report.j2:1) e o adapter correto está em [judge_validation_report_adapter.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/judge_validation_report_adapter.py:17).
- O relatório commitado contém `κ`, interpretação, `n_excluded_nan`, matriz 2x2 e cabeçalho da tabela de discordâncias em [docs/judge_validation_report.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/judge_validation_report.md:39).

## Validação executada

- `uv run --directory ... python -m inteligenciomica_eval.cli validate-judge --help` → OK
- `uv run --directory ... pytest tests/unit/application/test_judge_validation.py tests/unit/infrastructure/adapters/test_judge_validation_report.py tests/unit/infrastructure/stats/test_cohen_kappa_adapter.py -q` → `42 passed`
- `uv run --directory ... mypy --strict src` com `MYPY_CACHE_DIR=/tmp/mypy-cache` → `Success: no issues found in 54 source files`
- `uv run lint-imports` → `Contracts: 4 kept, 0 broken`

## Recomendação

**Request changes**.

Correção mínima esperada:
1. Propagar `judge_model` real do Parquet até o use case/result report, em vez de usar `answer.llm`.
2. Remover o import direto de `sklearn` do teste de aplicação; o teste pode usar um fake determinístico ou exercitar o adapter em seu próprio módulo de infraestrutura.
3. Adicionar teste que verifique explicitamente o `WARNING` quando `batch_invariant_confirmed=False`.
