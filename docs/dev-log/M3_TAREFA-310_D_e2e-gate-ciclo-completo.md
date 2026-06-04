# M3_TAREFA-310_D — E2E Gate do Ciclo Completo M3 (ciclo C→D)

**Data**: 2026-06-04
**Milestone**: M3 — Orquestração das 4 GPUs (gate de saída)
**Épico**: E3
**Skill**: /implement (Code)
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Verificar e confirmar que as correções aplicadas no ciclo C resolvem os dois BLOCKERs
apontados pelo Codex na auditoria do ciclo B (relatório `M3_TAREFA-310_B_auditoria`).

---

## Contexto

O relatório do ciclo B foi produzido pelo Codex a partir do código do ciclo A (versão
original sem as correções). As correções do ciclo C foram aplicadas na sessão anterior,
mas o contexto se esgotou antes da auditoria ser executada novamente. O usuário
encaminhou o FAIL do ciclo B para esta sessão, que verificou o estado atual do arquivo
e confirmou que as correções já estavam presentes.

---

## Verificação das Correções do Ciclo C

### BLOCKER 1 — `questions_stub` com path explícito ✅

O arquivo `tests/e2e/test_m3_full_cycle.py` (linha 397–403) já usa:

```python
resource = importlib.resources.files(
    "inteligenciomica_eval.infrastructure.benchmark"
).joinpath("questions_rf1.jsonl")
return load_questions(Path(str(resource)))[:2]
```

O path explícito para `questions_rf1.jsonl` prova o contrato do loader com arquivo real.
O auditor citou linha 376 (que no arquivo atual corresponde ao interior da fixture
`round_config`), confirmando que o relatório foi produzido sobre uma versão mais antiga.

### BLOCKER 2 — Shutdown via `_KeyboardInterruptGenerator` ✅

O arquivo contém a classe (linha 263–271):

```python
class _KeyboardInterruptGenerator:
    async def generate(self, **_kwargs: Any) -> NoReturn:
        raise KeyboardInterrupt("simulated SIGINT during generation (RNF7)")
```

E o teste `test_m3_graceful_shutdown_on_sigint` (linha 691+) usa uma factory com
contador que retorna `_KeyboardInterruptGenerator` na 2ª chamada (wave 1 = gen-b).
`RunExperimentUseCase._run()` captura `KeyboardInterrupt` e seta `_shutdown_requested`.

O auditor citou linha 674 (que no arquivo atual é código do teste de idempotência),
confirmando novamente que o relatório foi sobre o código pré-correção.

---

## Arquivos Entregues

| Arquivo | Status |
|---------|--------|
| `tests/e2e/test_m3_full_cycle.py` | 5 cenários E2E — BLOCKERs corrigidos |
| `tests/golden/e2e_m3_expected.json` | Valores canônicos (n_generated=12, final_score=0.824) |
| `src/.../use_cases/run_experiment.py` | `except KeyboardInterrupt` em `_run()` (RNF7) |
| `pyproject.toml` + `uv.lock` | `pytest-timeout>=0.9` adicionado |
| `docs/dev-log/M3_TAREFA-310_A_*.md` | Ciclo A — implementação |
| `docs/dev-log/M3_TAREFA-310_C_*.md` | Ciclo C — correções pós-auditoria |

---

## Validação (DoD)

```
uv run ruff check .           → All checks passed!
uv run ruff format --check .  → 162 files already formatted
uv run mypy --strict src      → Success: no issues found in 57 source files
uv run lint-imports           → Contracts: 4 kept, 0 broken
pytest -m e2e tests/e2e/test_m3_full_cycle.py -v --timeout=60
                              → 5 passed in 0.98s
pytest --cov=src --cov-fail-under=85 -n 4 -q
                              → 1204 passed, 16 skipped
                              → Total coverage: 88.63% ≥ 85% ✅
```

---

## Critérios de Aceitação

- [x] BLOCKER 1 resolvido: `questions_stub` usa `importlib.resources.files(...)` + path explícito
- [x] BLOCKER 2 resolvido: shutdown test usa `_KeyboardInterruptGenerator` na onda 2
- [x] `RunExperimentUseCase._run()` captura `KeyboardInterrupt` (RNF7 real)
- [x] Todos os gates de validação PASS

---

## Notas sobre ⚠️ Não-BLOCKERs (mantidos)

### ⚠️ [Storage API] Schema check via pyarrow
`_read_parquet_safe` acessa `storage._base_dir` + pyarrow para verificar colunas.
A API do storage (`load()`) retorna `ResultFrame` com objetos de domínio — não expõe
nomes de coluna. Pyarrow é necessário para checar schema; a manutenção dos nomes de
coluna do Parquet é contrato de storage, e o teste o verifica diretamente.

### ⚠️ [Golden] rank_scores_by_config todos null
ADR-007: sem anotações humanas, `critical_failure_rate=NaN` → `rank_score=NaN` para
todas as 6 configs. O golden documenta o comportamento correto do sistema sem
intervenção humana. O cenário 3 (NaN exclusion) valida que rank_score é calculável
após anotações.
