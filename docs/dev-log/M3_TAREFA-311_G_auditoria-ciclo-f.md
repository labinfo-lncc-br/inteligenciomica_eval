# M3_TAREFA-311_G — Correções ciclo F (judge_url externo + determinism_verified false-safe)

**Data**: 2026-06-05
**Milestone**: M3 — Orquestração e E2E
**Épico**: E3
**Skill**: implementação direta (Claude Code)
**Prioridade / Tamanho**: P0 / S
**Ciclo**: G (correções após auditoria Codex ciclo F — FAIL)

---

## Objetivo

Corrigir os 2 bloqueadores e 1 item importante identificados pela auditoria F:

1. **BLOCKER**: Em `server_mode="external"`, `PrometheusJudgeAdapter` e `RAGASLayer1Adapter` usavam `settings.VLLM_JUDGE_URL` (env global) em vez do endpoint validado no registry (`_judge_url_probe`). Probe e execução real podiam apontar para endpoints distintos.
2. **BLOCKER**: `_run_endpoint_probes()` iniciava `judge_det=True` e retornava `True` no fallback de exceção — probe com falha mantinha `determinism_verified=True` indevidamente.
3. **IMPORTANTE**: Referências `ADR-013` persistiam em 10+ locais de produção além dos corrigidos no ciclo E.

---

## Arquivos Modificados

| Arquivo | Alteração |
|---------|-----------|
| `src/inteligenciomica_eval/infrastructure/wiring.py` | `judge_det` inicia `False`; fallback de exceção retorna `False`; `judge_url` determinado por modo (`_judge_url_probe` em external, `settings.VLLM_JUDGE_URL` em managed) |
| `src/inteligenciomica_eval/infrastructure/adapters/external_vllm_server_manager.py` | ADR-013→ADR-014 (3 ocorrências) |
| `src/inteligenciomica_eval/domain/entities.py` | ADR-013→ADR-014 (4 ocorrências) |
| `src/inteligenciomica_eval/domain/errors.py` | ADR-013→ADR-014 (1 ocorrência) |
| `src/inteligenciomica_eval/cli.py` | ADR-013→ADR-014 (3 ocorrências) |
| `src/inteligenciomica_eval/infrastructure/config/schema.py` | ADR-013→ADR-014 |
| `src/inteligenciomica_eval/application/use_cases/run_generation_pass.py` | ADR-013→ADR-014 |
| `src/inteligenciomica_eval/infrastructure/config/model_registry.py` | ADR-013→ADR-014 |
| `src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py` | ADR-013→ADR-014 |
| `src/inteligenciomica_eval/infrastructure/provenance/__init__.py` | ADR-013→ADR-014 |
| `src/inteligenciomica_eval/domain/ports.py` | ADR-013→ADR-014 |
| `tests/unit/application/use_cases/test_run_generation_pass.py` | ADR-013→ADR-014 |

---

## Decisões Técnicas

### D1 — `judge_url` por modo em `build_container()`

```python
judge_url: str = (
    _judge_url_probe
    if config.server_mode == "external" and _judge_url_probe
    else settings.VLLM_JUDGE_URL
)
```

Em `server_mode="external"`, `_judge_url_probe` é a URL resolvida do `endpoint_env` do modelo juiz no registry — a mesma URL usada pelos probes. Em `server_mode="managed"`, usa a env global como antes. Garante que probes e adapters de julgamento apontam para o mesmo endpoint.

### D2 — `judge_det` inicia `False`

A semântica correta: `determinism_verified` só é `True` se o probe **executou e confirmou** determinismo. Se o probe falha por exceção, o flag fica `False` — ausência de prova não é prova de ausência de não-determinismo. Alinhado com o requisito da 311: "marcar false quando a verificação não é comprovada".

O fallback de exceção no `try/except` externo também retorna `False` pelo mesmo motivo.

---

## Validação (DoD)

| Gate | Resultado |
|------|-----------|
| `ruff check .` | ✅ All checks passed |
| `ruff format --check .` | ✅ |
| `mypy --strict src` | ✅ no issues found in 60 source files |
| `lint-imports` | ✅ 4 contratos KEPT |
| `pytest -m "not integration" --cov-fail-under=85 -n 4` | ✅ **1252 passed**, 6 skipped — **89.51%** |
| `grep -rn "ADR-013" src/` | ✅ 0 ocorrências |

---

## Critérios de Aceitação Ciclo F → G

| Bloqueador/Importante | Status |
|-----------------------|--------|
| `judge_url` correto em external mode (endpoint_env, não env global) | ✅ `_judge_url_probe if external else settings.VLLM_JUDGE_URL` |
| `determinism_verified=False` quando probe não comprovado | ✅ `judge_det: bool = False`; fallback retorna `False` |
| Zero referências ADR-013 em src/ | ✅ 0 ocorrências |
