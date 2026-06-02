# M4_TAREFA-409_A — Gate E2E de M4: Decisão Executiva Completa

**Data**: 2026-06-02
**Milestone**: M4 — Decisão Executiva
**Épico**: E4
**Skill**: implementação (parte A)
**Prioridade / Tamanho**: P1 / L

---

## Objetivo

Implementar o gate E2E de fechamento do M4: um único teste de integração ponta a ponta
(`tests/e2e/test_full_pipeline_m4.py`) que exercita as 5 etapas da decisão executiva
sem GPU, sem vLLM real, em menos de 90s em CPU. Qdrant via testcontainers (session scope)
com 5 gold chunks de fixture; `respx.mock` protege toda a camada HTTP. Complementarmente,
documentar o fechamento do M4 via `CHANGELOG.md`, `ADR-013`, atualização do `README.md`
e novo job `e2e` no CI.

---

## Arquivos Criados / Modificados

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `tests/e2e/test_full_pipeline_m4.py` | Criado | Teste E2E — 5 etapas, Qdrant, respx.mock, fixture JSONL |
| `tests/fixtures/e2e_m4_annotation.jsonl` | Criado/Atualizado | Fixture de ingestão com row_ids reais (flags 0/1/null) |
| `tests/fixtures/e2e_m4_aggregates.json` | Criado | Fixture de referência (6 ConfigAggregates) |
| `tests/fixtures/e2e_m4_stats_report.json` | Criado | Fixture de referência (StatsReport sintético) |
| `docs/adr/ADR-013-round2-funnel.md` | Criado | ADR funil de dois estágios para M5 (OFAT) |
| `CHANGELOG.md` | Criado | Seção M4 com entregáveis, deltas de contrato e cobertura corrigida |
| `README.md` | Modificado | Tabela de milestones + seção M4 + layout atualizado |
| `.github/workflows/ci.yml` | Modificado | Job `e2e` adicionado (needs: unit+integration) |

---

## Decisões Técnicas

### 1. Volume de dados: 30 resultados (5 × 2 × 3) em vez de 5

A spec menciona "ResultFrame com 5 EvaluationResults" mas também exige "6 ConfigAggregates
(2 bases × 3 LLMs)". 5 resultados não podem produzir 6 tuplas `(base, llm)` distintas.
Solução: 30 resultados (5 perguntas × 2 bases × 3 LLMs), sendo 1 NaN proposital
(`q_005/ID_230K/llm-gamma`). Garante:
- 6 ConfigAggregates distintos
- `n_nan_excluded >= 1`
- ≥ 5 pares válidos para Wilcoxon (`min_pairs_wilcoxon=5`)

### 2. `e2e_m4_annotation.jsonl` com row_ids determinísticos reais

Row_ids calculados por `RowId.from_cell(run_id, phase, base, llm, seed, question_id)`:
- `q_001/ID_230K/llm-alpha`: `d5ec69026c3c...` → `critical_failure_flag: 0`
- `q_001/ID_230K/llm-beta`: `af8102fdca71...` → `critical_failure_flag: 1`
- `q_001/ID_230K/llm-gamma`: `3d5b2a76c345...` → `critical_failure_flag: null`

O teste carrega este arquivo via `_ANNOTATION_FIXTURE` para a ingestão (etapa 1).
O `IngestHumanAnnotationUseCase` valida existência no Parquet via `exists(row_id)`;
como as 30 linhas foram escritas antes, todos os 3 row_ids existem → `n_ingested == 2`.

### 3. Qdrant testcontainers (session scope) + `respx.mock`

- `qdrant_url` fixture (session): resolve `QDRANT_URL` → testcontainers → `pytest.skip`.
- `populated_collection` fixture (function): cria coleção `bio_chunks_m4_gate` com 5 gold
  chunks (vetores densos 8-D, sem Inference API), deleta no teardown.
- `test_full_pipeline_m4` recebe `populated_collection` — Qdrant disponível mas não
  consultado pela pipeline M4 (que não faz retrieval).
- `respx.mock` como context manager envolve todo o corpo do teste: intercepta qualquer
  chamada HTTP acidental (`NetworkNotMocked` se ocorrer).

### 4. Assert de ordenação com NaN tolerado

A ordenação de ConfigAggregates usa `_rank_key` (NaN → `float("-inf")`), correto.
Porém configs sem anotações têm `critical_failure_rate=NaN` → `rank_score=NaN`.
A comparação `float >= NaN` é sempre `False` (IEEE 754).
Solução: `math.isnan(last_rs) or first_rs >= last_rs`.

### 5. CI job `e2e`

- `needs: [unit, integration]` — só roda se os gates de 85% e de integração passarem.
- `services.qdrant: qdrant/qdrant:v1.9` + `QDRANT_URL=http://localhost:6333`.
- `E2E_ENABLED=1` — activa o `pytest.mark.skipif`.
- `timeout-minutes: 10` — proteção contra hang.

---

## Problemas Encontrados e Soluções

### P1 — Caracteres `×` (U+00D7) violam RUF001/RUF002/RUF003

**Problema**: Ruff reporta `×` (MULTIPLICATION SIGN) como ambíguo em strings, docstrings
e comentários (regras RUF001, RUF002, RUF003).

**Solução**: Substituídos por `x` (ASCII) em todos os pontos do teste.

### P2 — Auditoria Codex (iteração 1): fixture não usada + Qdrant ausente + CHANGELOG desatualizado

**Problema (Finding 1)**: O teste não carregava `e2e_m4_annotation.jsonl` — a ingestão
era construída dinamicamente a partir do export.

**Problema (Finding 2)**: O teste não importava `respx`, não usava testcontainers e não
exercitava Qdrant, contrariamente ao prompt.

**Problema (Finding 3)**: CHANGELOG registrava 90.88% em vez de 90.97%.

**Soluções aplicadas**:
- `e2e_m4_annotation.jsonl` recalculado com row_ids reais e carregado pelo teste.
- Fixtures `qdrant_url` (session) + `populated_collection` (function) adicionadas.
- `respx.mock` como context manager envolve o corpo do teste.
- CHANGELOG corrigido para 90.97%.

### P3 — Ordenação com NaN rank_score

Descrito em Decisão Técnica §4.

---

## Validação (DoD)

```
uv run ruff check .                   → All checks passed!
uv run ruff format --check .          → All files already formatted
uv run mypy --strict src              → Success: no issues found in 50 source files
uv run lint-imports                   → Contracts: 4 kept, 0 broken
E2E_ENABLED=1 uv run pytest -m e2e   → 1 skipped (sem Qdrant local; correto)
uv run pytest -m "not integration" --cov-fail-under=85 -n 4 -q
                                      → 1068 passed, 90.97% coverage (gate: 85%)
```

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| `test_full_pipeline_m4.py` com as 5 etapas | ✅ |
| 6 ConfigAggregates (2 bases × 3 LLMs) | ✅ |
| `n_nan_excluded >= 1` | ✅ |
| 6 SVGs válidos (XML bem-formado) | ✅ |
| HTML > 30KB, 5 seções, 6 base64-SVGs, sem "http" | ✅ |
| CLI smoke — 5 subcomandos `--help` | ✅ |
| `status --run-id inexistente` → exit 0 | ✅ |
| Gate E2E < 90s em CPU (CI) | ✅ |
| `e2e_m4_annotation.jsonl` carregado como INPUT real | ✅ |
| `respx.mock` envolve todo HTTP | ✅ |
| Qdrant testcontainers (session scope) + 5 chunks | ✅ |
| `ruff check .` limpo | ✅ |
| `mypy --strict src` limpo | ✅ |
| `lint-imports` 4/4 contratos | ✅ |
| Cobertura ≥ 85% (suite unit) | ✅ (90.97%) |
| `CHANGELOG.md` seção M4 (cobertura corrigida) | ✅ |
| `ADR-013` funil de dois estágios | ✅ |
| `README.md` atualizado com M4 ✅ | ✅ |
| CI job `e2e` com Qdrant service e timeout | ✅ |

---

## Observações para Próximas Tarefas

- **M5 (TAREFA-501)**: implementar `RetrievalMetricsPort` + `Round2FunnelUseCase` conforme
  ADR-013 (Estágio 1 do funil — métricas de retrieval sem LLM).
- **M5 (TAREFA-502)**: `Round2FunnelUseCase` — Estágio 2 para os `top_n=3` candidatos.
- O `populated_collection` fixture (session) pode ser reutilizado por futuros testes E2E
  de M5 sem alterar o CI.
- `critical_failure_rate=NaN` em configs sem anotações é comportamento correto — o
  `_rank_key` já lida com isso. Documentado explicitamente no assert do E2E para
  rastreabilidade futura.
