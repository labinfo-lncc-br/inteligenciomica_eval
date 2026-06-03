# M6_TAREFA-603_C — Property-based Tests em Parsers e Serializers

**Data**: 2026-06-03
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: test-engineer
**Prioridade / Tamanho**: P1 / S

---

## Objetivo

Corrigir os dois achados reportados pelo Codex no relatório `M6_TAREFA-603_B`:

- **Bloqueador (B.1):** Target 3 testava apenas um helper local `_canonical_dict_hash`,
  nunca chamando a função de produção `config_hash(RoundConfig)`.
- **Aviso (B.2):** `_result_eq` no Target 4 omitia campos persistidos pelo Parquet
  (`retrieved_chunk_ids`, `retrieved_chunks_text`, `retrieval_scores`,
  `critical_failure_flag`, `critical_failure_note`).

---

## Arquivos Criados / Modificados

| Arquivo | Ação |
|---------|------|
| `tests/unit/infrastructure/config/test_config_hash_property.py` | Modificado — 4 testes novos sobre `config_hash(RoundConfig)` real (nível 1) |
| `tests/unit/infrastructure/adapters/test_parquet_roundtrip_property.py` | Modificado — `_result_eq` expandido para cobrir todos os campos do EVAL_SCHEMA |
| `docs/dev-log/M6_TAREFA-603_C_correcoes-pos-auditoria-codex.md` | Este arquivo |

---

## Decisões Técnicas

### B.1 — Target 3: dois níveis de cobertura

O arquivo passou a ter **dois níveis** de testes, separados e complementares:

**Nível 1 — função de produção `config_hash(RoundConfig)`** (4 testes novos):

| Teste | Propriedade | max_examples |
|-------|------------|-------------|
| `test_config_hash_stability` | P3.1r — mesma instância → mesmo hash | 200 |
| `test_config_hash_sensitivity_round_id` | P3.2r — `round_id` diferente → hash diferente | 200 |
| `test_config_hash_sensitivity_seeds` | P3.2r — lista de seeds diferente → hash diferente | 200 |
| `test_config_hash_cross_instance_consistency` | P3.3r — dados idênticos, objetos distintos → mesmo hash | 200 |

Estratégia `_round_config_strategy` via `st.builds(_make_round_config, ...)` com
campos variáveis: `round_id` (texto Unicode), `temperature` (float ≥ 0), `seeds`
(lista de ints não-negativos), `llms` (regex `[a-z][a-z0-9-]+`), `bases` (subconjunto
de `{"IDx_400k", "ID_230K"}`).  Os campos com validators restritos (`batch_invariant=True`,
pesos de scoring que somam 1.0, `endpoint_env` como env-var name) permanecem fixos no
factory `_make_round_config` para garantir validade de todos os exemplos gerados.

**Nível 2 — algoritmo canônico via `_canonical_dict_hash`** (4 testes mantidos):

Os testes originais foram preservados; o docstring agora deixa explícito que servem
de *regressão* — se `config_hash` mudar a serialização, o helper deve ser atualizado.
Eles cobrem casos impossíveis de expressar em `RoundConfig` válidos (e.g., chaves
com caracteres arbitrários) e verificam as propriedades matemáticas do `sort_keys`.

### B.2 — Target 4: cobertura completa de `_result_eq`

`_result_eq` reescrito para comparar **todos** os campos serializados no `EVAL_SCHEMA`:

```python
ans_ok = (
    ...
    and oa.retrieved_chunk_ids == la.retrieved_chunk_ids       # list_(string) → exato
    and oa.retrieved_chunks_text == la.retrieved_chunks_text   # list_(string) → exato
    and tuple(oa.retrieval_scores) == tuple(la.retrieval_scores)  # list_(float32)-seguro
)
annotation_ok = (
    original.critical_failure_flag == loaded.critical_failure_flag  # int8 NULL → None
    and original.critical_failure_note == loaded.critical_failure_note  # string NULL → None
)
return ans_ok and metrics_ok and score_ok and regime_ok and annotation_ok
```

**Por que a comparação exata funciona:**
- `retrieval_scores=(0.5,)` é fixo na estratégia — valor com representação float32 exata.
- `critical_failure_flag=None` e `critical_failure_note=None` (factory padrão) →
  int8 NULL e string NULL no Parquet → Python `None` no roundtrip.

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| `ruff E741` — variável `l` considerada ambígua em `o, l = original.answer, loaded.answer` | Renomeado para `oa, la` |
| `ruff RUF005` — `list(cfg.seeds) + [extra_seed]` preferível como desempacotamento | Alterado para `[*list(cfg.seeds), extra_seed]` |
| `_round_config_strategy` com `st.builds` recusava kwargs não-nomeados para parâmetros `**overrides` | Estratégia usa `st.builds(_make_round_config, round_id=..., temperature=..., ...)` passando apenas os campos variáveis como kwargs nomeados |

---

## Validação (DoD)

### Testes property após correções

```
uv run pytest -m property -v
→ 19 passed in 15.19 s
   (15 originais + 4 novos de nível 1 para config_hash real)
```

### Gate de cobertura (não integration)

```
uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4 -q
→ 1135 passed, 6 skipped — 90.43%  (gate 85% ✓)
```

### Linters

```
ruff check .          → All checks passed
ruff format --check . → (sem reformatações necessárias após ruff format)
mypy --strict src/    → Success: no issues found in 54 source files
lint-imports          → 4 kept, 0 broken
```

---

## Critérios de Aceitação (atualizado pós-ciclo C)

| Critério | Status |
|----------|--------|
| Marcadores `property` e `security` em `pyproject.toml` | ✅ |
| 4 arquivos de teste, um por target | ✅ |
| **Target 3: `config_hash()` real chamado diretamente** | ✅ (ciclo C) |
| Target 3: propriedades estabilidade, sensibilidade, canonicidade | ✅ |
| **Target 4: `_result_eq` cobre todos os campos do EVAL_SCHEMA** | ✅ (ciclo C) |
| Nenhum hypothesis falsifica as propriedades | ✅ |
| Testes property em < 60 s | ✅ (15.19 s) |
| `ruff`, `mypy --strict`, `import-linter` verdes | ✅ |
| Zero alterações em código de produção | ✅ |

---

## Observações para Próximas Tarefas

- O arquivo `M6_TAREFA-603_A2_correcoes-pos-auditoria.md` foi criado durante o ciclo de
  correção com nome não-canônico; este relatório (`_C_`) é o registro oficial do ciclo.
- A estratégia `_round_config_strategy` pode ser reutilizada em testes futuros que
  precisem de `RoundConfig` arbitrários (e.g., testes de `collect_provenance`).
- `critical_failure_flag` e `critical_failure_note` são testados apenas com valores
  `None` (padrão do factory).  Um ciclo futuro pode variar esses campos para cobrir
  os ramos de `update_annotation` no Parquet (linhas 544-573, ainda descobertas).
