# M2_TAREFA-024_B — Auditoria PrometheusRubricJudgeAdapter

Data: 2026-05-29
Auditor: ChatGPT Codex (`code-reviewer`)
Escopo: Prompt B da TAREFA-024

## Objetivo

Auditar a implementação do `PrometheusRubricJudgeAdapter` contra o contrato da
TAREFA-024, com ênfase em: protocolo `RubricJudgePort`, rubrica biomédica com 6
dimensões, parser Pydantic, normalização `1..5 -> 0..1`, política de erro,
`prompt_version`, logging e gates de validação.

## Veredito

FAIL / Request changes

## Divergências

| Critério | Evidência | Gravidade | Observação |
| --- | --- | --- | --- |
| Confirmar `pytest tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py` | [test_prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py:138) | Bloqueador | Os testes HTTP mockados com `respx` não concluíram nesta auditoria. A execução focal `timeout 8s ... -k "test_score_normalization and 1-0.0"` expirou com código 124. O primeiro teste assíncrono fica pendurado antes de retornar resultado. |

## Itens auditados sem divergência

1. **Contrato canônico (`RubricJudgePort.score`)**
   - Método `async def score(self, sample: EvaluationSample) -> RubricResult` implementado em [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:116).
   - `RubricJudgePort` segue `@runtime_checkable` em [ports.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/domain/ports.py:360).
   - Teste de `isinstance(adapter, RubricJudgePort)` existe em [test_prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py:108).

2. **Prompt versionado com exatamente 6 dimensões**
   - Arquivo existe em [biomed_rubric_v1.jinja2](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric_v1.jinja2:1).
   - Dimensões contadas no arquivo:
     1. `Correção factual`
     2. `Completude`
     3. `Contradições internas`
     4. `Alucinação`
     5. `Ressalvas omitidas`
     6. `Pertinência biomédica`
   - Linhas: [19](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric_v1.jinja2:19), [20](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric_v1.jinja2:20), [21](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric_v1.jinja2:21), [22](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric_v1.jinja2:22), [23](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric_v1.jinja2:23), [24](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric_v1.jinja2:24).

3. **Parser com Pydantic, sem `json.loads` cego**
   - Modelo `RubricOutput` com `score: int = Field(..., ge=1, le=5)` e `feedback: dict[str, str]` em [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:57).
   - O `json.loads` é imediatamente validado por `RubricOutput.model_validate(data)` em [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:172).

4. **Normalização**
   - Fórmula no código: `normalized = (parsed.score - 1) / 4.0` em [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:184).
   - Recomputação:
     - `1 -> (1-1)/4 = 0.0`
     - `3 -> (3-1)/4 = 0.5`
     - `5 -> (5-1)/4 = 1.0`

5. **Parse falho -> `RubricResult(NaN, "[parse_error]")` sem exceção**
   - Implementado no código em [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:175).

6. **Falha total de I/O -> `MetricComputationError`**
   - Tipos tratados: `APIConnectionError`, `APITimeoutError`, `InternalServerError` em [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:48).
   - Elevação da exceção: [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:144).

7. **`prompt_version` exposto**
   - Derivado do marcador `RUBRIC_VERSION` no arquivo de prompt em [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:69).
   - Exposto como `self.prompt_version` em [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:107).

8. **Logging sem vazar conteúdo completo**
   - Evento `rubric_judge_completed` registra `question_id`, `score`, `prompt_version`, `latency_ms`, `parse_error`, `feedback_len`; não loga feedback nem contexto completos em [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:151).

9. **Opção B com ADR inline**
   - Justificativa presente no docstring do módulo em [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:9).

10. **Determinismo**
    - `temperature=0.0` no corpo da chamada em [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:141).
    - `seed=42` em [prometheus_rubric_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py:142).

11. **Gates**
    - `uv run lint-imports` -> `Contracts: 4 kept, 0 broken`.
    - `uv run mypy --strict src` -> `Success: no issues found in 32 source files`.
    - Cobertura `>= 80%`: não reexecutei a suíte full com coverage nesta auditoria; uso apenas a evidência informada pelo desenvolvedor (`95%` no módulo).

## Probes executados

| Comando | Resultado |
| --- | --- |
| `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` | OK |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src` | OK |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py --collect-only -q` | OK, 19 testes coletados |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py -q -k test_prompt_has_exactly_six_dimensions` | OK, `1 passed` |
| `timeout 8s bash -lc 'UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py -q -k "test_score_normalization and 1-0.0"'` | FAIL, expirou (`124`) |

## Conclusão

O adapter está tecnicamente aderente ao contrato do Prompt A. O bloqueio está na
evidência de teste exigida pelo Prompt B: os testes unitários que exercitam a
chamada HTTP mockada com `respx` não concluíram nesta auditoria. Até esse gate
ficar reproduzivelmente verde, o veredito permanece `FAIL / Request changes`.
