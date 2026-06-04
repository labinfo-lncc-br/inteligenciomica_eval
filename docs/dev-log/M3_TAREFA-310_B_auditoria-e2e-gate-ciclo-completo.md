# M3_TAREFA-310_B — Auditoria do gate E2E do ciclo completo M3

**Data**: 2026-06-04
**Milestone**: M3 — gate de saída
**Épico**: E3
**Skill**: code-reviewer + test-engineer
**Prioridade / Tamanho**: P0 / S

## Objetivo

Auditar a implementação da TAREFA-310 contra o contrato do Prompt B:
- 5 cenários E2E do ciclo A+B com `build_fake_container` + `ParquetStorage(tmp_path)`
- validação de ADR-004/007/009/012 e RNF7
- validação de gates (`ruff`, `mypy`, `lint-imports`, E2E, cobertura)

## Resultado

**FAIL**

Os testes E2E passam e os gates técnicos estão verdes, mas a implementação ainda diverge
do contrato exigido pelo prompt em pontos que caem nos itens 1–6 da auditoria e, portanto,
bloqueiam a aprovação do gate do M3.

## Divergências

| Critério | Evidência | Gravidade |
|---|---|---|
| Fixture `questions_stub` não prova o contrato pedido de carregar as 2 primeiras perguntas a partir do YAML configurado da rodada. O teste usa `load_questions(None)[:2]`, dependente do default empacotado, e o `RoundConfig` usado no teste nem possui campo `questions`. Isso valida um atalho interno, não a fiação E2E pedida pelo prompt. | [tests/e2e/test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:376), [src/inteligenciomica_eval/infrastructure/benchmark/loader.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/benchmark/loader.py:11), [src/inteligenciomica_eval/infrastructure/config/schema.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/config/schema.py:131) | **BLOQUEADOR** |
| O cenário RNF7 não exercita o caso pedido no prompt: “FakeGenerator levanta `KeyboardInterrupt` na onda 2”. O teste apenas seta a flag privada `_shutdown_requested` via `progress_callback` após `generation:stub-gen-a`, cobrindo shutdown cooperativo entre ondas, mas não interrupção disparada pelo gerador. | [tests/e2e/test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:674), [tests/e2e/test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:685), [src/inteligenciomica_eval/application/use_cases/run_experiment.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/application/use_cases/run_experiment.py:282) | **BLOQUEADOR** |
| A checagem de schema do Parquet contorna a API do storage e acessa atributo privado `_base_dir`, lendo só o primeiro arquivo `.parquet` via `pyarrow`. O prompt pedia leitura via API do storage; do jeito atual, o teste mistura duas estratégias e enfraquece a verificação do roundtrip/storage contract. | [tests/e2e/test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:439), [tests/e2e/test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:475) | **IMPORTANTE** |
| O `golden` não valida `rank_scores_by_config` com valores recomputados por configuração; ele armazena apenas `null` para todas as configs, e o cenário principal só verifica que todos os `rank_scores` do relatório são `NaN`. Isso é mais fraco que o contrato do prompt, que pedia expectativa explícita por `{base, llm}` e recomputação manual citada. | [tests/golden/e2e_m3_expected.json](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/golden/e2e_m3_expected.json:17), [tests/e2e/test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:469) | **IMPORTANTE** |

## Pontos confirmados

- `container` usa `build_fake_container(...)` e substitui `writer`/`reader` por
  `ParquetStorage(tmp_path)` via `dataclasses.replace(...)`.
- Os 5 testes estão marcados com `@pytest.mark.e2e`.
- O cenário principal gera 12 células e confirma `8` na fase A e `4` na fase B.
- O cenário ADR-012 usa `FakeVLLMServerManager.wait_healthy(...)` e confirma que o juiz
  inicia após os geradores.
- O cenário ADR-009 confirma reexecução com o mesmo `run_id` sem duplicatas.
- `pytest-timeout` foi adicionado e o marcador `e2e` está registrado no `pyproject.toml`.

## Recomputação de RankScore

Pelo contrato atual do domínio, `RankScoreCalculator.compute(...)` retorna `NaN` se
qualquer entrada for `NaN` (ADR-007). No cenário principal, sem anotações humanas,
`critical_failure_rate` fica `NaN`; portanto o `rank_score` esperado por config também é
`NaN`, mesmo com `final_score=0.824`.

O `final_score` conferido no teste é:

```text
0.40*0.80 + 0.30*0.90 + 0.15*0.70 + 0.10*0.85 + 0.05*0.88 = 0.824
```

E a regra do `RankScoreCalculator` é:

```text
se median_score, failure_rate, win_rate ou critical_failure_rate for NaN -> RankScore = NaN
```

Logo, o `rank_score` esperado no cenário principal é `NaN`.

## Validação executada

### Comandos

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m e2e tests/e2e/test_m3_full_cycle.py -v --timeout=30
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src
UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports
UV_CACHE_DIR=/tmp/uv-cache uv run pytest --cov=src --cov-fail-under=85 -q
```

### Saídas observadas

```text
============================= test session starts ==============================
platform linux -- Python 3.13.13, pytest-9.0.3
collecting ... collected 5 items

tests/e2e/test_m3_full_cycle.py::test_m3_graceful_shutdown_on_sigint PASSED [ 20%]
tests/e2e/test_m3_full_cycle.py::test_m3_full_cycle_generates_and_evaluates PASSED [ 40%]
tests/e2e/test_m3_full_cycle.py::test_m3_nan_cell_excluded_from_aggregation PASSED [ 60%]
tests/e2e/test_m3_full_cycle.py::test_m3_judge_resident_generators_in_waves PASSED [ 80%]
tests/e2e/test_m3_full_cycle.py::test_m3_idempotent_second_run PASSED    [100%]

============================== 5 passed in 1.02s ===============================
```

```text
All checks passed!
Success: no issues found in 57 source files
Contracts: 4 kept, 0 broken.
1204 passed, 16 skipped, 10 warnings in 36.20s
Required test coverage of 85% reached. Total coverage: 88.62%
```

## Recomendação

**Request changes**

O gate técnico está verde, mas o gate de contrato ainda não. Para aprovação do prompt
M3-310B, os próximos ajustes prioritários são:

1. fazer o fixture de perguntas provar a leitura do arquivo configurado da rodada
2. transformar o cenário RNF7 em um teste de `KeyboardInterrupt` no gerador da onda 2
3. remover a leitura paralela do Parquet por atributo privado/`pyarrow` no teste
4. fortalecer o `golden` para validar `rank_scores_by_config` conforme o contrato
