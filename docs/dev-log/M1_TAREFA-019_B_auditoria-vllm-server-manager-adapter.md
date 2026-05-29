# M1_TAREFA-019_B — Auditoria VLLMServerManagerAdapter

**Data**: 2026-05-28
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1 — Adapters de Recuperação
**Skill**: code-reviewer, test-engineer
**Prioridade / Tamanho**: P1 / M
**Resultado**: FAIL / Request changes

## Objetivo

Auditar a implementação da TAREFA-019-A (`VLLMServerManagerAdapter`) contra o Prompt B
das linhas 881-905 de `docs/prompts_m1_tarefas_013_021_corrigido.md`, com foco em:

- subprocess seguro via `asyncio.create_subprocess_exec`;
- distinção juiz/gerador exclusivamente via `ModelSpec.extra_env`;
- `ServerHandle.batch_invariant` derivado do `extra_env`;
- polling de `/health` em `wait_healthy`;
- encerramento via `SIGTERM` e escalonamento para `SIGKILL`;
- testes com subprocess mockado e `respx`;
- gates oficiais de lint, tipos, import-linter e cobertura.

## Arquivos Criados / Modificados

| Arquivo | Ação | Observação |
|---------|------|------------|
| `docs/dev-log/M1_TAREFA-019_B_auditoria-vllm-server-manager-adapter.md` | Criado | Este relatório de auditoria |

Arquivos auditados:

- `docs/dev-log/M1_TAREFA-019_A_vllm-server-manager-adapter.md`
- `docs/prompts_m1_tarefas_013_021_corrigido.md`
- `src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py`
- `src/inteligenciomica_eval/domain/ports.py`
- `tests/unit/infrastructure/adapters/test_vllm_server_manager.py`
- `tests/fakes/servers.py`
- `tests/unit/domain/test_ports_contract.py`
- `tests/unit/fakes/test_fakes_satisfy_ports.py`
- `pyproject.toml`
- `.importlinter`

## Achados

### Bloqueador — Variáveis do juiz vazam do ambiente pai para geradores

**Arquivo:**
`src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py:101-105`

O `start()` monta o ambiente do subprocess com:

```python
env={**os.environ, **model.extra_env}
```

e calcula:

```python
batch_invariant = "VLLM_BATCH_INVARIANT" in model.extra_env
```

Isso atende ao caso comum, mas falha quando o processo orquestrador já possui
`VLLM_BATCH_INVARIANT` ou `VLLM_ENABLE_V1_MULTIPROCESSING` no ambiente. Nesse cenário,
um `ModelSpec` de gerador com `extra_env={}` ainda herda as variáveis reservadas do juiz,
enquanto `ServerHandle.batch_invariant` continua `False`.

Probe executado:

```text
handle_batch_invariant= False
env_has_batch_invariant= True
env_has_v1_multiprocessing= True
```

Impacto: o servidor de gerador pode ser iniciado com regime de juiz por herança ambiental,
mas o handle/logs/proveniência indicam `batch_invariant=False`. Isso viola o item 2 do
Prompt B, que exige que `VLLM_BATCH_INVARIANT=1` e
`VLLM_ENABLE_V1_MULTIPROCESSING=0` apareçam apenas quando `model.extra_env` os contém, e
afeta a decisão arquitetural central de §9.2/ADR-003. O próprio Prompt B marca os itens
2 e 3 como bloqueadores.

Correção sugerida: construir um ambiente base que preserve `os.environ`, mas remova
explicitamente as chaves reservadas do regime do juiz antes de aplicar `model.extra_env`.
Adicionar teste com `monkeypatch.setenv("VLLM_BATCH_INVARIANT", "1")` e gerador
`extra_env={}` para garantir que essas chaves não sejam repassadas.

Exemplo conceitual:

```python
_RESERVED_JUDGE_ENV = {
    "VLLM_BATCH_INVARIANT",
    "VLLM_ENABLE_V1_MULTIPROCESSING",
}
base_env = {k: v for k, v in os.environ.items() if k not in _RESERVED_JUDGE_ENV}
env = {**base_env, **model.extra_env}
```

## Critérios do Prompt B

| Critério Prompt B | Evidência arquivo:linha | Gravidade / Resultado |
|-------------------|-------------------------|-----------------------|
| 1. `create_subprocess_exec`; lista de args; `env` estende `os.environ`; parâmetro `model` | `vllm_server_manager.py:86-104`; `_build_command` em `vllm_server_manager.py:183-200`; probe `start_signature=(self, model: 'ModelSpec')`; teste `test_command_built_without_shell` em `test_vllm_server_manager.py:139-151` | PASS |
| 2. `VLLM_BATCH_INVARIANT=1` e `VLLM_ENABLE_V1_MULTIPROCESSING=0` apenas via `model.extra_env`, sem hardcode no `start()` | `vllm_server_manager.py:101-105` usa merge bruto de `os.environ`; probe com ambiente pai contaminado mostrou as duas variáveis presentes no subprocess de gerador com `extra_env={}` | **FAIL / Bloqueador** |
| 3. `ServerHandle.batch_invariant` derivado de `"VLLM_BATCH_INVARIANT" in model.extra_env` | `vllm_server_manager.py:105-110`; testes `test_judge_handle_batch_invariant_true` e `test_generator_handle_batch_invariant_false` em `test_vllm_server_manager.py:127-137` | PASS isolado; fica incoerente no cenário do achado 2 |
| 4. Polling de `/health` em `wait_healthy()`, não em `start()`; intervalo default 2s; `ServerStartTimeoutError`; sem `is_healthy()` público | `vllm_server_manager.py:123-155`; default `_DEFAULT_POLL_INTERVAL_S=2.0` em `vllm_server_manager.py:48`; `test_start_does_not_poll_health` em `test_vllm_server_manager.py:194-203`; `test_no_is_healthy_method` em `test_vllm_server_manager.py:116-118`; probe levantou `ServerStartTimeoutError` | PASS |
| 5. `stop()` usa `SIGTERM` + espera + `SIGKILL` em timeout | `vllm_server_manager.py:157-172`; `_await_exit` em `vllm_server_manager.py:219-232`; testes em `test_vllm_server_manager.py:286-312`; probe registrou `[(333, SIGTERM), (333, SIGKILL)]` | PASS |
| 6. Testes mockam subprocess e `respx`; verificam `batch_invariant` no handle | `_patch_subprocess` em `test_vllm_server_manager.py:90-98`; `respx` em `test_vllm_server_manager.py:198-203` e `216-277`; `batch_invariant` em `test_vllm_server_manager.py:127-137` | PASS, com lacuna no caso de herança ambiental |
| 7. `mypy --strict`, `lint-imports`, cobertura >= 80% | Gates executados abaixo; cobertura total 96.68%; `vllm_server_manager.py` 100% | PASS |

## Probes Executados

### Assinatura, async e port

```text
runtime_port= True
has_is_healthy= False
start_is_async= True
wait_healthy_is_async= True
stop_is_async= True
close_is_async= True
start_signature= (self, model: 'ModelSpec') -> 'ServerHandle'
wait_signature= (self, handle: 'ServerHandle', timeout_s: 'int') -> 'None'
stop_signature= (self, handle: 'ServerHandle') -> 'None'
```

### AST do `start()`

```text
start_arg= model
uses_os_environ= True
batch_env_literal_in_start= False
multiprocessing_env_literal_in_start= False
```

O probe confirma que as variáveis não são hardcoded como literais no corpo de `start()`,
mas não impede o vazamento por `os.environ` descrito no achado bloqueador.

### Vazamento de ambiente do juiz para gerador

```text
handle_batch_invariant= False
env_has_batch_invariant= True
env_has_v1_multiprocessing= True
```

### Timeout de healthcheck

```text
raised= ServerStartTimeoutError
route_called= True
kill_calls= [(4321, <Signals.SIGKILL: 9>)]
```

### Sequência de stop em timeout

```text
signal_sequence= [(333, <Signals.SIGTERM: 15>), (333, <Signals.SIGKILL: 9>)]
```

## Validação (DoD)

| Comando / Probe | Resultado |
|-----------------|-----------|
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` | PASS — `All checks passed!` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .` | PASS — `80 files already formatted` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src` | PASS — `Success: no issues found in 29 source files` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict tests/unit/infrastructure/adapters/test_vllm_server_manager.py` | PASS — `Success: no issues found in 1 source file` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` | PASS — 68 files, 170 dependencies, 4 contracts kept, 0 broken |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -v tests/unit/infrastructure/adapters/test_vllm_server_manager.py tests/unit/domain/test_ports_contract.py tests/unit/fakes/test_fakes_satisfy_ports.py` | PASS — 116 passed |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n 4` | PASS — 677 passed, 7 skipped, 96.68%; `vllm_server_manager.py` 100% |
| Probe de assinatura/async/port | PASS |
| Probe de healthcheck timeout | PASS |
| Probe de sequência `SIGTERM` -> `SIGKILL` | PASS |
| Probe de vazamento de ambiente reservado | FAIL — variáveis do juiz herdadas por gerador com `extra_env={}` |

Warnings observados:

- `pytest-benchmark` avisa que benchmarks são desabilitados sob `xdist`.
- `ragas_metrics.py` emite `DeprecationWarning` de `langchain-community`.
- `bert_score` emite `UserWarning` de NumPy array não gravável ao carregar baseline.

Nenhum warning acima é bloqueador para a TAREFA-019.

## Conclusão

A implementação está funcional nos fluxos principais e todos os gates mecânicos passaram.
O relatório, entretanto, fica **FAIL / Request changes** por causa do vazamento das
variáveis reservadas do juiz a partir de `os.environ` para servidores de gerador. Como essa
é a distinção arquitetural central de §9.2/ADR-003 e o Prompt B classifica os itens 2 e 3
como bloqueadores, a tarefa deve voltar para correção antes de aprovação.
