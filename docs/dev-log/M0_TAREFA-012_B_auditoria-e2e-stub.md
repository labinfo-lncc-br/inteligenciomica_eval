# M0_TAREFA-012_B — Auditoria do E2E stub: rodada mínima em CPU

**Data**: 2026-05-24
**Milestone**: M0 — Esqueleto e Validação Local
**Épico**: E0
**Skill**: code-reviewer + test-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Auditar o diff da TAREFA-012 contra:

- §3.4 e §14.3 de `docs/arquitetura_detalhada_validacao_inteligenciomica.md`
- ADR-009 (resumabilidade/idempotência) e ADR-007 (NaN explícito + exclusão na agregação), ambos materializados no documento de arquitetura
- skill `test-engineer` no escopo de E2E

---

## Arquivos Auditados

| Arquivo | Papel |
|---------|------|
| `tests/e2e/test_min_round_stub.py` | Teste E2E principal |
| `tests/e2e/_harness.py` | Harness da rodada mínima |
| `tests/golden/e2e_min_round_expected.json` | Golden do cenário |
| `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py` | Storage real Parquet / schema §5.3 |
| `src/inteligenciomica_eval/domain/services/final_score.py` | Fórmula do `final_score` |
| `src/inteligenciomica_eval/domain/services/aggregation.py` | Agregação + `n_excluded_nan` + `rank_score` |
| `src/inteligenciomica_eval/domain/services/rank_score.py` | Fórmula do `rank_score` |
| `tests/fakes/generation.py` | Fake do gerador |
| `tests/fakes/retrieval.py` | Fake do retriever |
| `tests/fakes/metrics.py` | Fakes de métricas / NaN |

---

## Resultado Geral

**FAIL**

O PR atende 7 dos 8 critérios pedidos, mas **não espelha o fluxo do §3.4**: o harness calcula métricas e `final_score` **antes** da persistência, e usa apenas `append`, sem passagem separada de `update_metrics`.

---

## Divergências

| Critério | Arquivo:linha | Gravidade |
|---------|---------------|-----------|
| Fluxo não espelha §3.4 (`retrieve → generate → persist → metrics → final_score → aggregate → rank`) | `tests/e2e/_harness.py:3-5`, `tests/e2e/_harness.py:174-229`, `docs/arquitetura_detalhada_validacao_inteligenciomica.md:193-211`, `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:438-490` | Alta |

---

## Verificação Item a Item

### 1. Usa `ParquetStorage` real em `tmp_path` e valida schema §5.3?

**PASS**

- Fixture `storage` instancia `ParquetStorage(tmp_path / "results", ...)`: `tests/e2e/test_min_round_stub.py:103-120`.
- O teste lê de volta via `storage.load(...)`: `tests/e2e/test_min_round_stub.py:225-228`, `:262-294`.
- O schema real está materializado em `EVAL_SCHEMA`: `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:42-87`.

### 2. Fluxo espelha §3.4?

**FAIL**

- O §3.4 exige: persistir linha parcial no passo 3c e só depois uma passada separada de métricas via `update`: `docs/arquitetura_detalhada_validacao_inteligenciomica.md:199-207`.
- O harness implementa `retrieve -> generate -> score -> persist -> aggregate`: `tests/e2e/_harness.py:3-5`.
- Na prática, ele calcula métricas, computa `final_score` e só então faz `storage.append(result)`: `tests/e2e/_harness.py:174-221`.
- Não há chamada a `ParquetStorage.update_metrics(...)`, embora o adapter exista: `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:438-490`.

### 3. Há uma resposta com métrica NaN, excluída da agregação e contada em `n_excluded_nan`?

**PASS**

- A célula NaN está fixada no cenário: `tests/e2e/test_min_round_stub.py:67-77`.
- O harness injeta `FakeMetricSuite(inject_nan=True)` e `FakeRubricJudge(inject_nan=True)` nessa célula: `tests/e2e/_harness.py:181-190`.
- O teste prova `n_excluded_nan == 1` e `n_observations == 1`: `tests/e2e/test_min_round_stub.py:347-388`.
- A agregação realmente exclui `FinalScore` NaN dos cálculos numéricos e contabiliza exclusões: `src/inteligenciomica_eval/domain/services/aggregation.py:183-246`.

### 4. Idempotência: segunda execução com mesmo `run_id` não duplica linhas?

**PASS**

- O harness consulta `storage.exists(row_id)` e pula a célula existente: `tests/e2e/_harness.py:125-136`.
- O teste de idempotência verifica zero chamadas ao gerador na segunda execução, zero novas linhas e cardinalidade estável no Parquet: `tests/e2e/test_min_round_stub.py:396-465`.
- O storage persiste por arquivo `{row_id}.parquet` e documenta a resumabilidade por `row_id`: `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:330-335`, `:492-513`.

### 5. `final_score` e `rank_score` conferem com golden calculado à mão?

**PASS**

- Fórmula canônica de `final_score`: `src/inteligenciomica_eval/domain/services/final_score.py:20-29`, `:79-100`.
- Fórmula canônica de `rank_score`: `src/inteligenciomica_eval/domain/services/rank_score.py:22-27`, `:109-143`.
- Golden declarado em `tests/golden/e2e_min_round_expected.json:8-47`.
- Testes cobrem o `final_score` por célula e os agregados com `rank_score`: `tests/e2e/test_min_round_stub.py:301-339`, `:472-534`.

Recomputação manual de uma célula normal:

```text
final_score
= 0.45*0.80
+ 0.20*0.90
+ 0.15*0.80
+ 0.10*0.70
+ 0.05*0.85
+ 0.05*0.88
= 0.8165
```

Confronto com o golden:

- Esperado no golden: `0.8165` — `tests/golden/e2e_min_round_expected.json:8-18`
- Produzido pelo teste: `pytest.approx(_NORMAL_FINAL_SCORE)` — `tests/e2e/test_min_round_stub.py:337-339`

Para `llm-alpha`, o `rank_score` também fecha:

```text
0.50*0.8165 + 0.20*(1-0.0) + 0.15*0.75 - 0.15*0.0 = 0.72075
```

Golden: `0.72075` em `tests/golden/e2e_min_round_expected.json:20-33`.

### 6. Roundtrip Parquet reconstrói os `EvaluationResult`?

**PASS**

- `storage.load(...)` retorna `EvaluationResult` via `from_row(...)`: `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:239-295`, `:523-558`.
- O teste confronta identidade, `generated_answer`, `final_score` (incluindo NaN) e `critical_failure_flag`: `tests/e2e/test_min_round_stub.py:239-294`.

### 7. Determinístico, sem rede/GPU?

**PASS**

- O teste instancia apenas `StubRetriever`, `FakeGenerator`, `FakeMetricSuite`, `FakeRubricJudge` e `FakeDeterministicMetric`: `tests/e2e/test_min_round_stub.py:123-157`.
- O harness recebe esses tipos concretos e não instancia adapters reais: `tests/e2e/_harness.py:53-71`.
- Os fakes são todos in-memory e sem I/O: `tests/fakes/retrieval.py:13-49`, `tests/fakes/generation.py:31-97`, `tests/fakes/metrics.py:38-125`.
- O teste estrutural confirma os tipos usados: `tests/e2e/test_min_round_stub.py:542-572`.

### 8. Roda sob `pytest -m e2e` em CPU, rápido? `import-linter`?

**PASS**

Resumo das execuções auditadas:

```text
$ uv run pytest -m e2e
7 passed, 533 deselected in 0.84s

$ uv run lint-imports
Contracts: 4 kept, 0 broken.
```

Isso atende o DoD transversal de execução rápida em CPU e contratos de importação preservados: `docs/arquitetura_detalhada_validacao_inteligenciomica.md:907-917`, `:939`.

---

## Validação (DoD)

Executado nesta auditoria:

```bash
uv run pytest -m e2e
uv run lint-imports
```

Resultados:

- `pytest -m e2e`: **7 passed**, **0.84s**
- `lint-imports`: **4 contracts kept**, **0 broken**

Não executei `ruff`, `format`, `mypy` nem a suíte completa porque o prompt de verificação pediu explicitamente apenas `pytest -m e2e` e `lint-imports`.

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| Usa `ParquetStorage` real em `tmp_path` | ✅ |
| Fluxo espelha §3.4 | ❌ |
| Célula NaN excluída e contada em `n_excluded_nan` | ✅ |
| Idempotência com mesmo `run_id` comprovada | ✅ |
| `final_score` / `rank_score` batem com golden manual | ✅ |
| Roundtrip Parquet reconstrói `EvaluationResult` | ✅ |
| Determinístico, sem rede/GPU | ✅ |
| `pytest -m e2e` e `lint-imports` verdes | ✅ |

---

## Observações para Próximas Tarefas

- Se a intenção é provar aderência literal ao §3.4, o E2E precisa exercitar o desacoplamento geração/persistência parcial/julgamento separado, usando `append` seguido de `update_metrics`.
- Se a intenção era apenas provar scoring e storage em CPU com stubs, o teste atual faz isso bem; o problema é de aderência arquitetural, não de corretude numérica.
