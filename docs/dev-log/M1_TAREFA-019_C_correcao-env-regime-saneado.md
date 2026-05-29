# M1_TAREFA-019_C — Correção pós-auditoria: saneamento de env de regime

**Data**: 2026-05-28
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E1 — Adapters de Recuperação
**Skill**: python-engineer, backend-engineer
**Prioridade / Tamanho**: P1 / S
**Em resposta a**: `M1_TAREFA-019_B_auditoria-vllm-server-manager-adapter.md` (FAIL / Request changes)

## Objetivo

Resolver o único bloqueador da auditoria 019-B do `VLLMServerManagerAdapter`:

> **Bloqueador** — variáveis do juiz vazam do ambiente pai para geradores. O `start()`
> montava `env={**os.environ, **model.extra_env}`. Se o orquestrador já tivesse
> `VLLM_BATCH_INVARIANT`/`VLLM_ENABLE_V1_MULTIPROCESSING` no ambiente, um gerador com
> `extra_env={}` herdava essas variáveis, mas `ServerHandle.batch_invariant` ficava
> `False` — o processo real rodaria em regime de juiz com proveniência indicando o
> contrário. Viola o item 2 do Prompt B (bloqueador) e a decisão central de §9.2/ADR-003.

Itens 1, 3, 4, 5, 6, 7 do Prompt B já estavam PASS; apenas o item 2 voltou para correção.

## Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/.../adapters/vllm_server_manager.py` | Novo `_RESERVED_REGIME_ENV` + `_build_env(model)` que **sana** as chaves de regime do `os.environ` herdado antes de aplicar `extra_env`; `start()` passa a usar `_build_env`; docstrings atualizadas |
| `tests/unit/.../test_vllm_server_manager.py` | +2 testes de regressão (`test_generator_does_not_inherit_regime_from_parent_env`, `test_judge_overrides_parent_regime_env`) |

## Decisão Técnica

**Saneamento das chaves de regime do ambiente herdado** — exatamente a correção sugerida
pelo auditor (019-B, linhas 81-95). Define-se:

```python
_RESERVED_REGIME_ENV = frozenset({"VLLM_BATCH_INVARIANT", "VLLM_ENABLE_V1_MULTIPROCESSING"})

@staticmethod
def _build_env(model: ModelSpec) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _RESERVED_REGIME_ENV}
    env.update(model.extra_env)
    return env
```

Garantias resultantes:

- **Gerador** (`extra_env={}`): as chaves de regime são removidas do ambiente herdado →
  nunca presentes no subprocess, independentemente do ambiente do orquestrador.
- **Juiz** (`extra_env` com as chaves): as chaves vêm de `extra_env` e **sobrescrevem**
  qualquer valor do pai (ex.: pai com `VLLM_BATCH_INVARIANT=0` → juiz força `=1`).
- **Coerência**: a presença de `VLLM_BATCH_INVARIANT` no env real do processo passa a ser
  idêntica a `("VLLM_BATCH_INVARIANT" in extra_env)` e a `ServerHandle.batch_invariant`.
  O regime é decidido **exclusivamente** por `model.extra_env`.
- **Variáveis não-regime** do ambiente pai continuam preservadas (ex.: `PATH`,
  `CUDA_VISIBLE_DEVICES`, `SENTINEL_VAR` do teste).

## Validação (DoD)

```
uv run ruff check .            → All checks passed!
uv run ruff format --check .   → arquivos já formatados
uv run mypy --strict src       → Success: no issues found in 29 source files
uv run mypy --strict tests/.../test_vllm_server_manager.py → Success
uv run lint-imports            → 4 kept, 0 broken
uv run pytest tests/.../test_vllm_server_manager.py → 23 passed
uv run pytest --cov ... -n 4   → 679 passed, 7 skipped — 96.69% total; vllm_server_manager.py 100% (102/102, 12 branches)
```

## Resposta item a item à auditoria 019-B

| Achado | Gravidade | Resolução |
|--------|-----------|-----------|
| Variáveis do juiz vazam do ambiente pai para geradores | Bloqueador | ✅ `_build_env` sana `_RESERVED_REGIME_ENV` do `os.environ` herdado; regressão `test_generator_does_not_inherit_regime_from_parent_env` comprova; `test_judge_overrides_parent_regime_env` comprova override do juiz |

## Observações para Próximas Tarefas

- Pronto para reauditoria (Prompt B novamente) — foco no item 2 (regime exclusivamente
  por `extra_env`, sem herança ambiental).
- Padrão reutilizável: adapters que lançam subprocess sensível a regime/determinismo devem
  **sanear** as chaves controladas do `os.environ` herdado, nunca confiar em merge bruto.
