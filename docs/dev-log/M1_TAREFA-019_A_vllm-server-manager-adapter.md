# M1_TAREFA-019_A — VLLMServerManagerAdapter

**Data**: 2026-05-28
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1 — Adapters de Recuperação
**Skill**: python-engineer, backend-engineer
**Prioridade / Tamanho**: P1 / M

## Objetivo

Implementar o `VLLMServerManagerAdapter` em
`src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py`, que orquestra
o ciclo de vida de servidores vLLM locais via `asyncio.create_subprocess_exec` (Nota M1
item 9 — sem Docker SDK), expondo `start` / `wait_healthy` / `stop` + `close()`.

## Arquivos Criados / Modificados

| Arquivo | Ação | Observação |
|---------|------|------------|
| `src/.../adapters/vllm_server_manager.py` | **Criado** | Adapter completo (100% cobertura) |
| `tests/unit/.../adapters/test_vllm_server_manager.py` | **Criado** | 21 testes (subprocess mock + respx) |
| `src/.../domain/ports.py` | Modificado | **PR retroativo**: `ModelSpec`/`ServerHandle` redesenhados + `VLLMServerManagerPort` promovido a `async` |
| `tests/fakes/servers.py` | Modificado | `FakeVLLMServerManager` async + novos campos dos DTOs |
| `tests/unit/domain/test_ports_contract.py` | Modificado | `_StubVLLMServerManager` async; `test_model_spec`/`test_server_handle`/lifecycle atualizados |
| `tests/unit/fakes/test_fakes_satisfy_ports.py` | Modificado | `TestFakeVLLMServerManager` async + teste de `batch_invariant` |
| `pyproject.toml` | Modificado | `httpx>=0.27` declarado como dep direta de runtime |
| `uv.lock` | Modificado | Relock (httpx promovido de transitivo a direto) |

## Decisões Técnicas

### 1. PR retroativo em `domain/ports.py` — DTOs e promoção do port a async

A spec (Prompt A, linhas 836-841) exige `ModelSpec`/`ServerHandle` com campos diferentes
dos definidos em M0/TAREFA-005:

- **`ModelSpec`**: `model`, `port`, `quantization: str | None`, `tensor_parallel_size`,
  `max_model_len`, `extra_env: dict[str, str]` (antes: `model_id`,
  `tensor_parallel_size`, `gpu_memory_utilization`).
- **`ServerHandle`**: `pid`, `url`, `model`, `batch_invariant: bool` (antes: `process_id`,
  `base_url`, `model_id`).

Além disso, o **Prompt A manda usar `await asyncio.create_subprocess_exec`,
`httpx.AsyncClient` e `async close()`** — incompatíveis com métodos síncronos. Isso e a
**Nota M1 item 1** (que lista `VLLMServerManagerAdapter` entre os adapters async-first)
implicam promover `start`/`wait_healthy`/`stop` de `def` para `async def`. Mesma natureza
de PR retroativo aplicado a `RetrieverPort`/`GeneratorPort` (item 1), `RubricJudgePort`
(016-D), `MetricSuitePort` (017). `isinstance(adapter, VLLMServerManagerPort)` continua
válido (`runtime_checkable` verifica presença de método, não sincronicidade), e os fakes
e stubs foram atualizados para async.

### 2. `close()` é extensão de ciclo de vida — fora do port (I3)

Igual ao `QdrantRetrieverAdapter.close` (Nota M1 item 1): `close()` para todos os handles
ainda vivos (rastreados internamente em `_handles`), mas **não** faz parte de
`VLLMServerManagerPort`. O `FakeVLLMServerManager` não precisa implementá-lo.

### 3. Juiz vs. gerador (§9.2) visível no código — bloqueador do Prompt B

`ServerHandle.batch_invariant = "VLLM_BATCH_INVARIANT" in model.extra_env`. As variáveis
`VLLM_BATCH_INVARIANT`/`VLLM_ENABLE_V1_MULTIPROCESSING` **nunca** são *hardcoded* no
`start()`: aparecem apenas se o caller as colocou no `ModelSpec.extra_env`. Isso atende
explicitamente aos itens 2 e 3 (bloqueadores) do Prompt B — a decisão arquitetural de
§9.2 fica no código, não só nos testes.

### 4. `start` lança via `create_subprocess_exec` (shell=False) + env estendido

Comando montado como **lista de args** (`sys.executable -m vllm.entrypoints.openai.
api_server --model … --port … --tensor-parallel-size … --max-model-len … [--quantization
…]`) — `shell=False` por construção (a API `_exec` não usa shell), sem risco de injeção
(DoD §14.2). `env={**os.environ, **model.extra_env}` **estende** o ambiente do processo,
não o substitui. Usa-se `sys.executable` (python do venv) em vez de `"python"` literal —
mais robusto, ainda sem shell.

### 5. `wait_healthy` faz polling em `/health` (não em `start`)

Polling de `GET {url sem /v1}/health` via `httpx.AsyncClient` a cada `_poll_interval_s`
(default 2 s) até o deadline (`_clock() + timeout_s`). `200` → retorna; erro de rede
transitório (`httpx.HTTPError`, servidor ainda subindo) → tratado como "não saudável" e
retry. Em timeout: `_force_kill` (SIGKILL) + `ServerStartTimeoutError` (não `TimeoutError`
genérico — erro de domínio já existente em `errors.py`).

### 6. `stop` faz SIGTERM → espera → SIGKILL (nunca SIGKILL direto)

`os.kill(pid, SIGTERM)` → `asyncio.wait_for(process.wait(), timeout=_sigterm_timeout_s)`
(default 30 s) → em `TimeoutError`, `os.kill(pid, SIGKILL)` + reaping. Log
`vllm_server_stopped` com `forced: bool`. `ProcessLookupError` (processo já morto) é
absorvido — não escala nem propaga.

### 7. Testabilidade determinística (convenção `_` do projeto)

`_poll_interval_s`, `_sigterm_timeout_s` e `_clock` são injetáveis (mesma convenção dos
`_retry_stop`/`_retry_wait`). O timeout de `wait_healthy` é exercitado com um relógio
falso (`itertools.count`) que ultrapassa o deadline em poucos polls — **sem espera de
relógio real** (suíte focada roda em 0,37 s). O caminho SIGKILL de `stop` usa um
`process.wait()` que bloqueia só na 1ª chamada (cancelada pelo `wait_for`) e retorna na 2ª.

### 8. Estratégia de teste (Nota M1 item 7)

- `asyncio.create_subprocess_exec` mockado via pytest-mock (alvo string → mypy limpo
  também no arquivo de teste).
- `respx` para `/health` — confirmado por probe que intercepta `httpx.AsyncClient` direto
  (o problema de §11 do CLAUDE.md era específico do SDK OpenAI + `asyncify`, não se aplica
  aqui).
- `os.kill` mockado (sem sinais reais ao SO).

## Validação (DoD)

```
uv run ruff check .            → All checks passed!
uv run ruff format --check .   → 80 files already formatted
uv run mypy --strict src       → Success: no issues found in 29 source files
uv run mypy --strict tests/.../test_vllm_server_manager.py → Success (preempção da observação 018-B)
uv run lint-imports            → 4 kept, 0 broken
uv run pytest tests/.../test_vllm_server_manager.py → 21 passed
uv run pytest --cov ... -n 4   → 677 passed, 7 skipped — 96.68% total; vllm_server_manager.py 100% (96/96, 12 branches)
```

## Critérios de Aceitação (TAREFA-019)

| Critério | Evidência | Resultado |
|----------|-----------|-----------|
| `extra_env={"VLLM_BATCH_INVARIANT":"1"}` → `handle.batch_invariant=True` | `TestStart.test_judge_handle_batch_invariant_true` | PASS |
| sem BATCH_INVARIANT → `batch_invariant=False` | `TestStart.test_generator_handle_batch_invariant_false` | PASS |
| `wait_healthy(timeout_s=10)` levanta `ServerStartTimeoutError` quando /health nunca 200 | `TestWaitHealthy.test_timeout_raises_and_kills_process` | PASS |
| SIGTERM em `stop`; SIGKILL após timeout | `TestStop.test_sigterm_then_clean_exit` / `test_escalates_to_sigkill_on_timeout` | PASS |
| `isinstance(adapter, VLLMServerManagerPort)` | `TestProtocolConformance.test_satisfies_port` | PASS |
| `shell=False`; `env={**os.environ, **extra_env}` | `TestStart.test_command_built_without_shell` / `test_env_extends_os_environ_with_extra_env` | PASS |
| sem `is_healthy()` no adapter | `TestProtocolConformance.test_no_is_healthy_method` | PASS |

## Observações para Próximas Tarefas

- Pronto para auditoria (Prompt B). Foco esperado: itens 2 e 3 (bloqueadores — juiz/gerador
  via `extra_env`, não hardcoded) e item 4 (polling em `wait_healthy`, não em `start`).
- O smoke E2E da TAREFA-021 exercitará o manager (não o pipeline de pergunta única —
  spec linha 1100).
- §9.3 do documento de arquitetura traz os comandos exatos dos dois servidores; o adapter
  monta o comando a partir do `ModelSpec` (genérico) — se a 021 exigir flags adicionais
  (ex.: `--dtype`, `--seed`), estender `ModelSpec` + `_build_command`.
