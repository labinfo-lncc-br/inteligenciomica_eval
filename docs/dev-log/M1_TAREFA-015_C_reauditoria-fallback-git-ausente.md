# M1_TAREFA-015_C - Reauditoria do fallback quando git esta ausente

**Data**: 2026-05-27
**Milestone**: M1 - Adapters de Infraestrutura
**Tarefa**: TAREFA-015 - `PromptRegistry`
**Prompt**: B - reauditoria apos correcao
**Commit avaliado**: `f818bb2`
**Resultado**: PASS

---

## Objetivo

Reavaliar a correcao do bloqueador apontado em
`M1_TAREFA-015_B_auditoria-prompt-registry.md`: `PromptRegistry._capture_version()`
falhava com `FileNotFoundError` quando o binario `git` nao existia no ambiente, impedindo
os fallbacks para `PROMPT_VERSION` e `"unversioned"`.

---

## Avaliacao da Correcao

O commit `f818bb2` resolve o bloqueador.

Em `src/inteligenciomica_eval/infrastructure/prompts/registry.py:55-64`, a chamada a
`subprocess.run(["git", "describe", "--tags", "--dirty"], ...)` agora fica dentro de
`try/except OSError`. Como `FileNotFoundError` e subclasse de `OSError`, ambientes sem
`git` seguem corretamente para a cascata:

1. `git describe --tags --dirty`
2. `PROMPT_VERSION`
3. `"unversioned"` com warning estruturado

Os testes novos em
`tests/unit/infrastructure/prompts/test_prompt_registry.py:256-279` cobrem os dois
cenarios que faltavam:

- `FileNotFoundError` sem `PROMPT_VERSION` -> `"unversioned"`
- `FileNotFoundError` com `PROMPT_VERSION` -> valor da env var

---

## Verificacao dos Criterios

| Criterio | Arquivo:linha | Resultado |
|---|---:|---|
| Fallback quando `git` retorna erro | `test_prompt_registry.py:226-253` | PASS |
| Fallback quando `git` nao esta instalado | `test_prompt_registry.py:256-279` | PASS |
| Tratamento de `FileNotFoundError`/`OSError` no registry | `registry.py:55-64` | PASS |
| Warning quando resultado final e `"unversioned"` | `registry.py:70-74`; reproduzido manualmente | PASS |
| Gates da TAREFA-015 | comandos abaixo | PASS |

Divergencias bloqueadoras: nenhuma.

---

## Comandos Executados

```bash
git show --stat --oneline f818bb2
```

Resultado: commit encontrado; alterou `registry.py`,
`tests/unit/infrastructure/prompts/test_prompt_registry.py` e incluiu o dev-log B.

```bash
uv --cache-dir /tmp/uv-cache run pytest tests/unit/infrastructure/prompts/test_prompt_registry.py -v
```

Resultado: `19 passed in 0.17s`.

```bash
uv --cache-dir /tmp/uv-cache run python -c "from unittest.mock import patch; from inteligenciomica_eval.infrastructure.prompts.registry import PromptRegistry; import os; os.environ['PROMPT_VERSION']='v-env'; p=patch('inteligenciomica_eval.infrastructure.prompts.registry.subprocess.run', side_effect=FileNotFoundError('git missing')); p.start(); print(PromptRegistry().prompt_version); p.stop()"
```

Resultado: `v-env`.

```bash
uv --cache-dir /tmp/uv-cache run python -c "from unittest.mock import patch; from inteligenciomica_eval.infrastructure.prompts.registry import PromptRegistry; import os; os.environ.pop('PROMPT_VERSION', None); p=patch('inteligenciomica_eval.infrastructure.prompts.registry.subprocess.run', side_effect=FileNotFoundError('git missing')); p.start(); print(PromptRegistry().prompt_version); p.stop()"
```

Resultado: warning estruturado `prompt_version_unversioned` e retorno `unversioned`.

```bash
uv --cache-dir /tmp/uv-cache run mypy --strict src
```

Resultado: `Success: no issues found in 25 source files`.

```bash
uv --cache-dir /tmp/uv-cache run lint-imports
```

Resultado: `4 contracts kept, 0 broken`.

```bash
uv --cache-dir /tmp/uv-cache run ruff check src/inteligenciomica_eval/infrastructure/prompts tests/unit/infrastructure/prompts
uv --cache-dir /tmp/uv-cache run ruff format --check src/inteligenciomica_eval/infrastructure/prompts tests/unit/infrastructure/prompts
```

Resultado: `All checks passed`; `4 files already formatted`.

```bash
timeout 180s uv --cache-dir /tmp/uv-cache run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -q -n auto
```

Resultado: `599 passed, 7 skipped in 10.92s`; cobertura total `96.49%`.

---

## Conclusao

PASS.

O bloqueador da auditoria B foi corrigido e testado. A TAREFA-015 pode seguir no DAG para
a TAREFA-016.
