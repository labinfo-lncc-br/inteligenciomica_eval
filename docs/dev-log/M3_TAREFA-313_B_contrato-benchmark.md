# M3_TAREFA-313_B — Auditoria do Contrato de Benchmark

**Data**: 2026-06-07
**Auditoria**: ChatGPT Codex
**Milestone**: M3 — Orquestração das 4 GPUs
**Escopo**: diff da TAREFA-313 (commit `6d2c5ab`) + relatório A + reprodução independente dos gates

---

## Veredito

**PASS**

O contrato de benchmark foi reconciliado no código para o M5 futuro. Não encontrei
bugs, regressões comportamentais ou lacunas de teste que invalidem a entrega.

---

## Achados

| Achado | Arquivo:símbolo | Gravidade |
|--------|------------------|-----------|
| Nenhum achado bloqueador ou importante identificado na auditoria | — | — |

---

## Evidências auditadas

### 1. `RoundConfig.questions` deixou de ser campo morto

- O wiring agora lê explicitamente `config.questions` quando a env override não está
  definida, resolvendo o caminho relativo ao diretório do YAML:
  [`wiring.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:635),
  [`wiring.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:639),
  [`wiring.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:640).
- O teste de regressão prova que `benchmark_loader()` devolve exatamente as perguntas
  do arquivo apontado por `questions`:
  [`test_wiring_questions.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/test_wiring_questions.py:149).

### 2. Precedência e resolução de path estão corretas

- Precedência implementada no wiring:
  `BENCHMARK_QUESTIONS_PATH` > `config.questions` > default empacotado
  [`wiring.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:631).
- Testes cobrindo:
  - `config.questions` carrega arquivo conhecido:
    [`test_wiring_questions.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/test_wiring_questions.py:149)
  - env vence sobre `config.questions`:
    [`test_wiring_questions.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/test_wiring_questions.py:172)
  - default empacotado quando nenhum definido:
    [`test_wiring_questions.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/test_wiring_questions.py:207)
  - resolução relativa ao YAML, não ao `cwd`:
    [`test_wiring_questions.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/test_wiring_questions.py:225)

### 3. `cli._run_dry_run` replica o mesmo contrato

- O fallback do `--dry-run` passou a usar a mesma precedência e resolve
  `cfg.questions` contra `config.parent`:
  [`cli.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/cli.py:427),
  [`cli.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/cli.py:433),
  [`cli.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/cli.py:434).
- O teste de regressão força o fallback por `ImportError` e valida
  `"Perguntas carregadas: 9"`:
  [`test_wiring_questions.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/test_wiring_questions.py:267).

### 4. Registry dual-mode está consistente

- As 6 entradas do registry possuem `endpoint_env`:
  [`model_registry.yaml`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/config/model_registry.yaml:71),
  [`model_registry.yaml`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/config/model_registry.yaml:83),
  [`model_registry.yaml`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/config/model_registry.yaml:95),
  [`model_registry.yaml`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/config/model_registry.yaml:107),
  [`model_registry.yaml`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/config/model_registry.yaml:119),
  [`model_registry.yaml`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/config/model_registry.yaml:137).
- O contrato de `endpoint_env` continua opcional no schema de infra, logo `managed`
  não é quebrado:
  [`model_registry.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/config/model_registry.py:60).
- Reproduzi a suíte de `wiring_external`, que permaneceu verde.

### 5. Não há vazamento de path/endpoint no novo log

- O novo helper mascara paths como `<...>/arquivo.ext`:
  [`wiring.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:300).
- O log `wiring_questions_source` usa esse helper e não grava layout bruto de disco:
  [`wiring.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:646).

### 6. O campo não foi removido

- `RoundConfig.questions` permanece no schema e agora está documentado como caminho
  canônico com override por env:
  [`schema.py`](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/config/schema.py:144).

---

## Reprodução dos gates

Executado nesta auditoria:

```text
ruff check .                                   → All checks passed!
ruff format --check .                          → 171 files already formatted
uv run mypy --strict src/                      → Success: no issues found in 60 source files
uv run lint-imports                            → 4 kept, 0 broken
uv run pytest tests/unit/infrastructure/test_wiring_questions.py -q
                                              → 5 passed
uv run pytest tests/unit/infrastructure/test_wiring_external.py -q
                                              → 9 passed
uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4 -q
                                              → 1257 passed, 6 skipped, 20 warnings
                                                Total coverage: 89.60%
```

---

## Riscos residuais

- O código desta tarefa está coerente, mas a documentação operacional ainda descreve o
  contrato antigo de benchmark em alguns pontos. Isso já está explicitamente endereçado
  pela TAREFA-315 e não bloqueia o merge da TAREFA-313.

---

## Conclusão

`RoundConfig.questions` foi ligado de fato, a semântica de resolução relativa ao YAML foi
restaurada, o `--dry-run` ficou consistente com o wiring real, e o registry passou a ser
compatível com `server_mode=external` sem edição manual. Para o escopo desta tarefa, o
contrato de benchmark está reconciliado.
