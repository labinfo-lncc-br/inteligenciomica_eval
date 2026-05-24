# M0_TAREFA-012_C — Reauditoria do E2E stub após correções

**Data**: 2026-05-24
**Milestone**: M0 — Esqueleto e Validação Local
**Épico**: E0
**Skill**: code-reviewer + test-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Reverificar o prompt B da TAREFA-012 após as correções reportadas pelo desenvolvedor,
confirmando o comportamento em código e em execução (`pytest -m e2e` e
`lint-imports`).

---

## Resultado Geral

**PASS**

Nenhuma divergência bloqueadora permaneceu nos 8 critérios auditados.

---

## Divergências

Nenhuma.

---

## Verificação Item a Item

### 1. O E2E usa `ParquetStorage` REAL (em `tmp_path`) em pelo menos um caminho?

**PASS**

- Fixture `storage` instancia `ParquetStorage(tmp_path / "results", ...)`:
  `tests/e2e/test_min_round_stub.py:103-120`.
- Os testes materializam e relêem Parquet via `storage.load(...)`:
  `tests/e2e/test_min_round_stub.py:225-228`, `:262-294`.
- O schema §5.3 continua sendo o real de `EVAL_SCHEMA`:
  `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:42-87`.

### 2. O fluxo espelha §3.4 (`retrieve→generate→persist→metrics→final_score→aggregate→rank`)?

**PASS**

- O harness foi corrigido para fluxo em duas passadas:
  - geração: `retrieve → generate → append(partial row)`:
    `tests/e2e/_harness.py:157-213`
  - julgamento: `load pending → score → update_metrics → append(complete)`:
    `tests/e2e/_harness.py:214-287`
  - agregação/ranking ao final:
    `tests/e2e/_harness.py:288-295`
- Isso agora espelha o §3.4:
  `docs/arquitetura_detalhada_validacao_inteligenciomica.md:193-211`.
- O caminho real de `update_metrics` do adapter é efetivamente exercitado:
  `tests/e2e/_harness.py:270-272`,
  `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:438-490`.

### 3. Há UMA resposta com métrica NaN, e o teste prova que ela é EXCLUÍDA da agregação e contada em `n_excluded_nan`?

**PASS**

- A célula NaN é única e explícita:
  `tests/e2e/test_min_round_stub.py:67-77`.
- O harness injeta NaN nessa célula:
  `tests/e2e/_harness.py:236-267`.
- O teste prova `n_excluded_nan == 1` e `n_observations == 1`:
  `tests/e2e/test_min_round_stub.py:347-388`.
- A exclusão de `FinalScore` NaN é responsabilidade real da agregação:
  `src/inteligenciomica_eval/domain/services/aggregation.py:183-246`.

### 4. Idempotência: 2ª execução com mesmo `run_id` NÃO duplica linhas — testado?

**PASS**

- A geração continua protegida por `storage.exists(row_id)`:
  `tests/e2e/_harness.py:165-176`.
- O teste de idempotência prova:
  - zero chamadas ao gerador na segunda execução:
    `tests/e2e/test_min_round_stub.py:452-455`
  - cardinalidade do Parquet inalterada:
    `tests/e2e/test_min_round_stub.py:457-461`
  - ausência de duplicação de linhas mesmo com reprocessamento idempotente da célula NaN:
    `tests/e2e/test_min_round_stub.py:463-468`
- A semântica last-write-wins do storage permanece consistente com ADR-009:
  `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:397-436`.

### 5. `final_score` / `rank_score` conferem com golden calculado à mão?

**PASS**

- `final_score` usa os pesos canônicos:
  `src/inteligenciomica_eval/domain/services/final_score.py:22-29`, `:79-100`.
- `rank_score` usa os pesos canônicos:
  `src/inteligenciomica_eval/domain/services/rank_score.py:22-27`, `:109-143`.
- O golden permanece:
  `tests/golden/e2e_min_round_expected.json:8-47`.
- Os testes confrontam:
  - `final_score` por célula:
    `tests/e2e/test_min_round_stub.py:301-339`
  - agregados e `rank_score`:
    `tests/e2e/test_min_round_stub.py:476-538`

Recompute manual de uma célula normal:

```text
0.45*0.80 + 0.20*0.90 + 0.15*0.80 + 0.10*0.70 + 0.05*0.85 + 0.05*0.88
= 0.8165
```

Confronto com o golden:

- `normal_final_score = 0.8165`:
  `tests/golden/e2e_min_round_expected.json:8-18`

### 6. Roundtrip Parquet (ler de volta) reconstrói os `EvaluationResult`?

**PASS**

- O roundtrip via `from_row(...)` continua sendo o caminho real do adapter:
  `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:239-295`,
  `:523-558`.
- O teste verifica identidade, `generated_answer`, `final_score` e
  `critical_failure_flag`:
  `tests/e2e/test_min_round_stub.py:239-294`.

### 7. Determinístico, SEM rede/GPU?

**PASS**

- Apenas tipos fake/stub são instanciados nas fixtures:
  `tests/e2e/test_min_round_stub.py:123-157`.
- O harness recebe esses adapters prontos; não instancia clients reais:
  `tests/e2e/_harness.py:79-98`.
- Os fakes são in-memory:
  `tests/fakes/retrieval.py:13-49`,
  `tests/fakes/generation.py:31-97`,
  `tests/fakes/metrics.py:38-125`.
- O teste estrutural confirma isso:
  `tests/e2e/test_min_round_stub.py:546-576`.

### 8. Roda sob `pytest -m e2e` em CPU, rápido? DoD §14.2; `import-linter`?

**PASS**

Resumo auditado nesta execução:

```text
$ uv run pytest -m e2e
7 passed, 533 deselected in 0.99s

$ uv run lint-imports
Contracts: 4 kept, 0 broken.
```

Isso é compatível com o DoD transversal:
`docs/arquitetura_detalhada_validacao_inteligenciomica.md:907-917`.

---

## Validação (DoD)

Executado nesta reauditoria:

```bash
uv run pytest -m e2e
uv run lint-imports
```

Resultados:

- `pytest -m e2e`: **7 passed**, **0.99s**
- `lint-imports`: **4 contracts kept**, **0 broken**

---

## Observações

- O único bloqueador do parecer anterior era a violação do fluxo §3.4. Esse ponto foi corrigido.
- Risco residual não bloqueador: células que permanecem com `final_score = NaN` são
  reprocessadas na segunda passada em execuções subsequentes, mas o teste demonstra
  que isso continua idempotente e sem duplicação de linhas:
  `tests/e2e/_harness.py:119-123`, `tests/e2e/test_min_round_stub.py:463-468`.
