# M3_TAREFA-314_B — Auditoria de observabilidade segura

**Data:** 2026-06-08
**Milestone:** M3 — Hardening E9
**Tarefa auditada:** M3-TAREFA-314
**Commit auditado:** `3c48d2a`
**Auditor:** ChatGPT Codex (`code-reviewer`, com foco em segurança e testes)

---

## Veredito

**FAIL**

O objetivo principal de mascaramento de URLs dos probes foi atendido e o helper único de
masking foi consolidado corretamente. Porém, ainda existe um caminho real de
`prometheus_judge_parse_failure` que registra `raw_content`, contrariando o critério da
tarefa ("sem payload textual completo") e o próprio Prompt B ("FAIL se payload completo
ainda logado").

---

## Achados

| Severidade | Arquivo:linha | Achado | Evidência / impacto |
|------------|---------------|--------|---------------------|
| **Bloqueador** | `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py:213-219` | O ramo `score` fora de `[0.0, 1.0]` ainda loga `raw_content=content[:500]`. | O fix de TAREFA-314 cobriu apenas o `except` de parse e o evento `prometheus_judge_nan`, mas não este terceiro caminho de falha. Replay local do caso `{"score": 1.5, ...}` capturou 3 eventos `prometheus_judge_parse_failure` contendo `raw_content` cru. Isso viola o critério de segurança e deixa payload textual completo em log. |
| **Importante** | `tests/unit/infrastructure/adapters/test_prometheus_judge.py:235-244` | Existe teste funcional para `score` fora da faixa, mas ele não verifica o conteúdo do log. | A suíte passa (`68 passed` no recorte auditado) porque `test_nan_on_score_out_of_range` só valida retorno `NaN` e `call_count == 3`. Falta um teste que prove ausência de `raw_content` também nesse ramo específico. |
| **Importante** | `docs/security_review.md:21`, `docs/security_review.md:161-178` | A documentação de segurança não descreve o estado real após a TAREFA-314. | O Prompt B pediu verificação explícita de `security_review.md` quanto ao novo estado "mascaramento total, não parcial". O documento ainda descreve apenas o fix anterior do `RAGASLayer1Adapter`; não cobre `endpoint_probe.py`, helper único `mask_url`, nem a redução de payload do juiz. Não bloqueia runtime, mas reprova a checagem documental do prompt. |

---

## Itens validados com sucesso

- `endpoint_probe.py` não passa mais URL crua nos eventos auditados.
  Evidência: `probe_served_model_*`, `probe_vllm_version_*` e `probe_judge_determinism_*`
  usam `mask_url(...)` em `src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py`.
- O helper único foi consolidado em `src/inteligenciomica_eval/infrastructure/masking.py`.
  Evidência: `rg -n "def _mask_url|def _mask_path" src/inteligenciomica_eval/infrastructure`
  não encontrou duplicatas remanescentes.
- `external_vllm_server_manager.py` e `wiring.py` foram reapontados para o helper central.
- Há cobertura específica de masking para probes e helper:
  `tests/unit/infrastructure/test_masking.py` e `tests/unit/infrastructure/test_endpoint_probe.py`.

---

## Evidência do bloqueador

Trecho auditado:

```python
if not (0.0 <= score <= 1.0):
    _log.warning(
        "prometheus_judge_parse_failure",
        raw_content=content[:500],
        error=f"score={score} out of [0.0, 1.0]",
    )
```

Replay local do caso fora da faixa:

```bash
PYTHONPATH=. UV_CACHE_DIR=/tmp/uv-cache uv run python /tmp/replay_t314.py
```

Resultado observado:

- `prometheus_judge_parse_failure` apareceu 3 vezes com `raw_content` contendo
  `{"score": 1.5, "feedback": "Score invalido."}`
- `prometheus_judge_nan` já usa `raw_len` + `raw_snippet`, mas o vazamento já ocorreu antes

---

## Gates reproduzidos

```text
ruff check .                                          -> OK
ruff format --check .                                 -> OK
uv run mypy --strict src/                             -> OK
UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports        -> 4 kept, 0 broken
UV_CACHE_DIR=/tmp/uv-cache uv run pytest \
  tests/unit/infrastructure/test_masking.py \
  tests/unit/infrastructure/test_endpoint_probe.py \
  tests/unit/infrastructure/adapters/test_prometheus_judge.py \
  tests/unit/infrastructure/test_external_server_manager.py -q
                                                     -> 68 passed
uv run pytest -m "not integration" --cov=src \
  --cov-fail-under=85 -n 4 -q                        -> 1273 passed, 6 skipped, 89.61%
```

Observação: o estado geral do repositório permanece verde, mas a suíte atual não captura o
vazamento residual no ramo `score out of range`.

---

## Recomendação

1. Corrigir `prometheus_judge.py` para substituir `raw_content` por `raw_len` +
   `raw_snippet[:120]` também no ramo `score` fora da faixa.
2. Estender `test_nan_on_score_out_of_range` ou criar teste dedicado que capture logs e
   prove ausência de `raw_content` nesse ramo.
3. Atualizar `docs/security_review.md` para refletir o estado real pós-TAREFA-314:
   helper único de masking, probes totalmente mascarados e payload reduzido no juiz.

**Recomendação de merge:** `Request changes`
