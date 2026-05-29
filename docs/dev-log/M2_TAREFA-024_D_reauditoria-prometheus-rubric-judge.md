# M2_TAREFA-024_D — Reauditoria PrometheusRubricJudgeAdapter

Data: 2026-05-29
Auditor: ChatGPT Codex (`code-reviewer`)
Escopo: re-veredito após TAREFA-024 Prompt C

## Objetivo

Revalidar a TAREFA-024 após a correção do Prompt C, que trocou o mocking dos
testes unitários de `respx` para `AsyncMock` no nível do SDK OpenAI.

## Veredito

PASS / Approve

## Resultado da reauditoria

Nenhuma divergência remanescente.

O bloqueio do Prompt B estava restrito ao runner de testes em sandbox. Com o
mock no nível de `adapter._client.chat.completions.create`, a evidência exigida
pelo contrato ficou reproduzível e estável.

## Evidências principais

1. **Correção do padrão de teste**
   - O arquivo agora documenta explicitamente o mock no nível do SDK em
     [test_prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py:3).
   - A injeção do `AsyncMock` ocorre em
     [test_prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py:96).

2. **Teste focal que travava agora passa**
   - `test_score_normalization[1-0.0]` continua cobrindo a fórmula `(s-1)/4` em
     [test_prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py:144).

3. **Cobertura dos cenários contratuais preservada**
   - `isinstance(adapter, RubricJudgePort)`:
     [test_prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py:116)
   - parse falho -> `NaN` + sentinel:
     [test_prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py:181)
   - `HTTP 5xx` / conexão -> `MetricComputationError` via erros do SDK:
     [test_prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py:199)
   - `temperature=0.0` e `seed=42` via `call_args`:
     [test_prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py:230)
   - prompt com exatamente 6 dimensões:
     [test_prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py:249)

4. **Implementação do adapter permanece aderente**
   - `score(sample) -> RubricResult`:
     [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:116)
   - normalização:
     [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:184)
   - `prompt_version` derivado do arquivo:
     [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:69)

## Probes executados

| Comando | Resultado |
| --- | --- |
| `timeout 20s bash -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py -q -k "test_score_normalization and 1-0.0"'` | `1 passed, 18 deselected in 0.57s` |
| `timeout 60s bash -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py -q'` | `19 passed in 1.02s` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` | `Contracts: 4 kept, 0 broken` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src` | `Success: no issues found in 32 source files` |

## Conclusão

O `Prompt C` resolveu corretamente o único bloqueio da auditoria anterior sem
alterar o contrato funcional do adapter. A TAREFA-024 fica aprovada.
