# M3_TAREFA-301_B_auditoria-model-registry-gpu-layout

## Prompt auditado

- TAREFA-301 — Prompt B
- Data: 2026-05-29
- Auditor: ChatGPT Codex (`code-reviewer`)

## Veredito

- PASS / Approve

## Reauditoria

- 2026-05-29: reauditoria executada sobre a versão corrigida do YAML versionado.
- Escopo material da correção: `config/model_registry.yaml` e `config/experiment_round1.yaml`.
- Resultado: o veredito **permanece PASS**. O código auditado anteriormente
  (`model_registry.py`, `schema.py`, `value_objects.py`) não mudou; a correção
  saneou os dados do registry/round config para o roster real do documento-base.

## Tabela de critérios

| Critério | Evidência | Gravidade | Resultado |
|---|---|---:|---|
| `ModelEntry` contém todos os campos, inclusive `gpu_index` | `src/inteligenciomica_eval/infrastructure/config/model_registry.py:46-55` | — | OK |
| Validação cross-field do juiz cita ADR-003 e exige `batch_invariant=True` + `tensor_parallel_size=1` | `src/inteligenciomica_eval/infrastructure/config/model_registry.py:57-78` | — | OK |
| `is_judge=False -> batch_invariant=False` validado | `src/inteligenciomica_eval/infrastructure/config/model_registry.py:73-77` | — | OK |
| `GPUSlot.available_gb = vram_gb - reserved_gb` | `src/inteligenciomica_eval/infrastructure/config/model_registry.py:81-101` | — | OK |
| `ModelRegistryConfig` garante unicidade, 1 juiz e VRAM contra slot alvo | `src/inteligenciomica_eval/infrastructure/config/model_registry.py:104-157` | — | OK |
| `get_model()` lança `ModelNotInRegistryError` | `src/inteligenciomica_eval/infrastructure/config/model_registry.py:160-176` | — | OK |
| `load_model_registry()` converte `ValidationError` em `ConfigValidationError` | `src/inteligenciomica_eval/infrastructure/config/model_registry.py:179-205` | — | OK |
| `config/model_registry.yaml` é separado do round YAML | `config/model_registry.yaml:1-17` e `config/experiment_round1.yaml:6-8` | — | OK |
| `RoundConfig` referencia `model_registry_path: str`, não embedda registry | `src/inteligenciomica_eval/infrastructure/config/schema.py:118-123` | — | OK |
| `ModelWaveSpec` frozen dataclass em `domain/` | `src/inteligenciomica_eval/domain/value_objects.py:244-270` | — | OK |
| `domain` não importa `infrastructure` | `lint-imports` verde | — | OK |
| YAML sem segredos | cabeçalho do registry + ausência de endpoints/credenciais em `config/model_registry.yaml:12-17` | — | OK |
| Roster real da rodada alinhado entre registry e round config | `config/model_registry.yaml:68-140` e `config/experiment_round1.yaml:18-41` | — | OK |

## Evidência de testes

- Cobertura específica do contrato em `tests/unit/config/test_model_registry.py:83-289`
  - `GPUSlot.available_gb`: `:83-91`
  - ADR-003 / cross-field: `:108-134`
  - zero/dois juízes, nomes duplicados, VRAM e slot alvo: `:142-200`
  - `get_model` / `ModelNotInRegistryError`: `:215-227`
  - registry versionado com 6 modelos: `:235-256`
  - `ModelWaveSpec` frozen/dataclass/campos: `:264-289`

## Observações

- `model_registry_path` com default em `RoundConfig` é uma reconciliação compatível com o
  repositório: preserva `tests/unit/config/test_schema.py` e `test_provenance.py`, sem
  violar o critério do prompt, que exige referência por path e proíbe embedding do registry.
- O diff em `.gitignore` (`tmp/`) está fora do escopo funcional da TAREFA-301 e não
  influencia o veredito desta auditoria.
- Na versão corrigida, o registry já usa o roster real informado para a rodada:
  `gpt-oss-120b`, `gemma4:31b`, `qwen3.6:35b`, `glm-4.7-flash`, `llama4:16x17b`
  e o juiz `prometheus-8x7b-v2.0`.
- Os valores explicitamente não resolvidos no documento-base foram tratados como
  sentinelas `PENDENTE` no YAML, com comentários claros. Isso é aceitável nesta
  tarefa porque o contrato aqui é de estrutura/validação, não de benchmark de VRAM.
- Confirmei também o alinhamento funcional:
  - `round.llms == registry.generators`
  - `round.judge.model == registry.judge.name`

## Execução confirmada

```text
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/config/test_schema.py tests/unit/config/test_provenance.py -q
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/config/test_model_registry.py tests/unit/config/test_schema.py tests/unit/config/test_provenance.py -q
-> 66 passed in 0.24s

UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports
-> Contracts: 4 kept, 0 broken

UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src
-> Success: no issues found in 35 source files

UV_CACHE_DIR=/tmp/uv-cache uv run python -c "<probe de alinhamento registry/round>"
-> registry_models=6
-> judge=prometheus-8x7b-v2.0
-> round_llms_match=True
-> judge_model_match=True
```
