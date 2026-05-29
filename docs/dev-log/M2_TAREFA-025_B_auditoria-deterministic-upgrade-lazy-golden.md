# M2_TAREFA-025_B — Auditoria DeterministicMetricsAdapter

## Objetivo

Auditar a implementação da `TAREFA-025` contra a spec de M2:

- assinatura canônica `DeterministicMetricPort.score(*, answer, ground_truth)`
- lazy init por atributo de instância (`_scorer`)
- `DeterministicAdapterConfig` com `lang="pt"` e `rescale_with_baseline=True`
- golden dataset PT-BR com 3 pares biomédicos
- determinismo e testes de integração
- conformidade com DoD (`mypy --strict`, import-linter, cobertura)

## Arquivos auditados

- `src/inteligenciomica_eval/domain/ports.py`
- `src/inteligenciomica_eval/infrastructure/adapters/deterministic_metrics.py`
- `src/inteligenciomica_eval/infrastructure/config/adapter_configs.py`
- `tests/unit/infrastructure/adapters/test_deterministic_metrics.py`
- `tests/integration/adapters/test_deterministic_integration.py`
- `tests/golden/det_metrics_pt_golden.json`
- `docs/prompts_m2_tarefas_022_028.md`

## Verificações

| Critério | Evidência | Resultado |
| --- | --- | --- |
| Assinatura canônica `.score(*, answer, ground_truth)` | `DeterministicMetricPort.score` em `domain/ports.py` e implementação em `deterministic_metrics.py` | PASS |
| `isinstance(adapter, DeterministicMetricPort)` | teste unitário explícito | PASS |
| Lazy init por atributo de instância | `self._scorer: BERTScorer | None = None` + `_get_scorer()` | PASS |
| Ausência de `cached_property` executável | adapter usa apenas atributo de instância; referências remanescentes são documentais | PASS |
| Motivo documentado para não usar `cached_property` | docstring de `_get_scorer()` | PASS |
| Isolamento entre instâncias (`id()` distinto) | teste `test_two_instances_do_not_share_scorer` | PASS |
| Config canônica (`lang="pt"`, `rescale_with_baseline=True`, `device="cpu"`) | `DeterministicAdapterConfig` | PASS |
| Regra de mudança de idioma depende de novo golden + aprovação | docstring de `DeterministicAdapterConfig` | PASS |
| Golden PT-BR com 3 pares biomédicos | `det_metrics_pt_golden.json` | PASS |
| Determinismo em integração | `test_determinism_same_input_same_float` | PASS |
| Síncrono (sem `async`) | método `score()` regular + teste unitário | PASS |
| Cobertura >= 80% | cobertura direcionada: 100% nos 2 arquivos alterados | PASS |
| `mypy --strict` | comando executado | PASS |
| `lint-imports` | comando executado | PASS |

## Recomputação manual de ROUGE-L

Par auditado: caso `similar` de `tests/golden/det_metrics_pt_golden.json`.

Tokenização efetiva do `rouge_score` (regex ASCII `[^a-z0-9]+`) produz:

- resposta: 19 tokens
- referência: 21 tokens
- LCS: 14

Logo:

- Precisão `P = 14 / 19 = 0.736842...`
- Revocação `R = 14 / 21 = 0.666666...`
- `F = 2PR / (P + R) = 0.7`

Valor esperado: `rouge_l = 0.7000`, coerente com o golden.

## Comandos executados

```bash
rg -n "cached_property|lang=\"en\"|lang=\"pt-br\"|compute_aux\\(|score\\(sample|async def score" \
  src/inteligenciomica_eval/infrastructure/adapters/deterministic_metrics.py \
  src/inteligenciomica_eval/infrastructure/config/adapter_configs.py \
  tests/unit/infrastructure/adapters/test_deterministic_metrics.py \
  tests/integration/adapters/test_deterministic_integration.py \
  src/inteligenciomica_eval/domain/ports.py

UV_CACHE_DIR=/tmp/uv-cache uv run pytest \
  tests/unit/infrastructure/adapters/test_deterministic_metrics.py \
  tests/integration/adapters/test_deterministic_integration.py -q

UV_CACHE_DIR=/tmp/uv-cache uv run pytest \
  tests/unit/infrastructure/adapters/test_deterministic_metrics.py \
  tests/integration/adapters/test_deterministic_integration.py \
  --cov=inteligenciomica_eval.infrastructure.adapters.deterministic_metrics \
  --cov=inteligenciomica_eval.infrastructure.config.adapter_configs \
  --cov-report=term-missing -q

UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports
UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src
```

## Resultados dos gates

- `pytest tests/unit/infrastructure/adapters/test_deterministic_metrics.py tests/integration/adapters/test_deterministic_integration.py -q`
  - `21 passed, 1 warning in 7.22s`
- cobertura direcionada
  - `deterministic_metrics.py`: `100%`
  - `adapter_configs.py`: `100%`
- `uv run lint-imports`
  - `Contracts: 4 kept, 0 broken`
- `uv run mypy --strict src`
  - `Success: no issues found in 32 source files`

## Veredito

**PASS / Approve**

Não encontrei divergências materiais entre a spec da `TAREFA-025` e a implementação auditada.
