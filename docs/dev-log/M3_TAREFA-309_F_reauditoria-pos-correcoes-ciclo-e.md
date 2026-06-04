# M3_TAREFA-309_F — Reauditoria pós-correções do ciclo E

**Data**: 2026-06-03
**Milestone**: M3 — Orquestração end-to-end
**Épico**: E3
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Reauditar as correções do ciclo E da TAREFA-309, focando nos 3 pontos declarados:
- dry-run sem `PYTHONPATH=tests`
- `--phase` no dry-run
- barras de progresso com avanço numérico

## Arquivos Criados / Modificados

- `docs/dev-log/M3_TAREFA-309_F_reauditoria-pos-correcoes-ciclo-e.md`

## Decisões Técnicas

- A reauditoria foi baseada em leitura direta do `cli.py` e execução de smoke tests.
- Também rodei a suíte reduzida de testes unitários ligados ao `run`, `dry-run` e wiring,
  porque o ciclo E alterou exatamente essas áreas.

## Problemas Encontrados e Soluções

### 1. Parcialmente corrigido — dry-run sem `PYTHONPATH` não exibe mais stacktrace

**Arquivo**: `src/inteligenciomica_eval/cli.py:263-293`

O fallback com `try/except ImportError` funciona:
- sem `PYTHONPATH=tests`, o comando não quebra
- há apenas log `debug`
- o usuário vê a saída normal do dry-run

Esse ponto específico ficou corrigido.

### 2. Corrigido — `--phase` passou a afetar o dry-run textual

**Arquivo**: `src/inteligenciomica_eval/cli.py:300-317`

Com `--dry-run --phase A`, a saída agora mostra:

```text
phases       : ['A']
```

e deixa de imprimir a contagem da fase B.

### 3. FAIL — o conjunto reduzido de testes ainda falha por fragilidade em `wiring`

**Arquivo**: `tests/unit/infrastructure/test_wiring.py:64-65`

Rodando:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/unit/infrastructure/test_wiring.py -vv
```

há falha em:

```text
TestBuildFakeContainer::test_constructs_without_error
assert isinstance(container, DIContainer)
```

O teste isolado passa, mas a suíte do arquivo falha após `importlib.reload()` feito em
`TestNoFakesAtModuleLevel`, caracterizando acoplamento por ordem/reload no módulo
`infrastructure.wiring`.

### 4. IMPORTANTE — totais das barras do `run` ainda não refletem corretamente as fases

**Arquivo**: `src/inteligenciomica_eval/cli.py:166-183`

Os contadores agora avançam, mas os totais foram calculados como:

```python
len(questions) * len(cfg.seeds) * len(cfg.bases) * len(cfg.llms)
```

Isso ignora:
- `--phase B` (onde a base é fixa e não deve multiplicar por `len(cfg.bases)`)
- `both` (onde o total correto inclui A + B, não apenas A)

Logo, o avanço é numérico, mas o denominador ainda pode ficar errado.

## Validação (DoD)

### Comandos executados

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/unit/cli/test_run_real.py tests/unit/cli/test_dry_run.py tests/unit/infrastructure/test_wiring.py tests/unit/infrastructure/test_benchmark_loader.py
UV_CACHE_DIR=/tmp/uv-cache uv run ielm-eval run --config config/experiment_round1.yaml --run-id test --dry-run
PYTHONPATH=tests UV_CACHE_DIR=/tmp/uv-cache uv run ielm-eval run --config config/experiment_round1.yaml --run-id test --dry-run --phase A
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/unit/infrastructure/test_wiring.py -vv
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/unit/infrastructure/test_wiring.py::TestBuildFakeContainer::test_constructs_without_error -vv
```

### Resultados observados

- dry-run sem `PYTHONPATH` ✅
- dry-run com `--phase A` ✅
- teste isolado de `build_fake_container` ✅
- suíte completa de `test_wiring.py` ❌ `1 failed, 12 passed`

## Critérios de Aceitação

| Critério | Evidência | Status |
|---|---|---|
| Dry-run sem `PYTHONPATH=tests` não mostra stacktrace | smoke | ✅ |
| `--phase` afeta o dry-run | smoke com `--phase A` | ✅ |
| Barras de progresso têm avanço numérico | `progress.advance(...)` presente | ✅ |
| Suíte reduzida ligada ao wiring/CLI permanece estável | `test_wiring.py` | ❌ |
| Totais das barras respeitam as fases selecionadas | cálculo em `cli.py` | ❌ |

## Observações para Próximas Tarefas

- Corrigir a fragilidade de identidade de `DIContainer` após `reload()` no módulo de wiring.
- Ajustar os totais de progresso do `run` para refletirem corretamente `A`, `B` e `both`.

## Resultado

**FAIL**

Resumo:
- duas das três correções declaradas no ciclo E ficaram evidentes nos smokes
- ainda restam uma fragilidade concreta na suíte de wiring e um erro no cálculo dos
  totais das barras de progresso
