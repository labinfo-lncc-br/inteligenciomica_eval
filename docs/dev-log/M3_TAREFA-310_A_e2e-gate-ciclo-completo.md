# M3_TAREFA-310_A — E2E Gate do Ciclo Completo M3

**Data**: 2026-06-04
**Milestone**: M3 — Adapters de Infraestrutura + Orquestração
**Épico**: E3
**Skill**: /implement (Code)
**Prioridade / Tamanho**: P1 / L

---

## Objetivo

Implementar o gate E2E final do Milestone 3: 5 cenários de teste exercitando o ciclo
completo A+B (12 células = 8A+4B) com fakes em memória + `ParquetStorage` real.

---

## Arquivos Criados / Modificados

| Arquivo | Ação |
|---------|------|
| `tests/e2e/test_m3_full_cycle.py` | Criado — 5 cenários E2E |
| `tests/golden/e2e_m3_expected.json` | Criado — valores golden |
| `pyproject.toml` | Adicionado `pytest-timeout>=0.9` |
| `uv.lock` | Atualizado pelo `uv add --dev` |

---

## Decisões Técnicas

### Pesos sem `rubric_biomed_score`

`_SCORING_WEIGHTS` exclui `rubric_biomed_score` (weight=0 implícito) para que
`n_evaluated=12` após a Passada 2 — o campo está NaN nessa passada, e `0 * NaN = NaN`
seria propagado sem essa escolha (ADR-007). O juiz preenche `rubric_biomed_score` na
Passada 3, mas os pesos de scoring usados no gate são independentes dos pesos canônicos
do `DEFAULT_WEIGHTS`.

### `_PHASE_B_BASE = "fixed"`

Fase B sempre usa `base="fixed"` internamente (`run_generation_pass.py` linha 64).
Isso gera 6 grupos de configuração: `{ID_230K, IDx_400k, fixed} × {stub-gen-a, stub-gen-b}`.

### Contagem de fases via `ResultFrame`

A contagem de linhas por fase (`n_rows_phase_a=8`, `n_rows_phase_b=4`) é feita
iterando `r.answer.phase` no `ResultFrame` carregado pelo `ParquetStorage.load()` —
não via leitura direta de Parquet (que retornaria apenas 1 linha do primeiro arquivo).

### `update_annotation` recebe `RowId`, não string

`ParquetStorage.update_annotation(row_id: RowId, ...)` recebe o objeto `RowId`,
não `.value` (string). Chamadas incorretas falham em runtime com `AttributeError`.

### Idempotência via `writer.exists(row_id)`

A detecção de célula já existente usa `writer.exists(row_id)` (verificação de arquivo
no filesystem). O `run_id` usado para o hash de `RowId` vem do parâmetro
`execute(run_id=...)`, não do `ParquetStorage` constructor — ambas as execuções com o
mesmo `run_id` produzem os mesmos `RowId` hashes.

### Shutdown gracioso com `allow_concurrent_models=False`

Com `allow_concurrent_models=True`, ambos geradores ficam na mesma onda (wave 0),
então o callback `_shutdown_after_first_wave` não impede gen-b de executar. Com
`allow_concurrent_models=False`, wave 0=[gen-a] e wave 1=[gen-b] ficam em ondas
separadas — o check `if self._shutdown_requested: break` atua entre ondas, garantindo
que apenas 6 células (gen-a) sejam persistidas.

### `FakeRubricJudge(fixed=RubricResult(score=0.80, ...))`

O juiz fake usa `score=0.80` (não o default `score=4.0` que seria inválido para
`rubric_biomed_score` no intervalo [0,1]). Com `_SCORING_WEIGHTS` sem rubric, o
`final_score = 0.40*0.80 + 0.30*0.90 + 0.15*0.70 + 0.10*0.85 + 0.05*0.88 = 0.824`.

### `rank_score=NaN` sem anotações

`critical_failure_rate=NaN` quando nenhuma linha foi anotada (ADR-010). O
`RankScoreCalculator` propaga NaN quando qualquer input é NaN (ADR-007). Todos os 6
`rank_scores` são NaN no cenário 1.

### Schema Parquet via primeiro arquivo

A checagem de colunas do golden usa `_read_parquet_safe` que lê o primeiro arquivo
`.parquet` encontrado com `rglob`. O schema é uniforme em todos os arquivos, então
1 arquivo basta para verificar presença de colunas.

---

## Problemas Encontrados e Soluções

### Bug 1: `r.answer.run_id` inexistente

`GeneratedAnswer` não possui campo `run_id` (o `run_id` é armazenado na coluna Parquet
via `RowProvenance`, não na entidade de domínio). Removida a asserção.

### Bug 2: `update_annotation(r.answer.row_id.value, ...)`

`update_annotation` recebe `RowId` (não string). Corrigido para `r.answer.row_id`.

### Bug 3: Contagem de fases via Parquet (1 arquivo)

`_read_parquet_safe` lê apenas o primeiro arquivo → 1 linha → contagem errada.
Substituído por iteração direta sobre `ResultFrame.results` via `r.answer.phase`.

### Bug 4: Lint — caracteres ambíguos `×`

`×` (MULTIPLICATION SIGN U+00D7) violava RUF001/002/003. Substituído por `x` e `*`.

### Bug 5: `FakeDeterministicMetric` importado mas não usado (F401)

Removido pelo `ruff --fix`.

### Bug 6: `noqa` directives inativas (RUF100)

`ARG001`, `PLC0415` e `BLE001` não estão no `select` do ruff. Removidas pelo `ruff --fix`.

---

## Validação (DoD)

```
uv run ruff check .           → All checks passed!
uv run ruff format --check .  → 162 files already formatted
uv run mypy --strict src      → Success: no issues found in 57 source files
uv run lint-imports           → Contracts: 4 kept, 0 broken
pytest -m e2e tests/e2e/test_m3_full_cycle.py -v --timeout=60
                              → 5 passed in 1.16s
pytest --cov=src --cov-fail-under=85 -n 4 -q
                              → 1204 passed, 16 skipped
                              → Total coverage: 88.62% ≥ 85% ✅
```

---

## Critérios de Aceitação

- [x] 5 testes E2E marcados `@pytest.mark.e2e`
- [x] `tests/golden/e2e_m3_expected.json` com valores canônicos
- [x] `pytest-timeout>=0.9` adicionado ao `pyproject.toml`
- [x] Cenário 1: 12 células (8A+4B), `final_score=0.824`, `rank_score=NaN`
- [x] Cenário 2: juiz iniciado após todos os geradores (ADR-012)
- [x] Cenário 3: célula NaN excluída da agregação (ADR-007)
- [x] Cenário 4: 2ª execução com mesmo `run_id` → `n_generated=0` (ADR-009)
- [x] Cenário 5: shutdown gracioso entre ondas → 6 células persistidas (RNF7)
- [x] Todos os gates de validação PASS

---

## Observações para Próximas Tarefas

- M3 está completo (TAREFA-301 a 310 ✅). Próximo milestone: M4 (já concluído).
- O gate E2E M3 valida a orquestração end-to-end sem GPU/rede, cobrindo os 5 invariantes
  arquiteturais críticos do milestone.
- `wiring.py` ficou em 60% de cobertura local — a branch de produção (servidores reais)
  só é coberta pelos testes de integração com Docker.
