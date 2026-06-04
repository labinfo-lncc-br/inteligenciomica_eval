# M3_TAREFA-309_B — Auditoria DI Wiring, CLI `run` e BenchmarkLoader

**Data**: 2026-06-03
**Milestone**: M3 — Orquestração end-to-end
**Épico**: E3
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / L

## Objetivo

Auditar a implementação da TAREFA-309 recebida no ciclo A contra o prompt de verificação,
com foco em:
- loader de benchmark
- `infrastructure/wiring.py`
- comando `ielm-eval run`
- preservação de subcomandos existentes
- aderência ao DoD e à UX exigida

## Arquivos Criados / Modificados

- `docs/dev-log/M3_TAREFA-309_B_auditoria-di-wiring-cli-run-benchmark.md`

## Decisões Técnicas

- A auditoria foi feita a partir do código efetivamente presente no repositório e do
  prompt B da TAREFA-309.
- O parecer considerou tanto os gates técnicos quanto aderência literal ao contrato
  funcional e arquitetural descrito no prompt.

## Problemas Encontrados e Soluções

### 1. FAIL — implementação seguiu contrato alternativo de JSONL/env var

**Arquivos**:
- `src/inteligenciomica_eval/infrastructure/benchmark/loader.py`
- `src/inteligenciomica_eval/infrastructure/config/settings.py`
- `src/inteligenciomica_eval/infrastructure/wiring.py`

O código implementado usa:
- `questions_rf1.jsonl` empacotado
- `load_questions(path: Path | None = None)`
- override por `BENCHMARK_QUESTIONS_PATH`

O prompt B auditado exigia o contrato canônico com:
- `config/questions.yaml`
- loader em `infrastructure/repositories/questions.py`
- `path` obrigatório
- `load_question_ids(path)`
- `RoundConfig.questions`

Isso gerou divergência material entre prompt e implementação entregue.

### 2. FAIL — `RoundConfig.questions` não foi adicionado

**Arquivo**: `src/inteligenciomica_eval/infrastructure/config/schema.py`

O schema permaneceu sem o campo `questions`, impedindo a fiação pelo caminho esperado
no prompt B auditado.

### 3. FAIL — `build_container` e `build_fake_container` não seguem o contrato auditado

**Arquivo**: `src/inteligenciomica_eval/infrastructure/wiring.py`

Na primeira versão auditada:
- o real container resolvia perguntas por env var/JSONL empacotado
- o fake container não restringia o loader às 2 primeiras perguntas reais
- o dry-run usava loader direto, e não `build_fake_container`

### 4. FAIL — regressão de CLI em subcomandos esperados pelo prompt B

**Arquivo**: `src/inteligenciomica_eval/cli.py`

Na auditoria inicial, `ielm-eval --help` não expunha `compute-metrics` nem
`run-round2`, embora o prompt B auditado os tratasse como subcomandos a preservar.

### 5. FAIL — `--phase`, `--serial` e `n_questions` não controlavam a execução real

**Arquivos**:
- `src/inteligenciomica_eval/cli.py`
- `src/inteligenciomica_eval/infrastructure/wiring.py`

Achados da primeira auditoria:
- `--phase` era parseado e ignorado na execução real
- `--serial` só afetava o dry-run
- `WaveSchedulerService` recebia `n_questions=len(config.llms)`, o que distorcia o plano

### 6. IMPORTANTE — progresso do `run` não atendia ao contrato pedido

**Arquivo**: `src/inteligenciomica_eval/cli.py`

O comando `run` exibia apenas um spinner/descrição dinâmica, não 3 barras de progresso
separadas para ondas, células geradas e células avaliadas.

## Validação (DoD)

### Comandos executados

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ielm-eval --help
UV_CACHE_DIR=/tmp/uv-cache uv run ielm-eval run --help
UV_CACHE_DIR=/tmp/uv-cache uv run ielm-eval run --config config/experiment_round1.yaml --run-id test --dry-run
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/unit/infrastructure/test_benchmark_loader.py tests/unit/infrastructure/test_wiring.py tests/unit/cli/test_run_real.py
UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports
UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q --cov=src --cov-fail-under=85
```

### Resultado dos gates

- `ruff check .` ✅
- `ruff format --check .` ✅
- `mypy --strict src` ✅
- `lint-imports` ✅
- `pytest --cov=src --cov-fail-under=85` ✅ `1199 passed, 16 skipped, 89%`

### Evidências observadas na auditoria

- `ielm-eval --help` listava `version`, `run`, `annotate`, `analyze`, `report`,
  `status`, `show-config`, `validate-judge`
- `ielm-eval run --help` expunha `--config`, `--run-id`, `--phase`, `--dry-run`,
  `--serial`
- `ielm-eval run --config ... --run-id test --dry-run` executava com 3 perguntas
  carregadas do benchmark empacotado

## Critérios de Aceitação

| Critério | Evidência | Status |
|---|---|---|
| Loader segue o contrato auditado pelo prompt B | `benchmark/loader.py` vs prompt B | ❌ |
| `RoundConfig.questions` presente | `schema.py` | ❌ |
| `build_container` usa filtro real de `--phase` | código auditado no ciclo B | ❌ |
| `build_container` respeita `--serial` | código auditado no ciclo B | ❌ |
| `WaveSchedulerService` usa `n_questions` correto | código auditado no ciclo B | ❌ |
| Dry-run prova wiring por `build_fake_container` | código auditado no ciclo B | ❌ |
| CLI preserva subcomandos esperados no prompt B | `--help` | ❌ |
| Gates técnicos verdes | comandos executados | ✅ |

## Observações para Próximas Tarefas

- Reavaliar a divergência entre o prompt canônico de `config/questions.yaml` e a
  implementação escolhida com JSONL empacotado.
- Corrigir `--phase`, `--serial`, `n_questions` e o caminho de `--dry-run`.
- Reauditar o contrato de subcomandos da CLI após os ajustes.

## Resultado

**FAIL**

Resumo:
- a implementação estava tecnicamente verde
- porém havia divergências funcionais e de contrato suficientes para reprovar a auditoria
  do ciclo B
