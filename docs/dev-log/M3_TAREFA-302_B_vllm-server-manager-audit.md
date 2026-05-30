# M3_TAREFA-302_B — Auditoria do VLLMServerManager real

**Data**: 2026-05-30
**Milestone**: M3 — Orquestração experimental
**Épico**: E3
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Auditar a implementação da TAREFA-302A contra o Prompt B do marco M3, o contrato atual
em `domain/ports.py`, ADR-003/004/012 e o padrão de arquitetura do projeto.

## Arquivos Criados / Modificados

| Arquivo | Mudança |
|---------|---------|
| `docs/dev-log/M3_TAREFA-302_B_vllm-server-manager-audit.md` | Relatório de auditoria da TAREFA-302B. |

## Decisões Técnicas

1. A auditoria considerou o diff real da 302A, inclusive o ajuste retroativo em
   `src/inteligenciomica_eval/domain/ports.py` e a reabertura de `config/model_registry.yaml`.
2. O desvio "async-first" foi tratado como aceitável em princípio, porque o Port já é
   assíncrono; o foco ficou em aderência comportamental ao contrato.
3. A validação de gates foi feita com o `.venv` local do repositório, porque `uv run`
   com ambiente temporário exigiu rede para reconstruir dependências.

## Problemas Encontrados e Soluções

### Rodada 1 — 2026-05-30

1. **Bloqueador** — `wait_healthy()` não propaga na exceção o contexto exigido pela spec.
   O Prompt 302 pede `ServerStartTimeoutError` com contexto de startup e `tail` de stderr;
   o código só registrava isso em log e levantava uma exceção genérica com
   `{server_name, timeout_seconds}`.
2. **Bloqueador** — `_assert_port_available()` tratava qualquer handle rastreado como vivo.
   Se o processo morresse fora de `stop()`/`wait_healthy()`, um handle stale continuava
   bloqueando a porta, contrariando o contrato documentado ("handle vivo + bind ao
   socket").
3. **Importante** — logging de ciclo de vida não atendia integralmente os campos pedidos
   no Prompt B. `vllm_server_healthy` não logava `port`/`batch_invariant`, `start` e `stop`
   não logavam `elapsed_ms`.
4. **Importante** — a suíte nova não ficou totalmente verde neste ambiente: dois testes de
   socket falharam com `PermissionError` ao abrir `AF_INET`.

### Rodada 2 — 2026-05-30

Os 4 apontamentos da rodada 1 foram corrigidos. A reauditoria não encontrou novas
divergências bloqueadoras ou importantes no escopo da TAREFA-302.

## Validação (DoD)

```text
.venv/bin/lint-imports
  -> Contracts: 4 kept, 0 broken

.venv/bin/pytest tests/integration/adapters/test_vllm_server_manager.py \
  tests/unit/domain/test_errors.py \
  tests/unit/domain/test_ports_contract.py \
  tests/unit/fakes/test_fakes_satisfy_ports.py
  -> 166 passed
```

## Critérios de Aceitação

| Critério | Arquivo:linha | Estado | Gravidade |
|----------|---------------|--------|-----------|
| Arquivo no local canônico `infrastructure/adapters/vllm_server_manager.py` | `src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py:1` | OK | - |
| Port com 3 métodos públicos (`start`, `wait_healthy`, `stop`) e `_is_healthy` privado | `src/inteligenciomica_eval/domain/ports.py:582`, `src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py:141`, `173`, `207`, `323` | OK | - |
| `CUDA_VISIBLE_DEVICES` injetado para todos os modelos | `src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py:262-282` | OK | - |
| Juiz injeta `VLLM_BATCH_INVARIANT=1` / gerador não herda regime | `src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py:262-282` | OK | - |
| `wait_healthy` com backoff, morte precoce e `tail` de stderr na exceção | `src/inteligenciomica_eval/domain/errors.py:266-303`, `src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py:186-205`, `344-371`, `tests/integration/adapters/test_vllm_server_manager.py:389-446`, `tests/unit/domain/test_errors.py:198-214` | OK | - |
| Porta ocupada detectada só para handle vivo ou socket bound | `src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py:284-308`, `tests/integration/adapters/test_vllm_server_manager.py:326-348` | OK | - |
| Logging com `{model_name, port, pid, batch_invariant, gpu_index, elapsed_ms}` | `src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py:162-169`, `190-197`, `218-226`, `353-361` | OK | - |
| `stop()` faz SIGTERM antes de SIGKILL | `src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py:213-227`, `386-399` | OK | - |
| `lint-imports` verde | `.importlinter` / execução local | OK | - |
| Testes mock-based sem vLLM real | `tests/integration/adapters/test_vllm_server_manager.py:1-9` | OK | - |
| Testes reproduzíveis no ambiente auditado | `tests/integration/adapters/test_vllm_server_manager.py:337-348` | OK | - |

## Observações para Próximas Tarefas

1. Como a 302A alterou `config/model_registry.yaml`, a 301 continua dependente de auditoria
   consolidada quando o fluxo do marco voltar a esse ponto.
2. No escopo da 302, a rodada 2 fecha em condições de aprovação.
