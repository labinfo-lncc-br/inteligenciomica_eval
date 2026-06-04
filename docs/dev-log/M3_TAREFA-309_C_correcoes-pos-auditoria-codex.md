# M3_TAREFA-309_C — Correções pós-auditoria Codex (ciclo B → ciclo C)

**Data**: 2026-06-03
**Milestone**: M3 — Orquestração end-to-end
**Épico**: E3
**Skill**: /implement (correção)
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Corrigir os achados legítimos do ciclo B (auditoria Codex) sobre a TAREFA-309.
Cinco problemas reais foram identificados; três achados do Codex foram descartados por
divergência de spec (Codex comparou com uma spec diferente do Prompt A real).

---

## Análise da Auditoria

### Achados legítimos (corrigidos neste ciclo)

| # | Achado Codex | Gravidade |
|---|---|---|
| 5 | `--serial` parseado mas não passado ao container real → `WaveSchedulerService` sempre concorrente | BLOQUEADOR |
| 5 | `--phase` parseado mas nunca usado na execução real | BLOQUEADOR |
| 5 | `n_questions=len(config.llms)` incorreto no `WaveSchedulerService` | BLOQUEADOR |
| 7 | `--dry-run` não usava `build_fake_container` (usava `load_questions()` direto) | IMPORTANTE |
| 6 | Apenas 1 spinner em vez de 3 barras de progresso Rich | IMPORTANTE |

### Achados descartados (spec divergente)

O Codex comparou a implementação com uma spec diferente do Prompt A real (arquivo
`docs/m3_tarefas_309_310.md`):

| Achado descartado | Motivo |
|---|---|
| "Loader no contrato errado — deve ser `infrastructure/repositories/questions.py` lendo `config/questions.yaml`" | Nosso Prompt A define `infrastructure/benchmark/loader.py` com JSONL; Prompt B verifica exatamente esse caminho (item 1) |
| "`RoundConfig.questions: str` faltando" | Campo não previsto no Prompt A; o override de path vai em `RuntimeSettings.BENCHMARK_QUESTIONS_PATH` (env var) |
| "CLI regression: compute-metrics e run-round2 ausentes" | Comandos inexistentes no M3; não previstos em nenhuma spec |

---

## Arquivos Modificados

| Arquivo | Alteração |
|---------|-----------|
| `src/inteligenciomica_eval/infrastructure/wiring.py` | Novos params `serial: bool` e `phases: list[str] \| None` em `build_container`; `n_questions` derivado das perguntas carregadas; `build_fake_container` pré-carrega 2 perguntas e usa `len()` para `n_questions`; `functools` removido (não mais usado) |
| `src/inteligenciomica_eval/cli.py` | `phases_filter` derivado de `--phase`; `build_container(serial=serial, phases=phases_filter)`; 3 barras Progress (task_waves / task_gen / task_eval); `_run_dry_run` usa `build_fake_container` |
| `docs/dev-log/M3_TAREFA-309_A_di-wiring-cli-run-benchmark.md` | Atualizado: smoke test, critérios CA-10 a CA-14, seção de problemas corrigidos, observações |
| `memory/m3-tarefa-309-state.md` | Atualizado com estado pós-ciclo B |

---

## Decisões Técnicas

### 1. `build_container(serial, phases)` — parâmetros de controle de execução

`serial: bool = False` é passado para `WaveSchedulerService(allow_concurrent_models=not serial)`.
`phases: list[str] | None = None` sobrescreve `config.phases` em `_ExperimentConfig.phases` quando fornecido.
No CLI: `phases_filter = None if phase == "both" else [phase.upper()]`.

### 2. `n_questions` derivado das perguntas carregadas

O `WaveSchedulerService` usava `n_questions=len(config.llms)` — valor incorreto (contava
LLMs, não perguntas). Correção: em `build_container`, perguntas são carregadas cedo
(`_loaded_questions = load_questions(questions_path)`) antes da criação do scheduler,
e `n_questions=len(_loaded_questions)` garante cell counts corretos.

Em `build_fake_container`: `_fake_questions = load_questions(None)[:2]` (2 primeiras
perguntas do arquivo empacotado); `n_questions=len(_fake_questions) = 2`.

### 3. `--dry-run` via `build_fake_container`

O ciclo A usava `load_questions()` diretamente para evitar `ModuleNotFoundError` fora
do pytest. O Prompt A §3 item 2 e Prompt B item 7f exigem que `--dry-run` use
`build_fake_container` para "provar que a fiação está correta". Decisão: aceitar a
dependência de `PYTHONPATH=tests` fora do pytest; documentar no docstring de
`_run_dry_run`. No contexto primário (pytest / desenvolvimento), `tests/` já está no
`sys.path`.

### 4. 3 barras de progresso Rich

Substituído o spinner único (`task_status`) por 3 tasks: `task_waves` (ondas),
`task_gen` (geração/métricas), `task_eval` (avaliação/julgamento). O callback
`_progress_callback(msg: str)` despacha para a task correta com base no prefixo da
mensagem (`"generation:"`, `"metrics_pass_*"`, `"judge_pass_*"`, `"experiment_completed"`).
Totais como `None` (indeterminate) pois o número de ondas/células não é conhecido no
CLI antes de `execute()` retornar o `WavePlan`.

### 5. `functools` removido

`functools.partial` foi substituído por funções `def benchmark_loader()` locais, que
são mais explícitas e não violam a regra ruff `E731` (lambda assignments). O import
de `functools` ficou sem uso e foi removido.

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| ruff `F821 Undefined name _loaded_questions` — usada antes de ser definida | Movida a carga de perguntas para antes da criação do `WaveSchedulerService` (secção "BenchmarkLoader — carregado cedo") |
| ruff `E731 Do not assign lambda` — dois lambdas em `benchmark_loader` | Substituídos por `def benchmark_loader() -> list[Question]: return list(...)` |
| `functools` unused após remoção dos `functools.partial` | Removido o import |
| ruff format | 1 arquivo reformatado (`cli.py`) |

---

## Validação (DoD)

### Gates executados

```
✅ uv run ruff check .          → All checks passed
✅ uv run ruff format --check . → 161 files already formatted
✅ uv run mypy --strict src     → Success: no issues found in 57 source files
✅ uv run lint-imports          → 4 contracts: 4 kept, 0 broken
✅ uv run pytest -n 4 -q --cov=src --cov-fail-under=85
   → 1199 passed, 16 skipped — 88.53% coverage (gate 85% ✓)
```

### Smoke test CLI (dry-run com build_fake_container)

```bash
$ PYTHONPATH=tests uv run ielm-eval run --config config/experiment_round1.yaml --dry-run

[info] wiring_fake_container_built  round_id=round-1

Dry-run plan — round-1
config_hash  : 490c21cd984c73a4d024eef425fbfe495781486c1dca6971eab9392f7894b33f
phases       : ['A', 'B']
Perguntas carregadas: 2

Cell counts (N_questions = 2):
  Phase A  : 2 base(s) x 5 LLM(s) x 3 seed(s) x 2 questions = 60 cells
  Phase B  : 5 LLM(s) x 3 seed(s) x 2 questions = 30 cells

Resolved endpoints (credentials masked):
  VLLM_GENERATOR_URL : <not set>
  ...

[GPU/wave map exibido]
Config valid — dry-run complete.
```

---

## Critérios de Aceitação (pós-correções)

| # | Critério | Status |
|---|----------|--------|
| CA-10 | `--serial` passa `allow_concurrent_models=False` ao `WaveSchedulerService` | ✅ |
| CA-11 | `--phase A` filtra `exp_config.phases = ["A"]` na execução real | ✅ |
| CA-12 | `n_questions` no scheduler derivado de `len(load_questions(...))` | ✅ |
| CA-13 | `--dry-run` chama `build_fake_container` e exibe `wiring_fake_container_built` | ✅ |
| CA-14 | 3 barras Rich Progress (task_waves / task_gen / task_eval) | ✅ |
| CA-15 | ruff + mypy + lint-imports + pytest 85% todos verdes | ✅ |

---

## Observações para Próximas Tarefas

- **TAREFA-310**: `build_fake_container` agora retorna 2 perguntas e scheduler correto —
  o gate E2E pode usar `container.benchmark_loader()` diretamente.
- Após este ciclo, TAREFA-309 está pronta para re-submissão ao Codex (ciclo D / PASS).
- O comentário de `_run_dry_run` documenta o requisito de `PYTHONPATH=tests` para uso
  em CLI externo; usuários de produção não devem usar `--dry-run` sem esse contexto.
