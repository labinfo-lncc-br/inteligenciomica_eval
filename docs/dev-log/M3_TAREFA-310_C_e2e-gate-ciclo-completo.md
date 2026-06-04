# M3_TAREFA-310_C — E2E Gate do Ciclo Completo M3 (ciclo B→C)

**Data**: 2026-06-04
**Milestone**: M3 — Orquestração das 4 GPUs (gate de saída)
**Épico**: E3
**Skill**: /implement (Code)
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Corrigir os dois BLOCKERs apontados pelo Codex na auditoria ciclo B:
1. Fixture `questions_stub` não prova o contrato do loader com path explícito.
2. Cenário de shutdown não usa `FakeGenerator` levantando `KeyboardInterrupt` na onda 2.

---

## Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/inteligenciomica_eval/application/use_cases/run_experiment.py` | Captura `KeyboardInterrupt` em `_run()` → shutdown gracioso (RNF7) |
| `tests/e2e/test_m3_full_cycle.py` | 3 mudanças: fixture path explícito, `_KeyboardInterruptGenerator`, factory com contador |

---

## Decisões Técnicas

### 1. Captura de `KeyboardInterrupt` em `RunExperimentUseCase._run()`

O spec diz que o UC "captura e finaliza via flag de shutdown". A implementação anterior
só capturava SIGINT via `loop.add_signal_handler`, que converte o sinal OS em flag — mas
`KeyboardInterrupt` Python direto (levantado por um gerador) não era capturado.

**Mudança**: adicionado `except KeyboardInterrupt:` no bloco `try/finally` que envolve
`gen_pass_uc.execute(...)`. Ao capturar:
1. Seta `_shutdown_requested = True`
2. Loga `generation_interrupted_by_signal`
3. `finally` executa normalmente: `stop(active_handle)` é chamado (sem leak)
4. Após `finally`: `if self._shutdown_requested: break` (sai do loop inner)
5. Outer loop: sem mais ondas → cai no `if self._shutdown_requested:` → retorna relatório parcial

Esta mudança é correta para RNF7: SIGINT real via `loop.add_signal_handler` e
`KeyboardInterrupt` de geradores são agora ambos tratados graciosamente.

### 2. Fixture `questions_stub` com path explícito

`load_questions(None)` já carregava o arquivo empacotado, mas não provava o contrato
do loader com um path de arquivo. Agora usa:
```python
resource = importlib.resources.files(
    "inteligenciomica_eval.infrastructure.benchmark"
).joinpath("questions_rf1.jsonl")
load_questions(Path(str(resource)))[:2]
```
Este path aponta para o arquivo real em disco (src layout + uv sync), provando que
loader + arquivo funcionam no contexto E2E.

### 3. `_KeyboardInterruptGenerator` + factory com contador

`_KeyboardInterruptGenerator.generate()` levanta `KeyboardInterrupt` em qualquer
chamada. A factory usa um contador por lista (`_call_count: list[int]`) para retornar
`FakeGenerator` na 1ª chamada (wave 0 = gen-a) e `_KeyboardInterruptGenerator` na
2ª chamada (wave 1 = gen-b), sem `nonlocal`.

Fluxo do shutdown test:
1. Wave 0=[gen-a]: `FakeGenerator` normal → 6 células em Parquet
2. Wave 1=[gen-b]: factory retorna `_KeyboardInterruptGenerator` → `generate()` levanta KI
3. `RunExperimentUseCase._run` captura KI → `_shutdown_requested=True`
4. `finally`: `stop(gen-b handle)` chamado → sem leak
5. Inner loop: `if _shutdown_requested: break` → sai do loop de modelos
6. Outer loop: sem mais ondas → cai no `if _shutdown_requested:` → relatório parcial
7. `report.n_evaluated=0, n_judged=0, aggregates=()` ✓
8. Parquet: 6 linhas (só gen-a) ✓
9. `start_calls=2, stop_calls=2` (gen-a + gen-b, juiz nunca iniciado) ✓

---

## Problemas Resolvidos

### BLOCKER 1: `questions_stub` não prova contrato do loader
- **Causa**: `load_questions(None)` usa PackageLoader interno, não path explícito
- **Solução**: `importlib.resources.files(...).joinpath(...)` → `Path(str(resource))` → `load_questions(path)`
- **Prova**: se `questions_rf1.jsonl` não existir, `load_questions(path)` lança `StorageError`

### BLOCKER 2: Shutdown test usa `progress_callback`, não `FakeGenerator` raising `KeyboardInterrupt`
- **Causa**: produção não capturava `KeyboardInterrupt` de geradores
- **Solução**: adicionado `except KeyboardInterrupt` em `_run()` (RNF7 correto)
- **Teste**: `_KeyboardInterruptGenerator` + factory com contador na onda 2

---

## Validação (DoD)

```
uv run ruff check .           → All checks passed!
uv run ruff format --check .  → 162 files already formatted
uv run mypy --strict src      → Success: no issues found in 57 source files
uv run lint-imports           → Contracts: 4 kept, 0 broken
pytest -m e2e tests/e2e/test_m3_full_cycle.py -v --timeout=60
                              → 5 passed in 0.95s
pytest --cov=src --cov-fail-under=85 -n 4 -q
                              → 1204 passed, 16 skipped
                              → Total coverage: 88.63% ≥ 85% ✅
```

---

## Notas sobre os ⚠️ do Codex (não-BLOCKERs)

### ⚠️ [Storage API] Schema check via pyarrow
A checagem de colunas do Parquet usa `_read_parquet_safe` + pyarrow porque a API do
storage (`load()`) retorna `ResultFrame` com objetos de domínio — não expõe nomes de
coluna diretamente. Pyarrow é necessário aqui; não é possível checar via API de storage.

### ⚠️ [Golden] rank_scores_by_config são todos null
Sem anotações humanas, `critical_failure_rate=NaN` → `rank_score=NaN` para todas as 6
configs (ADR-007). O golden documenta isso com comentários. O cenário NaN (teste 3)
valida que rank_score é calculável após anotações. O golden reflete o comportamento
correto do sistema sem intervenção humana.
