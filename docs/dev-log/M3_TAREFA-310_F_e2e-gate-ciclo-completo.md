# M3_TAREFA-310_F — E2E Gate do Ciclo Completo M3 (ciclo E→F)

**Data**: 2026-06-04
**Milestone**: M3 — Orquestração das 4 GPUs (gate de saída)
**Épico**: E3
**Skill**: /implement (Code)
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Corrigir os achados do ciclo E (reauditoria Codex):
1. **🛑 [Fixture]** `questions_stub` não passa por `round_config.questions` — BLOCKER
2. **⚠️ [Storage API]** Schema check acessa `storage._base_dir` (privado) — IMPORTANTE
3. **⚠️ [Golden]** `rank_scores_by_config` sem valores recomputados — IMPORTANTE

---

## Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/.../config/schema.py` | Campo `questions: str | None = None` adicionado ao `RoundConfig` |
| `tests/e2e/test_m3_full_cycle.py` | 4 mudanças (ver abaixo) |
| `tests/golden/e2e_m3_expected.json` | Adicionado `rank_scores_nan_scenario` com valores computados |

---

## Decisões Técnicas

### 1. Campo `questions` no `RoundConfig`

`RoundConfig` ganhou `questions: str | None = None` — path para o JSONL de perguntas.
`None` preserva compatibilidade com YAML existentes (default = arquivo empacotado no wiring).

Na fixture `round_config`, o campo é preenchido com:
```python
resource = importlib.resources.files(
    "inteligenciomica_eval.infrastructure.benchmark"
).joinpath("questions_rf1.jsonl")
return RoundConfig(..., questions=str(resource), ...)
```

### 2. `questions_stub` via `round_config.questions`

```python
@pytest.fixture()
def questions_stub(round_config: RoundConfig) -> list[Question]:
    assert round_config.questions is not None
    return load_questions(Path(round_config.questions))[:2]
```

Prova a cadeia completa: `round_config.questions` → `load_questions(Path)` → perguntas reais.

### 3. Schema check via `tmp_path` (sem `_base_dir`)

Removido `tmp_path_from_storage` (que acessava `storage._base_dir`). O teste agora
usa `tmp_path` diretamente (fixture pública do pytest):

```python
async def test_m3_full_cycle_generates_and_evaluates(..., tmp_path: Path) -> None:
    ...
    table = _read_parquet_safe(tmp_path / "data")
```

`tmp_path / "data"` é a estrutura definida em `tmp_storage = ParquetStorage(base_dir=tmp_path / "data", ...)`.

### 4. `rank_scores_nan_scenario` — cálculo manual

Cenário 3 (NaN exclusion), após anotar linhas normais com `critical_failure_flag=0`:

**Inputs para cada uma das 6 configs:**
- `median_score = 0.824` (única questão válida por config)
- `failure_rate = 0.0` (0.824 ≥ 0.30)
- `win_rate = 1/12`:
  - q[0] é NaN em todas as configs → 0 pontos para ninguém
  - q[1]: todas 6 configs empatam em 0.824 → cada recebe 1/6 vitórias
  - `win_rate = (1/6 vitórias) / 2 questões = 1/12`
- `critical_failure_rate = 0.0` (1 anotação por config, flag=0)

**RankScore (DEFAULT_WEIGHTS: w_m=0.50, w_f=0.20, w_w=0.15, w_p=0.15):**
```
= 0.50 * 0.824 + 0.20 * (1 - 0.0) + 0.15 * (1/12) - 0.15 * 0.0
= 0.412  +  0.200  +  0.0125  -  0.0
= 0.6245
```

Todos os 6 configs produzem `rank_score = 0.6245` (métricas idênticas).

---

## Validação (DoD)

```
uv run ruff check .           → All checks passed!
uv run ruff format --check .  → 162 files already formatted
uv run mypy --strict src      → Success: no issues found in 57 source files
uv run lint-imports           → Contracts: 4 kept, 0 broken
pytest -m e2e tests/e2e/test_m3_full_cycle.py -v --timeout=60
                              → 5 passed in 0.93s
pytest --cov=src --cov-fail-under=85 -n 4 -q
                              → 1204 passed, 16 skipped
                              → Total coverage: 88.63% ≥ 85% ✅
```

---

## Critérios de Aceitação

- [x] BLOCKER resolvido: `questions_stub` via `round_config.questions` → `load_questions(Path(...))`
- [x] ⚠️ Storage API: schema check via `tmp_path / "data"` (sem `_base_dir`)
- [x] ⚠️ Golden: `rank_scores_nan_scenario` com 0.6245 por config (cálculo manual documentado)
- [x] cenário 3 valida `agg.rank_score.value == approx(0.6245)` contra o golden
- [x] Todos os gates PASS
