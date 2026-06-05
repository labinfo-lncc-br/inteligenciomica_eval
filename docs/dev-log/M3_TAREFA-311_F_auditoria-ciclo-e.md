# M3_TAREFA-311_F — Auditoria ciclo E (modo external + proveniencia)

**Data**: 2026-06-05
**Escopo**: reauditoria do ciclo E da TAREFA-311 contra o prompt `docs/prompts_m3_tarefa_311.md` (Prompt B)
**Veredito**: `FAIL / Request changes`

## Findings

### BLOQUEADOR 1 — modo `external` ainda nao usa o endpoint real do juiz no fluxo principal

- Arquivo: `src/inteligenciomica_eval/infrastructure/wiring.py:601`
- Evidencia:
  - `judge_url = settings.VLLM_JUDGE_URL`
  - `PrometheusJudgeAdapter` e `RAGASLayer1Adapter` sao instanciados a partir desse valor em `:602-612`
- Impacto:
  - Em `server_mode="external"`, o prompt exige que o juiz seja resolvido por `endpoint_env` no registry.
  - O wiring usa corretamente o endpoint externo apenas para probes (`:520`, `:532-537`), mas o juiz real usado nas passadas 2 e 3 continua acoplado a `VLLM_JUDGE_URL`.
  - Na pratica, um run external pode:
    - falhar sem necessidade se `VLLM_JUDGE_URL` nao estiver setada;
    - ou pior, avaliar com um endpoint diferente do probe/reportado, quebrando a garantia de proveniencia verificada.
- Observacao adicional:
  - O mesmo wiring ainda instancia `RunGenerationPassUseCase` com `generator_factory(settings.VLLM_GENERATOR_URL)` em `:643-649`. A geracao acaba sendo sobrescrita por `active_handle.url` durante o loop, mas isso reforca que o bootstrap do modo `external` continua dependente de env global que deveria ser irrelevante.

### BLOQUEADOR 2 — falha de probe ainda pode gravar `determinism_verified=True`

- Arquivo: `src/inteligenciomica_eval/infrastructure/wiring.py:342-354`, `:373`, `:394`
- Evidencia:
  - `_run_endpoint_probes()` inicializa `judge_det: bool = True` em `:342`
  - se o probe do juiz falha, o `except Exception: pass` em `:353-354` preserva `True`
  - se a rotina inteira falha, o retorno de fallback e `return {}, True, {"server_mode": server_mode, "error": str(exc)}` em `:394`
- Impacto:
  - O valor retornado alimenta `judge_determinism_verified` em `_ExperimentConfig` (`src/inteligenciomica_eval/infrastructure/wiring.py:569`)
  - e depois e persistido por linha em `EvaluationResult` (`src/inteligenciomica_eval/application/use_cases/run_generation_pass.py:379`).
  - Isso contradiz o requisito central da 311: em external, se a verificacao do juiz falhar, o run deve no minimo prosseguir com `determinism_verified=false` e sinalizacao clara.
  - No estado atual, uma falha de probe pode autocertificar linhas e report com `True`.

### IMPORTANTE — a alegacao de limpeza total das referencias ADR continua incorreta

- Arquivos:
  - `src/inteligenciomica_eval/cli.py:105`, `:170`
  - `src/inteligenciomica_eval/domain/errors.py:328`
  - `src/inteligenciomica_eval/domain/entities.py:130-136`
  - `src/inteligenciomica_eval/infrastructure/adapters/external_vllm_server_manager.py:1`, `:72`
- Impacto:
  - Nao quebra a execucao, mas o relatorio do ciclo E afirma que as referencias `ADR-013 -> ADR-014` foram normalizadas no codebase/stubs.
  - Isso nao procede: ha referencias `ADR-013` espalhadas em docstrings e comentarios de producao.
  - Mantem a divergencia formal entre prompt/ADR entregue e reduz auditabilidade documental.

## Gates executados

- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` -> `PASS`
- `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src` -> `PASS`
- `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` -> `PASS`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m 'not integration' --cov-fail-under=85 -n 4 -q` -> `1252 passed, 6 skipped, 17 warnings in 86.91s`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/cli/test_run_external.py -W error::RuntimeWarning -q` -> `5 passed in 0.19s`

## Conclusao

O ciclo E resolveu os gates e removeu a regressao de `RuntimeWarning`, mas a entrega ainda nao fecha a TAREFA-311 de forma estrita. O problema central remanescente e funcional:

1. o modo `external` ainda nao usa o endpoint real do juiz no fluxo principal de metricas/julgamento;
2. a proveniencia de determinismo ainda pode ser gravada como `True` quando o probe falha.

Com isso, a parte mais sensivel da tarefa, "proveniencia verificada por sonda, nao declarada", segue vulneravel.

## Proximo ciclo recomendado

- Resolver `judge_url` e demais endpoints de runtime a partir do mesmo mapa validado de `endpoint_env` usado pelo `ExternalVLLMServerManager`, nao de `settings.VLLM_JUDGE_URL`.
- Corrigir `_run_endpoint_probes()` para que qualquer falha de probe do juiz degrade para `determinism_verified=False`, inclusive no fallback externo.
- Adicionar teste unitario de wiring/execucao que falhe se `server_mode="external"` depender de `VLLM_JUDGE_URL` para judge/metrics.
