# M4_TAREFA-409_B — Auditoria Gate E2E decisão executiva

**Data**: 2026-06-02
**Milestone**: M4 — Decisão executiva da Rodada 1
**Épico**: E9
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / L

## Objetivo
Auditar a implementação da TAREFA-409A contra `docs/m4_tarefa_409.md`, validar o gate E2E de M4 e verificar a documentação de fechamento do milestone.

## Arquivos Inspecionados
- `tests/e2e/test_full_pipeline_m4.py`
- `tests/fixtures/e2e_m4_aggregates.json`
- `tests/fixtures/e2e_m4_stats_report.json`
- `tests/fixtures/e2e_m4_annotation.jsonl`
- `CHANGELOG.md`
- `README.md`
- `.github/workflows/ci.yml`
- `docs/adr/ADR-013-round2-funnel.md`

## Achados
### 1. Bloqueador — E2E não usa os fixtures declarados no prompt
- **Arquivo**: `tests/e2e/test_full_pipeline_m4.py:90-224`, `tests/e2e/test_full_pipeline_m4.py:293-303`
- **Problema**: o prompt A exigiu fixtures determinísticas em `tests/fixtures/e2e_m4_aggregates.json`, `tests/fixtures/e2e_m4_stats_report.json` e `tests/fixtures/e2e_m4_annotation.jsonl`. O teste implementado reconstrói todos os dados inline por constantes e builders, e a ingestão monta um JSONL novo a partir do export em vez de consumir a fixture `e2e_m4_annotation.jsonl`.
- **Impacto**: os artefatos entregues existem, mas não participam do gate. Isso quebra a rastreabilidade e elimina a garantia de que o E2E valida exatamente os dados de referência declarados pelo milestone.

### 2. Bloqueador — Gate E2E não cobre `respx.mock` nem backend Qdrant/testcontainers exigidos
- **Arquivo**: `tests/e2e/test_full_pipeline_m4.py:22-30`, `tests/e2e/test_full_pipeline_m4.py:232-456`
- **Problema**: o prompt A fixou `respx.mock` para todo HTTP e Qdrant via `testcontainers.qdrant` com 5 chunks de fixture. O teste não importa `respx`, não usa `testcontainers`, não lê `QDRANT_URL` e não exercita nenhum fluxo real de retrieval/rede; o pipeline começa escrevendo `EvaluationResult` direto em `ParquetStorage`.
- **Impacto**: o job `e2e` em CI sobe `qdrant/qdrant:v1.9`, mas o teste não consome esse serviço. Na prática, o gate não valida a integração que o prompt pediu para a etapa fim-a-fim.

### 3. Importante — `CHANGELOG` ficou desatualizado em relação ao estado final declarado
- **Arquivo**: `CHANGELOG.md:53-56`
- **Problema**: a seção de fechamento de M4 registra `1068 testes` e `90.88%` de cobertura total. O estado final já aprovado em M4-408D era `1068 passed, 5 skipped` com `90.97%`.
- **Impacto**: a documentação de fechamento do milestone fica inconsistente com o último gate aprovado e perde valor como referência histórica.

## Validação (DoD)
### Parte A — Teste E2E
- Etapa 1 presente e asserta `critical_failure_flag is None`, `n_ingested > 0`, `n_invalid == 0`.
- Etapa 2 presente e asserta `len(aggregates) == 6`, `best_config is not None`, `n_nan_excluded >= 1` e ordenação.
- Etapa 3 presente e asserta criação do JSON e os 3 campos de síntese.
- Etapa 4 presente e asserta exatamente 6 SVGs com `st_size > 0` e XML válido.
- Etapa 5 presente e asserta `st_size > 30_000`, 5 section IDs, 6 SVGs base64, ausência de `http` e HTML parseável.
- CLI smoke presente para `analyze`, `report`, `status`, `show-config`, `annotate`.
- `status --run-id inexistente` asserta `exit_code == 0` e mensagem amigável.

### Parte B — Documentação
- `README.md` marca M4 como ✅ e inclui `analyze` / `report`.
- `ADR-013` está no arquivo correto e contém `Context`, `Decision`, `Consequences` e `top_n=3`.
- `.github/workflows/ci.yml` adiciona job `e2e` com `needs: [unit, integration]`, service `qdrant/qdrant:v1.9` e `timeout-minutes: 10`.
- `CHANGELOG.md` documenta os deltas de contrato de M4, mas está com números finais desatualizados.

## Comandos Executados
```bash
grep -i "http" tests/fixtures/e2e_m4_stats_report.json
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src
uv run lint-imports
UV_CACHE_DIR=/tmp/uv-cache E2E_ENABLED=1 uv run pytest -m e2e tests/e2e/test_full_pipeline_m4.py -v --tb=short
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m "unit or integration" --cov=src --cov-fail-under=85
```

## Resultados dos Gates
- `ruff check .` → `All checks passed!`
- `mypy --strict src` → `Success: no issues found in 50 source files`
- `lint-imports` → `4 kept, 0 broken`
- `pytest -m e2e tests/e2e/test_full_pipeline_m4.py -v --tb=short` → `1 passed in 2.98s`
- `pytest -m "unit or integration" --cov=src --cov-fail-under=85` → `528 passed, 10 skipped, 570 deselected`, mas **falhou** cobertura com total `66.56%`

## Evidências pedidas no Prompt B
### Grep do item 5d
```text
<sem saída>
```

### Cinco subcomandos do item 6
- `analyze`
- `report`
- `status`
- `show-config`
- `annotate`

### Últimas linhas do E2E
```text
============================= test session starts ==============================
platform linux -- Python 3.13.13, pytest-9.0.3, pluggy-1.6.0 -- /prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/.venv/bin/python
codspeed: 5.0.3 (disabled, mode: walltime, callgraph: enabled, timer_resolution: 1.0ns)
cachedir: .pytest_cache
hypothesis profile 'default'
Using --randomly-seed=2580505696
benchmark: 5.2.3 (defaults: timer=time.perf_counter disable_gc=False min_rounds=5 min_time=0.000005 max_time=1.0 calibration_precision=10 warmup=False warmup_iterations=100000)
rootdir: /prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval
configfile: pyproject.toml
plugins: mock-3.15.1, xdist-3.8.0, cov-7.1.0, recording-0.13.4, asyncio-1.3.0, respx-0.23.1, syrupy-5.2.0, hypothesis-6.152.9, randomly-4.1.0, socket-0.8.0, langsmith-0.8.6, codspeed-5.0.3, Faker-40.19.1, anyio-4.13.0, benchmark-5.2.3
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 1 item

tests/e2e/test_full_pipeline_m4.py::test_full_pipeline_m4 PASSED         [100%]

============================== 1 passed in 2.98s ===============================
```

### Resumo do comando `pytest -m "unit or integration" --cov=src --cov-fail-under=85`
```text
ERROR: Coverage failure: total of 67 is less than fail-under=85
...
TOTAL                                                                            3584   1105    602     47    67%
FAIL Required test coverage of 85% not reached. Total coverage: 66.56%
========= 528 passed, 10 skipped, 570 deselected, 3 warnings in 25.25s =========
```

## Critérios de Aceitação
- **FAIL** nesta iteração.
- O teste cobre as 5 etapas pedidas, mas não atende duas restrições explícitas do prompt A: uso das fixtures entregues e uso de `respx.mock` + backend Qdrant/testcontainers no gate E2E.

## Observações para Próximas Tarefas
- Na recodificação, o ideal é alinhar o E2E ao padrão já usado em `tests/integration/test_m1_pipeline_integration.py`: backend Qdrant real com fixture de chunks e interceptação de HTTP no nível exigido pelo projeto.
- Após corrigir o E2E, atualizar `CHANGELOG.md` com os números finais reais do fechamento de M4.
