# M3_TAREFA-313_A — Contrato de Benchmark (Wiring + Registry Dual-Mode)

**Data**: 2026-06-07
**Milestone**: M3 — Orquestração das 4 GPUs
**Épico**: E3
**Skill**: backend-engineer, test-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Reconciliar o contrato de benchmark do InteligenciÔmica Eval corrigindo três achados da
auditoria completa (2026-06-07):

- **I1**: `BENCHMARK_QUESTIONS_PATH` era resolvida contra o `cwd`, ao contrário de
  `model_registry_path` que resolve relativo ao YAML.
- **I2**: `RoundConfig.questions` existia no schema mas era campo morto — nenhum código o lia.
- **I5**: `model_registry.yaml` não tinha `endpoint_env` nas entradas, obrigando edição
  manual do registry em `server_mode=external`.

---

## Arquivos Criados / Modificados

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `src/inteligenciomica_eval/infrastructure/wiring.py` | Modificado | Precedência 3 níveis + helper `_mask_path` + log `wiring_questions_source` |
| `src/inteligenciomica_eval/cli.py` | Modificado | Fallback `_run_dry_run` usa mesma precedência |
| `src/inteligenciomica_eval/infrastructure/config/schema.py` | Modificado | Docstring de `questions` atualizado (campo agora canônico) |
| `config/model_registry.yaml` | Modificado | `endpoint_env` em todas as 6 entradas (5 geradores + juiz) |
| `config/experiment_round1.yaml` | Modificado | Comentário documentando a precedência de carregamento |
| `tests/unit/infrastructure/test_wiring_questions.py` | Criado | 5 testes de regressão (falhavam antes da tarefa) |

---

## Decisões Técnicas

### Precedência de carregamento (build_container + _run_dry_run fallback)

```
(a) BENCHMARK_QUESTIONS_PATH (env)      → override, máxima prioridade
(b) config.questions (campo do YAML)    → resolvido relativo ao diretório do YAML
(c) default empacotado                  → questions_rf1.jsonl via importlib.resources
```

Esta precedência foi implementada em dois pontos:

1. **`wiring.py::build_container`** (l. 627–643): a lógica substitui a linha anterior
   que só checava a env var. O novo código determina `_questions_source` e loga
   `wiring_questions_source` com o nome mascarado do arquivo (helper `_mask_path`).

2. **`cli.py::_run_dry_run`** (fallback ImportError): antes usava apenas
   `settings.BENCHMARK_QUESTIONS_PATH`. Agora segue a mesma precedência, incluindo
   `cfg.questions` resolvido relativo ao `config.parent`.

### Registry dual-mode (I5)

`endpoint_env` adicionado a todas as 6 entradas do `config/model_registry.yaml`:

| Modelo | `endpoint_env` |
|--------|----------------|
| `gpt-oss-120b` | `VLLM_GPT_OSS_120B_EXTERNAL_URL` |
| `gemma4:31b` | `VLLM_GEMMA4_31B_EXTERNAL_URL` |
| `qwen3.6:35b` | `VLLM_QWEN3_6_35B_EXTERNAL_URL` |
| `glm-4.7-flash` | `VLLM_GLM_4_7_FLASH_EXTERNAL_URL` |
| `llama4:16x17b` | `VLLM_LLAMA4_16X17B_EXTERNAL_URL` |
| `prometheus-8x7b-v2.0` (juiz) | `VLLM_JUDGE_EXTERNAL_URL` |

O campo é `str | None` em `ModelEntry` — ignorado em `server_mode=managed`, obrigatório
em `external` (comportamento já garantido pelo `_build_external_server_manager`).

### Masking de path em log

Criado helper `_mask_path(p: Path) -> str` que retorna `<...>/{p.name}` — expõe apenas
o nome do arquivo sem vazar o layout de diretórios. Reutiliza convenção de `_mask_url`.

---

## Problemas Encontrados e Soluções

**Teste de dry-run**: a primeira abordagem (manipulação de `sys.path` para forçar
`ImportError`) falhou porque `fakes` estava em `sys.modules` de execuções anteriores.
Solução: usar `patch(..., side_effect=ImportError(...))` em `build_fake_container` —
o CLI chama `_bfc(cfg)` e a chamada lança `ImportError`, que o `except ImportError`
no `_run_dry_run` captura corretamente.

---

## Validação (DoD)

### Gates de qualidade

```
ruff check .          → All checks passed!
ruff format --check . → 171 files already formatted
mypy --strict src/    → Success: no issues found in 60 source files
lint-imports          → 4 kept, 0 broken
```

### Suíte de testes

```
uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4 -q

1257 passed, 6 skipped, 20 warnings in 28.89s
TOTAL coverage: 89.60% (≥ 85% ✓)
```

### Testes novos (todos 5 PASSED)

```
tests/unit/infrastructure/test_wiring_questions.py::TestQuestionsSource::test_source_b_round_config_field_loads_relative_path PASSED
tests/unit/infrastructure/test_wiring_questions.py::TestQuestionsSource::test_source_a_env_overrides_round_config PASSED
tests/unit/infrastructure/test_wiring_questions.py::TestQuestionsSource::test_source_c_packaged_default_when_neither_set PASSED
tests/unit/infrastructure/test_wiring_questions.py::TestQuestionsSource::test_source_b_path_resolves_relative_to_yaml_not_cwd PASSED
tests/unit/infrastructure/test_wiring_questions.py::TestDryRunQuestionsConsistency::test_dry_run_fallback_uses_round_config_field PASSED
```

Cada teste falharia antes da TAREFA-313 (campo morto / fallback incompleto).

---

## Critérios de Aceitação

- [x] `RoundConfig.questions` efetivamente carrega o conjunto quando definido (regressão verde)
- [x] Resolução relativa ao YAML para `config.questions`; override via env documentado e testado
- [x] `model_registry.yaml` com `endpoint_env` em todas as 6 entradas
- [x] Managed continua funcionando sem env vars novas (campo `endpoint_env` é opcional)
- [x] External dry-run não exige mais edição manual do registry
- [x] Suíte completa ≥ 85%; gate de perguntas prova as 3 origens
- [x] Nenhum path/endpoint cru em log (path mascarado via `_mask_path`)
- [x] `RoundConfig.questions` não foi removido — ligado, não deletado
- [x] Relatório da Parte A gravado em `docs/dev-log/`

---

## Observações para Próximas Tarefas

- **TAREFA-314** (observabilidade): pode usar o log `wiring_questions_source` como
  referência de padrão de logging estruturado no wiring.
- **TAREFA-315** (acurácia documental): o manual de operação deve ser atualizado para
  documentar a nova precedência e os nomes canônicos de `endpoint_env` do registry.
- **TAREFA-607** (doc-sync): CLAUDE.md §12 (Estado Atual) e §13 (Decisões de Design)
  devem refletir que I1/I2/I5 foram corrigidos nesta tarefa.
- **M5** (futura): o seletor de IDs do funil (`load_question_ids`) deve ser construído
  sobre o contrato definido aqui — a precedência (a)/(b)/(c) é a fonte canônica de
  perguntas para qualquer filtragem futura.
