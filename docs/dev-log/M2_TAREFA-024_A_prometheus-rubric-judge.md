# M2_TAREFA-024_A — `PrometheusRubricJudgeAdapter` (Camada 2, rubrica biomédica)

**Data**: 2026-05-29
**Milestone**: M2 — Avaliação automática (Camadas 1+2, juiz determinístico)
**Épico**: E2
**Skill**: ml-engineer, rag-engineer
**Prioridade / Tamanho**: P0 / M
**Referência arquitetural**: TAREFA-204 (§14.5) — nova · ADR-003/006/008 · §5.1/§5.2

## Objetivo

Implementar a Camada 2 **formal**: `PrometheusRubricJudgeAdapter` avaliando a
resposta gerada pela rubrica biomédica versionada de 6 dimensões, com score
normalizado em `[0,1]`, parser Pydantic e feedback estruturado para auditoria.

## Arquivos Criados / Modificados

### Criados
- `src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py` —
  adapter `RubricJudgePort` + `RubricOutput` (Pydantic) + `_load_rubric_prompt`.
- `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric_v1.jinja2` —
  prompt versionado (marcador `RUBRIC_VERSION` na 1ª linha + 6 dimensões + JSON schema).
- `tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py` — 19 testes (respx).
- `tests/integration/adapters/test_rubric_judge_integration.py` — determinismo, skipável.

### Modificados
- `src/inteligenciomica_eval/infrastructure/config/adapter_configs.py` —
  `RubricJudgeAdapterConfig` (`vllm_judge_url`, `judge_model_name`, `vllm_judge_api_key`,
  `timeout_s`).

## Decisões Técnicas

1. **Opção B (chamada direta), não DeepEval — ADR inline no módulo.** `deepeval` **não**
   está instalado (uv.lock) e o `GEval` impõe sua própria cadeia de avaliação
   (evaluation steps + score interno), incompatível com o requisito de **prompt
   versionado externo** que devolve JSON `{"score": 1-5, "feedback": {...}}`. A chamada
   direta via `openai.AsyncOpenAI` (padrão do `PrometheusJudgeAdapter` de M1) dá controle
   total do prompt e do parser Pydantic, é determinística e testável por respx — exatamente
   a "Opção B (fallback)" prevista no Prompt A.
2. **`prompt_version` derivado do arquivo, não do config.** É propriedade do artefato
   versionado: o adapter lê o marcador `{# RUBRIC_VERSION: ... #}` da 1ª linha e expõe
   `adapter.prompt_version` (fonte única §5.3). Decisão consciente de **não** duplicar no
   `RubricJudgeAdapterConfig` para evitar divergência (a spec lista `prompt_version`, mas
   "lido do arquivo de prompt" — interpretei como derivação, não campo de conexão).
3. **Template em `.jinja2` com placeholders `{{ }}`.** Evita colisão com as chaves `{}`
   do JSON literal no corpo do prompt (str.format quebraria). Renderizado via
   `jinja2.Template`; carregado por `importlib.resources` (acesso ao texto bruto p/ a versão).
4. **Classificação de erro (Nota M2 item 4).** `_IO_ERROR_TYPES` = `APIConnectionError`,
   `APITimeoutError`, `InternalServerError` (HTTP 5xx) → `MetricComputationError`. Parsing
   (JSON malformado, score ∉ [1,5], campos ausentes) → `RubricResult(nan, "[parse_error]")`
   sem exceção (ADR-007). `max_retries=0` no SDK — retry é do `RetryableRubricJudgeAdapter`
   (TAREFA-027).
5. **`determinism_regime = JUDGE`** exposto (TAREFA-022) + `temperature=0.0` + `seed=42`.
6. **Logging sem vazamento.** `rubric_judge_completed` loga `question_id`, `score`,
   `prompt_version`, `latency_ms`, `parse_error`, `feedback_len` — nunca o feedback completo.

## Problemas Encontrados e Soluções

- **RUF002** no docstring (`×` ambíguo) → trocado por `2x`.
- **isort/format** ajustados via `ruff check --fix`/`ruff format`.
- **respx travou no ambiente do auditor (Prompt C — correção)**: a versão inicial dos testes
  unitários mockava o juiz via `respx.mock` global. No sandbox do auditor (TAREFA-024-B) o
  probe focal expirou (`timeout 8s`, exit 124) — exatamente a fragilidade descrita no
  CLAUDE.md §11: o SDK OpenAI v2 usa `asyncify`/`asyncio.to_thread` na 1ª chamada, que pode
  travar o transporte interceptado por respx em ambientes containerizados. **Solução**:
  reescrever `test_prometheus_rubric_judge.py` mockando no **nível do SDK**
  (`adapter._client.chat.completions.create = AsyncMock(...)`), mesmo padrão do
  `test_prometheus_judge.py` (M1/TAREFA-016) — 100% determinístico e independente de
  anyio/sniffio/httpx. Cobertura e contagem de testes preservadas (19 testes, adapter 95%).
  - HTTP 5xx agora simulado via `openai.InternalServerError(..., response=httpx.Response(500))`
    como `side_effect`; conexão via `openai.APIConnectionError(request=_DUMMY_REQUEST)`.
  - Determinismo verificado por `mock.call_args.kwargs["temperature"]` /
    `["extra_body"]["seed"]` (não mais inspeção do corpo HTTP).
  - `TestRubricPrompt` permaneceu intacto (lê o arquivo de prompt, sem rede).

## Validação (DoD §14.2)

```
ruff check / format          → OK
mypy --strict src            → Success (32 source files)
lint-imports                 → 4 kept, 0 broken
pytest test_prometheus_rubric_judge → 19 passed (1.06s — sem hang)
pytest (full, -n 4)          → 734 passed, 13 skipped — 96.82% cobertura
prometheus_rubric_judge.py   → 95% (linha 86 = guard de marcador ausente; 190 = close())
```

**Revalidado no Prompt C** (após troca respx → AsyncMock no nível do SDK): teste focal
`test_score_normalization[1-0.0]` que travava na auditoria agora passa em 0.53s; arquivo
inteiro em 1.06s; suíte completa e cobertura inalteradas.

## Critérios de Aceitação (TAREFA-024)

- [x] Exatamente 6 dimensões no arquivo de prompt — `TestRubricPrompt` (2 testes).
- [x] Normalização 1→0.0, 3→0.5, 5→1.0 — `TestNormalization` (parametrizado, 3 pontos).
- [x] Parse falho → `RubricResult(NaN, "[parse_error]")` sem exceção — `TestParseFailure` (6 casos).
- [x] HTTP 500 → `MetricComputationError` — `TestIOFailure`.
- [x] `adapter.prompt_version` acessível (= "biomed_rubric_v1") — `TestProtocolConformance`.
- [x] `isinstance(adapter, RubricJudgePort)` True (`@runtime_checkable`).
- [x] `temperature=0.0`/`seed=42` no body (via respx) — `TestDeterminism`.
- [x] import-linter OK; mypy --strict; cobertura 95% ≥ 80%.

## Observações para Próximas Tarefas

- **TAREFA-027 (`RetryableRubricJudgeAdapter`)**: absorve o `MetricComputationError` deste
  adapter, aplica backoff e devolve `RubricResult(nan, "[retry_exhausted:N]")` ao esgotar.
- **TAREFA-026 (`ComputeMetricsUseCase`)**: injeta o `PrometheusRubricJudgeAdapter` (envolto
  pelo retryable) como `rubric_judge`; lê `adapter.prompt_version` para a proveniência §5.3.
- **`PrometheusJudgeAdapter` (M1/TAREFA-016)** permanece para compatibilidade (depreciação
  suave); este é o canônico de Camada 2.
- O `rubric_biomed_score` do `MetricVector` recebe o `RubricResult.score` deste adapter; o
  `rubric_feedback` do schema §5.3 recebe `RubricResult.feedback` (a fiação fica na 026).
