# M3_TAREFA-312_A — Gate de integração e completude 309/310/311/606

**Data**: 2026-06-07
**Milestone**: M3 — Gate transversal (integração 309/310/311 + coerência com 606)
**Épico**: E3 (transversal)
**Skill**: code-reviewer, test-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Varredura completa de código e testes nas 6 superfícies de risco abertas por
TAREFA-309/310/311/606. Correção de todos os bloqueadores encontrados. Produção
da matriz de completude.

---

## Arquivos Criados / Modificados

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `docs/arquitetura_detalhada_validacao_inteligenciomica.md` | Modificado | §4.3 e §5.3 atualizados com os 3 campos de proveniência (ADR-014, TAREFA-311) |
| `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py` | Modificado | `from_row()` emite `WARNING` structlog ao encontrar colunas de proveniência ausentes (retrocompat) |
| `tests/unit/infrastructure/test_provenance_columns.py` | Modificado | Teste `test_from_row_defaults_when_columns_absent` atualizado para verificar o WARNING emitido |
| `docs/dev-log/M3_TAREFA-312_A_integration-gate-completude.md` | Criado | Este relatório |

---

## Varredura por Superfície

### A. Gates estáticos e suíte

| Gate | Resultado |
|------|-----------|
| `uv sync --frozen` | OK |
| `import inteligenciomica_eval` | OK (0.1.0) |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 170 files already formatted |
| `mypy --strict src` | Success: no issues in 60 files |
| `lint-imports` | 4 contracts kept, 0 broken |
| `pytest -m "not integration" -q -n 4 --cov-fail-under=85` | **1252 passed, 6 skipped, 89.52%** |

### B. Ripple schema §5.3 / entidade §4.3 (superfície 1)

**Construtores de `EvaluationResult` verificados:**

| Arquivo | Campos novos presentes? |
|---------|------------------------|
| `run_generation_pass.py:376` | ✅ `server_mode`, `served_model_id`, `determinism_verified` explícitos |
| `parquet_storage.py:301` | ✅ via `row.get(col, default)` |
| `tests/e2e/_harness.py:215,292` | ✅ valores de proveniência fornecidos pelo `_ExperimentConfig` |
| `tests/unit/domain/test_entities.py` | ✅ testes dos novos campos |
| `tests/factories/factories.py:194` | ✅ campos com defaults |
| `tests/unit/infrastructure/test_provenance_columns.py:40` | ✅ construtores completos |

Todos os construtores em src/ fornecem os 3 campos explicitamente ou via defaults documentados.
Roundtrip Parquet (escrita→leitura) coberto por `test_provenance_columns.py` (28 testes, 100%).
Coerência de escrita (`batch_invariant==True ⇔ juiz`) coberta por `test_batch_invariant_contract.py`.
Fakes em `tests/fakes/` produzem `EvaluationResult` com os 3 campos (defaults válidos).

### C. Leitura retrocompatível (superfície 2)

**Decisão registrada:** opção (a) — defaulta com mensagem de log.

- `from_row()` usa `row.get("server_mode", "managed")`, `row.get("served_model_id", "")`,
  `row.get("determinism_verified", True)` para Parquet antigo (sem as 3 colunas).
- **BLOQUEADOR C1 (corrigido):** `from_row()` defaultava silenciosamente sem log. Adicionado
  `log.warning("parquet_legacy_row_missing_provenance_columns", missing=[...], ...)` antes do
  `return EvaluationResult(...)`.
- Teste `test_from_row_defaults_when_columns_absent` atualizado para verificar o `WARNING`
  via `capsys` — teria falhado antes da correção.

### D. CLI / Config (superfície 3)

```
ielm-eval --help — subcomandos presentes:
  version, run, annotate, analyze, report, status, show-config, validate-judge

ielm-eval run --help — flags presentes:
  --config (required), --run-id, --phase, --dry-run, --serial,
  --require-verified-determinism
```

Todos os YAML de `config/` parseiam sem erro:
- `config/experiment_round1.yaml`: `RoundConfig` OK (`server_mode=managed`)
- `config/model_registry.yaml`: `ModelRegistryConfig` OK

Dry-run managed:

```
ielm-eval run --config config/experiment_round1.yaml --run-id smoke --dry-run

Dry-run plan — round-1
config_hash  : aad2920d356ce63ecb586d333516103453b59b30c9fe75ca256f501cc8a23771
phases       : ['A', 'B']
Perguntas carregadas: 3
...
Config valid — dry-run complete.
```

Exit 0. Plano de ondas + perguntas carregadas impressos.

**IMPORTANTE — subcomandos `compute-metrics` e `run-round2`:** O prompt D.1 lista esses dois
como esperados, mas eles nunca existiram na CLI. `compute-metrics` é um use case interno
(chamado pelo pipeline, sem CLI própria); `run-round2` pertence ao M5 (explicitamente adiado).
Nenhum subcomando existente foi removido — nível de risco = zero.

### E. Modo external end-to-end (superfície 4)

Todos os 32 testes de modo external passam:
- `test_external_server_manager.py` (17 testes): start sem subprocess; stop no-op;
  `EndpointUnreachableError` tratado; mascaramento de URL; `ServerHandle.pid=None`
- `test_wiring_external.py` (10 testes): `build_container` seleciona `ExternalVLLMServerManager`
  em `server_mode="external"`; `_build_embeddings` mockado (offline-safe)
- `test_run_external.py` (5 testes): `--require-verified-determinism` + probe False → exit 1;
  `--no-require-verified-determinism` → continua sem erro

Import de fakes em produção: ZERO imports de módulo no nível de topo.
`build_fake_container()` em `wiring.py:749` usa `from fakes import ...` **lazy**, documentado.

### F. Proveniência (superfície 5)

- `endpoints_provenance` presente em `ExperimentConfig` e propagado para `ExperimentReport`
  nos dois modos (`run_experiment.py:383, 447`).
- `_run_endpoint_probes()` inicializa `judge_det = False` (linha 343 — ADR-014); fallback de
  exceção retorna `{}, False, {}` (linha 396).
- `_mask_url()` aplicado em TODOS os logs/Panels com URL:
  - `wiring.py:372, 380`: `endpoint_masked` nas proveniências managed e external
  - `external_vllm_server_manager.py:135, 168, 179, 194`: mascaramento no adapter
- Nenhuma URL crua nos logs de produção. Valores "indisponíveis" usam `"unknown"` / `False`
  (nunca `True` inventado).

### G. Ripple 310/M4 (superfícies 1 e 6)

E2E M3 full cycle:

```
tests/e2e/test_m3_full_cycle.py — 5 PASSED em 0.89 s
```

Golden inclui `server_mode`, `served_model_id`, `determinism_verified` em `schema_columns`
(verificado em `tests/golden/e2e_m3_expected.json`).

Suíte M4 (analyze/report/status):

```
70 passed, 1 skipped em 11.41 s
```

### H. Coerência doc↔código (superfície 6)

**BLOQUEADOR H1 (corrigido):** `docs/arquitetura_detalhada_validacao_inteligenciomica.md`
§4.3 e §5.3 não tinham as 3 colunas de proveniência (TAREFA-311).

- **§4.3** (`EvaluationResult`): adicionados `server_mode`, `served_model_id`,
  `determinism_verified` com invariantes corretas (ADR-014).
- **§5.3** (tabela Parquet): 3 novas linhas `⊕` com tipo, origem e notas (schema real agora
  tem 46 colunas; spec atualizada de 43 → 46).

ADR-013 (`ADR-013-round2-funnel.md`): presente; refere-se ao seletor de funil da Rodada 2 (M5
adiado) — nenhuma inconsistência com código (nada implementado = nenhum conflito).

Smoke-test do manual:

```
PASS — todos os subcomandos e flags validados existem na CLI.
  version OK · run OK · status OK · annotate OK · analyze OK · report OK · validate-judge OK
  --run-id OK · --require-verified-determinism OK
```

### I. Varredura de pontas soltas (transversal)

`NotImplementedError` encontrados: TODOS em `stats_adapters.py` (guards defensivos —
"use `FriedmanNemenyiAdapter`"; "use `WilcoxonAdapter`"). **Fora do caminho `run`.**

`TODO`/`FIXME`: nenhuma ocorrência em src/.

`pass #` com comentário: 2 instâncias válidas:
- `registry.py:64`: `pass  # git não encontrado` (fallback de versão)
- `wiring.py:355`: `pass  # judge_det permanece False` (ADR-014)

Referências mortas: nenhuma. `compute_metrics_use_case.py` é um use case **ativo** (chamado
pelo pipeline); sem CLI própria — correto.

Placeholders antigos de analyze/report: sumiram (substituídos por comandos reais M4).

---

## Lista de Achados

### BLOQUEADORES (corrigidos)

| ID | Superfície | Arquivo:linha | Descrição | Correção |
|----|-----------|---------------|-----------|---------|
| C1 | Retrocompat | `parquet_storage.py:298-300` | `from_row()` defaultava silenciosamente sem log | Adicionado `log.warning("parquet_legacy_row_missing_provenance_columns", ...)` |
| H1 | Doc↔código | `arquitetura_detalhada_validacao_inteligenciomica.md` §4.3 §5.3 | Spec sem as 3 colunas de proveniência (TAREFA-311) | Adicionadas 3 linhas em §4.3 (invariantes de entidade) e 3 linhas ⊕ em §5.3 (tabela Parquet) |

### IMPORTANTES (registrados, sem correção de escopo)

| ID | Superfície | Arquivo | Descrição | Proposta |
|----|-----------|---------|-----------|---------|
| I1 | CLI/Doc | CLI real | Prompt D.1 lista `compute-metrics` e `run-round2` como subcomandos esperados; nunca existiram. `compute-metrics` é use case interno; `run-round2` pertence ao M5 adiado. | Atualizar checklist do prompt em eventual M5 |
| I2 | Entidade default | `entities.py:153`, `wiring.py:126` | `EvaluationResult.determinism_verified = True` e `_ExperimentConfig.judge_determinism_verified = True` como default de dataclass. Em runtime, o wiring sempre passa o valor medido. O default só afeta testes/fakes que não setam o campo explicitamente. | Anotar nos testes que usam o default qual é o valor intencionado |

### COSMÉTICOS (registrados)

- `questions_rf1.jsonl`: comentário "_comment" sobre 3 placeholders — adequado, responsabilidade do especialista biomédico em produção.

---

## Matriz de Completude

| Tarefa | Entregue | Testado | Gates verdes | Pendências |
|--------|----------|---------|-------------|------------|
| TAREFA-309 (Wiring + CLI `run` + `BenchmarkLoader`) | ✅ | ✅ | ✅ | — |
| TAREFA-310 (Gate E2E ciclo completo) | ✅ | ✅ 5 PASSED < 1 s | ✅ | — |
| TAREFA-311 (`ExternalVLLMServerManager` + probes) | ✅ | ✅ 32 testes externos | ✅ | — |
| TAREFA-606 (Manual + smoke-test) | ✅ | ✅ smoke-test PASS | ✅ | — |

---

## Validação Final

```
ruff check .          — All checks passed
ruff format --check . — 170 files already formatted
mypy --strict src     — Success: no issues in 60 files
lint-imports          — 4 contracts kept, 0 broken
pytest (unit, 89.52%) — 1252 passed, 6 skipped
e2e test_m3_full_cycle — 5 PASSED em 0.89 s
M4 suite (70 testes)   — 70 passed, 1 skipped
smoke-test manual      — PASS (7 subcomandos + 2 flags)
```

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| A–I executados; todas as saídas coladas | ✅ |
| ZERO bloqueadores remanescentes (C1, H1 corrigidos com teste) | ✅ |
| Matriz de completude: 309/310/311 verde; 606 coerente com CLI | ✅ |
| Suíte completa verde ≥ 85% | ✅ 89.52% |
| e2e 310 < 30 s (5 testes) | ✅ 0.89 s |
| Suíte M4 verde | ✅ |
| Smoke-test manual verde | ✅ |
| Dry-run managed exit 0 | ✅ |
| `from __future__ import annotations`; mypy; ruff; lint-imports verdes | ✅ |
| Nenhum import de fakes em produção (módulo) | ✅ (lazy dentro de `build_fake_container`) |
| Nenhum segredo/endpoint exposto | ✅ (`_mask_url` em todos os logs/Panels) |

---

## Observações para Próximas Tarefas

- §5.3 da arquitetura agora tem 46 colunas documentadas (3 novos campos TAREFA-311).
- Eventual M5 precisará adicionar `compute-metrics` e `run-round2` à CLI se esses
  subcomandos forem requeridos.
- `determinism_verified=True` como default de entidade/dataclass pode ser revisado para
  `False` em eventual PR de clareza (IMPORTANTE I2) — não urgente.
