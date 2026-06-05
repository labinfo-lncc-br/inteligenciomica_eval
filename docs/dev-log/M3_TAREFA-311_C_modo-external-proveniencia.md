# M3_TAREFA-311_C — Correções ciclo B (proveniência + wiring + probes)

**Data**: 2026-06-05  
**Milestone**: M3 — Orquestração e E2E  
**Épico**: E3  
**Skill**: implementação direta (Claude Code)  
**Prioridade / Tamanho**: P0 / L  
**Ciclo**: C (correções após auditoria Codex ciclo B — FAIL)

---

## Objetivo

Corrigir os 3 bloqueadores e 3 itens importantes identificados pela auditoria B:

1. **BLOCKER**: Proveniência real nunca entrava no fluxo de escrita (EvaluationResult com defaults).
2. **BLOCKER**: ExperimentReport sem `endpoints_provenance`.
3. **BLOCKER**: Wiring instanciava adapters pesados antes da validação external (fail-fast quebrado).
4. **IMPORTANTE**: `wait_healthy()` aceitava qualquer status < 500 como saudável.
5. **IMPORTANTE**: `probe_vllm_version()` sem fallback via header/`/v1/models`.
6. **IMPORTANTE**: `_run_external_probes()` resolvia `model_registry_path` relativo ao CWD.

---

## Arquivos Modificados

| Arquivo | Alteração |
|---------|-----------|
| `src/inteligenciomica_eval/application/use_cases/run_generation_pass.py` | `RunConfigView` +3 campos; `_generate_one_cell()` preenche proveniência em `EvaluationResult` |
| `src/inteligenciomica_eval/application/use_cases/run_experiment.py` | `ExperimentConfigView` +2 campos; `ExperimentReport.endpoints_provenance`; construção do report |
| `src/inteligenciomica_eval/infrastructure/wiring.py` | `_ExperimentConfig` +4 campos; nova função `_run_endpoint_probes()`; server_manager movido para ANTES dos adapters pesados; probes executados em ambos os modos |
| `src/inteligenciomica_eval/infrastructure/adapters/external_vllm_server_manager.py` | `wait_healthy()`: status < 300 (era < 500) |
| `src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py` | `probe_vllm_version()`: 3 fontes em ordem (JSON, header `/version`, header `/v1/models`) |
| `src/inteligenciomica_eval/cli.py` | `_run_external_probes()` +`config_dir` param; path resolution corrigida; chamada atualizada com `config_dir=config.parent` |
| `tests/unit/application/use_cases/test_run_generation_pass.py` | `_Config` stub +3 campos de proveniência |
| `tests/unit/application/use_cases/test_run_experiment.py` | `_Config` stub +2 campos de proveniência |
| `tests/unit/infrastructure/test_endpoint_probe.py` | `_mock_response` +`x_vllm_version` param + `resp.headers` mock |
| `tests/e2e/test_m3_full_cycle.py` | `_StubExpConfig` +4 campos de proveniência (com values de stub) |
| `tests/unit/cli/test_run_real.py` | `ExperimentReport` instantiation +`endpoints_provenance={}` |

---

## Decisões Técnicas

### D1 — `RunConfigView` recebe campos de proveniência (sem deps de infrastructure)
Os 3 campos `server_mode: str`, `generator_served_model_ids: dict[str, str]`,
`judge_determinism_verified: bool` são tipos primitivos — nenhuma violação de
import-linter Contract 2/4 (application NÃO importa infrastructure).

### D2 — `_run_endpoint_probes()` usa `asyncio.new_event_loop()` em `build_container()` sync
`build_container()` é chamada de contexto síncrono (CLI, antes do `asyncio.run()`).
Criar um novo loop dedicado evita conflito com qualquer loop preexistente. Best-effort:
toda exceção é capturada e produz valores sentinela.

### D3 — Probes em AMBOS os modos (managed e external)
O spec §3 diz "rodam em ambos os modos como auditoria". Implementado em `_run_endpoint_probes()`
chamada por `build_container()` independente de `server_mode`.

### D4 — `_ExperimentConfig` como veículo de proveniência
`_ExperimentConfig` é infra-específico (definido em wiring.py); adicionar campos a ele
não viola a arquitetura. Os Protocols `RunConfigView`/`ExperimentConfigView` expõem
apenas os campos que cada use case precisa.

### D5 — `ExperimentReport.endpoints_provenance: dict[str, object]`
Usa `dict[str, object]` (não `Any`) para satisfazer mypy --strict sem introduzir
dependência de tipos de infrastructure na camada application.

---

## Validação (DoD)

| Gate | Resultado |
|------|-----------|
| `ruff check .` | ✅ All checks passed |
| `ruff format --check .` | ✅ 170 files formatted |
| `mypy --strict src` | ✅ no issues found in 60 source files |
| `lint-imports` | ✅ 4 contratos KEPT |
| `pytest -m "not integration" --cov-fail-under=85 -n 4` | ✅ 1252 passed, 6 skipped — **89.50%** |

---

## Critérios de Aceitação Ciclo B → C

| Bloqueador/Importante | Status |
|-----------------------|--------|
| Proveniência real em EvaluationResult por linha | ✅ RunConfigView + _generate_one_cell() |
| ExperimentReport.endpoints_provenance | ✅ Adicionado + propagado |
| Wiring fail-fast antes de adapters pesados | ✅ server_manager selecionado primeiro |
| wait_healthy() aceita apenas 2xx | ✅ status < 300 |
| probe_vllm_version() com 3 fontes de fallback | ✅ /version, header, /v1/models |
| _run_external_probes() resolve path relativo à config | ✅ config_dir param + config.parent |
