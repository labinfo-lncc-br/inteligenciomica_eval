# M3_TAREFA-311_E — Correções ciclo D (proveniência completa + wiring offline-safe)

**Data**: 2026-06-05
**Milestone**: M3 — Orquestração e E2E
**Épico**: E3
**Skill**: implementação direta (Claude Code)
**Prioridade / Tamanho**: P0 / M
**Ciclo**: E (correções após auditoria Codex ciclo D — FAIL)

---

## Objetivo

Corrigir os 2 bloqueadores e 3 itens importantes identificados pela auditoria D:

1. **BLOCKER**: `ParquetStorage` criado sem proveniência real — `judge_model`, `embedding_model`, `vllm_version`, `config_hash`, `prompt_version` ficavam em defaults vazios.
2. **BLOCKER**: `config_hash` em `run_experiment.py:262` era `sha256(round_id)[:8]`, não o hash canônico da config; testes de wiring falhavam offline (HuggingFace eager loading).
3. **IMPORTANTE**: `endpoints_provenance` incompleto — faltavam URLs mascaradas, `config_hash`, nota de topologia, `vllm_version`/`healthy` por gerador.
4. **IMPORTANTE**: RuntimeWarning `coroutine ... was never awaited` nos testes de CLI.
5. **IMPORTANTE**: Referências ADR-013 em comentários (ADR-013 = round2-funnel; entrega é ADR-014).

---

## Arquivos Modificados

| Arquivo | Alteração |
|---------|-----------|
| `src/inteligenciomica_eval/application/use_cases/run_experiment.py` | Remove `import hashlib`; `ExperimentConfigView` +`config_hash: str`; `_run()` usa `self._config.config_hash[:8]` |
| `src/inteligenciomica_eval/infrastructure/wiring.py` | `_ExperimentConfig` +`config_hash`; nova função `_mask_url()`; `_run_endpoint_probes` +`config_hash` param + `vllm_version`/`healthy` por gerador + URLs mascaradas + nota de topologia; `build_container` importa `collect_provenance`, calcula `_prov`, passa `config_hash` p/ probes, move `get_default_registry()` antes do storage, popula `ParquetStorage` com todos os campos; `exp_config.config_hash = _prov.config_hash`; ADR-013→ADR-014 |
| `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py` | ADR-013→ADR-014 |
| `tests/unit/application/use_cases/test_run_experiment.py` | `_Config` stub +`config_hash: str = "abcd1234" * 8`; ADR-013→ADR-014 |
| `tests/unit/infrastructure/test_wiring_external.py` | +`MagicMock` import; fixture `autouse _patch_hf_embeddings` mocka `_build_embeddings` (offline-safe) |
| `tests/unit/cli/test_run_external.py` | Novo helper `_make_asyncio_run_mock(return_value)` com `side_effect` que fecha coroutine; 3 testes convertidos |
| `tests/e2e/test_m3_full_cycle.py` | `_StubExpConfig` +`config_hash`; `endpoints_provenance` enriquecido; ADR-013→ADR-014 |

---

## Decisões Técnicas

### D1 — `config_hash` canônico via `collect_provenance(config)`
`collect_provenance()` calcula SHA-256 canônico de `RoundConfig` (`json.dumps(model_dump, sort_keys=True)`). Em `build_container()`: `_prov = collect_provenance(config)` → `_prov.config_hash` passado para `_ExperimentConfig`, `ParquetStorage`, e `_run_endpoint_probes`. Em `run_experiment.py`, `_run()` usa `self._config.config_hash[:8]` sem hashlib.

### D2 — `ParquetStorage` com proveniência real
Todos os campos de `RowProvenance` agora populados: `judge_model`, `embedding_model`, `chunk_strategy`, `reranker or "none"`, `top_k`, `temperature`, `vllm_version` (probe do juiz → fallback pkg metadata), `ragas_version`, `config_hash`, `prompt_version`.

### D3 — `_mask_url()` e `endpoints_provenance` enriquecido
Nova função helper `_mask_url(url)` retorna `scheme://host:port/***`. No loop de geradores, além de `probe_served_model`, agora também `probe_vllm_version`. Dict `ep_prov` recebe `config_hash`, `topology` (nota legível) e cada endpoint com `vllm_version`, `endpoint_masked`, `healthy`.

### D4 — `_patch_hf_embeddings` autouse em test_wiring_external.py
Fixture `autouse=True` mocka `_build_embeddings` → sem carregamento de HuggingFace offline. Os testes de wiring validam tipo do `server_manager`, não RAGAS.

### D5 — Coroutine fechada no mock de `asyncio.run`
`_make_asyncio_run_mock(return_value)` retorna `side_effect` que chama `coro.close()` → elimina `RuntimeWarning: coroutine ... was never awaited`. Verificado com `-W error::RuntimeWarning`.

### D6 — ADR-014 consistente em todo o codebase
Substituído ADR-013 por ADR-014 em wiring.py, parquet_storage.py, e todos os stubs de teste afetados.

---

## Validação (DoD)

| Gate | Resultado |
|------|-----------|
| `ruff check .` | ✅ All checks passed |
| `ruff format --check .` | ✅ |
| `mypy --strict src` | ✅ no issues found in 60 source files |
| `lint-imports` | ✅ 4 contratos KEPT |
| `pytest -m "not integration" --cov-fail-under=85 -n 4` | ✅ **1252 passed**, 6 skipped — **89.51%** |
| `pytest test_run_external.py -W error::RuntimeWarning` | ✅ 5 passed, 0 RuntimeWarnings |

---

## Critérios de Aceitação Ciclo D → E

| Bloqueador/Importante | Status |
|-----------------------|--------|
| ParquetStorage com todos os campos de proveniência | ✅ collect_provenance + todos os kwargs |
| `config_hash` canônico em ExperimentReport | ✅ `self._config.config_hash[:8]` |
| `endpoints_provenance` com URLs mascaradas, config_hash, topologia, vllm/healthy por gerador | ✅ |
| RuntimeWarning eliminado nos testes de CLI | ✅ side_effect fecha coroutine |
| test_wiring_external.py offline-safe | ✅ fixture `_patch_hf_embeddings` autouse |
| Referências ADR-013→ADR-014 | ✅ wiring.py, parquet_storage.py, testes |
