# M1_TAREFA-015_B - Auditoria do PromptRegistry

**Data**: 2026-05-27
**Milestone**: M1 - Adapters de Infraestrutura
**Tarefa**: TAREFA-015 - `PromptRegistry`
**Prompt**: B - verificacao
**Papel**: code-reviewer + rag-engineer
**Resultado**: FAIL

---

## Objetivo

Auditar o commit `d9c3432` da TAREFA-015 contra o Prompt B: templates Jinja2 versionados
em `infrastructure/prompts`, rubrica biomédica completa, saída JSON para a TAREFA-016,
few-shot sem PII, `prompt_version` com fallback, singleton com `functools.cache`, testes
e gates (`mypy --strict`, `lint-imports`, `ruff`).

Nao foram feitas alteracoes no codigo de producao. Este arquivo registra apenas a
auditoria.

---

## Resumo Executivo

O `PromptRegistry`, os templates e os testes estao bem alinhados com a especificacao na
maior parte dos criterios. Os 6 criterios biomédicos estao presentes no template, a saida
JSON e solicitada explicitamente, os testes unitarios passam e os gates de qualidade
passam localmente.

Ainda assim, a auditoria e **FAIL** por uma falha no criterio 5: o fallback de
`prompt_version` nao funciona quando o executavel `git` esta ausente de fato. Nesse caso,
`subprocess.run(...)` levanta `FileNotFoundError` antes de o codigo consultar
`PROMPT_VERSION` ou retornar `"unversioned"`.

Esse caso importa porque o proprio requisito pede fallback quando `git` nao estiver
disponivel ou quando o ambiente nao tiver historico Git completo.

---

## Seis Criterios Biomédicos

Referencia esperada: `docs/visao_alto_nivel_validacao_inteligenciomica.md:190-203`.

| Criterio esperado | Evidencia no template | Status |
|---|---:|---|
| Correcao factual contra a resposta humana | `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric.j2:9-11` | Presente |
| Completude | `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric.j2:13-14` | Presente |
| Contradicoes | `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric.j2:16-18` | Presente |
| Alucinacao | `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric.j2:20-22` | Presente |
| Ressalvas omitidas | `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric.j2:24-27` | Presente |
| Pertinencia biomédica | `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric.j2:29-31` | Presente |

Faltantes: nenhum.

---

## Tabela de Verificacao

| Criterio | Arquivo:linha | Gravidade | Resultado |
|---|---:|---|---|
| 1. Templates `.j2` em `infrastructure/prompts`; sem prompt inline da rubrica em `.py` | `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric.j2:1`; `src/inteligenciomica_eval/infrastructure/prompts/ragas_system.j2:1`; loader em `registry.py:34-41` | - | PASS |
| 2. `biomed_rubric.j2` cobre os 6 criterios e placeholders corretos | criterios em `biomed_rubric.j2:9-31`; `question` em `64`; `ground_truth` em `67`; loop de contextos em `70-72`; `generated_answer` em `74` | - | PASS |
| 3. Template solicita JSON com `score` e `feedback` | `biomed_rubric.j2:33-39`, `76-77` | - | PASS |
| 4. Few-shot bom e fraco, sem PII | exemplo `score 1.0` em `biomed_rubric.j2:43-50`; exemplo `score 0.2` em `52-59` | - | PASS |
| 5. `prompt_version` usa `git describe --tags --dirty` com fallback para env var e depois `"unversioned"` | chamada em `registry.py:51-55`; fallback em `59-67` | Bloqueadora | FAIL: `FileNotFoundError` em `subprocess.run` impede fallback quando `git` nao existe |
| 6. `get_default_registry()` usa `functools.cache`, sem variavel global mutavel | `registry.py:106-116` | - | PASS |
| 7. Testes mockam subprocess, verificam 6 criterios e JSON | mock em `test_prompt_registry.py:227-253`; criterios em `106-181`; JSON em `189-212` | Importante | PASS parcial: cobre retorno non-zero, mas nao cobre excecao de `subprocess.run` |
| 8. `mypy --strict`, `lint-imports`, `ruff` | comandos abaixo | - | PASS |

---

## Divergencias

| Criterio | Arquivo:linha | Gravidade | Detalhe |
|---|---:|---|---|
| Fallback de `prompt_version` incompleto quando `git` esta indisponivel | `src/inteligenciomica_eval/infrastructure/prompts/registry.py:51-67` | Bloqueadora | Se `subprocess.run(["git", ...])` levanta `FileNotFoundError`, a instanciação do `PromptRegistry` falha antes de consultar `PROMPT_VERSION` ou retornar `"unversioned"`. |
| Teste nao cobre excecao de `subprocess.run` | `tests/unit/infrastructure/prompts/test_prompt_registry.py:227-253` | Importante | Os testes simulam `returncode=128`, mas nao simulam `FileNotFoundError`/`OSError`. Isso deixou passar a falha acima. |

Correcao esperada: envolver a chamada a `subprocess.run` em `try/except OSError` (e
opcionalmente `subprocess.SubprocessError`) antes da cascata de fallback, preservando a
ordem `git describe` -> `PROMPT_VERSION` -> `"unversioned"` e mantendo o warning quando
o resultado final for `"unversioned"`.

---

## Comandos Executados

```bash
git show --stat --oneline d9c3432
```

Resultado: commit encontrado com alteracoes em `registry.py`, `biomed_rubric.j2`,
`ragas_system.j2`, testes, `pyproject.toml`, `uv.lock` e dev-log A.

```bash
uv --cache-dir /tmp/uv-cache run pytest tests/unit/infrastructure/prompts/test_prompt_registry.py -v
```

Resultado: `17 passed in 0.15s`.

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

Resultado: `597 passed, 7 skipped in 10.92s`; cobertura total `96.48%`.

```bash
uv --cache-dir /tmp/uv-cache run python -c "from unittest.mock import patch; from inteligenciomica_eval.infrastructure.prompts.registry import PromptRegistry; import os; os.environ['PROMPT_VERSION']='v-env'; p=patch('inteligenciomica_eval.infrastructure.prompts.registry.subprocess.run', side_effect=FileNotFoundError('git missing')); p.start(); print(PromptRegistry().prompt_version); p.stop()"
```

Resultado: falhou com `FileNotFoundError: git missing`, demonstrando que o fallback para
`PROMPT_VERSION` nao e executado quando o binario `git` esta ausente.

```bash
uv --cache-dir /tmp/uv-cache build --wheel --out-dir /tmp/inteligenciomica-eval-build
```

Resultado: falhou por DNS ao tentar baixar `hatchling` de `pypi.org`. Como o ambiente de
auditoria esta sem rede e este build nao faz parte do Prompt B, o resultado nao foi usado
para o veredito.

---

## Conclusao

FAIL.

Todos os criterios de template, testes e gates passam. O bloqueio e restrito ao fallback
de `prompt_version`: a implementacao precisa tratar excecao de `subprocess.run` para
cumprir a promessa `git describe` -> env var -> `"unversioned"` em ambientes sem `git`.
