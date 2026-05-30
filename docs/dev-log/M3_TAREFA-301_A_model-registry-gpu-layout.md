# M3_TAREFA-301_A — Model registry + GPU layout

**Data**: 2026-05-29
**Milestone**: M3 — Orquestração experimental (gestão de servidores, 3 passadas, ciclo A+B)
**Épico**: E3
**Skill**: backend-engineer
**Prioridade / Tamanho**: P0 / S
**Referência arquitetural**: §8 (estrutura) · §7.2/§15 (topologia/modelos) · ADR-003 (regimes) · ADR-008 (config declarativa) · ADR-012 (alocação de GPUs) · Nota de operacionalização M3 itens 2 e 5

## Objetivo

Implementar o catálogo de modelos e o layout de GPUs da rodada como configuração
Pydantic v2 de infraestrutura (`ModelRegistryConfig`), fixando o contrato de regimes
determinísticos do ADR-003 (juiz `batch_invariant=True`/`tp=1`; geradores
`batch_invariant=False`) e a alocação de GPUs do ADR-012 (juiz na GPU 3; geradores
nas 0/1/2). Expor o VO de domínio `ModelWaveSpec` (abstração de serving/GPU para a
camada `application` sem acoplar infraestrutura) e referenciar o registry no
`RoundConfig` via `model_registry_path` (arquivo SEPARADO, nunca embutido).

## Arquivos Criados / Modificados

### Criados
- `src/inteligenciomica_eval/infrastructure/config/model_registry.py` — `ModelEntry`,
  `GPUSlot`, `ModelRegistryConfig` (Pydantic v2), `get_model()` e `load_model_registry()`.
- `config/model_registry.yaml` — arquivo SEPARADO do `experiment_round1.yaml` (§8/§12.1);
  6 modelos (5 geradores + Prometheus-2 juiz) + 4 `gpu_slots` (GH200).
- `tests/unit/config/test_model_registry.py` — 20 testes (GPUSlot, validação cross-field
  ADR-003, validação de conjunto, `get_model`, registry versionado, `ModelWaveSpec`).

### Modificados
- `src/inteligenciomica_eval/domain/value_objects.py` — adiciona `ModelWaveSpec`
  (frozen dataclass pura; Nota M3 item 5).
- `src/inteligenciomica_eval/infrastructure/config/schema.py` — adiciona
  `model_registry_path: str` ao `RoundConfig` (referência ao path, NÃO `ModelRegistryConfig`).
- `config/experiment_round1.yaml` — referencia `model_registry_path: "model_registry.yaml"`;
  `llms` alinhado ao roster canônico (5 geradores, doc l.826); `judge.model` corrigido para
  `prometheus-8x7b-v2.0`; `embedding_model`/`chunk_strategy` = `PENDENTE-rodada1`.

## Decisões Técnicas

1. **Validators levantam `ValueError`; o loader converte em `ConfigValidationError`.**
   Mesmo padrão de `schema.py`/`load_round_config` (§3): `load_model_registry` captura
   `pydantic.ValidationError` e re-levanta `ConfigValidationError(field, reason)` apontando
   o primeiro campo falho (fail-fast, §14.2). Construir `ModelEntry`/`ModelRegistryConfig`
   direto levanta `ValidationError`; o contrato público de erro do projeto é via a função
   de carga, então os testes de `ConfigValidationError` passam por YAML + `load_model_registry`.
2. **Cross-field do regime via `model_validator(mode="after")` no `ModelEntry` (ADR-003).**
   `is_judge=True` ⟹ exige `batch_invariant=True` **e** `tensor_parallel_size=1`;
   `is_judge=False` ⟹ exige `batch_invariant=False`. As mensagens citam **ADR-003**
   (verificável pelo auditor: a string "ADR-003" propaga até a `ConfigValidationError`).
3. **`GPUSlot.available_gb` como `@property` (não `computed_field`).** `vram_gb - reserved_gb`;
   não precisa ser serializado, então uma property simples basta e mantém mypy `--strict` limpo.
4. **VRAM checada contra o slot ALVO (`gpu_slots[model.gpu_index]`), não o máximo.**
   Validação de conjunto em `ModelRegistryConfig`: nomes únicos, **exatamente 1 juiz**,
   `gpu_index` com slot correspondente, e `vram_gb_awq <= slot.available_gb` por modelo
   (mensagem inclui nome do modelo + necessário vs. disponível). Teste dedicado
   (`test_vram_check_uses_target_slot_not_max`) prova que um slot maior em OUTRA GPU não
   "salva" um modelo que estoura sua GPU designada.
5. **`ModelWaveSpec` é dataclass de domínio pura.** Sem Pydantic/yaml (proibidos em `domain`
   pelo import-linter). Construído pelo wiring (TAREFA-309) a partir de `ModelEntry`; permite
   ao `WaveSchedulerService` (application, TAREFA-303) planejar ondas sem importar `infrastructure`.
6. **`model_registry_path: str = "model_registry.yaml"` — campo com DEFAULT (decisão de compatibilidade).**
   A spec lista `model_registry_path: str`. Optei por **default** em vez de obrigatório porque
   `RoundConfig` é construído sem esse campo em `test_schema.py` (model_validate de `_BASE_DICT`)
   e em `test_provenance.py` (`_BASE_DATA`); torná-lo obrigatório quebraria essas suites
   retroativamente. O default mantém o tipo `str`, é uma **referência de path** (jamais
   `ModelRegistryConfig` embutido — critério do auditor atendido) e o `experiment_round1.yaml`
   o define explicitamente. Análogo a `experiment_b: ... | None = None`, já opcional no schema.
7. **Impacto no `config_hash` analisado e neutro.** `config_hash` faz `model_dump(mode="json")`
   + SHA-256; o novo campo entra no dump, então o hash de uma config muda em valor absoluto.
   Porém `test_provenance.py` só faz asserções **relacionais** (igual→igual, diferente→diferente,
   64 hex) — **nenhum** golden fixa um valor. As demais referências `config_hash="abc123"`
   (`test_min_round_stub.py`, `test_row_mapper.py`) são valores de campo de `EvaluationResult`,
   não derivados do `RoundConfig`. Nenhuma regressão.
8. **Juiz Prometheus-2 8x7B em AWQ — valores REAIS do doc.** `name: prometheus-8x7b-v2.0`,
   `hf_repo: prometheus-eval/prometheus-8x7b-v2.0` (§15.3 l.835/1143), `quantization: "awq"`
   (l.1144), `vram_gb_awq: 26.0` (§15 l.548, ~26 GB AWQ — único footprint citado nas fontes),
   `tensor_parallel_size: 1`, `gpu_index: 3` (ADR-012). `extra_args` carrega
   `VLLM_BATCH_INVARIANT=1` / `VLLM_ENABLE_V1_MULTIPROCESSING=0` (l.1149; consumidos pelo
   `VLLMServerManager` em TAREFA-302). `vram_gb_fp16` é sentinela PENDENTE (referência
   teórica ausente do doc).
9. **`gpu_index` dos geradores é NOMINAL (não há check de duplicata entre modelos).**
   `_validate_registry` só veta `gpu_index` duplicado em `gpu_slots`, não entre modelos —
   correto, pois os 5 geradores giram nas 3 GPUs em 2 ondas (ADR-012). O registry fixa apenas
   o juiz na GPU 3; o orquestrador (TAREFA-303/309) reatribui 0/1/2 por onda (doc §15.3 l.1153).

## Problemas Encontrados e Soluções

- **Roster/juiz corrigidos para os valores REAIS do doc (§15.3) — correção pós-auditoria interna.**
  A primeira versão do YAML usara um roster ESTIMADO (Llama-3.1/Mixtral/Qwen2.5/gemma-2 + juiz
  prometheus-7b/bfloat16), por eu não ter consultado o documento de arquitetura. Corrigido para o
  roster canônico (gpt-oss-120b, gemma4:31b, qwen3.6:35b, glm-4.7-flash, llama4:16x17b + juiz
  prometheus-8x7b-v2.0 AWQ ~26 GB). Ver memória [[ask-dont-deduce-from-docs]].
- **Valores ausentes das fontes = SENTINELAS PENDENTE (decisão do usuário, não fabricação).**
  O doc NÃO traz footprint de VRAM por modelo (Premissa P1.1 ABERTA, §17.3 l.1400; registry-exemplo
  do §15.3 sem campo de VRAM) nem `model_path`/`quantization` dos geradores
  (`<...>`/`<conforme-produção>`). Como o schema do `ModelEntry` exige esses campos concretos, os
  geradores recebem sentinelas conservadoras documentadas (`vram_gb_awq=80 <= 88`,
  `vram_gb_fp16=160`, `quantization="awq"`, `hf_repo="PENDENTE"` exceto `llama4:16x17b` cujo repo o
  Prompt A fornece), marcadas PENDENTE-P1.1 no cabeçalho do YAML e a MEDIR no M0. Não são
  apresentadas como medições.
- **`experiment_round1.yaml` alinhado ao roster canônico.** `llms` passou de placeholders
  Llama-3.1 (2 entradas) para os 5 geradores reais (l.826); `judge.model` corrigido de
  `Llama-3.1-70B` (errado — sequer era o juiz) para `prometheus-8x7b-v2.0`;
  `embedding_model`/`chunk_strategy` viram `PENDENTE-rodada1` (doc `<baseline-a-definir>`
  l.832-833; a variação desses parâmetros é a Rodada 2 / TAREFA-505/506). Nenhum teste carrega
  este YAML; sanidade verificada via `load_round_config`.
- **`experiment_round1.yaml` exigiu Read via ferramenta antes do Edit.** A primeira edição
  falhou ("File has not been read yet") porque eu só havia lido o arquivo via `cat`; após um
  Read pela ferramenta, a edição aplicou.
- **Latência intermitente do canal de saída das ferramentas.** Resultados chegaram em rajadas
  atrasadas. Mitigado consolidando gates em logs (`tmp/gate301*.log`, dir ignorada pelo git) e
  lendo-os; as AÇÕES (Write/Edit/commits) executam de forma confiável mesmo com a saída atrasada.

## Validação (DoD §14.2)

```
ruff check .                 → All checks passed
ruff format --check .        → (após reformatar o teste) todos formatados
mypy --strict src            → Success: no issues found in 35 source files
lint-imports                 → 4 kept, 0 broken
pytest tests/unit/config     → schema + provenance + model_registry (20 novos) verdes
pytest (full, -n 4)          → ver tmp/gate301_full.log (confirmado no fechamento)
```

## Critérios de Aceitação (TAREFA-301)

- [x] Juiz com `batch_invariant=False` **ou** `tensor_parallel_size=2` → `ConfigValidationError`
      citando ADR-003 (2 testes).
- [x] Dois juízes (`is_judge=True` em dois) → `ConfigValidationError`.
- [x] `vram_gb_awq` excedendo `available_gb` do `gpu_index` → falha na carga (com nome do modelo).
- [x] `get_model` lança `ModelNotInRegistryError` para nome desconhecido (não KeyError/ValueError).
- [x] `config/model_registry.yaml` carrega sem erros e contém 6 modelos (5 geradores + juiz).
- [x] `ModelWaveSpec` é frozen dataclass em `domain/`; sem import de `infrastructure` (import-linter KEPT).
- [x] `RoundConfig` contém `model_registry_path: str` (referência), **não** `ModelRegistryConfig` embutido.
- [x] `is_judge=False` ⟹ `batch_invariant=False` também verificado (teste dedicado).
- [x] Sem segredos no YAML versionado (endpoints via env — ADR-008).

## Observações para Próximas Tarefas

- **TAREFA-302 (`VLLMServerManagerAdapter`)**: consome `ModelEntry.extra_args` (juiz carrega
  `VLLM_BATCH_INVARIANT=1`/`VLLM_ENABLE_V1_MULTIPROCESSING=0`) e `gpu_index` (→ `CUDA_VISIBLE_DEVICES`).
  Atenção: o port atual usa `ModelSpec` (domain/ports), cujos campos diferem de `ModelEntry`;
  o wiring (TAREFA-309) fará a conversão `ModelEntry → ModelSpec`.
- **TAREFA-303 (`WaveSchedulerService`)**: recebe `tuple[ModelWaveSpec, ...]` (não
  `ModelRegistryConfig`). O wiring deve construir `ModelWaveSpec` a partir de cada `ModelEntry`.
- **`config/model_registry.yaml`**: revisar `vram_gb_*`/repos contra §7.2/§15 antes de uma rodada real.
- **`.importlinter`**: ainda sem subpaths novos; `application/use_cases` e `application/services`
  entram em 303/304+ (atualizar contratos lá).
