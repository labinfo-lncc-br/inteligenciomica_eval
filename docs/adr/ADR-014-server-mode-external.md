# ADR-014 — Modo de Implantação External (vLLM/Qdrant Pré-existentes via Túnel)

**Status**: Aprovado  
**Data**: 2026-06-05  
**Milestone**: M3 — TAREFA-311  
**Autores**: lgp-almeida

---

## Contexto

Nos ambientes de produção do projeto (cluster LNCC), os servidores vLLM e Qdrant são
iniciados externamente — frequentemente via SSH tunnel — antes da execução do ciclo de
avaliação. O `VLLMServerManagerAdapter` existente assume controle total do ciclo de vida
via `asyncio.create_subprocess_exec`, o que é inapropriado quando os processos:
1. Já estão em execução (gerenciados por um operador ou script externo).
2. Estão em hosts remotos acessíveis apenas por túnel.
3. Não podem ser encerrados pelo processo de avaliação (ex.: servidores compartilhados).

## Decisão

Introduzir um campo `server_mode: Literal["managed", "external"]` no `RoundConfig`
(default `"managed"` para retrocompatibilidade) e um novo adapter
`ExternalVLLMServerManager` que implementa `VLLMServerManagerPort` sem gerenciar
subprocessos.

### Contrato do ExternalVLLMServerManager

| Método | Comportamento |
|--------|--------------|
| `start(model)` | Resolve URL a partir de `endpoint_map`; retorna `ServerHandle(pid=None, gpu_index=-1)`. |
| `wait_healthy(handle, timeout_s)` | Polling `GET /health` com backoff; levanta `EndpointUnreachableError` se timeout. |
| `stop(handle)` | **No-op** — loga `external_server_stop_noop`; nunca encerra o processo remoto. |

### ServerHandle.pid agora é `int | None`

`pid=None` indica servidor externo; `gpu_index=-1` indica ausência de alocação local
de GPU. O campo é opcional no serialization path (o Parquet não serializa ServerHandle).

### Proveniência via endpoint_env no ModelEntry

Cada entrada do registry pode ter `endpoint_env: str | None` — o nome da env var que
contém a URL do endpoint tunelado. Em `server_mode="external"`:
- O campo é **obrigatório** (validado pelo wiring no momento de `build_container`).
- A URL nunca é armazenada no YAML (ADR-008 — apenas nomes de env vars).

### Sondas de proveniência (`infrastructure/provenance/endpoint_probe.py`)

Três sondas independentes, executadas antes do ciclo em `server_mode="external"`:
1. `probe_served_model(url)` — `GET /v1/models` → id do modelo servido.
2. `probe_vllm_version(url)` — `GET /version` → versão do vLLM.
3. `probe_judge_determinism(url)` — 2× `POST /v1/chat/completions` → comparação byte a byte.

Todas retornam valores sentinela (`""`, `None`, `False`) em caso de falha — nunca
propagam exceções. A flag `--require-verified-determinism` na CLI força exit 1 se o
probe de juiz retornar `False`.

### Campos de proveniência em EvaluationResult e Parquet

Três campos adicionados com defaults retrocompat:
- `server_mode: str = "managed"` — modo de implantação.
- `served_model_id: str = ""` — ID do modelo confirmado por probe.
- `determinism_verified: bool = True` — resultado do probe de determinismo.

Mapeados em `EVAL_SCHEMA` (3 novas colunas `pa.string`, `pa.string`, `pa.bool_`).

## Consequências

**Positivas**:
- Suporte imediato a ambientes de cluster sem reinicialização de servidores.
- Retrocompatibilidade total: `server_mode="managed"` é o default; nenhuma rodada
  existente precisa ser atualizada.
- Probes de proveniência melhoram a rastreabilidade em modo external (ADR-007/ADR-008).
- `EndpointUnreachableError` fornece contexto estruturado sem depender de mensagens de
  log para diagnóstico.

**Negativas / trade-offs**:
- O wiring valida `endpoint_env` sincronamente no `build_container` — erro detectado
  cedo, mas exige restart do processo para corrigir uma env var ausente.
- As sondas dependem de `httpx` em `infrastructure/provenance/` — sem violação dos
  contratos de importação (httpx é permitido em `infrastructure`).
- `stop()` no-op cria assimetria conceitual com `start()` — documentada explicitamente
  no adapter e no ADR; não é um bug, é uma decisão de design consciente.

## Alternativas Consideradas

1. **Reutilizar `VLLMServerManagerAdapter` com subprocess noop**: mais acoplado, mais
   difícil de testar, e a assinatura `pid: int` seria forçada em cenários sem PID.
2. **Resolver URLs no YAML diretamente**: viola ADR-008 (URLs como segredos não devem
   aparecer em arquivos de configuração versionados).
3. **Adapter por Protocol duck-typing sem novo campo em RoundConfig**: mais difícil de
   descobrir e de validar; o campo `server_mode` é o ponto de configuração explícito.
