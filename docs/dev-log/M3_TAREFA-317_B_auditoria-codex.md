# M3_TAREFA-317_B — Auditoria Codex

**Data**: 2026-06-15  
**Milestone**: M3 — Orquestração das 4 GPUs  
**Épico**: E3/E4 (orquestração + proveniência)  
**Papel**: code-reviewer (+ checagens de segurança no escopo da auditoria)  
**Veredito**: **PASS**

---

## Escopo auditado

- Commit auditado: `08ca13a` (`feat(M3-TAREFA-317): add smoke command and served-model fix`)
- Relatório A: `docs/dev-log/M3_TAREFA-317_A_served-model-id-smoke.md`
- Código auditado:
  - `src/inteligenciomica_eval/infrastructure/wiring.py`
  - `src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py`
  - `src/inteligenciomica_eval/cli.py`
  - `docs/operations_manual.md`
  - `tests/unit/infrastructure/test_vllm_generator_factory.py`
  - `tests/unit/test_cli_smoke_command.py`
  - `docs/adr/ADR-014-server-mode-external.md`

---

## Resultado

Nenhum bloqueador ou divergência relevante foi encontrado contra o contrato da TAREFA-317.

### Tabela de divergências

| Critério | Arquivo:linha | Gravidade | Resultado |
|---|---|---:|---|
| 1. Factory prefere `served_model_by_url`, depois `port_layout`, por fim `"model"`; loga com `mask_url` | `src/inteligenciomica_eval/infrastructure/wiring.py:225-271` | — | **OK** |
| 2. `build_container` monta e injeta `served_model_by_url`; comentário explica por que managed não regride | `src/inteligenciomica_eval/infrastructure/wiring.py:668-686` | — | **OK** |
| 3. Convenção managed `8000 + gpu_index` e `_entry_to_model_spec` intactos; contrato `GeneratorPort.generate` não foi alterado | `src/inteligenciomica_eval/infrastructure/wiring.py:206-219` | — | **OK** |
| 4. `smoke` constrói container real, roda 1×1×1 nas 3 passadas, usa storage temporário, imprime diagnóstico exigido e sai com exit code coerente | `src/inteligenciomica_eval/cli.py:607-974` | — | **OK** |
| 5. `smoke` reaproveita use cases e proveniência existentes, sem duplicar probes | `src/inteligenciomica_eval/cli.py:692-797`, `src/inteligenciomica_eval/infrastructure/wiring.py:345-441` | — | **OK** |
| 6. Há regressão da factory e testes do smoke para EXIT 0 / EXIT != 0 / uso de temp | `tests/unit/infrastructure/test_vllm_generator_factory.py:37-130`, `tests/unit/test_cli_smoke_command.py:277-459` | — | **OK** |
| 7. Manual aponta o comando real `smoke`; logs/probes continuam mascarando endpoint | `docs/operations_manual.md:454-489`, `src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py:37-58`, `src/inteligenciomica_eval/infrastructure/wiring.py:266-271` | — | **OK** |
| 8. Gates exigidos passam; cobertura >= 85% | saídas coladas abaixo | — | **OK** |

---

## Verificação item a item

### 1. FIX da resolução do nome do modelo

- A precedência implementada está correta:
  - `served_model_by_url[url]` primeiro;
  - `port_to_model[port]` apenas quando `served` é vazio;
  - `"model"` como último recurso.
- Evidência: `src/inteligenciomica_eval/infrastructure/wiring.py:245-264`.
- O log do caminho de resolução usa `mask_url(url)` e só expõe `url_masked`, `model` e `resolution`.
- Evidência: `src/inteligenciomica_eval/infrastructure/wiring.py:266-271`.

### 2. Injeção de `served_model_by_url` no wiring

- `build_container()` monta o dicionário a partir de `_gen_urls` e `_gen_served_ids`, filtrando apenas entradas com `served_model_id` não-vazio.
- Evidência: `src/inteligenciomica_eval/infrastructure/wiring.py:675-679`.
- O comentário explica corretamente o caso `external` (URLs distintas, probe confiável) e o caso `managed` (URLs degeneradas, probe tende a falhar antes do start, fallback para layout de porta).
- Evidência: `src/inteligenciomica_eval/infrastructure/wiring.py:670-674`.

### 3. Regressão em managed / contratos públicos

- `_entry_to_model_spec()` permanece com a convenção `8000 + gpu_index`.
- Evidência: `src/inteligenciomica_eval/infrastructure/wiring.py:206-219`.
- Não houve alteração na assinatura do contrato de geração; a mudança ficou confinada ao wiring/factory.

### 4. Comando `smoke`

- O comando constrói o container real via `build_container(cfg, settings, config_dir=config.parent)`.
- Evidência: `src/inteligenciomica_eval/cli.py:684-690`.
- Seleção de 1 LLM, 1 pergunta e 1 seed:
  - LLM: `src/inteligenciomica_eval/cli.py:674-680`
  - pergunta: `src/inteligenciomica_eval/cli.py:731-746`
  - seed: `src/inteligenciomica_eval/cli.py:682`
- Storage temporário, sem escrita em `data/`:
  - `TemporaryDirectory` + `ParquetStorage(base_dir=Path(_tmpdir), ...)`
  - Evidência: `src/inteligenciomica_eval/cli.py:750-760`
- Três passadas reaproveitando use cases existentes:
  - geração: `src/inteligenciomica_eval/cli.py:778-784`, `818-839`
  - métricas: `src/inteligenciomica_eval/cli.py:785-791`, `845-856`
  - juiz: `src/inteligenciomica_eval/cli.py:792-797`, `861-873`
- Diagnóstico exigido está coberto:
  - `server_mode`: `897`
  - `served_model_id`: `899-902`
  - nome enviado ao endpoint + WARN se `"model"`: `903-909`
  - status da geração: `911-920`
  - score do juiz / `NaN`: `922-927`
  - embeddings: `928-933`
  - `determinism_verified`: `934-937`
- Exit code:
  - `0` somente se geração `ok` e score do juiz não-NaN: `942-946`
  - `1` nos demais casos com hints acionáveis: `948-974`

### 5. Reaproveitamento de proveniência / sem duplicar probes

- O `smoke` lê `container.endpoints_provenance` para obter `served_model_id` e `determinism_verified`, sem rerodar probes.
- Evidência: `src/inteligenciomica_eval/cli.py:692-703`.
- O campo foi exposto no `DIContainer` e preenchido pelo `build_container`.
- Evidência: `src/inteligenciomica_eval/infrastructure/wiring.py:182-183`, `784-803`.

### 6. Testes

- Regressões da factory cobrem os cenários pedidos, inclusive o caso que falharia antes da TAREFA-317:
  - túnel + `served_model_by_url` -> `served_model_id`: `tests/unit/infrastructure/test_vllm_generator_factory.py:37-55`
  - managed sem `served` -> layout de porta: `56-71`
  - desconhecida sem `served` -> `"model"`: `73-85`
  - precedência `served_probe > port_layout`: `87-100`
- Testes do `smoke` cobrem:
  - EXIT 0 com fakes saudáveis: `tests/unit/test_cli_smoke_command.py:277-291`
  - EXIT != 0 com geração vazia: `329-357`
  - EXIT != 0 com juiz NaN: `363-387`
  - ausência de escrita em `data/`: `394-410`
  - ajuda/registro do subcomando: `451-459`

### 7. Manual e política de logs

- O manual agora aponta para o comando real `ielm-eval smoke --config ... [--llm ...] [--question-id ...]`.
- Evidência: `docs/operations_manual.md:454-489`.
- O caminho de auditoria relevante continua mascarando endpoint:
  - probes: `src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py:48-57`, `120-125`, `164-175`
  - resolução da factory: `src/inteligenciomica_eval/infrastructure/wiring.py:266-271`

### 8. ADR-014

- O ADR continua coerente com o as-built auditado:
  - `probe_served_model` / `probe_vllm_version` / `probe_judge_determinism`
  - `determinism_verified=False` por default
- Evidência: `docs/adr/ADR-014-server-mode-external.md:47-65`.

---

## Gates executados na auditoria

### `ruff check`

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests/unit/infrastructure/test_vllm_generator_factory.py tests/unit/test_cli_smoke_command.py
All checks passed!
```

### `ruff format --check`

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .
176 files already formatted
```

### `mypy --strict src/`

```text
$ uv run mypy --strict src/
Success: no issues found in 61 source files
```

### `lint-imports`

```text
$ uv run lint-imports
Contracts: 4 kept, 0 broken.
```

### Testes novos da tarefa

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/test_vllm_generator_factory.py tests/unit/test_cli_smoke_command.py -q --timeout=60
...................                                                      [100%]
19 passed in 1.15s
```

### Suite com cobertura

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m "not integration" --cov=src --cov-report=term --cov-fail-under=85 -n 4 --timeout=120 -q
1337 passed, 6 skipped, 21 warnings in 162.56s (0:02:42)
Required test coverage of 85% reached. Total coverage: 88.93%
```

---

## Observações residuais

- A auditoria não encontrou divergência funcional contra o prompt B.
- O `smoke` foi validado via fakes e pela suite automatizada; esta auditoria não executou um endpoint `external` real.
- O papel `security-auditor` foi solicitado no prompt, mas a skill não estava disponível nesta sessão; as verificações de exposição de URL/log foram feitas manualmente no escopo da review.
