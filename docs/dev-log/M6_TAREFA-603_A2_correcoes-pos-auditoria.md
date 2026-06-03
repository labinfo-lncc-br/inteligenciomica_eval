# M6_TAREFA-603_A2 — Correções pós-auditoria Codex (ciclo B → A2)

**Data**: 2026-06-03
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: test-engineer
**Ciclo**: Correção após achados do Prompt B

---

## Achados do Codex e correções aplicadas

### Achado 1 — BLOQUEADOR: Target 3 não exercitava `config_hash()` real

**Localização:** `tests/unit/infrastructure/config/test_config_hash_property.py:31`

**Problema:** Os 4 testes do Target 3 testavam apenas `_canonical_dict_hash` (helper
local), nunca chamando a função de produção `config_hash(RoundConfig)`.  Um drift
na serialização de `RoundConfig.model_dump(mode="json")` passaria invisível.

**Correção:** Adicionados 4 novos testes de **nível 1** que chamam `config_hash()`
diretamente com instâncias reais de `RoundConfig`:

| Teste novo | Propriedade |
|-----------|------------|
| `test_config_hash_stability` | P3.1r — mesma instância → mesmo hash (200 exemplos) |
| `test_config_hash_sensitivity_round_id` | P3.2r — round_id diferente → hash diferente |
| `test_config_hash_sensitivity_seeds` | P3.2r — seeds diferentes → hash diferente |
| `test_config_hash_cross_instance_consistency` | P3.3r — dados idênticos, instâncias distintas → mesmo hash |

**Estratégia:** `_round_config_strategy` via `st.builds(_make_round_config, ...)` com
campos variáveis: `round_id` (texto Unicode), `temperature` (float ≥ 0), `seeds`
(lista de ints não-negativos), `llms` (regex `[a-z][a-z0-9-]+`), `bases`
(subconjunto de `{"IDx_400k", "ID_230K"}`).  `batch_invariant=True` e pesos de scoring
fixos (`0.5 + 0.5 = 1.0`) para satisfazer os validators do Pydantic.

Os 4 testes de nível 2 (`_canonical_dict_hash`) foram mantidos — servem de
regressão se o algoritmo interno mudar e verificam casos impossíveis via RoundConfig.

**Arquivo:** `tests/unit/infrastructure/config/test_config_hash_property.py`
— 8 testes no total (4 sobre a função real + 4 sobre o algoritmo).

---

### Achado 2 — AVISO: `_result_eq` omitia campos persistidos no Parquet

**Localização:** `tests/unit/infrastructure/adapters/test_parquet_roundtrip_property.py:99`

**Problema:** A comparação original ignorava:
- `retrieved_chunk_ids` (tuple de strings)
- `retrieved_chunks_text` (tuple de strings)
- `retrieval_scores` (tuple de floats — armazenados como `list_(float32)`)
- `critical_failure_flag` (int | None — int8 NULL)
- `critical_failure_note` (str | None)

Uma regressão nessas colunas do EVAL_SCHEMA passaria invisível.

**Correção:** `_result_eq` expandido para incluir todos os campos:
```python
ans_ok = (
    ...
    and oa.retrieved_chunk_ids == la.retrieved_chunk_ids
    and oa.retrieved_chunks_text == la.retrieved_chunks_text
    and tuple(oa.retrieval_scores) == tuple(la.retrieval_scores)
)
annotation_ok = (
    original.critical_failure_flag == loaded.critical_failure_flag
    and original.critical_failure_note == loaded.critical_failure_note
)
return ans_ok and metrics_ok and score_ok and regime_ok and annotation_ok
```

**Precisão de retrieval_scores:** já era `(0.5,)` fixo na estratégia (valor float32-exato),
portanto comparação exata é válida.

**critical_failure_flag / critical_failure_note:** produzidos como `None` pelo factory
(não-anotado); roundtrip via int8 NULL / string NULL → `None` confirmado.

---

## Validação pós-correções

```
pytest -m property -v
→ 19 passed in 15.19 s   (+ 4 testes novos do Target 3)

pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4
→ 1135 passed, 6 skipped — 90.43%  ✓

ruff check .              → All checks passed
mypy --strict src/        → Success: no issues found in 54 source files
lint-imports              → 4 kept, 0 broken
```

**Nenhuma propriedade falsificada pelo hypothesis.**
