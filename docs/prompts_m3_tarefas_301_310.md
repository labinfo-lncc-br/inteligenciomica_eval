# Prompts M3 — TAREFA-301 a 310 (Claude Code ↔ ChatGPT Codex)

**Milestone:** M3 — Orquestração experimental (gestão de servidores, arquitetura de 3 passadas, ciclo completo A+B, wiring e gate de integração)
**Documento de referência:** `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1)
**Continuação de:** `prompts_m0_tarefas_007_012.md` (M0), prompts M1 e M2
**Formato:** para cada tarefa, um **Prompt A (implementação — Claude Code)** e um **Prompt B (verificação — ChatGPT Codex)**, conforme seção 16 do documento de arquitetura.
**Uso:** o desenvolvedor sênior cola o Prompt A no Claude Code; ao receber o PR, cola o Prompt B no Codex; arbitra PASS/FAIL; itera até PASS; só então avança respeitando o DAG do §14.3.

> Pressupõe que **M0 (001–012), M1 e M2 já estão mergeados e verdes**. M1 entregou os adapters core de retrieval e geração: `QdrantRetrieverAdapter` (implementa `RetrieverPort`), `OpenAICompatibleClient` (cliente HTTP base com retry/backoff), `VLLMGeneratorAdapter` (implementa `GeneratorPort`). M2 entregou o pipeline de métricas: `RAGASMetricSuiteAdapter` (implementa `MetricSuitePort`), `BERTScoreAdapter` (implementa `DeterministicMetricPort`), `PrometheusJudgeAdapter` (implementa `RubricJudgePort`). A "Nota de operacionalização" do M0 (lista canônica de libs proibidas em `domain`/`application`; `ResultFrame` como wrapper sobre `tuple[EvaluationResult, ...]`) **continua valendo integralmente** e é referenciada abaixo.

---

## Nota de operacionalização adicional (decisões que M3 fixa — vetáveis pela equipe)

Quatro pontos que 301–310 precisam fixar para Code e Codex não divergirem:

1. **Arquitetura de 3 passadas independentes e retomáveis (§5.4 e ADR-004).** A execução de cada célula `{base, llm, seed, question}` é decomposta em três passadas sequenciais, cada uma implementada como um use case independente em `application/use_cases/`:
   - **Passada 1 — Geração** (`RunGenerationPassUseCase`): chama retriever + gerador, persiste `generated_answer` + campos de retrieval + `latency_ms`/tokens. Não computa métricas.
   - **Passada 2 — Métricas** (`RunMetricsPassUseCase`): lê as linhas já geradas, computa métricas de Camada 1 (RAGAS) + BERTScore, chama `FinalScoreCalculator`, escreve os campos de métrica + `final_score`. Não sobe o juiz.
   - **Passada 3 — Juiz** (`RunJudgePassUseCase`): lê as linhas já pontuadas, chama o Prometheus-2 (Camada 2), escreve `rubric_biomed_score` + `rubric_feedback`. Requer servidor juiz com `VLLM_BATCH_INVARIANT=1`.
   - Cada passada é idempotente por `RowId` (ADR-009): linhas com campos da passada já preenchidos são puladas silenciosamente. Isso permite reexecução parcial sem regeração de respostas.

2. **`VLLMServerManager` gerencia PROCESSOS via `subprocess`, não apenas URLs.** O adapter real (`infrastructure/adapters/vllm_server_manager.py`) — localização canônica conforme §8 — inicia instâncias do vLLM como subprocessos, aguarda o health check (`GET /health` → HTTP 200) e os encerra na saída. **Cada servidor é fixado a uma GPU via `CUDA_VISIBLE_DEVICES`** (ADR-012 — pré-requisito de isolamento de concorrência). Timeout de startup configurável (default: 180 s); falha → `ServerStartTimeoutError`. Dois perfis de servidor são rigidamente distintos pelo flag `batch_invariant: bool` que vem do `ModelEntry` (TAREFA-301): **juiz** (`batch_invariant=True`, `temperature=0`, `tensor_parallel_size=1`) e **gerador** (`batch_invariant=False`, configuração de produção). Esta separação NÃO pode ser colapsada — é a garantia de reprodutibilidade científica do subsistema (ADR-003).

3. **Wave scheduler segue ADR-012 — ondas CONCORRENTES por padrão.** O GH200 tem 4 GPUs; ADR-012 aloca GPU 3 ao juiz residente e GPUs 0–2 aos geradores em **2 ondas concorrentes** (onda 1: 3 modelos; onda 2: 2 modelos). O `WaveSchedulerService` (`application/services/wave_scheduler.py`) planeja esse layout por padrão. Flag `allow_concurrent_models: bool = True` (default ADR-012: True = concorrente; False = serial, 1 modelo por onda — modo conservador para depuração ou quando apenas 1 GPU está disponível). Empacotamento de onda: para `allow_concurrent_models=True`, verificar que `sum(vram_awq dos modelos da onda) ≤ sum(available_gb dos slots de geração)`. **NUNCA** colocar juiz e gerador na mesma onda (ADR-003). O `WaveSchedulerService` recebe um VO de domínio `ModelWaveSpec` (ver item 5 abaixo) — nunca `ModelRegistryConfig` diretamente.

4. **DI wiring vive em `infrastructure/wiring.py`, não no CLI.** O `cli.py` permanece enxuto: chama `build_container(config, settings) -> DIContainer` definido em `infrastructure/wiring.py`, que instancia e injeta todos os adapters reais nos use cases. Para testes, o harness de E2E substitui o container por um container de fakes sem alterar `cli.py`. `DIContainer` é uma `@dataclass(frozen=True)` ou similar — sem frameworks de DI de terceiros em M3 (suficiência antes de sofisticação; referência: ADR-001 Clean Architecture + ADR-008 config declarativa). O CLI nunca instancia adapters diretamente.

5. **Extensões de contrato que M3 declara (não previstas em §5.1 mas necessárias — registrar como delta do contrato, vetável pela equipe):**
   - **`ModelWaveSpec`** (novo VO de domínio, `domain/value_objects.py`): `name: str`, `vram_gb_awq: float`, `is_judge: bool`, `tensor_parallel_size: int`, `quantization: str`, `extra_args: dict[str,str]`, `gpu_index: int`. Extrai de `ModelEntry` (TAREFA-301) no wiring (TAREFA-309). Permite que `WaveSchedulerService` (camada `application/`) opere sem importar de `infrastructure/`.
   - **`MetricSuitePort.score_batch(samples)`**: extensão opcional ao port §5.1 para processamento em lote; o adapter retorna `list[Layer1Metrics]`. A assinatura canônica `score(sample)` permanece inalterada.
   - **`ResultWriterPort.update_metrics()` com kwargs estendidos**: M2 fixou `update_metrics(row_id, metrics, final_score)`. M3 adiciona `regime: DeterminismRegime` (para persistir `batch_invariant` conforme §4.3) e, na Passada 3, `rubric_score`, `rubric_feedback`. Declarar assinatura completa: `update_metrics(row_id, *, metrics: MetricVector | None = None, final_score: FinalScore | None = None, regime: DeterminismRegime | None = None, rubric_score: float | None = None, rubric_feedback: str | None = None) -> None`.
   - **`GeneratorFactory`** (novo Protocol em `domain/ports.py`): `__call__(self, url: str) -> GeneratorPort`. Permite ao `RunExperimentUseCase` criar geradores apontados para a URL do handle de cada onda sem acoplar infrastructure.
   - **Subpastas de `application/`**: M3 adota `application/use_cases/` e `application/services/` para organização (extensão ao §8 aprovada internamente). Atualizar `.importlinter` para incluir os novos subpaths.

---

## TAREFA-301 — Model registry + GPU layout (`infrastructure/config/model_registry.py`)

**Épico:** E3 · **Skill:** backend-engineer · **Prioridade:** P0 · **Tamanho:** S
**Dependências:** TAREFA-010 (config YAML), TAREFA-002 (exceções), TAREFA-003 (VOs) · **ADRs:** ADR-003 (regimes), ADR-008 (config declarativa), ADR-012 (alocação de GPUs) · **Camadas:** infrastructure/config + domain/value_objects

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §8 estrutura de código,
ADR-003, ADR-008, ADR-012). Padrão: python-clean-architecture §3 (config via Pydantic v2;
fail-fast na carga). Depende de TAREFA-010 (schema de rodada em infrastructure/config/schema.py)
e TAREFA-002 (ModelNotInRegistryError). VER "Nota de operacionalização M3" itens 2 e 5.

TAREFA: TAREFA-301 — implementar o model registry e o GPU layout em dois artefatos:
  (a) `src/inteligenciomica_eval/infrastructure/config/model_registry.py` — modelos Pydantic
      de configuração de serving (infra pura).
  (b) `src/inteligenciomica_eval/domain/value_objects.py` — adicionar `ModelWaveSpec`
      (VO de domínio que abstrai os dados de GPU para uso em `application/`).
  (c) `config/model_registry.yaml` — arquivo separado de `experiment_round1.yaml` (§8 e §12.1).

ESPECIFICAÇÃO:
- Modelo Pydantic v2 `ModelEntry` (por LLM registrado):
    name        : str           # ex.: "llama4:16x17b" — deve bater com LLMId do domínio
    hf_repo     : str           # ex.: "meta-llama/Llama-4-Scout-17B-16E-Instruct"
    vram_gb_fp16 : float        # memória em FP16 (referência teórica)
    vram_gb_awq  : float        # memória em AWQ 4-bit (valor real de produção)
    quantization : Literal["awq", "fp16", "fp8", "bfloat16"]
    tensor_parallel_size : int  # TP default; 1 obrigatório para o juiz (ADR-003/012)
    gpu_index   : int           # GPU dedicada (ADR-012: juiz=3; geradores=0,1,2)
    is_judge    : bool          # True somente para Prometheus-2
    batch_invariant : bool      # deve ser True quando is_judge=True (ADR-003)
    extra_args  : dict[str, str] = {}  # flags vLLM adicionais

  Validação cross-field: se `is_judge=True`, exigir `batch_invariant=True` e
  `tensor_parallel_size=1`; caso contrário, levantar `ConfigValidationError` com mensagem
  explicitando ADR-003. Se `is_judge=False`, `batch_invariant` DEVE ser False (produção real).

- Modelo Pydantic v2 `GPUSlot`:
    gpu_index   : int           # 0-based
    vram_gb     : float         # VRAM disponível (ex.: 96.0 ou 141.0 para GH200)
    reserved_gb : float = 8.0   # headroom para KV-cache e OS; default 8 GB

  Propriedade calculada `available_gb -> float` = vram_gb - reserved_gb.

- Modelo Pydantic v2 `ModelRegistryConfig`:
    models      : list[ModelEntry]
    gpu_slots   : list[GPUSlot]
    Validações:
      * Nomes de modelos únicos (sem duplicatas).
      * Exatamente um modelo com `is_judge=True` — levantar `ConfigValidationError`
        se zero ou mais de um.
      * Para CADA `ModelEntry`, verificar que `vram_gb_awq <= gpu_slots[model.gpu_index].available_gb`;
        se exceder, levantar `ConfigValidationError` com nome do modelo e VRAM necessária vs. disponível.

- `config/model_registry.yaml` como arquivo SEPARADO de `experiment_round1.yaml` (§8/§12.1):
  Atualizar `config/model_registry.yaml` com as entradas dos 5 LLMs avaliados + Prometheus-2
  como juiz, usando os valores reais da §7.2 / §15 do doc-base e ADR-012 (gpu_index por modelo).
  O YAML de rodada (`experiment_round1.yaml`) NÃO embute o registry — referencia apenas
  `model_registry_path: str` (path relativo ao YAML de rodada). O `DIContainer` (TAREFA-309)
  carrega os dois arquivos separadamente.

- VO de domínio `ModelWaveSpec` (`domain/value_objects.py`):
  `@dataclass(frozen=True) ModelWaveSpec`: name, vram_gb_awq, is_judge,
  tensor_parallel_size, quantization, gpu_index, extra_args.
  Construído pelo wiring (TAREFA-309) a partir de `ModelEntry`; passado ao
  `WaveSchedulerService` (TAREFA-303) para evitar import de infrastructure em application/.

- Função utilitária `get_model(registry: ModelRegistryConfig, llm_id: LLMId) -> ModelEntry`:
  lança `ModelNotInRegistryError` se não encontrado.

ENTREGÁVEL:
- src/inteligenciomica_eval/infrastructure/config/model_registry.py
- Atualização de src/inteligenciomica_eval/domain/value_objects.py (ModelWaveSpec)
- Atualização de src/inteligenciomica_eval/infrastructure/config/schema.py
  (adicionar `model_registry_path: str` em RoundConfig — NÃO embutir ModelRegistryConfig)
- config/model_registry.yaml (arquivo separado, 6 modelos)
- tests/unit/config/test_model_registry.py

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; Pydantic v2; docstrings Google; type hints; mypy --strict.
- infrastructure → domain (nunca o contrário); import-linter verde.
- `config/model_registry.yaml` nunca contém segredos (endpoints via env — ADR-008).

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-301):
- YAML com juiz `batch_invariant=False` ou `tensor_parallel_size=2` falha com
  `ConfigValidationError` apontando ADR-003.
- YAML com dois juízes (`is_judge=True` em dois modelos) falha.
- Modelo cujo `vram_gb_awq` excede `available_gb` do seu `gpu_index` falha na carga.
- `get_model` lança `ModelNotInRegistryError` para nome desconhecido.
- `config/model_registry.yaml` carrega sem erros e contém os 6 modelos (5 geradores + juiz).
- `ModelWaveSpec` é frozen dataclass em domain/; sem import de infrastructure em domain/.
- `RoundConfig` contém `model_registry_path: str`, NÃO `ModelRegistryConfig` embutido.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-301 + arquitetura §8 (estrutura de código) + ADR-003/008/012 +
skill python-clean-architecture §3.

VERIFIQUE, item a item, citando arquivo:linha:
1. ModelEntry tem todos os campos especificados incluindo `gpu_index`? Validação cross-field
   is_judge→batch_invariant=True e tensor_parallel_size=1 presente com mensagem citando ADR-003?
   is_judge=False → batch_invariant=False também verificado?
2. GPUSlot: campos corretos, `available_gb` calculado como vram_gb - reserved_gb?
3. ModelRegistryConfig: unicidade de nomes, exatamente 1 juiz, verificação de VRAM por
   `gpu_slots[model.gpu_index].available_gb` (não max de todos os slots)?
4. `config/model_registry.yaml` é ARQUIVO SEPARADO de `experiment_round1.yaml`? `RoundConfig`
   contém `model_registry_path: str` (referência ao path), NÃO `ModelRegistryConfig` embutido?
5. `ModelWaveSpec` adicionado em `domain/value_objects.py` com os campos corretos?
   Domain NÃO importa infrastructure (import-linter)?
6. `get_model` lança ModelNotInRegistryError (não KeyError/ValueError genérico)?
7. Sem segredo no YAML versionado? DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Confirme execução de pytest (test_model_registry) e lint-imports.
~~~

---

## TAREFA-302 — `VLLMServerManager` real (`infrastructure/adapters/vllm_server_manager.py`)

**Épico:** E3 · **Skill:** backend-engineer · **Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-301 (ModelRegistryConfig), TAREFA-005 (VLLMServerManagerPort), TAREFA-002 (exceções) · **ADRs:** ADR-003 (regimes determinísticos), ADR-004 (geração/julgamento desacoplados), ADR-012 (alocação de GPUs via CUDA_VISIBLE_DEVICES) · **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §8 estrutura de código,
ADR-003, ADR-004, ADR-012). Padrão: python-clean-architecture §1 (adapter de infra implementa
Port de domínio); gestão de subprocessos, health check, graceful shutdown. Depende de
TAREFA-301 (ModelRegistryConfig) e TAREFA-005 (VLLMServerManagerPort). VER "Nota de
operacionalização M3" itens 2 e 5.

TAREFA: TAREFA-302 — implementar `VLLMServerManagerAdapter` em
`src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py`,
implementando `VLLMServerManagerPort` (TAREFA-005) com os métodos canônicos de §5.1.

ESPECIFICAÇÃO:
- `VLLMServerManagerAdapter` implementa `VLLMServerManagerPort` (assinaturas exatas de §5.1):
    `start(model_spec: ModelSpec) -> ServerHandle`
    `wait_healthy(handle: ServerHandle, timeout_s: int) -> None`
    `stop(handle: ServerHandle) -> None`

  Método auxiliar privado (NÃO faz parte do Port §5.1):
    `_is_healthy(handle: ServerHandle) -> bool`  # usado internamente por wait_healthy

- `start()`:
  * Monta o comando `python -m vllm.entrypoints.openai.api_server` com argumentos
    derivados do `ModelSpec` (que é construído a partir do `ModelEntry` da TAREFA-301):
    `--model`, `--quantization`, `--tensor-parallel-size`, `--max-model-len`, `--port`.
  * **`CUDA_VISIBLE_DEVICES` obrigatório (ADR-012):** injetar `CUDA_VISIBLE_DEVICES=str(model_spec.gpu_index)`
    no ambiente do subprocesso para fixar cada servidor à sua GPU dedicada (juiz=GPU 3;
    geradores=GPUs 0, 1, 2). Sem isso, ADR-012 não implementado.
  * Para o JUIZ (`batch_invariant=True`): injetar TAMBÉM `VLLM_BATCH_INVARIANT=1` e
    `VLLM_ENABLE_V1_MULTIPROCESSING=0` no ambiente do subprocesso (ADR-003).
    Para GERADORES: NÃO setar essas variáveis (ADR-003, produção realista).
  * Inicia via `subprocess.Popen` com `stdout=PIPE` e `stderr=PIPE` redirecionados
    para logging estruturado (structlog) sem bloquear — use threads daemon para drenar os
    pipes (evitar deadlock no SO por buffer cheio).
  * Retorna `ServerHandle` com `{pid, port, url, model_name, batch_invariant, gpu_index, started_at}`.

- `wait_healthy()` (nome canônico §5.1 — NÃO `wait_until_ready`):
  * Poll em `GET {handle.url}/health` com backoff exponencial (initial=1s, max=15s).
  * Timeout: `timeout_s` (padrão 180 s, int conforme §5.1). Se expirado → `ServerStartTimeoutError`
    com pid + model_name + elapsed.
  * Verificar também que o processo não morreu (`handle.process.poll() is not None`) antes
    do timeout: se morreu, levantar imediatamente com tail das últimas 20 linhas de stderr.

- `stop()`:
  * Enviar SIGTERM; aguardar até 30 s (configurável); se ainda vivo, SIGKILL.
  * Logar resultado (graceful vs. forçado) via structlog.

- `_is_healthy()` (privado, auxiliar):
  * `GET /health` → True se HTTP 200 em < 2 s; False caso contrário (sem levantar exceção).
  * Usado por `wait_healthy()` no poll; NÃO exposto como método público do Port.

- Errors: `ServerStartTimeoutError` e `ModelSwitchError` (TAREFA-002). `ModelSwitchError`
  é levantado quando `start()` é chamado em uma porta já ocupada (detectado por tentativa
  de bind ao socket).

- Logging estruturado (structlog) obrigatório: logar start, wait_healthy, ready, stop
  com campos {model_name, port, pid, batch_invariant, gpu_index, elapsed_ms}.
  NÃO logar conteúdo das respostas dos modelos.

ENTREGÁVEL:
- src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py
- tests/integration/adapters/test_vllm_server_manager.py (usa `unittest.mock.patch` para
  substituir `subprocess.Popen` e `requests.get` — NÃO exige vLLM real instalado;
  testa fluxo completo incluindo timeout, morte do processo e SIGKILL fallback)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings; mypy --strict.
- Sem segredos hardcoded. SIGTERM antes de SIGKILL — nunca matar sem tentar graceful.
- Método público: apenas os 3 do Port §5.1. `_is_healthy` privado (prefixo `_`).
- import-linter: infrastructure → domain/ports; sem ciclo.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-302):
- `CUDA_VISIBLE_DEVICES=str(gpu_index)` injetado no env do subprocesso para TODOS os
  modelos (juiz=3, geradores=0/1/2) — testado via inspeção do env do Popen mockado.
- Juiz lança processo com `VLLM_BATCH_INVARIANT=1` no env; gerador NÃO tem essa variável —
  testado via inspeção do env do Popen mockado.
- Timeout durante `wait_healthy` ⇒ ServerStartTimeoutError com tail do stderr.
- Processo morre antes do timeout ⇒ ServerStartTimeoutError imediata.
- `stop()` envia SIGTERM primeiro; SIGKILL apenas se necessário.
- Pipe de stdout/stderr drenado em thread daemon (sem deadlock).
- `_is_healthy` é PRIVADO (prefixo `_`); `VLLMServerManagerPort` satisfeito com 3 métodos.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-302 + arquitetura §8 (estrutura de código) + §7.2 (topologia) +
ADR-003/004/012 + skill backend-engineer.

VERIFIQUE, item a item, citando arquivo:linha:
1. Arquivo em `infrastructure/adapters/vllm_server_manager.py` (NÃO em servers/)?
2. Implementa exatamente VLLMServerManagerPort §5.1 (3 métodos: start, wait_healthy, stop)?
   `is_healthy` é PRIVADO (`_is_healthy`) — não faz parte do Port?
3. `CUDA_VISIBLE_DEVICES=str(gpu_index)` injetado para TODOS os modelos (incluindo geradores)?
   gpu_index=3 para o juiz, 0/1/2 para geradores? Testado inspecionando env do Popen mockado?
4. JUIZ: `VLLM_BATCH_INVARIANT=1` e `VLLM_ENABLE_V1_MULTIPROCESSING=0` injetados?
   GERADOR: essas variáveis AUSENTES (ADR-003)? Ambos testados via env do Popen?
5. Pipes stdout/stderr drenados em threads daemon (deadlock impossível)?
6. `wait_healthy` (nome canônico §5.1 — não `wait_until_ready`): poll com backoff, timeout
   `int`, verifica `process.poll()` para morte precoce, tail de stderr na exceção?
7. `stop()`: SIGTERM → espera → SIGKILL se necessário? Nunca só SIGKILL direto?
8. Logging com campos {model_name, port, pid, batch_invariant, gpu_index, elapsed_ms}?
9. import-linter verde? DoD §14.2? Nenhum vLLM real necessário nos testes?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Sinalizar como BLOQUEADOR se CUDA_VISIBLE_DEVICES ou VLLM_BATCH_INVARIANT não forem
verificados nos dois sentidos (juiz E gerador). Confirme pytest e lint-imports.
~~~

---

## TAREFA-303 — `WaveSchedulerService` + extensão do CLI `--dry-run`

**Épico:** E3 · **Skill:** backend-engineer · **Prioridade:** P0 · **Tamanho:** S
**Dependências:** TAREFA-301 (ModelWaveSpec via domain/value_objects), TAREFA-010 (dry-run CLI) · **ADRs:** ADR-012 (ondas concorrentes — 3+2 geradores; juiz dedicado) · **Camadas:** application/services + cli

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §14.6 M3 TAREFA-303,
ADR-012). Padrão: python-clean-architecture §2 (serviço de aplicação PURO — recebe config,
produz plano de execução sem I/O). Depende de `ModelWaveSpec` (VO de domínio, TAREFA-301)
e TAREFA-010 (CLI dry-run). VER "Nota de operacionalização M3" itens 3 e 5.

TAREFA: TAREFA-303 — implementar `WaveSchedulerService` em
`src/inteligenciomica_eval/application/services/wave_scheduler.py` e estender o
comando `ielm-eval run --dry-run` (TAREFA-010) para exibir o mapa de ondas.

ESPECIFICAÇÃO:
- DTO de saída `WavePlan` (frozen dataclass, camada de aplicação):
    waves       : tuple[Wave, ...]
    total_cells : int
    estimated_vram_peak_gb : float  # peak = max(wave.vram_required_gb)

- DTO `Wave` (frozen dataclass):
    wave_index  : int
    models      : tuple[str, ...]   # nomes dos modelos nessa onda
    gpu_indices : tuple[int, ...]   # GPU de cada modelo na onda (ADR-012)
    vram_required_gb : float        # soma dos vram_gb_awq dos modelos da onda
    cells_in_wave : int

- `WaveSchedulerService`:
    `plan(model_specs: tuple[ModelWaveSpec, ...], round_config: RoundConfig) -> WavePlan`
    — recebe `tuple[ModelWaveSpec, ...]` (VO de domínio, TAREFA-301), NÃO `ModelRegistryConfig`
    (que é de infrastructure) — garante que application/ não importa de infrastructure/.

    Lógica (ADR-012 — default concorrente):
      1. Filtrar modelos da lista que estão na `round_config.llms`; lançar
         `ModelNotInRegistryError` para llm listado em round_config mas ausente em model_specs.
      2. Excluir o juiz das ondas de geração (o juiz é servido separadamente — ADR-012 GPU 3).
      3. `allow_concurrent_models=True` (DEFAULT, ADR-012): distribuir geradores pelas GPUs
         de geração (0–2) em ondas. Onda 1: até 3 modelos (um por GPU); Onda 2: modelos restantes.
         Ordenar cada onda por `vram_gb_awq DESC` (modelos maiores ganham prioridade de alocação).
         Verificar que `sum(vram_awq da onda) ≤ sum(available_gb das GPUs de geração)`.
      4. `allow_concurrent_models=False` (conservador, depuração ou GPU única): uma onda por
         modelo — serializa a execução. Documentar como "modo serial; vai contra ADR-012 salvo
         restrição de hardware".
      5. NUNCA misturar juiz e geradores na mesma onda (ADR-003).
      6. Calcular `cells_in_wave`: `len(models) × len(seeds) × n_questions × len(bases)`.
         Para Experimento B: `len(models) × len(seeds) × n_questions` (base fixa "fixed").
      7. Retornar `WavePlan` com todas as ondas + totais.
    Puro: sem I/O, sem logging. Determinístico (ordem estável de ondas).

- Extensão do CLI `--dry-run` (cli.py, comando `run`):
  Após imprimir nº de células e config_hash (já feito em TAREFA-010), adicionar:
    * Tabela Rich com as ondas: colunas {onda, modelos, GPUs, VRAM req. (GB), células}.
    * Total: células nas 3 passadas (geração + métricas + julgamento).
    * Aviso visível (Rich Panel amarelo) se `allow_concurrent_models=False` (serial —
      contra ADR-012) ou se algum modelo excede o `available_gb` da sua GPU.
  NÃO chama vLLM/Qdrant.

ENTREGÁVEL:
- src/inteligenciomica_eval/application/services/wave_scheduler.py
- Atualização de cli.py (extensão dry-run)
- tests/unit/application/services/test_wave_scheduler.py
- Atualização de tests/unit/cli/test_dry_run.py

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; frozen dataclasses; docstrings; type hints; mypy --strict.
- Serviço PURO em `application/` — sem I/O, sem logging, sem import de infrastructure.
  Recebe `tuple[ModelWaveSpec, ...]`, não `ModelRegistryConfig`. import-linter verde.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-303):
- `allow_concurrent_models=True` (default ADR-012): 3 modelos na onda 1, 2 na onda 2 — testado.
- `allow_concurrent_models=False`: uma onda por modelo — testado e documentado como contra-ADR-012.
- LLM em round_config mas ausente em model_specs → `ModelNotInRegistryError` — testado.
- Juiz NUNCA aparece nas ondas de geração — testado.
- `cells_in_wave` correto (produto das dimensões) — testado com golden.
- `WaveSchedulerService` NÃO importa de infrastructure/ (import-linter) — confirmado.
- `ielm-eval run --dry-run` exibe tabela de ondas com coluna GPUs; NÃO acessa rede.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-303 + arquitetura §14.6 M3 + ADR-012 +
skill python-clean-architecture §2.

VERIFIQUE, item a item, citando arquivo:linha:
1. WavePlan e Wave são frozen dataclasses com os campos corretos (incluindo `gpu_indices`)?
2. WaveSchedulerService recebe `tuple[ModelWaveSpec, ...]` — NÃO `ModelRegistryConfig`?
   application NÃO importa infrastructure? import-linter verde?
3. `allow_concurrent_models=True` (DEFAULT ADR-012): 3 geradores na onda 1, 2 na onda 2?
   Testado com golden correspondente ao cenário de 5 geradores + 3 GPUs?
4. `allow_concurrent_models=False`: uma onda por modelo; documentado como contra-ADR-012?
5. LLM ausente em model_specs → ModelNotInRegistryError?
6. Juiz NUNCA incluído nas ondas de geração?
7. cells_in_wave correto para Exp. A e B (cálculo distinto)?
8. CLI dry-run: tabela de ondas com coluna GPUs; aviso se serial (contra-ADR-012)?
9. DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Recompute cells_in_wave de 1 onda manualmente e compare com o golden do teste.
Confirme pytest (test_wave_scheduler + test_dry_run) e lint-imports.
~~~

---

## TAREFA-304 — `RunGenerationPassUseCase` (`application/use_cases/run_generation_pass.py`)

**Épico:** E3 · **Skill:** backend-engineer · **Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-004 (entidades), TAREFA-005 (ports), TAREFA-010 (config), TAREFA-303 (WavePlan), TAREFA-011 (fakes) · **ADRs:** ADR-004 (3 passadas), ADR-009 (idempotência) · **Camadas:** application/use_cases

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §3.4 fluxo de dados
passo 3, §14.6 M3 TAREFA-304/305 — Passada 1 da arquitetura de 3 passadas, §5.4). Padrão:
python-clean-architecture §2 (use case de aplicação: orquestra ports, sem I/O direto,
sem lógica de domínio). Depende de TAREFA-004 (EvaluationResult), TAREFA-005 (ports),
TAREFA-010 (config) e TAREFA-011 (fakes). VER "Nota de operacionalização M3" itens 1 e 2.

TAREFA: TAREFA-304 — implementar `RunGenerationPassUseCase` em
`src/inteligenciomica_eval/application/use_cases/run_generation_pass.py`.

ESPECIFICAÇÃO:
- `RunGenerationPassUseCase` recebe no `__init__` (todos como ports/interfaces do domínio):
    retriever    : RetrieverPort
    generator    : GeneratorPort
    writer       : ResultWriterPort
    reader       : ResultReaderPort  # para verificar idempotência
    config       : RoundConfig       # da TAREFA-010

- Método principal:
    `execute(*, run_id: str, wave_plan: WavePlan) -> GenerationPassReport`

  Fluxo interno:
  1. Para cada onda em `wave_plan.waves`:
     - Para cada `{base, llm}` da onda × `{seed}` × `{question}`:
       a. Computar `RowId.from_cell(run_id=run_id, phase=phase, base=base, llm=llm,
          seed=seed, question_id=question.question_id)`.
       b. Verificar `writer.exists(row_id)` → se True, logar skip e incrementar
          `n_skipped`. NÃO reprocessar (ADR-009).
       c. Se não existe:
          - Experimento A: `retriever.retrieve(base, question.text, top_k=config.retrieval.top_k)`
          - Experimento B: usar contextos canônicos pré-carregados (`canonical_contexts`,
            passados como argumento — ver abaixo).
          - `generator.generate(llm, question, contexts, seed=seed, temperature=config.temperature)`
          - Construir `GeneratedAnswer` e `EvaluationResult` parcial (sem métricas —
            `MetricVector` com todos os campos NaN; `final_score=FinalScore(NaN)`;
            `determinism_regime=GENERATOR`).
          - `writer.append(result)`
          - Incrementar `n_generated`.
       d. Erros: `GenerationError` → logar + incrementar `n_errors` + continuar (não
          abortar a passada inteira por erro de uma célula); máx. `max_retries` (config,
          default 3) antes de registrar a célula como erro permanente (linha NÃO persiste).

  2. Para o Experimento B, `canonical_contexts` é um `dict[str, list[Chunk]]` (question_id
     → chunks fixos). A **construção** dos contextos canônicos NÃO é responsabilidade deste
     use case — deve ser injetada via argumento `canonical_contexts: dict[str, list[Chunk]] | None`.
     Se `config.phases` inclui "B" e `canonical_contexts is None`, levantar `ConfigValidationError`.

- `GenerationPassReport` (frozen dataclass):
    run_id, wave_plan (resumo), n_generated, n_skipped, n_errors,
    duration_s: float, failed_cells: tuple[str, ...] (row_ids com erro)

- Logging estruturado: logar início/fim de onda, progresso a cada 10 células, skips e erros —
  com campos {run_id, wave_index, llm, base, seed, question_id, action}. NÃO logar o texto
  das respostas geradas (podem ser extensos e confidenciais).

ENTREGÁVEL:
- src/inteligenciomica_eval/application/use_cases/run_generation_pass.py
- tests/unit/application/use_cases/test_run_generation_pass.py (usa fakes de TAREFA-011)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings; mypy --strict.
- Use case de aplicação: sem I/O direto; sem imports de infrastructure; só ports + domínio.
  Logging via structlog É permitido em application (não em domain/services).
  import-linter: application NÃO importa infrastructure.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-304):
- Célula já existente (exists=True) é pulada; n_skipped incrementado — testado.
- Experimento B sem canonical_contexts → ConfigValidationError — testado.
- GenerationError em uma célula NÃO aborta as demais; n_errors correto — testado.
- Após max_retries, célula vai para failed_cells e NÃO persiste linha parcial — testado.
- Experimento B usa contextos canônicos injetados; Experimento A chama o retriever.
- Todas as linhas geradas têm MetricVector com todos os campos NaN (métricas ausentes
  na saída desta passada) — testado via InMemoryResultWriter da TAREFA-011.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-304 + arquitetura §3.4/§5.4/§14.6 + ADR-004/009 +
skill backend-engineer + "Nota de operacionalização M3" item 1.

VERIFIQUE, item a item, citando arquivo:linha:
1. Use case recebe SOMENTE ports + RoundConfig (sem adapters concretos)?
   application NÃO importa infrastructure? import-linter verde?
2. Idempotência (ADR-009): exists() verificado antes de gerar; skip correto; n_skipped?
3. GenerationError: uma célula falha NÃO aborta as demais? Retries até max_retries?
   failed_cells lista apenas células que esgotaram retries?
4. Experimento B: canonical_contexts injetado; None com phase B → ConfigValidationError?
5. Linhas geradas têm MetricVector com TODOS os campos NaN (passada 1 não computa métricas)?
   determinism_regime=GENERATOR? final_score=NaN?
6. GenerationPassReport com todos os campos preenchidos?
7. Logging sem texto das respostas; com campos {llm, base, seed, question_id, action}?
8. Cobertura de ramos de erro; DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Confirme pytest (test_run_generation_pass) e lint-imports.
~~~

---

## TAREFA-305 — `RunMetricsPassUseCase` (`application/use_cases/run_metrics_pass.py`)

**Épico:** E3 · **Skill:** ml-engineer · **Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-006 (FinalScoreCalculator), TAREFA-005 (ports), TAREFA-008 (AggregationService para NaN) · **ADRs:** ADR-004 (3 passadas), ADR-007 (NaN) · **Camadas:** application/use_cases

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §3.4 fluxo de dados
passo 4a–c, §14.6 M3 TAREFA-305 — Passada 2 da arquitetura de 3 passadas). Padrão:
python-clean-architecture §2 (use case puro que orquestra ports de métricas).
Depende de TAREFA-006 (FinalScoreCalculator), TAREFA-005 (MetricSuitePort,
DeterministicMetricPort, ResultWriterPort, ResultReaderPort). VER "Nota de
operacionalização M3" item 1 e ADR-007. Assinaturas canônicas de Port (§5.1 + M2 Nota item 1):
`MetricSuitePort.score(sample)`, `DeterministicMetricPort.score(answer, ground_truth)`,
`ResultWriterPort.update_metrics(row_id, *, metrics, final_score, regime)` (extensão M2/M3).

TAREFA: TAREFA-305 — implementar `RunMetricsPassUseCase` em
`src/inteligenciomica_eval/application/use_cases/run_metrics_pass.py`.

ESPECIFICAÇÃO:
- `RunMetricsPassUseCase` recebe no `__init__`:
    metric_suite   : MetricSuitePort      # RAGAS (Camada 1)
    deterministic  : DeterministicMetricPort  # BERTScore
    score_calc     : FinalScoreCalculator  # serviço de domínio (TAREFA-006)
    writer         : ResultWriterPort
    reader         : ResultReaderPort
    config         : RoundConfig

- Método principal:
    `execute(*, run_id: str, round_id: str, phase: str | None = None) -> MetricsPassReport`

  Fluxo:
  1. Carregar via `reader.load(round_id=round_id, phase=phase)` todas as linhas do run.
  2. Filtrar linhas que JÁ têm `answer_correctness` não-NaN (já avaliadas) → skip.
     Filtrar linhas onde `generated_answer` é vazio/ausente (Passada 1 não concluída) →
     logar aviso, adicionar a `n_skipped_missing_generation`.
  3. Para cada linha elegível (em lotes `batch_size` configurável, default 10):
     a. Construir `EvaluationSample` (question, ground_truth, generated_answer, contexts).
     b. `metric_suite.score(sample) -> Layer1Metrics` — pode levantar
        `MetricComputationError` (falha de parsing JSON do RAGAS; até 3 retries antes
        de aceitar NaN, conforme §12 riscos do doc-base e ADR-007).
     c. `deterministic.score(answer=result.generated_answer, ground_truth=result.ground_truth) -> AuxMetrics`
        (BERTScore — determinístico, assinatura canônica §5.1, sem retry).
     d. Montar `MetricVector` a partir de `Layer1Metrics` + `AuxMetrics.bertscore_f1`.
     e. `score_calc.compute(metrics) -> FinalScore` (NaN propaga se alguma métrica for NaN).
     f. `writer.update_metrics(row_id, metrics=metric_vector, final_score=final_score,
        regime=DeterminismRegime.GENERATOR)` (as métricas de Camada 1 são computadas
        localmente, sem o juiz — regime é GENERATOR aqui).
     g. Contar `n_evaluated`, `n_nan` (linhas que ficaram NaN após retries).

- `MetricsPassReport` (frozen dataclass): run_id, round_id, n_evaluated, n_skipped,
  n_skipped_missing_generation, n_nan, n_errors, duration_s.

- Tratamento de NaN (ADR-007): MetricComputationError após 3 retries → MetricVector com
  todos os campos NaN + FinalScore(NaN) → persistir com update_metrics (NaN é um estado
  legítimo; NÃO ignorar a linha — ela entrará como excluída na agregação).

- Processamento em lotes: implementar `_process_batch(samples: list[EvaluationSample]) -> list[Layer1Metrics]`
  que permite ao adapter de RAGAS processar o lote de uma vez (o MetricSuitePort tem
  `score_batch` como extensão declarada na Nota M3 item 5 — use-o; a implementação stub já
  retorna lote).

ENTREGÁVEL:
- src/inteligenciomica_eval/application/use_cases/run_metrics_pass.py
- tests/unit/application/use_cases/test_run_metrics_pass.py (usa fakes de TAREFA-011;
  inclui cenário com MetricComputationError + retry + NaN final)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings; mypy --strict.
- application NÃO importa infrastructure. FinalScoreCalculator vem do domínio (não re-instanciado).

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-305):
- Linhas já avaliadas são puladas (idempotência por campo preenchido) — testado.
- MetricComputationError: 3 retries → NaN aceito e persistido (não descartado) — testado.
- Processamento em lotes correto (chamada a `score_batch`, não N chamadas individuais a `score`) — testado.
- MetricVector com BERTScore preenchido (vem do DeterministicMetricPort, não do RAGAS).
- NaN em métrica de peso>0 → FinalScore(NaN) (via FinalScoreCalculator — testado no domínio,
  mas verificar integração correta aqui).
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-305 + arquitetura §3.4/§5.4/§14.6 + ADR-004/007 +
skill ml-engineer + "Nota de operacionalização M3" item 1.

VERIFIQUE, item a item, citando arquivo:linha:
1. Use case recebe somente ports + FinalScoreCalculator (domínio) + RoundConfig?
   application NÃO importa infrastructure? import-linter verde?
2. Idempotência: linhas com answer_correctness não-NaN são puladas?
   Linhas sem generated_answer são contabilizadas em n_skipped_missing_generation?
3. MetricComputationError: 3 retries → NaN aceito e persistido (não descartado, ADR-007)?
4. `metric_suite.score(sample)` usado (NÃO `.compute()`)? `score_batch` em vez de
   `compute_batch`? batch_size configurável?
5. `deterministic.score(answer=..., ground_truth=...)` usado (assinatura canônica §5.1 —
   NÃO `.compute(sample)`)?
6. `update_metrics` chamado com `regime=DeterminismRegime.GENERATOR` (não JUDGE)?
7. MetricsPassReport com todos os campos preenchidos?
8. Cobertura de cenários de retry e NaN; DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Confirme pytest (test_run_metrics_pass) e lint-imports.
~~~

---

## TAREFA-306 — `RunJudgePassUseCase` (`application/use_cases/run_judge_pass.py`)

**Épico:** E3 · **Skill:** ml-engineer · **Prioridade:** P0 · **Tamanho:** S
**Dependências:** TAREFA-005 (RubricJudgePort), TAREFA-004 (entidades, DeterminismRegime), TAREFA-302 (VLLMServerManager) · **ADRs:** ADR-003 (determinismo do juiz), ADR-004, ADR-007 · **Camadas:** application/use_cases

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §3.4 fluxo de dados
passo 4b, §14.6 M3 TAREFA-306 — Passada 3 da arquitetura de 3 passadas). Padrão:
python-clean-architecture §2. Depende de TAREFA-005 (RubricJudgePort assinatura canônica
§5.1: `score(sample) -> RubricResult`, ResultWriterPort, ResultReaderPort) e TAREFA-004
(DeterminismRegime.JUDGE). VER "Nota de operacionalização M3" item 1 e ADR-003.

TAREFA: TAREFA-306 — implementar `RunJudgePassUseCase` em
`src/inteligenciomica_eval/application/use_cases/run_judge_pass.py`.

ESPECIFICAÇÃO:
- `RunJudgePassUseCase` recebe no `__init__`:
    judge        : RubricJudgePort   # Prometheus-2 com VLLM_BATCH_INVARIANT=1
    writer       : ResultWriterPort
    reader       : ResultReaderPort
    config       : RoundConfig

- Método principal:
    `execute(*, run_id: str, round_id: str, phase: str | None = None) -> JudgePassReport`

  Fluxo:
  1. Carregar linhas com `reader.load(round_id=round_id, phase=phase)`.
  2. Filtrar linhas com `rubric_biomed_score` não-NaN (já julgadas) → skip.
     Filtrar linhas sem `generated_answer` → aviso + n_skipped_missing_generation.
     Filtrar linhas com `final_score` NaN (métricas ainda não calculadas) → aviso, mas
     PROCESSAR MESMO ASSIM (o juiz pode rodar independente do RAGAS para diagnóstico;
     documentar essa decisão de design).
  3. Para cada linha elegível (em sequência; NÃO em paralelo — determinismo exige
     ordem estável de submissão ao juiz batch-invariant):
     a. `judge.score(sample) -> RubricResult` — pode levantar `JudgeUnavailableError`
        (servidor caiu); até 3 retries com backoff 5s antes de aceitar NaN (ADR-007).
     b. `writer.update_metrics(row_id, rubric_score=result.score,
        rubric_feedback=result.feedback, regime=DeterminismRegime.JUDGE)`.
     c. Registrar em `batch_invariant_confirmed=True` (o use case CONFIA que o servidor
        já foi configurado com VLLM_BATCH_INVARIANT=1; a verificação é responsabilidade
        do VLLMServerManager e do wiring — este use case NÃO acessa subprocess).
  4. Contar n_judged, n_skipped, n_nan.

- Ordem de processamento ESTÁVEL: sempre ordenar as linhas por `row_id` antes de iterar
  (garante que o mesmo dataset julgado em dias diferentes passe as linhas ao juiz na mesma
  ordem — importante para auditoria de reprodutibilidade).

- `JudgePassReport` (frozen dataclass): run_id, round_id, n_judged, n_skipped,
  n_skipped_missing_generation, n_nan, duration_s,
  batch_invariant_assumed: bool = True  # campo informativo para auditoria.

ENTREGÁVEL:
- src/inteligenciomica_eval/application/use_cases/run_judge_pass.py
- tests/unit/application/use_cases/test_run_judge_pass.py (usa FakeRubricJudge de TAREFA-011;
  inclui cenário de JudgeUnavailableError + retry + NaN final; verifica ordem estável)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings; mypy --strict.
- application NÃO importa infrastructure. Sem subprocess/env access no use case.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-306):
- Linhas com rubric_biomed_score não-NaN são puladas (idempotência) — testado.
- Linhas com final_score NaN são processadas (não bloqueadas) — testado e documentado.
- JudgeUnavailableError: 3 retries → NaN aceito (ADR-007) — testado.
- Processamento em ordem ESTÁVEL por row_id — testado (mock registra chamadas; verifica ordem).
- update_metrics chamado com regime=DeterminismRegime.JUDGE — testado.
- Sem chamada a subprocess/env no use case (responsabilidade do VLLMServerManager) — confirmado por inspeção.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-306 + arquitetura §3.4/§5.4/§14.6 + ADR-003/004/007 +
skill ml-engineer.

VERIFIQUE, item a item, citando arquivo:linha:
1. Use case usa somente RubricJudgePort (não acessa subprocess nem env)?
   application NÃO importa infrastructure?
2. Linhas com rubric_biomed_score não-NaN puladas? Linhas com final_score NaN PROCESSADAS
   (não bloqueadas) com decisão documentada em docstring?
3. JudgeUnavailableError: 3 retries com backoff → NaN (ADR-007)?
4. Ordem estável por row_id antes de iterar — testado verificando a sequência de chamadas
   ao mock (não apenas que "foram chamados")?
5. regime=DeterminismRegime.JUDGE no update_metrics?
6. JudgePassReport tem campo batch_invariant_assumed=True (auditoria)?
7. Processamento SEQUENCIAL (não paralelo — determinismo do juiz)?
8. Cobertura de retry e ordem; DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Sinalizar como BLOQUEADOR se ordem estável não for testada ou regime=JUDGE ausente.
Confirme pytest e lint-imports.
~~~

---

## TAREFA-307 — `RunExperimentUseCase` (`application/use_cases/run_experiment.py`)

**Épico:** E3 · **Skill:** backend-engineer · **Prioridade:** P0 · **Tamanho:** L
**Dependências:** TAREFA-304, TAREFA-305, TAREFA-306, TAREFA-303 (WaveSchedulerService), TAREFA-008 (AggregationService), TAREFA-007 (RankScoreCalculator), TAREFA-005 (VLLMServerManagerPort) · **ADRs:** ADR-004, ADR-012; **RNF:** RNF7 (graceful shutdown/resumabilidade) · **Camadas:** application/use_cases

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §3.3/§3.4
componentes e fluxo, §14.6 M3 TAREFA-307 — orquestrador top-level do ciclo completo A+B).
Padrão: python-clean-architecture §2. Depende dos 3 use cases de passada (304/305/306), do
WaveSchedulerService (303), AggregationService (008), RankScoreCalculator (007) e
VLLMServerManagerPort (005). VER "Nota de operacionalização M3" todos os itens.

TAREFA: TAREFA-307 — implementar `RunExperimentUseCase` em
`src/inteligenciomica_eval/application/use_cases/run_experiment.py`.

ESPECIFICAÇÃO:
- `RunExperimentUseCase` recebe no `__init__` (todos como abstrações — ports ou serviços
  de domínio/aplicação):
    wave_scheduler      : WaveSchedulerService
    server_manager      : VLLMServerManagerPort
    gen_pass_uc         : RunGenerationPassUseCase
    metrics_pass_uc     : RunMetricsPassUseCase
    judge_pass_uc       : RunJudgePassUseCase
    aggregation_service : AggregationService
    rank_calc           : RankScoreCalculator
    writer              : ResultWriterPort
    reader              : ResultReaderPort
    config              : RoundConfig

- Método principal:
    `execute(*, run_id: str, progress_callback: Callable[[str], None] | None = None)
        -> ExperimentReport`

  Fluxo de alto nível (§3.4 e §6 do doc-base):
  1. **Preparação:**
     a. Calcular o plano de ondas: `wave_plan = wave_scheduler.plan(config.model_registry, config)`.
     b. Construir `canonical_contexts` para Experimento B (se "B" em `config.phases`):
        usar o retriever (injetado) para buscar top-k na base `IDx_400k` para cada pergunta.
        Guardar em memória como `dict[question_id, list[Chunk]]`.

  2. **Passada de geração por onda:**
     Para cada onda em `wave_plan.waves`:
     a. Iniciar servidor gerador: `handle = server_manager.start(model_spec, port=...)`.
     b. `server_manager.wait_healthy(handle, timeout_s=config.startup_timeout_s)`.
     c. Substituir o adapter de geração no `gen_pass_uc` pelo adapter apontando para este
        handle (injetar URL do handle no GeneratorPort — estratégia: `gen_pass_uc` recebe
        uma factory `GeneratorFactory(url: str) -> GeneratorPort` que o wiring fornece;
        `GeneratorFactory` é Protocol declarado em `domain/ports.py` conforme Nota M3 item 5;
        o use case chama `factory(handle.url)` para o gerador da onda).
     d. `gen_pass_uc.execute(run_id=run_id, wave_plan=single_wave_plan, ...)`
     e. `server_manager.stop(handle)`.
     f. Se `ServerStartTimeoutError`: logar, registrar onda como falha, CONTINUAR com
        próxima onda (degraded mode — não abortar toda a rodada).

  3. **Passada de métricas (única, após todas as gerações):**
     `metrics_pass_uc.execute(run_id=run_id, round_id=config.round_id)`

  4. **Passada do juiz (única, com servidor juiz dedicado):**
     a. Iniciar servidor juiz: `judge_handle = server_manager.start(judge_spec, port=...)`.
     b. `server_manager.wait_healthy(judge_handle, timeout_s=config.startup_timeout_s)`.
     c. `judge_pass_uc.execute(run_id=run_id, round_id=config.round_id)`
     d. `server_manager.stop(judge_handle)`.

  5. **Agregação final:**
     a. `all_results = reader.load(round_id=config.round_id)`.
     b. `aggregates = aggregation_service.aggregate_all(all_results.results,
        threshold=config.scoring.failure_threshold)`.
     c. Calcular `rank_scores` via `rank_calc.compute(inputs)` para cada `ConfigAggregate`.
     d. Retornar `ExperimentReport`.

  6. **Graceful shutdown (RNF7 — resumabilidade, §2.3):** registrar handler para `SIGTERM`/`SIGINT` que
     sinaliza uma flag `_shutdown_requested`. O loop de ondas verifica essa flag antes
     de iniciar cada nova onda; se True, completa a onda corrente e para. Servidores
     ativos são encerrados antes de sair (`server_manager.stop(handle)` em bloco finally).

- `ExperimentReport` (frozen dataclass): run_id, config_hash, wave_plan, n_generated,
  n_evaluated, n_judged, n_cells_total, aggregates: tuple[ConfigAggregate, ...],
  rank_scores: tuple[RankScore, ...], duration_s, failed_waves: tuple[int, ...].

- `GeneratorFactory`: Protocol declarado em `domain/ports.py` (única localização, conforme
  Nota M3 item 5) com `__call__(self, url: str) -> GeneratorPort`.

ENTREGÁVEL:
- src/inteligenciomica_eval/application/use_cases/run_experiment.py
- Atualização de `domain/ports.py` com `GeneratorFactory` Protocol (Nota M3 item 5)
- tests/unit/application/use_cases/test_run_experiment.py (todos os fakes; inclui cenário
  de ServerStartTimeoutError em uma onda, shutdown gracioso via _shutdown_requested)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings; mypy --strict.
- application NÃO importa infrastructure. NÃO instancia adapters concretos.
- Graceful shutdown: SIGTERM/SIGINT → completa onda atual → para → encerra servidores.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-307):
- ServerStartTimeoutError em uma onda NÃO aborta a rodada inteira; onda registrada em
  failed_waves; demais ondas executam — testado.
- Shutdown gracioso: flag _shutdown_requested interrompe loop entre ondas; servidores
  encerrados em finally — testado via mock de signal/flag.
- Servidor juiz iniciado APÓS todas as gerações (nunca simultaneamente com geradores) —
  testado verificando sequência de chamadas ao server_manager mock.
- ExperimentReport contém aggregates + rank_scores calculados — testado com valores golden.
- canonical_contexts construídos via retriever para todas as perguntas antes da Passada 1.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-307 + arquitetura §3.3/§3.4/§14.6 + ADR-004/012 + RNF7 +
skill backend-engineer.

VERIFIQUE, item a item, citando arquivo:linha:
1. Use case recebe somente ports/serviços (sem adapters concretos)?
   application NÃO importa infrastructure? `GeneratorFactory` é Protocol em `domain/ports.py`?
2. Servidor juiz iniciado somente APÓS toda a geração (não em paralelo com geradores)?
   Verificado pela sequência de chamadas ao mock?
3. ServerStartTimeoutError em onda: rodada continua, onda registrada em failed_waves?
4. Graceful shutdown (RNF7): SIGTERM/SIGINT → flag → completa onda atual → para → finally
   encerra servidores ativos?
5. Passadas executam na ordem correta: 1 geração (por onda) → 2 métricas → 3 juiz?
6. `wait_healthy` (NÃO `wait_until_ready`) chamado em todos os `server_manager.start()`?
7. ExperimentReport contém aggregates + rank_scores calculados via domínio?
8. canonical_contexts construídos via retriever antes da Passada 1?
9. Cobertura dos ramos de erro e shutdown; DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Verificar se "servidor juiz simultâneo com gerador" é impossível pela implementação
(não só pelo teste). Confirme pytest (test_run_experiment) e lint-imports.
~~~

---

## TAREFA-308 — `AnnotationWorkflowUseCase` + CLI `annotate` (Camada 3)

**Épico:** E3 · **Skill:** python-engineer · **Prioridade:** P1 · **Tamanho:** M
**Dependências:** TAREFA-005 (AnnotationReaderPort, ResultWriterPort), TAREFA-004 (EvaluationResult) · **ADRs:** ADR-010 (Camada 3 — anotação humana) · **Camadas:** application/use_cases + cli
**Rastreabilidade M4:** esta tarefa antecipa TAREFA-401 (CLI `annotate`) e TAREFA-402 (`IngestHumanAnnotationUseCase`) do milestone M4 (§14.7). M4 **não deve reimplementar** — apenas referenciar e, se necessário, estender o que esta tarefa entrega.

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §3.3 componentes
IngestHumanAnnotationUseCase, §14.7 M4 TAREFA-401/402, ADR-010). Esta tarefa antecipa
TAREFA-401/402 do M4 — entregando o fluxo de anotação no M3 para que o especialista
biomédico possa começar a revisar as primeiras respostas assim que a Passada 3 terminar.
Padrão: python-clean-architecture §2 + CLI enxuto. Depende de TAREFA-005 (ports) e
TAREFA-004 (with_human_annotation).

TAREFA: TAREFA-308 — implementar `AnnotationWorkflowUseCase` em
`src/inteligenciomica_eval/application/use_cases/annotation_workflow.py` e o comando
`ielm-eval annotate` no CLI.

ESPECIFICAÇÃO:
- `AnnotationWorkflowUseCase` recebe no __init__:
    reader  : ResultReaderPort
    writer  : ResultWriterPort
    config  : AnnotationConfig  # subseção do RoundConfig; ver abaixo

- `AnnotationConfig` (Pydantic, em schema.py ou separado): threshold para priorização
  de revisão (default: listar respostas com `final_score < config.scoring.failure_threshold`
  OU `rubric_biomed_score < 0.5`), `max_to_review: int | None` (None = todas), `round_id`.

- Método `get_review_queue(*, run_id: str) -> tuple[EvaluationResult, ...]`:
  Carrega resultados, aplica os filtros de priorização, ordena por final_score ASC
  (piores primeiro), respeita max_to_review. Respostas com critical_failure_flag
  já anotado (não-None) são EXCLUÍDAS da fila (já revisadas).

- Método `annotate(*, row_id: RowId, flag: int, note: str) -> None`:
  Chama `with_human_annotation(flag, note)` na entidade (TAREFA-004) e persiste via
  `writer.update_metrics(row_id, critical_failure_flag=flag, critical_failure_note=note)`.
  Valida `flag ∈ {0, 1}`; senão `ScoreOutOfRangeError` com mensagem clara.

- CLI `ielm-eval annotate`:
  Modo interativo com Rich:
    1. Carregar e exibir a fila de revisão (tabela Rich: question_id, llm, base,
       seed, final_score, rubric_score, os primeiros 200 chars da resposta gerada).
    2. Para cada item da fila:
       - Exibir a pergunta e a resposta completa (Rich Panel).
       - Exibir o ground truth abaixo (para comparação).
       - Prompt `[0] Sem erro grave / [1] Erro crítico biomédico / [s] Pular / [q] Sair`:
         capturar input via Typer/stdin; tratar KeyboardInterrupt graciosamente.
       - Se 0 ou 1: chamar `annotate(row_id, flag, note="")`.
       - Opção para adicionar nota textual (prompt secundário se flag=1).
    3. Ao sair: imprimir resumo (N anotados, N pulados, N pendentes).
  Modo não-interativo (`--csv path`): lê CSV com colunas {row_id, flag, note} e persiste
  em lote sem prompt — para integração com ferramentas externas.

ENTREGÁVEL:
- src/inteligenciomica_eval/application/use_cases/annotation_workflow.py
- Atualização de cli.py com comando `annotate`
- Atualização de infrastructure/config/schema.py com `AnnotationConfig`
- tests/unit/application/use_cases/test_annotation_workflow.py
  (fila de revisão correta; anotação persiste via update_metrics; flag inválido falha)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings; mypy --strict.
- application NÃO importa infrastructure. CLI não armazena estado de sessão além da
  memória do processo.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-308):
- Fila de revisão exclui respostas já anotadas (flag não-None) — testado.
- Fila ordenada por final_score ASC; respeita max_to_review — testado.
- Anotação chama with_human_annotation + update_metrics — testado via InMemoryResultWriter.
- flag inválido (ex.: 2) → ScoreOutOfRangeError — testado.
- Modo --csv persiste lote sem prompt interativo — testado.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-308 + arquitetura §3.3/§14.7 M4 TAREFA-401/402 + ADR-010 +
skill python-clean-architecture §2.

VERIFIQUE, item a item, citando arquivo:linha:
1. get_review_queue exclui respostas com critical_failure_flag não-None (já revisadas)?
   Ordenação por final_score ASC? max_to_review respeitado?
2. annotate chama with_human_annotation (ADR-010 — imutabilidade da entidade) antes de
   persistir? flag fora de {0,1} → ScoreOutOfRangeError?
3. CLI interativo: exibe pergunta + resposta completa + ground_truth? Trata q/s/0/1?
   KeyboardInterrupt gracioso (não stacktrace)?
4. Modo --csv funciona sem interação? Lote persistido via update_metrics?
5. application NÃO importa infrastructure? CLI não persiste estado além do processo?
6. AnnotationConfig em schema.py? Integra com RoundConfig?
7. Cobertura dos ramos de fila, anotação e CSV; DoD §14.2?
8. **Rastreabilidade M4:** o PR documenta (docstring ou comentário) que esta tarefa
   implementa TAREFA-401/402 do M4? M4 não terá conflito de reimplementação?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Confirme pytest (test_annotation_workflow) e lint-imports.
~~~

---

## TAREFA-309 — DI wiring real + CLI `run` completo

**Épico:** E3 · **Skill:** python-engineer · **Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-302 (VLLMServerManager), TAREFA-307 (RunExperimentUseCase), TAREFA-308 (AnnotationWorkflow), TAREFA-010 (config/settings) · **ADRs:** ADR-001 (Clean Architecture), ADR-008 (config declarativa); **RNF:** RNF7 (graceful shutdown) · **Camadas:** infrastructure/wiring + cli
> **Nota §8:** `infrastructure/wiring.py` é adição aprovada ao blueprint de estrutura de código (§8 não a lista explicitamente; registrar em `docs/adr/` como extensão ao ADR-001 se necessário).

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §8 estrutura de
código + §3.2 containers + ADR-001 Clean Architecture + ADR-008 config declarativa).
Padrão: python-clean-architecture §1 (CLI chama wiring; wiring instancia adapters reais;
use cases recebem ports, nunca adapters concretos). Depende de todos os adapters reais
de M1/M2 + TAREFA-302 (`infrastructure/adapters/vllm_server_manager.py`) + TAREFA-307/308.
VER "Nota de operacionalização M3" item 4 (wiring em infrastructure/wiring.py).

TAREFA: TAREFA-309 — implementar `infrastructure/wiring.py` (container de DI) e completar
o comando `ielm-eval run` no CLI com execução real (não só --dry-run).

ESPECIFICAÇÃO:
- `infrastructure/wiring.py`:
  * `@dataclass(frozen=True) DIContainer`: contém instâncias prontas de todos os
    ports e use cases, já conectados. Campos:
      retriever, generator_factory, metric_suite, deterministic_metric, rubric_judge,
      server_manager, wave_scheduler, gen_pass_uc, metrics_pass_uc, judge_pass_uc,
      experiment_uc, annotation_uc, writer, reader, agg_service, rank_calc.
  * Função `build_container(config: RoundConfig, settings: AppSettings) -> DIContainer`:
    instancia CADA adapter real com os parâmetros corretos (URLs de env via settings,
    config de modelo via `model_registry`). Carregar `ModelRegistryConfig` do path em
    `config.model_registry_path` (TAREFA-301); converter `ModelEntry` → `ModelWaveSpec`
    (TAREFA-301) para passar ao WaveSchedulerService. Ordem: primeiro adapters sem dependências
    (cliente HTTP, storage), depois compostos. Sem framework de DI de terceiros (ADR-001).
  * Função `build_fake_container(config: RoundConfig) -> DIContainer`: para testes e
    dry-run avançado — substitui adapters reais por fakes de TAREFA-011.
    CLI --dry-run usa `build_fake_container` para provar que a fiação está correta.
  * Exceção: se env var obrigatória (ex.: VLLM_GENERATOR_URL) estiver ausente ao chamar
    `build_container`, levantar `ConfigValidationError` com nome da variável faltante.

- CLI — comando `run` (atualizar cli.py):
  Já tem `--dry-run`. Adicionar execução real:
    `ielm-eval run --config path --run-id id [--phase A|B|both] [--dry-run]`
  * Sem `--dry-run`: chamar `build_container(config, settings)`, instanciar
    `RunExperimentUseCase`, exibir progresso via Rich `Progress` com task bars:
    {ondas concluídas / total, células geradas / total, células avaliadas / total}.
  * `progress_callback` injetado no `RunExperimentUseCase.execute()` (TAREFA-307) para
    atualizar as barras de progresso.
  * Capturar `ServerStartTimeoutError` e `ConfigValidationError`: exibir via Rich Panel
    vermelho com a mensagem e exit code 1. NÃO exibir stacktrace ao usuário final —
    logar stacktrace via structlog ao nível DEBUG.
  * Ao terminar (sucesso): exibir sumário rich: nº de células, ondas, falhas, top-3
    configurações por RankScore.
  * Tratar SIGTERM/SIGINT: exibir "⚠ Encerramento solicitado — aguardando onda atual..."
    e repassar para o shutdown gracioso (RNF7) já implementado em TAREFA-307.

- Comando `ielm-eval analyze` (placeholder para M4): adicionar stub que imprime
  "M4 não implementado ainda" e exit 0.
- Comando `ielm-eval report` (placeholder para M5): idem.

ENTREGÁVEL:
- src/inteligenciomica_eval/infrastructure/wiring.py
- Atualização de cli.py (run completo + placeholders analyze/report)
- tests/unit/infrastructure/test_wiring.py:
    * `build_fake_container` constrói DIContainer válido com fakes sem exceção.
    * `build_container` levanta ConfigValidationError se env var obrigatória ausente.
- tests/unit/cli/test_run_real.py:
    * `ielm-eval run --config ... --run-id ...` com DIContainer fake (patch build_container)
      executa sem erro; exibe sumário; exit code 0.
    * `ielm-eval run` com env var faltante → exit code 1 + mensagem clara (sem stacktrace).

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings; mypy --strict.
- CLI permanece enxuto: NÃO instancia adapters diretamente; delega para wiring.
- Sem segredos hardcoded. Sem framework DI de terceiros (ADR-001).

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-309):
- `build_fake_container` constrói container sem erro; `build_container` sem env → erro claro.
- CLI run: com fakes, executa e exibe sumário; exit code 0 em sucesso, 1 em erro.
- Progresso via Rich Progress (não apenas print) — verificado no output do teste.
- SIGINT → mensagem amigável + shutdown gracioso (via flag TAREFA-307) — testado com mock.
- Stacktrace não aparece no stdout em condição de erro (vai para log) — verificado.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-309 + arquitetura §8/§3.2 + ADR-001/008 + RNF7 +
skill python-clean-architecture §1.

VERIFIQUE, item a item, citando arquivo:linha:
1. DIContainer é dataclass frozen com todos os campos (retriever, generator_factory,
   metric_suite, deterministic_metric, rubric_judge, server_manager, wave_scheduler,
   3 passadas UC, experiment_uc, annotation_uc, writer, reader, agg_service, rank_calc)?
2. build_container: env var ausente → ConfigValidationError com nome da variável?
   Sem framework DI de terceiros? Sem segredos hardcoded?
3. build_fake_container: substitui adapters por fakes (de TAREFA-011)?
   --dry-run usa build_fake_container?
4. CLI run: usa build_container (ou fake); Progress via Rich (não print); sumário final?
   Stacktrace NÃO aparece no stdout em caso de erro (apenas em log DEBUG)?
5. SIGINT/SIGTERM: mensagem amigável + repassa para shutdown gracioso do TAREFA-307?
6. Placeholders analyze e report com exit 0?
7. CLI não instancia adapters diretamente (ADR-001 Clean Architecture)?
8. Cobertura dos ramos de erro; DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Cole a saída de `ielm-eval run --help` e `ielm-eval run --dry-run --config ...`.
Confirme pytest (test_wiring + test_run_real) e lint-imports.
~~~

---

## TAREFA-310 — E2E gate M3: ciclo completo com adapters semi-reais

**Épico:** E3 · **Skill:** test-engineer · **Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-301 a 309 (todos mergeados) · **ADRs:** ADR-004, ADR-009; **RNF:** RNF7 · **Camadas:** tests/e2e

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §14.4 "Gate de
saída M3"). Padrão: test-engineer §9 (E2E enxuto e valioso). Todos os componentes de
M3 implementados. ESTE TESTE FECHA O M3: prova o ciclo completo das 3 passadas +
agregação + rank, usando Parquet real e serviços de domínio reais, mas sem GPU.

TAREFA: TAREFA-310 — implementar o teste E2E de gate do M3 em
`tests/e2e/test_m3_full_cycle.py` (marcado `@pytest.mark.e2e`).

ESPECIFICAÇÃO:
Cenário determinístico mínimo (estende o E2E do M0, TAREFA-012, com o fluxo de 3 passadas):
  - 2 perguntas, 2 bases, 2 LLMs stub, 1 seed, fases A e B.
  - Fase A: perguntas(2) × bases(2) × LLMs(2) × seeds(1) = **8 células**
  - Fase B: perguntas(2) × base_fixed(1) × LLMs(2) × seeds(1) = **4 células**
  - **Total: 12 células** (A+B somados, não multiplicados).

Componentes REAIS usados no E2E (sem GPU, sem rede):
  - `ParquetStorage` em `tmp_path` (schema §5.3 real).
  - `FinalScoreCalculator`, `RankScoreCalculator`, `AggregationService` (domínio real).
  - `WaveSchedulerService` (aplicação real).
  - `RunGenerationPassUseCase`, `RunMetricsPassUseCase`, `RunJudgePassUseCase`,
    `RunExperimentUseCase` (application real).
  - `FakeVLLMServerManager` (de TAREFA-011) — simula start/wait/stop sem subprocesso.

Componentes FAKE (sem GPU/rede):
  - `StubRetriever`, `FakeGenerator`, `FakeMetricSuite`, `FakeRubricJudge`,
    `FakeDeterministicMetric` (todos de TAREFA-011).
  - `FakeMetricSuite` injetado com 1 resposta com `answer_correctness=NaN` para
    exercitar ADR-007 em todo o pipeline.

Roteiro do teste:
  1. Montar `DIContainer` com `build_fake_container` (TAREFA-309) + ParquetStorage em tmp_path.
  2. Executar `RunExperimentUseCase.execute(run_id="e2e_m3_test", ...)`.
  3. Asserções sobre o ExperimentReport:
     a. `n_generated == 12`, `n_evaluated == 12`, `n_judged == 12`.
     b. Parquet lido de volta: 12 linhas; schema correto (todos os campos do §5.3 presentes).
     c. Roundtrip fiel: `EvaluationResult` reconstruídos batem com os persistidos.
     d. Linha com métrica NaN: `final_score` é NaN e é EXCLUÍDA da agregação
        (`n_excluded_nan > 0`) — verificado via `ConfigAggregate.n_excluded_nan`.
     e. `RankScore` calculado para cada `{base, llm}` — valores conferem com golden
        calculado à mão (ou via `FinalScoreCalculator` + `AggregationService` em
        chamadas isoladas).
     f. `ExperimentReport.failed_waves == ()` (nenhuma onda falhou com os fakes).
  4. Idempotência (ADR-009): executar o UseCase **uma segunda vez** com o mesmo `run_id`.
     Resultado: nenhuma linha nova criada no Parquet (n_generated=0, n_skipped=12 na
     segunda execução). Verificar via contagem de linhas no arquivo Parquet.
  5. Servidor juiz iniciado DEPOIS de todos os geradores: verificar via `FakeVLLMServerManager`
     que registra a sequência {start, wait, stop} × {modelo} — o juiz deve aparecer após
     o último gerador nas chamadas registradas.
  6. Graceful shutdown: via mock de `signal.signal`, disparar SIGINT durante a onda 2
     (de 2 ondas). Asserção: onda 1 completou (n_generated >= células da onda 1),
     servidores ativos foram encerrados (stop() chamado), exit limpo.

Critério de performance: `pytest -m e2e tests/e2e/test_m3_full_cycle.py` completa em < 30 s
(CPU; fakes são rápidos). Sem rede, sem GPU.

ENTREGÁVEL:
- tests/e2e/test_m3_full_cycle.py
- Atualização de tests/e2e/_harness.py se necessário
- tests/golden/e2e_m3_expected.json (valores esperados de RankScore por {base, llm} para
  o cenário com os fakes determinísticos)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings no harness.
- Determinístico (seeds, freezegun para timestamp). SEM rede/GPU em nenhum caminho.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-310 — gate de saída do M3):
- **12 células** (8 fase A + 4 fase B) geradas, avaliadas, julgadas; schema Parquet correto; roundtrip fiel.
- Linha NaN excluída da agregação e contada em n_excluded_nan.
- RankScores conferem com golden; idempotência comprovada (2ª execução n_generated=0, n_skipped=12).
- Sequência server_manager confirma juiz após geradores (ADR-012).
- Graceful shutdown (RNF7): onda 2 cancelada, onda 1 completa, servidores encerrados.
- Tempo < 30 s em CPU. CI verde.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-310 + arquitetura §14.6 M3 + ADR-004/009 + RNF7 +
skill test-engineer §9.

VERIFIQUE, item a item, citando arquivo:linha:
1. **12 células** esperadas: Fase A = 2×2×2×1 = 8; Fase B = 2×1×2×1 = 4; total = 12?
   Asserted in test (não 20)?
2. Parquet REAL em tmp_path? Schema §5.3 verificado (não apenas "arquivo existe")?
   Roundtrip fiel (read → reconstruct → compare)?
3. Linha NaN: excluída da agregação E contada em n_excluded_nan?
4. RankScore: confere com golden calculado à mão para o cenário? (recompute 1 valor
   você mesmo e cite).
5. Idempotência: 2ª execução NÃO cria linhas novas (n_generated=0, n_skipped=12)?
6. Sequência server_manager: juiz iniciado APÓS todos os geradores (ADR-012)?
   `wait_healthy` (não `wait_until_ready`) chamado nos start mocks?
7. Graceful shutdown testado (RNF7): onda 1 completa, onda 2 cancelada, stop() chamado?
8. SEM rede/GPU em NENHUM caminho? Tempo < 30 s afirmado (ou medido)?
9. DoD §14.2; todos os fakes de TAREFA-011 usados corretamente?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Este é o gate do M3 — qualquer item 1–8 como FAIL bloqueia o avanço para M4.
Inclua sua recomputação de RankScore para 1 configuração do cenário.
Confirme `pytest -m e2e tests/e2e/test_m3_full_cycle.py` (tempo e resultado).
~~~

---

## Apêndice — Ordem de execução e gate de saída do M3 (301–310)

Sub-DAG do M3 (caminho crítico marcado com `*`):

```
301* ─┬─ 302* ─────────────────────────────────────┐
      │                                             │
      └─ 303* ─────────────────────────────────────┤
                                                    │
M1/M2 ─┬─ 304* ─┐                                  │
        ├─ 305* ─┤                                  │
        └─ 306* ─┴─ 307* ──────────────────────────┤
                                                    │
310 (depende de 301..309) ◄── 308, 309* ────────────┘
```

Sequência recomendada de PRs (respeitando dependências):

1. **TAREFA-301** (model registry) — raiz do M3; sem isso, 302 e 303 não têm config.
2. **TAREFA-302** (VLLMServerManager) e **TAREFA-303** (WaveScheduler) — paralelizáveis
   após 301.
3. **TAREFA-304** (geração), **TAREFA-305** (métricas), **TAREFA-306** (juiz) — podem
   ser paralelizados entre si (dependem de M1/M2 + TAREFA-005, já prontos).
4. **TAREFA-307** (RunExperimentUseCase) — após 302, 303, 304, 305, 306.
5. **TAREFA-308** (AnnotationWorkflow) — pode ir em paralelo com 304–306 (independente).
6. **TAREFA-309** (wiring + CLI run) — após 302 + 307 + 308.
7. **TAREFA-310** (E2E gate) — ÚLTIMA: todos os anteriores mergeados.

**Gate de saída do M3 (go/no-go para M4 — análise estatística):**
- `mypy --strict`, `ruff`, `ruff format --check`, `lint-imports` e `pytest` (unit +
  integration + e2e) todos VERDES no CI.
- E2E gate (TAREFA-310) verde: **12 células** (8A + 4B), Parquet real, 3 passadas, agregação, RankScore,
  NaN excluído, idempotência, sequência de servidores (ADR-012), graceful shutdown (RNF7).
- `ielm-eval run --dry-run` exibe tabela de ondas com coluna GPUs + config_hash; não acessa rede/GPU.
- `ielm-eval run` (com fakes via build_fake_container) executa e exibe sumário; exit 0.
- Cobertura: `application/use_cases/` ≥ 85%; `infrastructure/adapters/` ≥ 80%;
  `domain/` continua ≥ 95%.

> **Observação para M4 (análise estatística):** o `StatsPort` (TAREFA-005) foi declarado
> em M0 com estrutura mínima e documentado como "a ser detalhado no milestone que o
> consome (M4)". Com o M3 fechado, o Parquet de resultados estará sendo produzido de
> forma real pelo pipeline; M4 pode ler esse Parquet via `ResultReaderPort` e implementar
> os adapters `WilcoxonAdapter`, `FriedmanAdapter` e `MLMAdapter` (statsmodels/pymer4)
> que implementam `StatsPort`. O E2E de M3 já produz o dataset mínimo para exercitar
> os testes estatísticos em M4 sem necessidade de dados reais de GPU.
