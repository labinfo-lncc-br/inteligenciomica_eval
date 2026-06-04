# Prompt M3 — TAREFA-311 (Claude Code ↔ ChatGPT Codex)

**Milestone:** M3 (extensão pós-gate) — modo de implantação `external` + proveniência verificada
**Tarefa:** TAREFA-311 — Modo `external` de servidores (vLLM/Qdrant pré-existentes via túnel)
+ endurecimento de proveniência e rastreabilidade (sondas + schema §5.3)
**Documentos de referência:**
- `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1, §§ 4.3, 5.1, 5.3, 12, 14.6;
  RF8 proveniência total; RNF6 observabilidade; ADR-003/004/008/012)
- `prompts_m3_tarefas_301_310.md` — `VLLMServerManager` (managed), `ModelRegistryConfig`,
  `WaveSchedulerService`, run report (TAREFA-306)
- `prompts_m3_tarefa_309.md` / `prompts_m3_tarefa_310.md` — wiring, CLI `run`, gate E2E
**Formato:** **Prompt A (implementação — Claude Code)** + **Prompt B (verificação — ChatGPT Codex)**.
**Épico coberto:** E3/E4 (orquestração + proveniência).
**Introduz:** **ADR-013** — "Modo de servidor: `managed` vs `external`; proveniência verificada
por sonda (probe), não declarada".

> **Pressupõe** TAREFA-301..310 mergeadas e verdes (em especial `VLLMServerManagerPort`
> §5.1, `VLLMServerManager` managed/subprocess, `RunExperimentUseCase`, `ParquetStorage`
> §5.3, `provenance.py`/`config_hash`, run report TAREFA-306, wiring TAREFA-309 e gate
> E2E TAREFA-310).
> **Contexto de implantação (motivação):** em cluster compartilhado e **air-gapped** com
> GH200 (build ARM custoso), o vLLM e o Qdrant já rodam como serviços. O ielm-eval roda
> numa máquina x86 com internet e acessa os serviços por **túnel SSH** (portas locais).
> Nesse cenário o ielm-eval **NÃO** é dono do ciclo de vida do vLLM — apenas o consome.
> **Consequência central (ADR-013):** a garantia de determinismo (ADR-003) e a identidade
> dos modelos deixam de ser *garantidas pelo lançamento* e passam a ser *verificadas por
> sonda e gravadas* como proveniência. O modo `managed` (atual) permanece o **default** e
> inalterado.
> **O M5 permanece adiado** — nada de M5 é importado.
> DoD §14.2; `from __future__ import annotations`; `import-linter`; libs proibidas em
> `domain`/`application` continuam valendo.

---

## Protocolo de desenvolvimento em pares (Claude Code ↔ ChatGPT Codex)

Estamos desenvolvendo o **inteligenciômica-eval**, executando prompts organizados por
marcos. Cada prompt é dividido em **Parte A — implementação (Claude Code)** e **Parte B —
revisão e auditoria (ChatGPT Codex)**.

**Toda execução gera obrigatoriamente um relatório** do que foi feito e dos resultados.
O processo é **iterativo**: A → B → correção (A) → nova auditoria (B), até **PASS por
ambos**. O avanço **nunca é automático**: só com **minha autorização explícita** e após
`add`/`commit`/`push`. O **`CLAUDE.md`** padroniza os relatórios em `docs/dev-log/` e é
mantido atualizado.

> **Início:** execute a **Parte A** abaixo e produza o relatório. A **Parte B** roda em
> seguida (relatório + diff + saída de testes). Itere A↔B até PASS.

---

## Nota de operacionalização — decisões fixadas para 311

### 1. Config — `server_mode` e `endpoint_env`

- **`RoundConfig.server_mode: Literal["managed","external"] = "managed"`** (schema.py).
  Default `managed` (retrocompatível: 310 e produção GH200 local seguem funcionando).
- **`ModelEntry.endpoint_env: str | None = None`** (model_registry, TAREFA-301).
  No modo `external`, **cada** modelo (geradores + juiz) precisa de `endpoint_env`
  resolvível (env var com a URL tunelada). No modo `managed`, o campo é ignorado (a URL
  vem do `ServerHandle` do subprocesso). O juiz já tinha `endpoint_env` (M0); estender aos
  geradores.
- Validação no wiring: `server_mode=="external"` e algum `endpoint_env` ausente/não
  resolvível → `ConfigValidationError` nomeando o modelo e a env var faltante.

### 2. Adapter `ExternalVLLMServerManager` (implementa `VLLMServerManagerPort`)

`infrastructure/adapters/external_vllm_server_manager.py` — mesmos 3 métodos do Port (§5.1):
- `start(model_spec) -> ServerHandle`: **sem subprocess**. Resolve a URL de
  `model_spec.endpoint_env` (via settings/env). Retorna `ServerHandle` com
  `{pid=None, port=<parseada>, url, model_name, batch_invariant=<declarado>, gpu_index=-1, started_at}`.
  **Nunca** chama `subprocess.Popen`.
- `wait_healthy(handle, timeout_s)`: probe real `GET {url}/health` com backoff; se
  inacessível no timeout → `EndpointUnreachableError` (novo erro de domínio) com a URL
  mascarada. A CLI trata como Panel vermelho + exit 1 (mesmo caminho do
  `ServerStartTimeoutError`).
- `stop(handle)`: **NO-OP** — NÃO encerra processos (são compartilhados/remotos). Loga
  structlog `"external_server_stop_noop"` com a URL mascarada.

O Port e os use cases **não mudam** — só troca o adapter (inversão de dependência limpa).

### 3. Sondas de proveniência (`infrastructure/provenance/endpoint_probe.py`)

Rodam **uma vez por endpoint** no início do run (managed E external — servem de auditoria
nos dois modos) e o resultado é injetado por célula:
- `probe_served_model(url) -> str`: `GET {url}/v1/models` → id do modelo servido.
- `probe_vllm_version(url) -> str | None`: de `/version`, header de resposta ou metadata
  de `/v1/models`; indisponível → `None` (gravar `"unknown"`, **nunca** valor inventado).
- `probe_judge_determinism(url) -> bool`: envia a MESMA requisição mínima 2× (`temperature=0`)
  ao endpoint do **juiz** e compara as saídas byte a byte. Aplica-se **só ao juiz**
  (geradores rodam `temperature=0.1`, não-determinísticos por design — não sondar).

### 4. Proveniência por linha (extensão do schema §5.3) — ripple aceito

Adicionar **3 colunas** ao schema §5.3 (e ao agregado `EvaluationResult` §4.3):
- `server_mode: string` — `"managed"` | `"external"` (sempre preenchido).
- `served_model_id: string` — id real servido pelo endpoint **do gerador** desta célula
  (verifica se o `llm` lógico corresponde ao modelo realmente servido; protege contra
  túnel apontando para o modelo errado).
- `determinism_verified: bool` — resultado **medido** do probe de determinismo do **juiz**
  para este run (denormalizado por linha; a linha se autocertifica quanto ao regime do
  juiz que a pontuou).

A coluna existente `vllm_version` **muda de fonte**: passa a preferir o probe do endpoint;
fallback para `importlib.metadata`/env; indisponível → `"unknown"`. A checagem de coerência
de escrita existente (`batch_invariant==True ⇔ veio do juiz`) **permanece**. Acrescentar:
em `external` com `determinism_verified==False`, o run report sinaliza de forma proeminente.

### 5. Run report (estende TAREFA-306) — proveniência de nível de run

Acrescentar ao run report uma seção `endpoints_provenance`:
`server_mode`; por endpoint (gerador(es) + juiz): `{logical_name, endpoint (mascarado),
served_model_id, vllm_version, healthy, determinism_verified (juiz)}`; `config_hash`; nota
de topologia (texto livre, ex.: "via túnel SSH"). É o "passaporte" da rodada — auditável
sem acesso aos nodes.

### 6. Escalonador de ondas no modo `external`

`start`/`stop` são no-ops, então o fluxo do `WaveSchedulerService` não causa dano; porém:
- **Pular** a validação de empacotamento VRAM/GPU (`sum(vram_awq) ≤ available_gb`) — não há
  GPUs de posse do ielm-eval. O plano de ondas vira **informativo**.
- Os endpoints estão todos disponíveis simultaneamente; não há rotação de modelos.

### 7. CLI — aviso de responsabilidade + modo estrito

- No início de um run `external`, imprimir **Rich Panel (warning)** inequívoco: neste modo
  o ielm-eval **não controla** determinismo nem identidade de modelo; mostrar resultado dos
  probes (determinismo do juiz: PASS/FAIL; modelos servidos == esperados: sim/não).
- Flag **`--require-verified-determinism`**: se presente e o probe do juiz falhar → abortar
  com exit 1 (runs de qualidade de publicação). Default: avisar + prosseguir + marcar as
  linhas (`determinism_verified=false`).
- O aviso e o resultado dos probes vão também para structlog e para o run report.

### 8. Ripple coordenado (no MESMO PR)

- `domain/entities`/`value_objects` (`EvaluationResult` §4.3 + 3 campos).
- `ResultWriterPort`/`ParquetStorage` (schema §5.3 + coerência de escrita).
- **TAREFA-310 (gate E2E):** atualizar `tests/e2e/test_m3_full_cycle.py` e
  `tests/golden/e2e_m3_expected.json` para incluir as 3 colunas; os fakes devem fornecê-las
  (`server_mode="managed"`, `served_model_id` derivado do stub, `determinism_verified=True`).
- **M4 (análise/relatório):** confirmar que tolera as colunas novas (aditivas); opcionalmente
  expor `server_mode`/`determinism_verified` no relatório. **Não quebrar** o E2E do M4.
- Atualizar a doc §§4.3/5.3 e registrar **ADR-013** em `docs/adr/`.

---

## TAREFA-311 — Modo `external` + proveniência verificada

**Épico:** E3/E4 · **Skills:** backend-engineer, python-engineer, python-clean-architecture §1 ·
**Prioridade:** P0 · **Tamanho:** L
**Dependências:** TAREFA-301 (ModelRegistry/ModelEntry), TAREFA-302 (VLLMServerManagerPort +
managed adapter), TAREFA-306 (run report), TAREFA-307 (RunExperimentUseCase), TAREFA-309
(wiring + CLI), TAREFA-310 (gate E2E) · **ADRs:** ADR-003, ADR-004, ADR-008, ADR-012,
**ADR-013 (novo)** · **RF:** RF8 · **RNF:** RNF6 · **Camadas:** `domain`, `infrastructure/adapters`,
`infrastructure/provenance`, `infrastructure/config`, `infrastructure/wiring`, `cli`, `tests`

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §§4.3, 5.1, 5.3, 12,
14.6; RF8; RNF6; ADR-003/004/008/012). Skills: backend-engineer, python-engineer,
python-clean-architecture §1. TAREFA-301..310 mergeadas e verdes. Esta tarefa adiciona o
modo de implantação `external` (vLLM/Qdrant pré-existentes acessados por túnel) e endurece
a proveniência: o que era garantido pelo lançamento dos servidores passa a ser VERIFICADO
por sonda e GRAVADO em cada linha + no run report. Registrar ADR-013.
VER "Nota de operacionalização — 311", itens 1–8.

LEIA ANTES DE CODAR: `VLLMServerManagerPort` (§5.1) e o `VLLMServerManager` managed
(TAREFA-302), `ServerHandle`, `ModelRegistryConfig`/`ModelEntry` (TAREFA-301), o run report
(TAREFA-306), o `RunExperimentUseCase` (TAREFA-307), o wiring (TAREFA-309), o schema §5.3 do
`ParquetStorage`/`ResultWriterPort` e o `EvaluationResult` (§4.3). NÃO inventar nomes —
confirmar os reais.

TAREFA: TAREFA-311 — implementar:
  (a) ADR-013 (docs/adr/) — managed vs external; proveniência por sonda.
  (b) config: `RoundConfig.server_mode` + `ModelEntry.endpoint_env`.
  (c) `ExternalVLLMServerManager` (implementa `VLLMServerManagerPort`).
  (d) sondas de endpoint (served_model, vllm_version, judge_determinism).
  (e) extensão do schema §5.3 + `EvaluationResult`: server_mode, served_model_id,
      determinism_verified; vllm_version passa a vir do probe.
  (f) run report: seção endpoints_provenance.
  (g) wiring: seleção de adapter por server_mode + validação de endpoint_env.
  (h) CLI: aviso de responsabilidade + flag --require-verified-determinism.
  (i) ripple coordenado: atualizar gate E2E (310) + golden; doc §§4.3/5.3.

ESPECIFICAÇÃO:

1. ADR-013 — docs/adr/ADR-013-server-mode-external.md
   Decisão, contexto (air-gap/ARM/cluster compartilhado), consequências (responsabilidade
   de determinismo/identidade migra para o operador; proveniência verificada por sonda),
   alternativas consideradas. Referenciar ADR-003/004/012.

2. CONFIG (infrastructure/config/schema.py + model_registry)
   - RoundConfig.server_mode: Literal["managed","external"] = "managed" (validado).
   - ModelEntry.endpoint_env: str | None = None. Documentar: obrigatório em external;
     ignorado em managed.

3. ADAPTER — infrastructure/adapters/external_vllm_server_manager.py
   - Implementa exatamente VLLMServerManagerPort (start/wait_healthy/stop).
   - start(): sem subprocess (patch de Popen NÃO deve ser chamado); resolve URL de
     endpoint_env; ServerHandle com pid=None, gpu_index=-1, batch_invariant declarado.
   - wait_healthy(): GET {url}/health com backoff; inacessível → EndpointUnreachableError
     (novo erro em domain/errors) com URL mascarada.
   - stop(): NO-OP + log structlog "external_server_stop_noop".
   - Logging estruturado em todos os métodos.

4. SONDAS — infrastructure/provenance/endpoint_probe.py
   - probe_served_model(url) -> str  (GET /v1/models)
   - probe_vllm_version(url) -> str | None  (/version | header | metadata; None se ausente)
   - probe_judge_determinism(url) -> bool  (mesma prompt 2×, temperature=0, byte-igual)
   - HTTP via o mesmo cliente já usado pelos adapters (httpx); timeouts; erros tratados.

5. SCHEMA §5.3 + ENTIDADE §4.3
   - Adicionar a EvaluationResult (domain): server_mode: str, served_model_id: str,
     determinism_verified: bool.
   - ParquetStorage/ResultWriterPort: 3 colunas novas (tipos: string, string, bool).
     vllm_version preenchido pelo probe (fallback importlib.metadata/env; "unknown" se nada).
   - Manter a coerência de escrita (batch_invariant==True ⇔ juiz). Em external +
     determinism_verified==False, marcar para o run report sinalizar.

6. RUN REPORT (estende TAREFA-306)
   - Seção endpoints_provenance: server_mode; por endpoint {logical_name, endpoint
     (mascarado), served_model_id, vllm_version, healthy, determinism_verified(juiz)};
     config_hash; nota de topologia. Persistido junto ao report existente.

7. WIRING (infrastructure/wiring.py — estende TAREFA-309)
   - build_container escolhe ExternalVLLMServerManager se config.server_mode=="external",
     senão o managed (TAREFA-302).
   - external: validar endpoint_env de cada modelo (ausente → ConfigValidationError com
     modelo+var); pular validação VRAM/GPU; rodar os probes e injetar a proveniência.
   - managed: comportamento atual (inclui rodar probes como auditoria; determinism_verified
     esperado True — se False, sinalizar no report).

8. CLI (cli.py — estende run da TAREFA-309)
   - external: Rich Panel (warning) de responsabilidade no início, com resultado dos probes.
   - flag --require-verified-determinism: probe do juiz falho → exit 1.
   - Resultado dos probes em structlog + run report. NUNCA stacktrace no stdout.

9. RIPPLE COORDENADO
   - tests/e2e/test_m3_full_cycle.py + tests/golden/e2e_m3_expected.json: incluir as 3
     colunas (fakes: server_mode="managed", served_model_id do stub, determinism_verified=True);
     o gate continua 12 células, < 30 s.
   - Confirmar que o E2E/relatório do M4 tolera as colunas novas (rodar a suíte do M4).
   - Atualizar doc §§4.3 e 5.3 (tabela de colunas) com os 3 campos.

10. TESTES
   tests/unit/infrastructure/test_external_server_manager.py:
     - start não chama subprocess.Popen (mock) e devolve ServerHandle da env var.
     - wait_healthy: /health 200 (httpx mock) → ok; inacessível → EndpointUnreachableError.
     - stop é no-op (nenhum kill/terminate chamado).
   tests/unit/infrastructure/test_endpoint_probe.py:
     - served_model_id parseado de /v1/models mockado.
     - vllm_version de header/version; None quando ausente.
     - judge_determinism True (2 respostas idênticas) e False (diferentes).
   tests/unit/infrastructure/test_provenance_columns.py:
     - roundtrip Parquet com as 3 colunas; tipos corretos; "unknown" quando version ausente.
   tests/unit/infrastructure/test_wiring_external.py:
     - server_mode=external seleciona ExternalVLLMServerManager.
     - endpoint_env ausente → ConfigValidationError (modelo+var).
     - VRAM check pulado em external.
   tests/unit/cli/test_run_external.py:
     - Panel de responsabilidade exibido em external.
     - --require-verified-determinism + probe falho → exit 1.

ENTREGÁVEL:
- docs/adr/ADR-013-server-mode-external.md
- src/inteligenciomica_eval/infrastructure/adapters/external_vllm_server_manager.py
- src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py (+ __init__)
- src/inteligenciomica_eval/infrastructure/config/schema.py (server_mode)
- src/inteligenciomica_eval/infrastructure/config/model_registry.py (endpoint_env)
- src/inteligenciomica_eval/domain/{entities,value_objects,errors}.py
  (EvaluationResult + 3 campos; EndpointUnreachableError)
- src/inteligenciomica_eval/infrastructure/storage/<parquet>.py + ResultWriterPort (3 colunas)
- src/inteligenciomica_eval/infrastructure/<run_report>.py (endpoints_provenance)
- src/inteligenciomica_eval/infrastructure/wiring.py (seleção de adapter + probes)
- src/inteligenciomica_eval/cli.py (Panel + --require-verified-determinism)
- tests/... (5 arquivos acima) + atualização de tests/e2e/test_m3_full_cycle.py + golden
- docs (atualização §§4.3/5.3)
- docs/dev-log/M3_TAREFA-311_A_<slug>.md (relatório; Observações: o operations_manual
  precisa da seção de modo external — TAREFA da emenda do manual)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings Google-style; mypy --strict.
- `ruff check`/`ruff format --check`/`lint-imports` verdes.
- Port inalterado: external entra por adapter (inversão de dependência). use cases não mudam.
- external NUNCA encerra processos remotos (stop no-op). managed default e inalterado.
- Sem segredos hardcoded (URLs por env, ADR-008); endpoints mascarados em logs/Panels.
- Nenhum valor de proveniência inventado: indisponível → "unknown"/false explícito.
- Cobertura: gate 85%.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-311):
- server_mode=managed: comportamento idêntico ao atual; suíte M3/M4 verde.
- server_mode=external: build_container seleciona ExternalVLLMServerManager; endpoint_env
  ausente → ConfigValidationError; start não sobe subprocess; stop é no-op.
- Probes: served_model_id, vllm_version (ou "unknown"), judge_determinism corretos.
- 3 colunas novas presentes e fiéis no Parquet (roundtrip); coerência de escrita mantida.
- Run report tem endpoints_provenance com os campos do item 6.
- CLI external: Panel de responsabilidade + probes; --require-verified-determinism aborta
  em probe falho.
- Gate E2E (310) atualizado: 12 células, < 30 s, 3 colunas no golden; suíte M4 verde.
- ADR-013 versionado; doc §§4.3/5.3 atualizadas.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer + test-engineer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-311 + arquitetura §§4.3/5.1/5.3/14.6 + RF8/RNF6 +
ADR-003/004/008/012 + ADR-013 (novo) + "Nota de operacionalização 311" + relatório (Parte A).

VERIFIQUE, item a item, citando arquivo:linha:

1. ADR-013 presente, descrevendo managed vs external e a migração da responsabilidade de
   determinismo/identidade para o operador, com proveniência por sonda?

2. Config:
   a. RoundConfig.server_mode com default "managed" (retrocompatível) e validado?
   b. ModelEntry.endpoint_env opcional; doc diz obrigatório em external/ignorado em managed?

3. ExternalVLLMServerManager:
   a. Implementa exatamente o Port (start/wait_healthy/stop)?
   b. start() NÃO chama subprocess.Popen (mock comprova)? ServerHandle da env var?
   c. wait_healthy() faz GET /health; inacessível → EndpointUnreachableError com URL mascarada?
   d. stop() é NO-OP (nenhum kill/terminate)? Log "external_server_stop_noop"?

4. Sondas:
   a. probe_served_model lê /v1/models? probe_vllm_version retorna None quando ausente
      (e o pipeline grava "unknown", nunca valor inventado)?
   b. probe_judge_determinism compara 2 respostas (temperature=0) só para o juiz?

5. Schema/entidade:
   a. EvaluationResult tem server_mode, served_model_id, determinism_verified?
   b. ParquetStorage/ResultWriterPort gravam as 3 colunas (tipos corretos)?
   c. vllm_version vem do probe (fallback importlib/env; "unknown" se nada)?
   d. Coerência de escrita batch_invariant==True ⇔ juiz mantida?

6. Run report:
   a. Seção endpoints_provenance com server_mode + por-endpoint (served_model_id,
      vllm_version, healthy, determinism_verified) + config_hash + topologia?

7. Wiring:
   a. server_mode=external → ExternalVLLMServerManager; managed → adapter de subprocess?
   b. endpoint_env ausente em external → ConfigValidationError (modelo+var)?
   c. Validação VRAM/GPU pulada em external?
   d. Probes executados e proveniência injetada (em ambos os modos)?

8. CLI:
   a. Panel de responsabilidade em external com resultado dos probes?
   b. --require-verified-determinism + probe falho → exit 1?
   c. Endpoints mascarados em Panels/log? Nenhum stacktrace no stdout?

9. Ripple coordenado:
   a. tests/e2e/test_m3_full_cycle.py + golden atualizados (3 colunas; fakes fornecem-nas)?
      Gate ainda 12 células < 30 s?
   b. Suíte do M4 (análise/relatório) PASS com as colunas novas (cole o resultado)?
   c. Doc §§4.3/5.3 atualizadas com os 3 campos?

10. Testes (5 arquivos): external_server_manager, endpoint_probe, provenance_columns,
    wiring_external, run_external — todos os casos presentes e verdes?

11. DoD §14.2:
    a. Port inalterado (external por adapter; use cases intactos)?
    b. external nunca encerra processos remotos? managed inalterado?
    c. `from __future__ import annotations`; mypy --strict; ruff; lint-imports verdes?
    d. Cobertura ≥ 85% (cole o relatório)?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade:
BLOQUEADOR | IMPORTANTE | SUGESTÃO).
Confirme regressão: server_mode=managed mantém o comportamento atual (suíte M3/M4 verde).
Cole a saída de: `pytest -m "unit or e2e" -q` (sumário) e `pytest --cov=src --cov-fail-under=85 -q`.
~~~
