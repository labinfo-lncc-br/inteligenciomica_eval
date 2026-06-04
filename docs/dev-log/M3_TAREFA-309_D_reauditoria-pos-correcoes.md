# M3_TAREFA-309_D — Reauditoria pós-correções do DI Wiring, CLI `run` e BenchmarkLoader

**Data**: 2026-06-03
**Milestone**: M3 — Orquestração end-to-end
**Épico**: E3
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Reauditar a TAREFA-309 após as correções declaradas pelo desenvolvedor no ciclo B,
com foco estrito nos achados aceitos para retrabalho:
- `--serial` na execução real
- `--phase` na execução real
- `n_questions` do `WaveSchedulerService`
- dry-run via `build_fake_container`
- 3 barras/tarefas de progresso no `run`

## Arquivos Criados / Modificados

- `docs/dev-log/M3_TAREFA-309_D_reauditoria-pos-correcoes.md`

## Decisões Técnicas

- Esta reauditoria desconsidera os itens explicitamente rejeitados pelo desenvolvedor como
  fora do Prompt A e verifica apenas o delta de correções do ciclo B.
- O parecer foi emitido com base em leitura de código e smoke tests do CLI.

## Problemas Encontrados e Soluções

### 1. FAIL — `--dry-run` agora depende de `PYTHONPATH=tests`

**Arquivos**:
- `src/inteligenciomica_eval/cli.py:120-125`
- `src/inteligenciomica_eval/cli.py:247-249`
- `src/inteligenciomica_eval/infrastructure/wiring.py:498-505`

O dry-run passou a chamar `build_fake_container(cfg)`, que faz `from fakes import ...`.
Sem `PYTHONPATH=tests`, o comando real falha com:

```text
ModuleNotFoundError: No module named 'fakes'
```

Isso introduz dependência de ambiente de teste no caminho normal do CLI e ainda exibe
stacktrace Rich ao usuário.

### 2. IMPORTANTE — `--phase` segue ignorado no `--dry-run`

**Arquivo**: `src/inteligenciomica_eval/cli.py:240-329`

Embora `--phase` tenha sido conectado na execução real, `_run_dry_run()` não recebe a
flag nem filtra `cfg.phases`. Em smoke test com `--dry-run --phase A`, a saída continuou
mostrando:

```text
phases       : ['A', 'B']
```

e calculando células das duas fases.

### 3. IMPORTANTE — as “3 barras” ainda são indeterminadas

**Arquivo**: `src/inteligenciomica_eval/cli.py:163-199`

Foram criadas 3 tasks no `Progress`, mas todas com `total=None` e sem avanço numérico.
Na prática, o usuário recebe 3 descrições com barra/spinner indeterminado, não o progresso
quantificado exigido para:
- ondas concluídas/total
- células geradas/total
- células avaliadas/total

## Validação (DoD)

### Comandos executados

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/unit/cli/test_run_real.py tests/unit/cli/test_dry_run.py tests/unit/infrastructure/test_wiring.py tests/unit/infrastructure/test_benchmark_loader.py
UV_CACHE_DIR=/tmp/uv-cache uv run ielm-eval run --config config/experiment_round1.yaml --run-id test --dry-run
PYTHONPATH=tests UV_CACHE_DIR=/tmp/uv-cache uv run ielm-eval run --config config/experiment_round1.yaml --run-id test --dry-run --phase A
```

### Resultado dos testes executados

- `pytest -q tests/unit/cli/test_run_real.py tests/unit/cli/test_dry_run.py tests/unit/infrastructure/test_wiring.py tests/unit/infrastructure/test_benchmark_loader.py` ✅ `53 passed`

### Evidências observadas

Sem `PYTHONPATH=tests`:

```text
ModuleNotFoundError: No module named 'fakes'
```

Com `PYTHONPATH=tests`:

```text
2026-06-03 ... wiring_fake_container_built round_id=round-1
Perguntas carregadas: 2
```

Com `--dry-run --phase A`:

```text
phases       : ['A', 'B']
Phase A ...
Phase B ...
```

## Critérios de Aceitação

| Critério | Evidência | Status |
|---|---|---|
| `--serial` controla a execução real | `build_container(..., serial=serial)` + `allow_concurrent_models=not serial` | ✅ |
| `--phase` controla a execução real | `build_container(..., phases=...)` + `_ExperimentConfig(phases=...)` | ✅ |
| `n_questions` do scheduler usa benchmark carregado | `WaveSchedulerService(n_questions=len(_loaded_questions))` | ✅ |
| `--dry-run` usa `build_fake_container` | `_run_dry_run()` | ✅ |
| `--dry-run` funciona como CLI normal, sem dependência de ambiente de teste | smoke sem `PYTHONPATH=tests` | ❌ |
| `--phase` afeta o plano exibido no `--dry-run` | smoke com `--phase A` | ❌ |
| Progresso mostra contadores reais nas 3 barras | `Progress` tasks sem `total` | ❌ |

## Observações para Próximas Tarefas

- Remover a dependência de `tests/fakes` do caminho normal de dry-run, ou capturar a falha
  com mensagem amigável sem stacktrace.
- Propagar `--phase` também para o planejamento do dry-run.
- Se o requisito de UX continuar valendo, converter as 3 tasks para progresso quantitativo
  real, com totais calculados previamente.

## Resultado

**FAIL**

Resumo:
- as correções de `--serial`, `--phase` na execução real e `n_questions` foram aplicadas
- o caminho de `--dry-run` regrediu em robustez e ainda há lacunas objetivas no contrato
  de `--phase` e no progresso exibido
