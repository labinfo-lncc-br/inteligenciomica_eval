# M3_TAREFA-311_D — Correções ciclo C (proveniência completa + wiring offline-safe)

**Data**: 2026-06-05  
**Milestone**: M3 — Orquestração e E2E  
**Tarefa**: TAREFA-311  
**Prompt auditado**: `docs/prompts_m3_tarefa_311.md` (Prompt B)  
**Status**: **FAIL / Request changes**

---

## Escopo da auditoria

Reauditoria do ciclo C após a resposta do desenvolvedor indicando correção de todos os
itens bloqueadores/importantes da auditoria B.

Validação executada sobre:
- implementação atual no workspace;
- testes unitários e suíte `not integration`;
- aderência literal ao prompt `M3-311B`.

---

## Findings

### 1. BLOQUEADOR — proveniência antiga do writer/report continua sem preenchimento real

**Referências**
- `src/inteligenciomica_eval/infrastructure/wiring.py:534`
- `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:214`
- `src/inteligenciomica_eval/application/use_cases/run_experiment.py:262`

**Problema**

Os 3 campos novos (`server_mode`, `served_model_id`, `determinism_verified`) agora entram
em `EvaluationResult`, mas a proveniência já existente do writer continua praticamente sem
alimentação real no ciclo principal:

- `ParquetStorage` é instanciado em `build_container()` apenas com `base_dir` e `round_id`;
- `to_row()` continua lendo `vllm_version`, `config_hash`, `judge_model`,
  `embedding_model`, `prompt_version`, `top_k`, etc. de `RowProvenance`;
- esses campos ficam nos defaults do writer;
- `ExperimentReport.config_hash` segue sendo `sha256(round_id)[:8]`, não o hash canônico
  da configuração via `infrastructure.config.provenance.config_hash`.

**Impacto**

O prompt 311 exige endurecimento de proveniência e rastreabilidade, incluindo mudança da
fonte de `vllm_version` e run report com `config_hash`. No estado atual, a trilha de
proveniência segue parcial/inconsistente entre linha e report.

---

### 2. BLOQUEADOR — gates declarados pelo desenvolvedor não reproduzem; wiring continua quebrando offline

**Referências**
- `src/inteligenciomica_eval/infrastructure/wiring.py:556`
- `tests/unit/infrastructure/test_wiring_external.py:203`
- `tests/unit/infrastructure/test_wiring_external.py:252`

**Problema**

Os testes de wiring continuam falhando porque `build_container()` ainda instancia
`RAGASLayer1Adapter` eagermente e tenta resolver embeddings/HuggingFace durante a
construção do container, inclusive nos cenários cujo objetivo do teste é apenas validar a
seleção do `server_manager`.

Falhas reproduzidas:
- `test_build_container_external_mode_uses_external_manager`
- `test_build_container_managed_mode_skips_external_manager`

**Impacto**

Isso contradiz diretamente o resumo do desenvolvedor (“todos os bloqueadores e
importantes corrigidos” e suíte verde) e impede aprovar a tarefa sob critério objetivo.

---

### 3. IMPORTANTE — `endpoints_provenance` ainda não atende o contrato pedido no prompt

**Referências**
- `src/inteligenciomica_eval/infrastructure/wiring.py:342`
- `src/inteligenciomica_eval/application/use_cases/run_experiment.py:382`

**Problema**

O report agora carrega `endpoints_provenance`, mas a estrutura atual permanece abaixo do
que o prompt pede. Faltam, ao menos:

- endpoint mascarado por endpoint;
- `config_hash`;
- nota de topologia;
- `healthy` por gerador;
- `vllm_version` por gerador.

Hoje o judge tem estrutura mais rica, enquanto os geradores ficam só com
`served_model_id`.

**Impacto**

Entrega parcial do item 6 do prompt. O run report melhorou, mas não está completo em
termos de auditabilidade do run.

---

### 4. IMPORTANTE — `_run_external_probes()` ainda deixa warning de coroutine não aguardada

**Referências**
- `src/inteligenciomica_eval/cli.py:309`
- `src/inteligenciomica_eval/cli.py:349`

**Problema**

Nos testes de CLI, quando `asyncio.run` é mockado, o coroutine criado por `_run_probes()`
fica sem await e a suíte emite:

`RuntimeWarning: coroutine '_run_external_probes.<locals>._run_probes' was never awaited`

**Impacto**

Não bloqueia o fluxo funcional principal, mas a suíte não está limpa e o item do ciclo C
não pode ser considerado totalmente resolvido.

---

### 5. IMPORTANTE — divergência formal de ADR permanece

**Referências**
- `docs/adr/ADR-014-server-mode-external.md:1`
- `docs/prompts_m3_tarefa_311.md`

**Problema**

O prompt pede `ADR-013`, mas a implementação segue registrada como `ADR-014`.

**Impacto**

Divergência formal de entregável. Pode ser aceitável por convenção local, mas precisa ser
explicitamente alinhada; do ponto de vista literal do prompt, permanece inconsistente.

---

## Gates executados

| Gate | Resultado |
|------|-----------|
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` | ✅ PASS |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src` | ✅ PASS |
| `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` | ✅ PASS |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/test_external_server_manager.py tests/unit/infrastructure/test_endpoint_probe.py tests/unit/infrastructure/test_provenance_columns.py tests/unit/infrastructure/test_wiring_external.py tests/unit/cli/test_run_external.py -q` | ❌ `2 failed, 70 passed` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m 'not integration' --cov-fail-under=85 -n 4 -q` | ❌ `2 failed, 1250 passed, 6 skipped` |

### Falhas reproduzidas

- `tests/unit/infrastructure/test_wiring_external.py::test_build_container_external_mode_uses_external_manager`
- `tests/unit/infrastructure/test_wiring_external.py::test_build_container_managed_mode_skips_external_manager`

### Warning relevante observado

- `RuntimeWarning: coroutine '_run_external_probes.<locals>._run_probes' was never awaited`

---

## Conclusão

O ciclo C corrigiu parte relevante da auditoria B, principalmente o fluxo dos 3 novos
campos de proveniência em `EvaluationResult`. Mesmo assim, a entrega ainda **não** passa
na auditoria `311B` por dois motivos centrais:

1. os gates declarados como verdes pelo desenvolvedor não reproduzem no estado atual;
2. a proveniência/run report continuam incompletos frente ao que o prompt exige.

**Veredito final**: **FAIL / Request changes**

---

## Próximo ciclo recomendado

1. Preencher `ParquetStorage` com a proveniência completa da rodada no `build_container()`
   usando os dados já disponíveis de config/provenance/probes.
2. Trocar `ExperimentReport.config_hash` para o hash canônico real da config.
3. Completar `endpoints_provenance` com endpoint mascarado, `config_hash`, topologia,
   `healthy` e `vllm_version` por endpoint.
4. Corrigir o acoplamento do wiring aos adapters pesados para que os testes de wiring
   não dependam de carga de embeddings/rede externa.
5. Eliminar o warning de coroutine não aguardada em `_run_external_probes()`.
6. Alinhar formalmente a numeração do ADR (`013` vs `014`).
