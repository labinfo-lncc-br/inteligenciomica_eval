# M1_TAREFA-019_D — Reauditoria env de regime saneado

**Data**: 2026-05-28
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1 — Adapters de Recuperação
**Skill**: code-reviewer, test-engineer
**Prioridade / Tamanho**: P1 / S
**Resultado**: PASS / Approve

## Objetivo

Reauditar a correção da TAREFA-019-C em resposta ao bloqueador registrado em
`M1_TAREFA-019_B_auditoria-vllm-server-manager-adapter.md`: vazamento de
`VLLM_BATCH_INVARIANT` e `VLLM_ENABLE_V1_MULTIPROCESSING` do ambiente pai para servidores
geradores com `ModelSpec.extra_env={}`.

O foco principal foi o item 2 do Prompt B da TAREFA-019, mantendo a verificação dos demais
itens do checklist:

- subprocess seguro via `asyncio.create_subprocess_exec`;
- regime juiz/gerador exclusivamente por `model.extra_env`;
- `ServerHandle.batch_invariant` derivado do `extra_env`;
- polling de `/health` em `wait_healthy`;
- encerramento via `SIGTERM` e `SIGKILL` em timeout;
- testes com subprocess mockado e `respx`;
- gates oficiais.

## Arquivos Criados / Modificados

| Arquivo | Ação | Observação |
|---------|------|------------|
| `docs/dev-log/M1_TAREFA-019_D_reauditoria-env-regime-saneado.md` | Criado | Este relatório de reauditoria |

Arquivos auditados:

- `docs/dev-log/M1_TAREFA-019_C_correcao-env-regime-saneado.md`
- `docs/dev-log/M1_TAREFA-019_B_auditoria-vllm-server-manager-adapter.md`
- `docs/prompts_m1_tarefas_013_021_corrigido.md`
- `src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py`
- `tests/unit/infrastructure/adapters/test_vllm_server_manager.py`
- `src/inteligenciomica_eval/domain/ports.py`

## Verificação do Achado 019-B

| Achado 019-B | Verificação | Resultado |
|--------------|-------------|-----------|
| Variáveis do juiz vazavam do ambiente pai para geradores porque `start()` usava merge bruto de `os.environ` | `vllm_server_manager.py:48-58` define `_RESERVED_REGIME_ENV`; `vllm_server_manager.py:114-117` passa `env=self._build_env(model)`; `vllm_server_manager.py:215-232` remove chaves reservadas de `os.environ` antes de aplicar `model.extra_env`; probes confirmaram gerador sem herança e juiz sobrescrevendo ambiente pai | Resolvido |

## Critérios do Prompt B

| Critério Prompt B | Evidência arquivo:linha | Gravidade / Resultado |
|-------------------|-------------------------|-----------------------|
| 1. `create_subprocess_exec` com lista de args; parâmetro `model`; ambiente preserva `os.environ` sem substituir tudo | `vllm_server_manager.py:98-117`; `_build_command` em `vllm_server_manager.py:196-213`; `_build_env` em `vllm_server_manager.py:215-232`; probe `start_signature=(self, model: 'ModelSpec')`; probe `shell_kw_present=False` | PASS. Observação: o merge agora preserva variáveis não-regime e saneia apenas chaves reservadas, para satisfazer o item 2 |
| 2. `VLLM_BATCH_INVARIANT=1` e `VLLM_ENABLE_V1_MULTIPROCESSING=0` aparecem apenas quando `model.extra_env` contém essas chaves, sem herança ambiental | `_RESERVED_REGIME_ENV` em `vllm_server_manager.py:48-58`; `_build_env` em `vllm_server_manager.py:215-232`; regressões `test_generator_does_not_inherit_regime_from_parent_env` em `test_vllm_server_manager.py:180-201` e `test_judge_overrides_parent_regime_env` em `test_vllm_server_manager.py:203-213`; probe contaminado retornou `env_has_batch_invariant=False` e `env_has_v1_multiprocessing=False` | PASS |
| 3. `ServerHandle.batch_invariant` derivado de `"VLLM_BATCH_INVARIANT" in model.extra_env` | `vllm_server_manager.py:118-124`; `ModelSpec` documenta a decisão em `ports.py:222-246`; testes em `test_vllm_server_manager.py:127-137`; probe de gerador contaminado retornou `handle_batch_invariant=False`; probe de juiz retornou `handle_batch_invariant=True` | PASS |
| 4. Polling de `/health` em `wait_healthy()`, não em `start()`; intervalo default 2s; `ServerStartTimeoutError`; sem `is_healthy()` público | `vllm_server_manager.py:59-62`, `vllm_server_manager.py:136-168`; `test_no_is_healthy_method` em `test_vllm_server_manager.py:116-118`; `test_start_does_not_poll_health` em `test_vllm_server_manager.py:229-238`; timeout em `test_vllm_server_manager.py:279-293` | PASS |
| 5. `stop()` usa `SIGTERM` + espera + `SIGKILL` em timeout | `vllm_server_manager.py:170-185`; `_await_exit` em `vllm_server_manager.py:251-264`; testes em `test_vllm_server_manager.py:320-347` | PASS |
| 6. Testes mockam subprocess e `respx`; verificam `batch_invariant` no handle | `_patch_subprocess` em `test_vllm_server_manager.py:90-98`; `respx` em `test_vllm_server_manager.py:233-238` e `251-312`; `batch_invariant` em `test_vllm_server_manager.py:127-137`, `180-213` | PASS |
| 7. `mypy --strict`, `lint-imports`, cobertura >= 80% | Gates executados abaixo; cobertura total 96.69%; `vllm_server_manager.py` 100% | PASS |

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
start_calls_build_env= True
start_uses_os_environ_directly= False
batch_env_literal_in_start= False
multiprocessing_env_literal_in_start= False
```

### Gerador com ambiente pai contaminado

Entrada: ambiente pai com `VLLM_BATCH_INVARIANT=1`,
`VLLM_ENABLE_V1_MULTIPROCESSING=0` e `SENTINEL_VAR=keep-me`; `ModelSpec.extra_env={}`.

```text
handle_batch_invariant= False
env_has_batch_invariant= False
env_has_v1_multiprocessing= False
sentinel_preserved= True
```

Resultado: o bloqueador da auditoria 019-B foi corrigido. As chaves de regime não vazam
para o gerador, mas variáveis não-regime do ambiente pai continuam preservadas.

### Juiz sobrescrevendo ambiente pai

Entrada: ambiente pai com `VLLM_BATCH_INVARIANT=0` e
`VLLM_ENABLE_V1_MULTIPROCESSING=1`; `ModelSpec.extra_env` do juiz com os valores corretos.

```text
handle_batch_invariant= True
env_batch_invariant= 1
env_v1_multiprocessing= 0
```

Resultado: o regime do juiz vem de `model.extra_env` e sobrescreve valores errados do pai.

### Comando de subprocess

```text
shell_kw_present= False
command_args= ('.../.venv/bin/python3', '-m', 'vllm.entrypoints.openai.api_server',
 '--model', 'llama3-8b', '--port', '8000', '--tensor-parallel-size', '2',
 '--max-model-len', '8192', '--quantization', 'awq')
```

## Validação (DoD)

| Comando / Probe | Resultado |
|-----------------|-----------|
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` | PASS — `All checks passed!` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .` | PASS — `80 files already formatted` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src` | PASS — `Success: no issues found in 29 source files` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict tests/unit/infrastructure/adapters/test_vllm_server_manager.py` | PASS — `Success: no issues found in 1 source file` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` | PASS — 68 files, 170 dependencies, 4 contracts kept, 0 broken |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -v tests/unit/infrastructure/adapters/test_vllm_server_manager.py tests/unit/domain/test_ports_contract.py tests/unit/fakes/test_fakes_satisfy_ports.py` | PASS — 118 passed |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n 4` | PASS — 679 passed, 7 skipped, 96.69%; `vllm_server_manager.py` 100% |
| Probe de assinatura/async/port | PASS |
| Probe de AST do `start()` | PASS |
| Probe de gerador com ambiente pai contaminado | PASS |
| Probe de juiz sobrescrevendo ambiente pai | PASS |
| Probe de subprocess sem shell | PASS |

Warnings observados:

- `pytest-benchmark` avisa que benchmarks são desabilitados sob `xdist`.
- `ragas_metrics.py` emite `DeprecationWarning` de `langchain-community`.
- `bert_score` emite `UserWarning` de NumPy array não gravável ao carregar baseline.

Nenhum warning acima é bloqueador para a TAREFA-019.

## Conclusão

A correção 019-C resolve o bloqueador da auditoria 019-B. O regime juiz/gerador passa a
ser decidido exclusivamente por `ModelSpec.extra_env`: geradores não herdam chaves de
regime do ambiente pai, juízes aplicam os valores de `extra_env`, e
`ServerHandle.batch_invariant` permanece coerente com a presença de
`VLLM_BATCH_INVARIANT` no `extra_env`.

Veredito: **PASS / Approve**.
