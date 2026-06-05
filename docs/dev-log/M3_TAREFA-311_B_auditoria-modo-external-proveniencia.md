## M3_TAREFA-311_B — Auditoria Codex do modo `external` e proveniência

**Data**: 2026-06-05  
**Milestone**: M3 — extensão pós-gate  
**Épico**: E3/E4  
**Papel**: Prompt B — code-reviewer + test-engineer  
**Status**: **FAIL**

### Escopo auditado

Auditoria da implementação da `TAREFA-311 Parte A`, com foco em:
- modo `server_mode="external"`
- `ExternalVLLMServerManager`
- probes de proveniência
- extensão do schema Parquet / `EvaluationResult`
- wiring / CLI
- regressão dos gates de qualidade

### Resultado executivo

Os gates rápidos (`ruff`, `mypy`, `lint-imports`) passaram, mas a implementação **não cumpre o contrato funcional completo do prompt** e a suíte relevante **não está verde**.

Principais motivos do `FAIL`:
- a proveniência medida por probe não é injetada no fluxo real de geração/persistência;
- o run report exigido no prompt não foi implementado;
- `build_container()` instancia adapters caros/de rede antes do fail-fast de `external`, causando regressão real nos testes;
- a suíte `pytest -m "not integration"` falha no estado atual.

### Findings

#### 1. BLOQUEADOR — probes não alimentam as linhas persistidas

**Referências**
- `src/inteligenciomica_eval/application/use_cases/run_generation_pass.py:367`
- `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:246`
- `src/inteligenciomica_eval/cli.py:170`

**Problema**

As colunas `server_mode`, `served_model_id` e `determinism_verified` foram adicionadas ao schema, mas os valores reais nunca entram no caminho de escrita.

- `EvaluationResult` é criado com defaults em `run_generation_pass.py`.
- `ParquetStorage.to_row()` persiste os campos a partir de `result.server_mode`, `result.served_model_id` e `result.determinism_verified`.
- As probes são executadas somente pela CLI, antes do run, sem injeção em `EvaluationResult`, `RunExperimentUseCase`, `RunGenerationPassUseCase` ou `RowProvenance`.

**Impacto**

O Parquet passa a ter as colunas, mas não a proveniência medida exigida pelo prompt. Na prática, as linhas continuam carregando defaults retrocompatíveis em vez do estado real do endpoint.

#### 2. BLOQUEADOR — run report de proveniência não foi implementado

**Referências**
- `src/inteligenciomica_eval/application/use_cases/run_experiment.py:112`
- `src/inteligenciomica_eval/cli.py:170`

**Problema**

O prompt pede uma seção `endpoints_provenance` no run report com:
- `server_mode`
- por endpoint: `logical_name`, endpoint mascarado, `served_model_id`, `vllm_version`, `healthy`, `determinism_verified`
- `config_hash`
- nota de topologia

`ExperimentReport` permanece sem qualquer campo desse tipo, e não há persistência equivalente em outro artefato de report.

**Impacto**

O requisito central de auditoria de proveniência em nível de run não foi entregue.

#### 3. BLOQUEADOR — `build_container()` falha antes da validação external

**Referências**
- `src/inteligenciomica_eval/infrastructure/wiring.py:415`
- `src/inteligenciomica_eval/infrastructure/wiring.py:439`

**Problema**

`build_container()` instancia `QdrantRetrieverAdapter`, `PrometheusJudgeAdapter` e `RAGASLayer1Adapter` antes de selecionar/validar o `server_manager` do modo `external`.

Isso viola o fail-fast esperado para `endpoint_env` e produz regressão real: os testes de wiring falham tentando carregar embeddings/rede antes de chegar na validação de external mode.

**Impacto**

O contrato “`endpoint_env` ausente -> `ConfigValidationError`” deixa de ser confiável, porque a construção pode explodir antes em dependências laterais.

#### 4. IMPORTANTE — `wait_healthy()` aceita qualquer status `< 500`

**Referência**
- `src/inteligenciomica_eval/infrastructure/adapters/external_vllm_server_manager.py:164`

**Problema**

O adapter considera o endpoint saudável quando `resp.status_code < 500`.

Isso aceita `401`, `403`, `404` ou `302` como sucesso de healthcheck.

**Impacto**

Endpoints incorretos ou mal roteados podem ser marcados como prontos, escondendo erro de configuração.

#### 5. IMPORTANTE — `probe_vllm_version()` não implementa os fallbacks pedidos

**Referência**
- `src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py:55`

**Problema**

A implementação tenta somente `GET /version`. O prompt pede fallback por header de resposta ou metadata de `/v1/models`.

**Impacto**

Servidores sem `/version` mas com a informação disponível em outra fonte continuam sendo classificados como `None`/`unknown`, abaixo do contrato exigido.

#### 6. IMPORTANTE — `_run_external_probes()` resolve o registry relativo ao `cwd`

**Referência**
- `src/inteligenciomica_eval/cli.py:321`

**Problema**

Os probes recarregam o registry com `Path(cfg.model_registry_path)` sem usar o `config.parent` já resolvido por `build_container()`.

**Impacto**

Quando a config está fora do diretório atual, os probes de `served_model` podem ser silenciosamente pulados pelo `except Exception: pass`.

#### 7. IMPORTANTE — regressão real de suíte e warning de coroutine não aguardada

**Referências**
- `tests/unit/infrastructure/test_wiring_external.py`
- `src/inteligenciomica_eval/cli.py:344`

**Problema**

Os testes de wiring falham no estado atual e os testes da CLI expõem `RuntimeWarning: coroutine '_run_external_probes.<locals>._run_probes' was never awaited`.

**Impacto**

A entrega não satisfaz o critério de aceitação de suíte verde e ainda deixa um problema assíncrono no fluxo novo da CLI.

### Gates executados

#### 1. Ruff

```text
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
-> All checks passed!
```

#### 2. Mypy

```text
UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src
-> Success: no issues found in 60 source files
```

#### 3. Import-linter

```text
uv run lint-imports
-> Contracts: 4 kept, 0 broken
```

#### 4. Testes novos / diretamente relevantes da 311

```text
UV_CACHE_DIR=/tmp/uv-cache uv run pytest \
  tests/unit/infrastructure/test_external_server_manager.py \
  tests/unit/infrastructure/test_endpoint_probe.py \
  tests/unit/infrastructure/test_provenance_columns.py \
  tests/unit/infrastructure/test_wiring_external.py \
  tests/unit/cli/test_run_external.py -q
-> 3 failed, 69 passed, 6 warnings in 11.72s
```

Falhas observadas:
- `tests/unit/infrastructure/test_wiring_external.py::test_build_container_managed_mode_skips_external_manager`
- `tests/unit/infrastructure/test_wiring_external.py::test_build_container_external_mode_uses_external_manager`
- `tests/unit/infrastructure/test_wiring_external.py::test_build_container_external_missing_env_var_raises`

#### 5. Gate ampliado sem integração

```text
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m "not integration" --cov-fail-under=85 -n 4 -q
-> 3 failed, 1249 passed, 6 skipped, 21 warnings in 19.78s
```

Observação importante:
- o gate falhou pelas mesmas regressões de wiring acima;
- também apareceu `RuntimeWarning` ligado a `_run_external_probes`.

### Conformidade com o prompt B

#### Atendido

- `RoundConfig.server_mode` com default `"managed"` e validação.
- `ModelEntry.endpoint_env` adicionado.
- `ExternalVLLMServerManager` criado com `start()/wait_healthy()/stop()`.
- 3 novas colunas adicionadas ao schema Parquet e ao `EvaluationResult`.
- CLI recebeu flag `--require-verified-determinism`.
- ADR foi criado, embora numerado como `ADR-014` em vez de `ADR-013`.

#### Não atendido / incompleto

- proveniência de probe persistida por linha;
- `vllm_version` vindo do probe com fallbacks;
- run report com `endpoints_provenance`;
- probes também em `managed` como auditoria;
- wiring external com fail-fast limpo antes de adapters pesados/de rede;
- suíte relevante verde.

### Observação sobre ADR

O prompt pede `ADR-013`, mas a implementação criou `ADR-014` porque `ADR-013` já existe para `round2-funnel`.

Isso pode ser aceitável como decisão de numeração do projeto, mas permanece como divergência formal em relação ao texto do prompt.

### Recomendação

**Não fazer merge neste estado.**

Próximo ciclo recomendado:
1. mover a validação/seleção de `external` para antes da inicialização de adapters pesados em `build_container()`;
2. definir um objeto explícito de proveniência de endpoints e injetá-lo no caminho real de geração/escrita;
3. estender `ExperimentReport` com `endpoints_provenance`;
4. corrigir o warning assíncrono de `_run_external_probes`;
5. rerodar a suíte relevante até `PASS`.
