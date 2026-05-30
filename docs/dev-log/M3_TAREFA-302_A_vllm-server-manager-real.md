# M3_TAREFA-302_A — VLLMServerManager real (upgrade para o contrato M3)

**Data**: 2026-05-30
**Milestone**: M3 — Orquestração experimental
**Épico**: E3
**Skill**: backend-engineer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Promover o `VLLMServerManagerAdapter` (já existente da era M1/TAREFA-019, async-first) ao
contrato da TAREFA-302: GPU pinning via `CUDA_VISIBLE_DEVICES` (ADR-012), injeção do regime
determinístico **a partir de flag** (ADR-003), `extra_args` como flags de CLI, recusa de
porta ocupada (`ModelSwitchError`), drenagem de pipes anti-deadlock com `tail` de stderr,
detecção de morte precoce do processo e backoff exponencial no health check.

> **Não foi criação do zero**: o arquivo `infrastructure/adapters/vllm_server_manager.py` já
> existia. A TAREFA-302 é um *upgrade* (mesma natureza dos "upgrade" de M2), preservando a
> arquitetura **async-first** do Port (`VLLMServerManagerPort` é `async`).

## Arquivos Criados / Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/.../domain/ports.py` | **PR retroativo** de contrato: `ModelSpec` ganha `gpu_index: int` e `batch_invariant: bool` (flag autoritativa) e troca `extra_env` → `extra_args: dict[str,str]` (flags de CLI); `ServerHandle` ganha `port`, `gpu_index`, `started_at`. |
| `src/.../infrastructure/adapters/vllm_server_manager.py` | Reescrita do adapter (regime por flag, CUDA pinning, extra_args CLI, ModelSwitchError, drenagem stderr+tail, morte precoce, backoff exp.). |
| `config/model_registry.yaml` | **Editado** (deliverable da 301): removidas `VLLM_BATCH_INVARIANT`/`VLLM_ENABLE_V1_MULTIPROCESSING` do `extra_args` do juiz — agora injetadas pelo adapter via `batch_invariant=true`. Comentário atualizado. |
| `tests/fakes/servers.py` | `FakeVLLMServerManager`: `batch_invariant` da flag (não de `extra_env`); novos campos de `ServerHandle`. |
| `tests/unit/domain/test_ports_contract.py` | `_StubVLLMServerManager`, `test_model_spec`, `test_server_handle`, `test_stub_vllm_manager_lifecycle` atualizados ao novo contrato. |
| `tests/unit/fakes/test_fakes_satisfy_ports.py` | 3 `ModelSpec` atualizados (sem `extra_env`; + `gpu_index`/`batch_invariant`/`extra_args`). |
| `tests/integration/adapters/test_vllm_server_manager.py` | **Novo** (local canônico da spec); mock-based, 32 testes, sem marker `integration` (roda no gate de cobertura). |
| `tests/unit/infrastructure/adapters/test_vllm_server_manager.py` | **Removido** (substituído pelo novo; testava o contrato M1 `extra_env`). |

## Decisões Técnicas

1. **Regime por FLAG, não por dado de ambiente (decisão do dev sênior — Prompt 302A).**
   `ModelSpec.batch_invariant` é a fonte autoritativa: o adapter **injeta**
   `VLLM_BATCH_INVARIANT=1` + `VLLM_ENABLE_V1_MULTIPROCESSING=0` *sse* a flag for `True`.
   Geradores ficam **provadamente** sem essas variáveis (garantia de código, não de
   disciplina de config). Substitui a heurística M1 `"VLLM_BATCH_INVARIANT" in extra_env`.
   O saneamento das chaves de regime do `os.environ` herdado (correção 019-B) foi preservado.
2. **`extra_args` = flags de CLI** (consumo explicitamente pedido pelo dev sênior). Apendadas
   ao comando como `--nome valor`. Isso forçou editar o YAML da 301 (as env vars do juiz não
   são flags de CLI; deixá-las geraria `--VLLM_BATCH_INVARIANT 1`, argumento inválido).
3. **Async-first mantido (reconciliação com a spec).** O Prompt A menciona `subprocess.Popen`
   + threads daemon + `requests.get`; mas o Port de domínio é `async` (M1, com fakes/stubs/307
   dependendo disso). Implementei o **equivalente async**: `asyncio.create_subprocess_exec` +
   `httpx.AsyncClient` + drenagem por **tasks de fundo** (mesma garantia anti-deadlock das
   threads daemon). Documentado no topo do adapter.
4. **Porta ocupada → `ModelSwitchError`** em dois ramos: (a) handle vivo já na porta
   (`from_model` = modelo existente); (b) bind ao socket falha (`from_model="unknown"`).
5. **`tail` de stderr (20 linhas) via anel `deque(maxlen=20)`** alimentado pela task de
   drenagem; coletado em `_collect_stderr_tail` (após `force_kill`, que fecha os pipes → EOF
   → drain conclui) e logado em `vllm_server_start_failed`. A assinatura do
   `ServerStartTimeoutError` (`server_name`, `timeout_seconds`) não mudou — o tail vai no log.
6. **Morte precoce**: `wait_healthy` checa `process.returncode is not None` a cada iteração →
   `ServerStartTimeoutError` imediata (`reason="process_exited"`).
7. **Backoff exponencial** (initial=1 s, max=15 s) injetável (`_poll_initial_s`/`_poll_max_s`).
8. **`_is_healthy` privado** (timeout 2 s) — não faz parte do Port.

## Problemas Encontrados e Soluções

- **`MagicMock.returncode` é truthy** → `_process_died` daria falso-positivo. Solução: o
  `_fake_process` de teste seta `returncode=None` explicitamente para processo "vivo".
- **Task de drenagem vazando** ("Task pending"): validado com `-W error::RuntimeWarning` (32
  passed) — `stop`/`_fail` cancelam (`_cancel_drains`) e streams falsos atingem EOF.
- **`ResourceWarning: unclosed socket`** na suíte completa: confirmado **pré-existente**
  (httpx/respx/qdrant de outros testes); meu arquivo isolado com `-W default` não emite.
- **SIM117** (ruff): dois `with` aninhados combinados em um só.

## Validação (DoD §14.2)

```text
ruff check .              -> All checks passed!
ruff format --check .     -> 100 files already formatted
mypy --strict src         -> Success: no issues found in 35 source files
lint-imports              -> Contracts: 4 kept, 0 broken
pytest --cov -n 4 --cov-fail-under=85
  -> 790 passed, 15 skipped — coverage 97.31%
  -> vllm_server_manager.py: 177 stmts, 0 missed = 100%
adapter test isolado -W error::RuntimeWarning -> 32 passed (sem leak de task)
```

## Critérios de Aceitação (tabela TAREFA-302)

| Critério | Estado | Evidência (teste) |
|----------|--------|-------------------|
| `CUDA_VISIBLE_DEVICES=str(gpu_index)` para TODOS (juiz=3, gerador=0/1/2) | ✅ | `test_cuda_visible_devices_injected_for_judge/_generator` |
| Juiz com `VLLM_BATCH_INVARIANT=1`; gerador SEM a variável (inspeção do env) | ✅ | `test_judge_env_has_regime_vars_injected`, `test_generator_env_has_no_regime_vars` |
| Timeout em `wait_healthy` ⇒ `ServerStartTimeoutError` + tail de stderr | ✅ | `test_timeout_raises_kills_and_logs_stderr_tail` |
| Processo morre antes do timeout ⇒ `ServerStartTimeoutError` imediata | ✅ | `test_process_death_raises_immediately_with_stderr` |
| `stop()` envia SIGTERM primeiro; SIGKILL só se necessário | ✅ | `test_sigterm_then_clean_exit`, `test_escalates_to_sigkill_on_timeout` |
| Pipe stdout/stderr drenado sem deadlock (tasks de fundo ≈ threads daemon) | ✅ | `test_stdout_and_stderr_drained_and_cancelled_on_stop` |
| `_is_healthy` PRIVADO; Port satisfeito com 3 métodos | ✅ | `test_no_public_is_healthy_method`, `test_satisfies_port` |
| `ModelSwitchError` em porta ocupada (bind ao socket) | ✅ | `test_second_start_same_port...`, `test_externally_bound_port...`, `test_port_in_use_*` |
| Logging com `{model, port, pid, batch_invariant, gpu_index, elapsed_ms}` | ✅ | `test_handle_fields_and_log`, `test_sigterm_then_clean_exit` |
| Sem vLLM real nos testes; import-linter verde | ✅ | suíte mock-based; `4 kept, 0 broken` |

## Correções pós-auditoria 302-B (rodada 1 — 2026-05-30)

O Codex retornou **FAIL** com 4 apontamentos; todos corrigidos:

1. **🛑 Exceção descartava contexto (`vllm_server_manager.py` `_fail`)**: `ServerStartTimeoutError`
   foi **estendida** (`domain/errors.py`) com kwargs-only opcionais `pid`/`reason`/`stderr_tail`
   (retrocompatível — usos posicionais intactos). `_fail` agora **carrega** o `tail` de stderr,
   `pid` e `reason` na exceção (além de logar). Testes: `test_*_carries_diagnostic_context`,
   asserts em `exc_info.value.stderr_tail/.pid/.reason` nos testes de timeout e morte precoce.
2. **🛑 Handle stale bloqueava porta (`_assert_port_available`)**: agora só bloqueia se o
   processo dono da porta está **vivo** (`returncode is None`); handle stale (processo morto)
   é esquecido e a porta liberada. Teste: `test_stale_handle_does_not_block_port_reuse`.
3. **⚠️ Logging incompleto (item 8)**: `vllm_server_healthy` ganhou `port`+`batch_invariant`;
   `vllm_server_started` e `vllm_server_stopped` ganharam `elapsed_ms` (spawn e uptime resp.).
4. **⚠️ Testes de socket falhavam no sandbox do Codex (`PermissionError` em AF_INET)**: os dois
   testes de `_port_in_use` foram tornados **herméticos** (mock de `socket.socket`, sem socket
   real) → reproduzíveis em qualquer ambiente.

Regates após correção: ruff/format limpos · mypy 35 files · lint-imports 4/0 ·
`pytest --cov -n 4` → **792 passed, 15 skipped, 97.34%** · `vllm_server_manager.py` e
`errors.py` em **100%**.

## Observações para Próximas Tarefas

- **TAREFA-309 (wiring)**: o mapeamento `ModelEntry → ModelSpec` deve levar
  `ModelEntry.extra_args` → `ModelSpec.extra_args` (flags de CLI) e `ModelEntry.gpu_index`/
  `batch_invariant` → campos homônimos. `ModelSpec.model` = `hf_repo`; `port`/`max_model_len`
  vêm do orquestrador/round config. **NÃO** repassar env vars de regime em `extra_args`.
- **Desvio consciente da spec a sinalizar ao Codex (Prompt B)**: (a) implementação
  **async** (não `subprocess.Popen`/threads/`requests`) — exigência do Port async existente;
  (b) teste mock-based em `tests/integration/adapters/` **sem** marker `integration` (roda no
  job de cobertura, não no de containers — é o local canônico da spec, mas o teste não usa
  serviços reais).
- **Edição da 301**: o `config/model_registry.yaml` (deliverable aprovado da 301) foi alterado
  no `extra_args` do juiz. Conforme o protocolo, isso reabre o ciclo de auditoria.
