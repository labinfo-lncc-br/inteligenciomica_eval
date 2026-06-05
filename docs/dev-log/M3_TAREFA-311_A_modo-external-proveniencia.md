# M3_TAREFA-311_A — Modo External e Proveniência de Endpoint

**Data**: 2026-06-05  
**Milestone**: M3 — Orquestração e E2E  
**Épico**: E3  
**Skill**: implementação direta (Claude Code)  
**Prioridade / Tamanho**: P1 / L

---

## Objetivo

Adicionar suporte a servidores vLLM pré-existentes (modo `external`) acessados via
túnel SSH/ngrok, incluindo:

1. `ExternalVLLMServerManager` — adapter VLLMServerManagerPort sem subprocess (no-op start/stop, polling `/health`).
2. Probes de proveniência (`probe_served_model`, `probe_vllm_version`, `probe_judge_determinism`) via `httpx`.
3. 3 novas colunas Parquet: `server_mode`, `served_model_id`, `determinism_verified`.
4. Campo `server_mode` em `RoundConfig`; campo `endpoint_env` em `ModelEntry`.
5. Flag CLI `--require-verified-determinism` com painel Rich de aviso.
6. ADR-014 documentando a decisão de arquitetura.
7. 5 novos arquivos de teste (58 novos testes).
8. Wiring atualizado para selecionar adapter conforme `server_mode`.

---

## Arquivos Criados / Modificados

### Novos arquivos

| Arquivo | Descrição |
|---------|-----------|
| `src/inteligenciomica_eval/infrastructure/provenance/__init__.py` | Init do subpacote `provenance` |
| `src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py` | Probes HTTP: `probe_served_model`, `probe_vllm_version`, `probe_judge_determinism` |
| `src/inteligenciomica_eval/infrastructure/adapters/external_vllm_server_manager.py` | `ExternalVLLMServerManager` — implementa `VLLMServerManagerPort` sem subprocess |
| `docs/adr/ADR-014-server-mode-external.md` | ADR aprovado: modo external, responsabilidade de determinismo migra ao operador |
| `tests/unit/infrastructure/test_endpoint_probe.py` | 12 testes das probes HTTP |
| `tests/unit/infrastructure/test_external_server_manager.py` | 18 testes do adapter externo |
| `tests/unit/infrastructure/test_provenance_columns.py` | Testes das 3 novas colunas Parquet |
| `tests/unit/infrastructure/test_wiring_external.py` | Testes do seletor de adapter no wiring |
| `tests/unit/cli/test_run_external.py` | 5 testes CLI `--require-verified-determinism` |

### Arquivos modificados

| Arquivo | Alteração |
|---------|-----------|
| `src/inteligenciomica_eval/domain/errors.py` | Novo `EndpointUnreachableError(model_name, reason)` |
| `src/inteligenciomica_eval/domain/ports.py` | `ServerHandle.pid: int | None` (antes `int`) |
| `src/inteligenciomica_eval/domain/entities.py` | `EvaluationResult` +3 campos: `server_mode`, `served_model_id`, `determinism_verified` |
| `src/inteligenciomica_eval/infrastructure/config/schema.py` | `RoundConfig.server_mode: Literal["managed","external"] = "managed"` |
| `src/inteligenciomica_eval/infrastructure/config/model_registry.py` | `ModelEntry.endpoint_env: str | None = None` |
| `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py` | 3 novas colunas PyArrow, `to_row()`/`from_row()` atualizados |
| `src/inteligenciomica_eval/infrastructure/wiring.py` | Seletor `server_mode`, helper `_build_external_server_manager`; `Any` adicionado ao typing |
| `src/inteligenciomica_eval/cli.py` | `--require-verified-determinism`, `_run_external_probes()`, imports `asyncio`/`build_container` no nível de módulo |
| `src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py` | `assert handle.pid is not None` em `_fail`/`_force_kill` (mypy strict) |
| `tests/unit/cli/test_run_real.py` | Patch target atualizado: `inteligenciomica_eval.cli.build_container` (era `wiring.build_container`) |
| `tests/golden/e2e_m3_expected.json` | Colunas `server_mode`, `served_model_id`, `determinism_verified` adicionadas |

---

## Decisões Técnicas

### D1 — `pid: int | None` em `ServerHandle`
O campo `pid` mudou de `int` para `int | None` para acomodar servidores externos
(sem subprocess local). O `VLLMServerManagerAdapter` (modo managed) sempre tem
`pid != None`; adicionamos `assert handle.pid is not None` em `_fail` e `_force_kill`
para satisfazer mypy `--strict` sem perder a intenção.

### D2 — `ExternalVLLMServerManager` implementa `VLLMServerManagerPort` sem herança
O adapter implementa o Protocol via duck-typing, sem declarar `implements`. `isinstance`
permanece válido pois `VLLMServerManagerPort` é `@runtime_checkable`.

### D3 — Probes em `infrastructure/provenance/` (não em `adapters/`)
Probes são utilitários de diagnóstico, não adapters de porta. Subpacote `provenance/`
mantém a separação de responsabilidades.

### D4 — `_build_external_server_manager` com `manager_cls: type[Any]`
A função helper recebe a classe `ExternalVLLMServerManager` como argumento para
evitar import circular no topo de `wiring.py` (o adapter é importado lazily dentro
de `build_container`). O tipo de retorno é `Any` (documentado) para satisfazer o
assignment tipado na variável `server_manager: VLLMServerManagerPort`.

### D5 — imports de `asyncio` e `build_container` no nível de módulo em `cli.py`
Para que `patch("inteligenciomica_eval.cli.asyncio.run")` e
`patch("inteligenciomica_eval.cli.build_container")` funcionem nos testes unitários,
esses nomes devem existir como atributos do módulo `cli` em tempo de coleta.
Imports lazy dentro de funções tornam o target de mock inacessível.

### D6 — ADR numerado como 014 (não 013)
`ADR-013` já estava reservado para `round2-funnel`. O novo ADR de server mode
foi alocado como ADR-014.

---

## Problemas Encontrados e Soluções

### P1 — `import httpx` tardio em `endpoint_probe.py` e `external_vllm_server_manager.py`
**Problema**: testes tentavam `patch("endpoint_probe.httpx.AsyncClient")`, mas `httpx`
não era atributo do módulo (import dentro de função).  
**Solução**: mover `import httpx` e `import asyncio` para o topo de cada módulo.

### P2 — `EndpointUnreachableError` com assinatura duplicada e incompatível
**Problema**: sessão anterior criou uma versão 3-arg (`endpoint_name, masked_url, timeout_s`);
a versão correta do domínio tem 2 args (`model_name, reason`).  
**Solução**: remover a versão duplicada; atualizar todas as chamadas para `(model_name, reason)`.

### P3 — `test_run_real.py` quebrou após tornar `build_container` import de módulo
**Problema**: testes antigos patcheavam `inteligenciomica_eval.infrastructure.wiring.build_container`;
depois que `cli.py` passou a importar diretamente, o patch deixou de interceptar.  
**Solução**: substituir todos os 5 targets por `inteligenciomica_eval.cli.build_container`.

### P4 — `_print_run_summary` falhava com `MagicMock.duration_s`
**Problema**: `f"{report.duration_s:.1f}"` não funciona em `MagicMock` — `TypeError`.  
**Solução**: setar `mock_report.duration_s = 0.0` e `mock_report.run_id = "test-run"` na fixture.

### P5 — mypy `no-any-return` em `endpoint_probe.py:122`
**Problema**: `resp.json()["choices"][0]["message"]["content"]` retorna `Any`; a comparação
`text1 == text2` também é `Any` na visão do mypy.  
**Solução**: anotar explicitamente `text1: str` e `text2: str` nas atribuições.

### P6 — mypy `arg-type` em `vllm_server_manager.py` com `handle.pid: int | None`
**Problema**: métodos internos `_collect_stderr_tail`, `_cancel_drains`, `_forget`, `_signal`
esperam `int` mas `handle.pid` agora é `int | None`.  
**Solução**: `assert handle.pid is not None` no início de `_fail` e `_force_kill` (único ponto
de entrada para esses métodos no adapter managed). Invariante documentado no assert.

---

## Validação (DoD)

| Gate | Resultado |
|------|-----------|
| `ruff check .` | ✅ All checks passed |
| `ruff format --check .` | ✅ 170 files already formatted |
| `mypy --strict src` | ✅ no issues found in 60 source files |
| `lint-imports` | ✅ 4 contratos KEPT, 0 broken |
| `pytest -m "not integration" --cov-fail-under=85 -n 4` | ✅ 1252 passed, 6 skipped — **89.72%** |

---

## Critérios de Aceitação

| # | Critério | Status |
|---|----------|--------|
| CA-1 | `ExternalVLLMServerManager` implementa `VLLMServerManagerPort` | ✅ |
| CA-2 | `start()` resolve URL via `endpoint_map`; `stop()` é no-op | ✅ |
| CA-3 | `wait_healthy()` faz polling `/health`; levanta `EndpointUnreachableError` em timeout | ✅ |
| CA-4 | Probes `probe_served_model`, `probe_vllm_version`, `probe_judge_determinism` | ✅ |
| CA-5 | 3 novas colunas Parquet: `server_mode`, `served_model_id`, `determinism_verified` | ✅ |
| CA-6 | `RoundConfig.server_mode` e `ModelEntry.endpoint_env` com defaults retrocompat | ✅ |
| CA-7 | CLI `--require-verified-determinism`: exit 1 se probe False | ✅ |
| CA-8 | ADR-014 criado e aprovado | ✅ |
| CA-9 | Wiring seleciona adapter conforme `server_mode` | ✅ |
| CA-10 | Gates: mypy, ruff, lint-imports, pytest ≥ 85% | ✅ |

---

## Observações para Próximas Tarefas

- `ServerHandle.pid: int | None` é um PR retroativo que afeta qualquer código que
  assuma `pid` nunca é `None`. Revisar em M4/M5 se algum use case acessa `handle.pid` diretamente.
- A probe `probe_judge_determinism` faz 2 chamadas ao endpoint com `seed=42, temperature=0.0`
  e compara as respostas. Em modelos grandes com geração não-determinística no nível de
  atenção (flash attention), pode retornar False mesmo em configuração determinística —
  documentado no ADR-014.
- `ExternalVLLMServerManager` não valida `batch_invariant` contra a configuração real do
  servidor (é responsabilidade do operador). `require_verified_determinism` cobre o juiz,
  não os geradores.
