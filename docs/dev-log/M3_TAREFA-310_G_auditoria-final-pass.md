# M3_TAREFA-310_G — Auditoria final do ciclo F

**Data:** 2026-06-04  
**Tarefa:** TAREFA-310 — E2E gate M3  
**Escopo auditado:** correções do ciclo F + robustez dos testes E2E  
**Resultado:** **PASS**

## Verificação dos achados anteriores

### 1. Fixture via `round_config.questions` — resolvido

O `RoundConfig` agora expõe `questions: str | None = None`, a fixture `round_config`
preenche esse campo com o path real do `questions_rf1.jsonl`, e `questions_stub`
passa a carregar as 2 primeiras perguntas por `load_questions(Path(round_config.questions))[:2]`.

**Evidências:**
- [schema.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/config/schema.py:143)
- [test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:370)
- [test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:405)

### 2. Remoção do acesso a atributo privado do storage — resolvido

O schema check não depende mais de `storage._base_dir`. O teste usa `tmp_path / "data"`
como diretório explícito da fixture `tmp_storage`, eliminando o acoplamento ao atributo
privado do adapter.

**Evidências:**
- [test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:412)
- [test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:470)

### 3. Golden de rank score no cenário NaN — resolvido

O golden agora inclui `rank_scores_nan_scenario` com valores explícitos (`0.6245`) e o
cenário ADR-007 confronta `agg.rank_score.value` contra esse golden por `{base, llm}`.

**Evidências:**
- [e2e_m3_expected.json](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/golden/e2e_m3_expected.json:35)
- [test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:644)

## Robustez observada

- O cenário principal continua cobrindo 12 células (8A + 4B), roundtrip, schema e contagem por fase.
- ADR-012 continua coberto por sequência observável de `start/wait_healthy/stop`.
- ADR-007 agora valida tanto exclusão de NaN quanto rank score recomputado após anotação.
- ADR-009 e RNF7 permanecem verdes.

## Validação executada

```text
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m e2e tests/e2e/test_m3_full_cycle.py -v --timeout=30
→ 5 passed in 0.82s

UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
→ All checks passed!

UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src
→ Success: no issues found in 57 source files

UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports
→ Contracts: 4 kept, 0 broken.

UV_CACHE_DIR=/tmp/uv-cache uv run pytest --cov=src --cov-fail-under=85 -q
→ 1204 passed, 16 skipped, 10 warnings in 36.72s
→ Required test coverage of 85% reached. Total coverage: 88.63%
```

## Nota residual

O novo campo `RoundConfig.questions` foi introduzido corretamente e está exercitado no
gate E2E. Nesta auditoria eu não tratei como exigência adicional que `build_container` /
`build_fake_container` passem a consumi-lo, porque isso não era um critério aberto do
Prompt B da TAREFA-310 nesta etapa.

## Recomendação

`Approve`
