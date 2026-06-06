# Manual de Operação — InteligenciÔmica Eval

**Versão:** 0.1.0 · **Milestone:** M6 · **Atualizado:** 2026-06-05

Este manual descreve os procedimentos operacionais para executar o subsistema de
validação InteligenciÔmica no nó GH200 do LNCC. Todos os comandos foram validados
durante M0–M4 e M3 (incluindo modo `external`, TAREFA-311). A Seção 9 é stub pendente
de M5.

---

## Seção 1 — Pré-requisitos da máquina

### Driver NVIDIA e CUDA

O nó de produção é um GH200 (Nota de operacionalização M3, ADR-012). Antes de
iniciar, confirme a instalação com:

```bash
nvidia-smi
```

Saída esperada (referência GH200):

```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 550.x.x   Driver Version: 550.x.x   CUDA Version: 12.4          |
|                                                                             |
| GPU  Name                    Persistence-M | Bus-Id        Disp.A | ...    |
|   0  NVIDIA GH200 120GB HBM3 ...            |                              |
|   1  NVIDIA GH200 120GB HBM3 ...            |                              |
|   2  NVIDIA GH200 120GB HBM3 ...            |                              |
|   3  NVIDIA GH200 120GB HBM3 ...            |                              |
+-----------------------------------------------------------------------------+
```

> **[PENDENTE: P1.1]** Versão exata de driver/CUDA a confirmar na bancada. O checklist
> §17.3 do documento de arquitetura registra a medição de VRAM por modelo (Premissa P1.1)
> como pendente.

### vLLM

Versão mínima recomendada: **0.4.x** (suporte à env `VLLM_BATCH_INVARIANT`).

Para verificar a versão instalada no servidor vLLM:

```bash
python -c "import vllm; print(vllm.__version__)"
```

Para confirmar suporte a `VLLM_BATCH_INVARIANT` (necessário para o juiz determinístico
— ADR-003):

```bash
VLLM_BATCH_INVARIANT=1 python -c "import vllm; print('VLLM_BATCH_INVARIANT OK')"
```

Se o comando acima retornar erro, atualize o vLLM para uma versão que suporte a
variável de ambiente antes de continuar.

### Qdrant

- **Versão:** 1.9 (imagem `qdrant/qdrant:v1.9` usada no CI de integração)
- **Porta padrão:** 6333
- **Coleções existentes (Rodada 1):** `IDx_400k`, `ID_230K`

Para verificar saúde do serviço:

```bash
curl http://localhost:6333/healthz
```

Resposta esperada: `{"title":"qdrant - vector search engine","version":"1.9.x",...}`

### Python e uv

- **Python:** 3.11+ (ambiente local usa 3.12)
- **uv:** instalado e no PATH

```bash
python --version    # deve ser >= 3.11
uv --version        # deve estar disponível
```

---

## Seção 2 — Setup do ambiente (reprodutível)

### Sequência completa de instalação

```bash
git clone <repo-url>
cd inteligenciomica_eval

# Instala todas as dependências (runtime + dev) usando o lock file
uv sync --frozen

# Verifica que o entry point funciona
uv run ielm-eval --help
uv run ielm-eval version
```

### Variáveis de ambiente obrigatórias

As URLs dos serviços **nunca** entram nos arquivos YAML (ADR-008). Defina-as no
ambiente antes de executar qualquer subcomando que faça chamadas de rede:

| Variável             | O que controla                                         |
|----------------------|--------------------------------------------------------|
| `VLLM_GENERATOR_URL` | URL base do servidor vLLM dos geradores (inclui `/v1`) |
| `VLLM_JUDGE_URL`     | URL base do servidor vLLM do juiz (inclui `/v1`)       |
| `QDRANT_URL`         | URL do serviço Qdrant (ex.: `http://localhost:6333`)   |

Exemplo de configuração (não use credenciais reais no shell history):

```bash
export VLLM_GENERATOR_URL="http://localhost:8000/v1"
export VLLM_JUDGE_URL="http://localhost:8001/v1"
export QDRANT_URL="http://localhost:6333"
```

> **Segurança (ADR-008):** nunca coloque tokens, senhas ou URLs com credenciais
> embutidas nos arquivos YAML de configuração. Use exclusivamente variáveis de ambiente.

### Variáveis de endpoint em modo `external` (ADR-014)

Em `server_mode: external` (ver Seção 4-B), **não** há novas variáveis de ambiente
obrigatórias globais. As URLs dos servidores tunelados são fornecidas via env vars
**cujos nomes** são declarados no campo `endpoint_env` de cada entrada do
`model_registry.yaml`. Somente os **nomes** ficam no YAML; os **valores** vêm do ambiente:

| Declaração no YAML | Env var que deve ser definida pelo operador |
|--------------------|---------------------------------------------|
| `endpoint_env: VLLM_GEN1_URL` | `export VLLM_GEN1_URL="http://localhost:8010/v1"` |
| `endpoint_env: VLLM_GEN2_URL` | `export VLLM_GEN2_URL="http://localhost:8011/v1"` |
| `endpoint_env: VLLM_JUDGE_EXTERNAL_URL` | `export VLLM_JUDGE_EXTERNAL_URL="http://localhost:8020/v1"` |

> Os nomes das env vars (`VLLM_GEN1_URL`, etc.) são definidos pelo operador e devem
> seguir o padrão de nomes de variáveis de ambiente válidos (maiúsculas, dígitos e
> sublinhados). O wiring valida que cada `endpoint_env` declarado está presente em
> `os.environ` na hora de `build_container` — env var ausente gera `ConfigValidationError`
> imediata.

### Verificação de ambiente pronto

Para confirmar que o ambiente está corretamente configurado sem tocar em GPU ou rede:

```bash
uv run ielm-eval run --dry-run --config config/experiment_round1.yaml
```

Saída esperada: plano com contagem de células, mapa GPU/onda, `config_hash` e a mensagem
final `Config valid — dry-run complete.` — sem erros de validação.

---

## Seção 3 — O `model_registry.yaml` — configuração de serving

### Estrutura do arquivo

O arquivo `config/model_registry.yaml` é **separado** do YAML de rodada
(`experiment_round1.yaml`). O YAML de rodada referencia o registry via:

```yaml
model_registry_path: "model_registry.yaml"
```

Campos principais do registry:

| Campo           | Descrição                                                          |
|-----------------|--------------------------------------------------------------------|
| `gpu_slots`     | Lista de 4 GPUs com `vram_gb` e `reserved_gb` cada               |
| `models`        | Lista de todos os modelos (geradores + juiz) com seus parâmetros  |
| `name`          | Nome lógico do modelo (deve casar com `llms` do YAML de rodada)   |
| `hf_repo`       | Repositório HuggingFace para download do modelo                   |
| `quantization`  | Esquema de quantização (`awq`, `gptq`, ou `null` para FP16)       |
| `tensor_parallel_size` | Número de GPUs para tensor parallelism do modelo          |
| `gpu_index`     | GPU atribuída (nominal para geradores; fixa para o juiz)          |
| `is_judge`      | `true` apenas para o Prometheus-2 (ADR-003)                       |
| `batch_invariant` | `true` → juiz determinístico; `false` → gerador (produção)    |
| `extra_args`    | Flags de CLI adicionais passadas ao servidor vLLM                 |

### Regra de ouro GPU (ADR-012)

```
GPU 3  → Juiz (prometheus-8x7b-v2.0) — residente, fixa durante toda a rodada
GPU 0  → Geradores — onda 1 (modelos 1, 2, 3) e onda 2 (modelos 4, 5)
GPU 1  → Geradores — onda 1 (modelos 1, 2, 3) e onda 2 (modelos 4, 5)
GPU 2  → Geradores — onda 1 (modelos 1, 2, 3)
```

- O **juiz** tem `gpu_index: 3` vinculante — nunca é movido.
- Os **geradores** têm `gpu_index` nominal no registry; o orquestrador
  (`WaveSchedulerService`, TAREFA-303) reatribui dinamicamente 0/1/2 por onda.
- **Onda 1** (concorrente): 3 modelos nas GPUs 0, 1, 2.
- **Onda 2** (concorrente): 2 modelos restantes nas GPUs 0, 1.

### Como adicionar um novo modelo gerador (5 passos)

1. Adicione o modelo em `config/model_registry.yaml` sob `models:` com `is_judge: false`.
2. Defina `hf_repo`, `quantization`, `tensor_parallel_size` (verificar footprint — ver abaixo).
3. Defina `gpu_index` nominal (0, 1 ou 2) para fins de documentação; o orquestrador redistribuirá.
4. Adicione o `name` do modelo na lista `llms:` do YAML de rodada
   (`config/experiment_round1.yaml`).
5. Valide com `ielm-eval run --dry-run --config config/experiment_round1.yaml` e confirme
   que o wave map não exibe warnings de VRAM.

### Como verificar `tensor_parallel_size` necessário

Regra prática: `vram_gb_awq ≤ available_gb_por_gpu (88 GB)` → `tensor_parallel_size: 1`.
Se o modelo AWQ não couber em uma GPU, use `tensor_parallel_size: 2` e ajuste o
`gpu_index` de acordo (ocupa 2 GPUs em vez de 1).

O `dry-run` emite um aviso de VRAM se `vram_gb_awq > available_gb` para qualquer GPU
na onda planejada.

> **[PENDENTE: P1.1]** Os valores `vram_gb_awq` dos geradores no registry atual são
> sentinelas conservadoras (80 GB). Medir o footprint real de cada modelo na quantização
> de produção AWQ e atualizar o registry antes de executar a Rodada 1.

---

## Seção 4 — Subindo o ambiente vLLM (antes do `run`)

### Subindo os servidores

O orquestrador `VLLMServerManagerAdapter` (TAREFA-019/302) gerencia os processos
vLLM automaticamente quando `ielm-eval run` for executado em modo full. Para fins de
validação manual ou depuração, você pode subir os servidores individualmente:

**Juiz (GPU 3, residente):**

```bash
VLLM_BATCH_INVARIANT=1 VLLM_ENABLE_V1_MULTIPROCESSING=1 \
  python -m vllm.entrypoints.openai.api_server \
    --model prometheus-eval/prometheus-8x7b-v2.0 \
    --port 8001 \
    --tensor-parallel-size 1 \
    --max-model-len 4096 \
    --quantization awq \
    --device cuda \
    --gpu_memory_utilization 0.90 &
```

**Verificar que o servidor está respondendo:**

```bash
curl http://localhost:8001/v1/models
```

### Confirmando determinismo do juiz

O juiz **deve** ser determinístico (ADR-003). Para confirmar, envie a mesma prompt
duas vezes e compare os scores:

```bash
# Primeira execução
curl -s -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"prometheus-8x7b-v2.0","messages":[{"role":"user","content":"Score: 0.8"}],"temperature":0.0,"seed":42}' \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"

# Segunda execução — saída deve ser IDÊNTICA
curl -s -X POST http://localhost:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"prometheus-8x7b-v2.0","messages":[{"role":"user","content":"Score: 0.8"}],"temperature":0.0,"seed":42}' \
  | python -c "import sys,json; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
```

Se os scores diferem, `VLLM_BATCH_INVARIANT` não foi aplicado — pare o servidor,
confirme a versão do vLLM e reinicie com a variável.

### Confirmando que o Qdrant está acessível

```bash
curl http://localhost:6333/healthz
```

---

## Seção 4-B — Modo `external` — servidores pré-existentes via túnel SSH (ADR-014)

### Quando usar

Use o modo `external` quando o vLLM e/ou Qdrant já estão em execução em hosts remotos
e **não devem ser gerenciados** pelo `ielm-eval` (ex.: cluster compartilhado LNCC,
nós GH200 arm64 onde o build do vLLM é custoso e pré-provisionado). O `ielm-eval`
roda numa máquina de controle (x86 com internet) e acessa os servidores por túnel.

`managed` continua sendo o **default** e permanece inalterado: quando omitido, o
orquestrador (`VLLMServerManagerAdapter`) sobe e derruba os processos vLLM localmente.

### Topologia (diagrama textual)

```
Máquina de controle (x86)          Cluster GH200 (LNCC)
┌─────────────────────┐            ┌────────────────────────────────┐
│                     │  SSH túnel │  node-gpu-0                    │
│  ielm-eval run      │◄──────────►│    vLLM gerador-1  :8010       │
│                     │            │    vLLM gerador-2  :8011       │
│  VLLM_GEN1_URL=     │            │                                │
│    localhost:8010   │  SSH túnel │  node-gpu-3                    │
│  VLLM_JUDGE_URL=    │◄──────────►│    vLLM juiz       :8020       │
│    localhost:8020   │            │                                │
│  QDRANT_URL=        │  SSH túnel │  node-qdrant                   │
│    localhost:6333   │◄──────────►│    Qdrant          :6333       │
└─────────────────────┘            └────────────────────────────────┘
```

### Configuração do YAML de rodada

```yaml
# config/experiment_round1_external.yaml
server_mode: external   # ← ativa modo external (ADR-014)
# ... demais campos inalterados ...
```

No `model_registry.yaml`, cada modelo que roda em servidor externo precisa de
`endpoint_env` com o nome da env var que contém a URL tunelada:

```yaml
# config/model_registry.yaml (trecho — modo external)
models:
  - name: gpt-oss-120b
    endpoint_env: VLLM_GEN1_URL    # ← nome da env var; NUNCA o valor literal
    is_judge: false
    # ... demais campos ...
  - name: prometheus-8x7b-v2.0
    endpoint_env: VLLM_JUDGE_EXTERNAL_URL
    is_judge: true
    batch_invariant: true
    # ...
```

### Túneis SSH — exemplos

Abra um túnel por servidor **antes** de executar o `ielm-eval run`:

```bash
# Gerador-1 (porta 8010 no nó remoto)
ssh -N -L localhost:8010:node-gpu-0:8010 usuario@gateway.lncc.br &

# Gerador-2 (porta 8011)
ssh -N -L localhost:8011:node-gpu-0:8011 usuario@gateway.lncc.br &

# Juiz (porta 8020 no nó gpu-3)
ssh -N -L localhost:8020:node-gpu-3:8020 usuario@gateway.lncc.br &

# Qdrant (porta 6333)
ssh -N -L localhost:6333:node-qdrant:6333 usuario@gateway.lncc.br &
```

Verificar que os túneis estão ativos:

```bash
curl http://localhost:8010/health
curl http://localhost:8020/health
curl http://localhost:6333/healthz
```

> Resposta esperada de `/health` (vLLM): `{"status":"OK"}`.
> Resposta esperada de `/healthz` (Qdrant): JSON com `"title":"qdrant - vector search engine"`.

### ⚠ RESPONSABILIDADE DO OPERADOR — modo `external`

> **Neste modo o `ielm-eval` NÃO controla o lançamento dos servidores vLLM.**
> O operador é inteiramente responsável por garantir que:
>
> 1. **O juiz** está em execução com as flags obrigatórias de determinismo (ADR-003):
>    - `VLLM_BATCH_INVARIANT=1` — proíbe reorganização de batch
>    - `VLLM_ENABLE_V1_MULTIPROCESSING=0` — sem multiprocessamento V1
>    - `--temperature 0` / inferência com `temperature=0.0, seed=42`
>    - `--tensor-parallel-size 1` (prometheus-8x7b-v2.0)
>
>    Exemplo de comando para subir o juiz no nó remoto:
>    ```bash
>    VLLM_BATCH_INVARIANT=1 VLLM_ENABLE_V1_MULTIPROCESSING=0 \
>      python -m vllm.entrypoints.openai.api_server \
>        --model prometheus-eval/prometheus-8x7b-v2.0 \
>        --port 8020 \
>        --tensor-parallel-size 1 \
>        --max-model-len 4096 \
>        --quantization awq
>    ```
>
> 2. **Cada endpoint serve o modelo esperado** — o `ielm-eval` verifica via sonda
>    (`GET /v1/models`) e grava o resultado, mas **não pode corrigir** um endpoint
>    apontando para o modelo errado.
>
> O `ielm-eval` **executa sondas de proveniência** automaticamente antes do ciclo
> e exibe os resultados num painel Rich. Use `--require-verified-determinism` para
> runs de qualidade de publicação (aborta com exit 1 se o probe do juiz falhar).

### Executando em modo `external`

```bash
ielm-eval run \
  --config config/experiment_round1_external.yaml \
  --run-id <run_id> \
  --require-verified-determinism
```

### Auditando a proveniência da rodada

Cada linha do Parquet contém três colunas de proveniência:

| Coluna Parquet | Tipo | Descrição |
|----------------|------|-----------|
| `server_mode` | string | `"managed"` ou `"external"` |
| `served_model_id` | string | ID do modelo confirmado por sonda (`GET /v1/models`) |
| `determinism_verified` | bool | `True` se as duas completions com `seed=42` foram idênticas |

> **Regra (ADR-014):** `determinism_verified` é `False` por default — sem prova,
> sem `True`. Só fica `True` se a sonda executar **e** confirmar tokens idênticos.

O run report (log estruturado ao final do ciclo) inclui a seção `endpoints_provenance`
com `config_hash`, topologia, endpoint mascarado (`scheme://host:port/***`),
`vllm_version` por gerador e flag `judge_det`:

```json
{
  "endpoints_provenance": {
    "config_hash": "a3f2b1c9...",
    "topology": "external",
    "generators": [
      {"name": "gpt-oss-120b", "endpoint_masked": "http://localhost:8010/***",
       "healthy": true, "vllm_version": "0.4.2", "served_model_id": "gpt-oss-120b"}
    ],
    "judge_det": true
  }
}
```

---

## Seção 5 — Executando a Rodada 1 (Experimentos A e B)

### Dry-run (validação sem GPU/rede)

Sempre execute o dry-run antes de uma execução real:

```bash
ielm-eval run --dry-run --config config/experiment_round1.yaml
```

Saída mostra: `config_hash`, fases, contagem de células, mapa GPU/onda, endpoints
mascarados. Qualquer erro de configuração aparece aqui, antes de consumir GPU.

### Execução completa

```bash
ielm-eval run --config config/experiment_round1.yaml --run-id <run_id>
```

`--run-id` é **obrigatório** para execuções reais (identifica o run no armazenamento
Parquet e é usado para retomar execuções interrompidas). Opções relevantes:

| Flag | Padrão | Descrição |
|------|--------|-----------|
| `--phase A\|B\|both` | `both` | Executa somente a fase A, somente a B, ou ambas |
| `--serial` | desligado | Serializa geradores (1 onda/modelo); contra ADR-012, útil para hardware single-GPU ou depuração |
| `--require-verified-determinism` | desligado | Em `server_mode='external'`: aborta (exit 1) se o probe de determinismo do juiz retornar `False` (ver Seção 4-B) |

> `--run-id` é ignorado em `--dry-run`. Use o **mesmo** `<run_id>` para retomar uma
> execução interrompida — a resumabilidade por `row_id` (ADR-009) garante que apenas
> linhas ausentes são recomputadas.

### De onde vêm as perguntas

As perguntas do benchmark são carregadas de um arquivo JSONL referenciado pelo campo
`questions:` no YAML de rodada (RF4/P4):

```yaml
# config/experiment_round1.yaml (trecho)
questions: "config/questions.yaml"   # path relativo ao diretório do YAML de rodada
```

Se `questions:` for omitido, o `ielm-eval` usa o arquivo empacotado no pacote Python
(`questions_rf1.jsonl`, 13 perguntas RF1 — preencher antes da Rodada 1 de produção).

**Formato do arquivo de perguntas** (JSONL — uma entrada por linha):

```json
{"question_id": "resistencia-beta-lactamicos",
 "text": "Quais são os principais mecanismos de resistência bacteriana...",
 "ground_truth": "Os principais mecanismos incluem: (1) produção de beta-lactamases..."}
```

**Multi-área de conhecimento:** cada área usa seu próprio arquivo de perguntas e um
YAML de rodada próprio que o referencia:

```
config/
  questions_resistencia.yaml      ← perguntas de resistência bacteriana
  questions_sepse.yaml            ← perguntas de sepse
  experiment_resistencia.yaml     ← round YAML com questions: config/questions_resistencia.yaml
  experiment_sepse.yaml           ← round YAML com questions: config/questions_sepse.yaml
```

Sem nova env var, sem re-release — basta criar o arquivo e atualizar o `questions:` do YAML.

> **Rodada 2 (M5):** `question_id` deve casar exatamente com as entradas de
> `config/gold_chunks.jsonl` (chunks-ouro curados) para que o funil de retrieval
> (TAREFA-501+) funcione. Mantenha os IDs consistentes entre os arquivos.

### Monitorar progresso

Os logs estruturados (structlog, JSON) são emitidos para stdout. O status do run
pode ser consultado a qualquer momento:

```bash
ielm-eval status --run-id <run_id> --config config/experiment_round1.yaml
```

### Retomando uma execução interrompida (ADR-009)

A resumabilidade é garantida por `row_id` (ADR-009): cada linha do Parquet tem um
`row_id` único (SHA-256 hex dos parâmetros da célula). Ao re-executar, linhas já
existentes são detectadas via `exists()` e a computação upstream é pulada.

> Quando o full run estiver implementado, basta re-executar o mesmo comando — nenhum
> flag adicional é necessário.

### Onde ficam os Parquets gerados

Os resultados são gravados em partições Hive aninhadas sob `config/data/`:

```
config/data/
  round_id=round-1/
    experiment_phase=A/
      base=IDx_400k/
        llm=gpt-oss-120b/
          <row_id_hex>.parquet
        llm=gemma4:31b/
          <row_id_hex>.parquet
        ...
      base=ID_230K/
        llm=gpt-oss-120b/
          <row_id_hex>.parquet
        ...
    experiment_phase=B/
      base=IDx_400k/
        llm=gpt-oss-120b/
          <row_id_hex>.parquet
        ...
```

Cada arquivo corresponde a uma linha (1 pergunta × 1 LLM × 1 seed × 1 base).
O `<row_id_hex>` é o SHA-256 (64 hex chars) dos parâmetros da célula.
O diretório `data/` fica junto ao arquivo de configuração (`config/experiment_round1.yaml`).

### Verificar integridade

```bash
# Dry-run verifica a config; status mostra contagens do Parquet existente
ielm-eval run --dry-run --config config/experiment_round1.yaml
ielm-eval status --run-id <run_id> --config config/experiment_round1.yaml
```

---

## Seção 6 — Troca de ondas de geradores (M3 GH200)

### Funcionamento automático

O orquestrador `VLLMServerManagerAdapter` (TAREFA-019) + `WaveSchedulerService`
(TAREFA-303) gerenciam as trocas de onda automaticamente:

- **Onda 1:** sobe 3 geradores concorrentes (GPUs 0, 1, 2), executa todas as células
  da onda, para os processos (SIGTERM → SIGKILL).
- **Onda 2:** sobe os 2 geradores restantes (GPUs 0, 1), executa, para.
- O **juiz** (GPU 3) fica residente durante toda a rodada — nunca é reiniciado entre
  ondas.

O operador **não precisa fazer nada manualmente** entre ondas.

### Como verificar o estado das ondas

Os logs estruturados registram cada evento de ciclo de vida do servidor:

```
{"event":"vllm_server_started","model":"gpt-oss-120b","url":"http://localhost:8000/v1","wave":1}
{"event":"vllm_server_stopped","model":"gpt-oss-120b","forced":false,"wave":1}
{"event":"vllm_server_started","model":"glm-4.7-flash","url":"http://localhost:8000/v1","wave":2}
```

O `ielm-eval status` também exibe quantas células foram completadas por modelo.

### Sinal de falha na troca de onda

Se um processo vLLM morrer inesperadamente, o orquestrador lança `ServerStartTimeoutError`
(ver Seção 11 para solução). Os processos órfãos ficam vinculados às portas; use
`fuser -k 8000/tcp 8001/tcp` para liberá-las antes de reiniciar.

---

## Seção 7 — Anotação humana (Camada 3)

### Exportar respostas para revisão offline

```bash
ielm-eval annotate \
  --config config/experiment_round1.yaml \
  --run-id <run_id> \
  --export export_review.jsonl \
  --threshold 0.70
```

Exporta respostas com `final_score < 0.70` (ou NaN) ordenadas por score ascendente.
O especialista biomédico edita o arquivo JSONL offline.

### Formato do arquivo de anotação

O arquivo JSONL de entrada do especialista deve ter as colunas:

| Campo                  | Tipo      | Obrigatório | Descrição                                    |
|------------------------|-----------|-------------|----------------------------------------------|
| `row_id`               | string    | ✅          | SHA-256 hex (64 chars) — identificador único |
| `critical_failure_flag`| int (0/1) | ✅          | 0 = sem falha crítica; 1 = falha crítica     |
| `note`                 | string    | ❌          | Comentário opcional do especialista          |

### Ingerir anotações de volta ao Parquet

```bash
ielm-eval annotate \
  --config config/experiment_round1.yaml \
  --run-id <run_id> \
  --ingest export_review_editado.jsonl
```

A ingestão é **idempotente por `row_id`** (ADR-009): executar o comando com o mesmo
arquivo duas vezes não duplica registros. Para sobrescrever anotações existentes:

```bash
ielm-eval annotate \
  --config config/experiment_round1.yaml \
  --run-id <run_id> \
  --ingest export_review_editado.jsonl \
  --force
```

---

## Seção 8 — Análise e relatório (M4)

### Análise estatística

```bash
ielm-eval analyze \
  --run-id <run_id> \
  --config config/experiment_round1.yaml \
  --tests all
```

Executa os três testes estatísticos configurados (Wilcoxon signed-rank, Friedman +
Nemenyi post-hoc, modelo linear misto). Imprime tabela de p-valores e ranking de
configurações via `rich`. O JSON com estatísticas é salvo em:

```
config/data/<run_id>_round-1_stats.json
```

### Relatório executivo HTML

```bash
ielm-eval report \
  --run-id <run_id> \
  --config config/experiment_round1.yaml \
  --format html \
  --output-dir reports/
```

Gera 6 plots canônicos (heatmap de rankscore, boxplots de final_score, gráfico de
interação, radar, ranking por questão, breakdown de falhas) e um HTML executivo.

Outputs gerados em `reports/`:

```
reports/
  <run_id>_report.html          ← relatório executivo HTML
  plots/
    rankscore_heatmap.png
    finalscore_boxplots.png
    interaction.png
    radar.png
    per_question_ranking.png
    failure_breakdown.png
```

### Status do run

```bash
ielm-eval status \
  --run-id <run_id> \
  --config config/experiment_round1.yaml
```

---

## Seção 9 — Rodada 2 — funil de retrieval (M5)  `[PENDENTE: M5 não implementado]`

> **Esta seção é um STUB.** O M5 (Rodada 2 — funil OFAT de chunking/embedding) foi
> deliberadamente adiado; os subcomandos da CLI correspondentes (funil de retrieval e a
> fase top-N da Rodada 2) **ainda não existem**. Por isso esta seção **NÃO contém blocos
> de comando executáveis** — o smoke-test (`scripts/validate_manual.py`) não tem
> subcomando a validar aqui (blocos sob seção `[PENDENTE: ...]` são ignorados).
>
> Quando o M5 for implementado (TAREFA-501..507), esta seção deverá documentar — em prosa
> e com os blocos de comando REAIS confirmados via `ielm-eval --help`:
> - como configurar as variantes de chunking (fase 2a) e embedding (fase 2b) nos YAMLs
>   `config/experiment_round2a.yaml` / `config/experiment_round2b.yaml`;
> - o funil barato de retrieval puro (estágio 1, sem LLM) que ranqueia as configurações
>   por `precision@k`, `recall@k`, `MRR`, `nDCG@k` contra os chunks-ouro;
> - a execução da fase cara (estágio 2, com LLM e juiz) apenas nas top-N configurações
>   selecionadas pelo funil.
>
> **Atenção:** o nome exato do subcomando do funil (ex.: `ielm-eval funnel` ou outro)
> deve ser verificado na saída de `ielm-eval --help` quando o M5 for implementado.
> Não use este nome em scripts antes de confirmar via `ielm-eval --help`.
>
> **Pré-requisito do M5:** curadoria de chunks-ouro (Premissa P5) entregue. Até lá, o
> subsistema opera sobre a Rodada 1 (variação base × LLM).

---

## Seção 10 — Validação do juiz (M6)

### Computar Cohen's κ

```bash
ielm-eval validate-judge \
  --run-id <run_id> \
  --round-id A \
  --threshold 0.50 \
  --report docs/judge_validation_report.md \
  --config config/experiment_round1.yaml
```

Lê `rubric_biomed_score` e `critical_failure_flag` do Parquet, binariza o score do
juiz (`judge_binary = 1` quando `rubric_biomed_score < threshold`) e calcula κ.
Gera um relatório Markdown em `docs/judge_validation_report.md`.

### Interpretação do κ

| Faixa de κ    | Interpretação              | Ação recomendada                                    |
|---------------|----------------------------|-----------------------------------------------------|
| κ ≥ 0.60      | Concordância substancial   | Juiz aprovado — prosseguir com análise              |
| 0.40 ≤ κ < 0.60 | Concordância moderada    | Revisão das discordâncias; aceitável com ressalvas  |
| κ < 0.40      | Concordância fraca/ruim    | **Investigar**; revisar rubrica e prompt do juiz    |

**Se κ < 0.40:**
1. Analisar os casos de discordância (o relatório Markdown lista as linhas divergentes).
2. Revisar o template de prompt do juiz em
   `src/inteligenciomica_eval/infrastructure/prompts/`.
3. Verificar se `VLLM_BATCH_INVARIANT=1` estava ativo durante a execução da rodada
   (juiz não-determinístico invalida a comparação).
4. Ajustar o `threshold` de binarização (`--threshold`) se houver evidência de que o
   ponto de corte 0.50 não captura a escala do juiz.

---

## Seção 11 — Troubleshooting

| Problema | Diagnóstico | Solução |
|----------|-------------|---------|
| `ServerStartTimeoutError`: vLLM não sobe em tempo | Memória GPU insuficiente ou processo órfão bloqueando a porta | Verificar `nvidia-smi` para checar uso de VRAM. Matar processos órfãos: `fuser -k 8000/tcp 8001/tcp` |
| `VLLM_BATCH_INVARIANT` não reconhecido ou ignorado | Versão do vLLM anterior a 0.4.x | Atualizar vLLM: `uv add vllm --upgrade`. Verificar com `VLLM_BATCH_INVARIANT=1 python -c "import vllm; print(vllm.__version__)"` |
| Parquet corrompido / `ArrowTypeError` ao ler | Partição incompleta ou tipo incompatível | Deletar a partição afetada em `config/data/round-1/` e re-executar. A resumabilidade por `row_id` (ADR-009) garante que apenas as linhas ausentes serão recomputadas |
| Taxa de NaN no juiz > 5% | Prompt template mal-formado ou modelo não carregado corretamente | Checar o template em `infrastructure/prompts/`. Verificar logs de `prometheus_judge_completed` com `nan_fields` preenchido. `[PENDENTE: subcomando compute-metrics não implementado — recomputar manualmente re-executando o run]` |
| `import-linter` falha após adicionar nova dependência | Dependência de I/O importada em `domain` ou `application` | Revisar em qual camada o import está. Mover para `infrastructure/`. Atualizar `forbidden_modules` em `.importlinter` se necessário |
| `uv sync --frozen` falha com conflito de lock | `uv.lock` desatualizado em relação ao `pyproject.toml` | Executar `uv lock --upgrade` (atualiza o lock file) e commitar |
| Qdrant retorna 503 nas buscas | Coleção não encontrada ou serviço não inicializado | Verificar `curl http://localhost:6333/collections` e confirmar que `IDx_400k` e `ID_230K` existem |
| Score κ ausente (`not enough samples`) | Menos de 10 linhas com anotações humanas válidas | Aumentar o conjunto de anotações via `annotate --export` + ingestão antes de rodar `validate-judge` |

---

*Manual atualizado em 2026-06-05 — TAREFA-606 (M6-E9): Seção 4-B modo `external` + `--run-id` + perguntas multi-área. Gerado originalmente em 2026-06-03 (TAREFA-604). Próxima revisão: quando M5 for implementado.*
