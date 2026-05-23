# M0_TAREFA-003_C — Correções Pós-Auditoria dos Value Objects

**Data**: 2026-05-23
**Milestone**: M0 — Bootstrap e Estrutura Base
**Épico**: E0
**Skill**: python-engineer
**Prioridade / Tamanho**: P0 / S
**Referência**: M0_TAREFA-003_B_auditoria-value-objects.md (resultado: FAIL)

---

## Objetivo

Corrigir as duas divergências materiais apontadas pela auditoria B:
1. `DeterminismRegime` com valores serializados errados (`"JUDGE"/"GENERATOR"` em vez de `"judge"/"generator"`).
2. `RankScore` sem rejeição consistente de valores não-`float`.

---

## Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/inteligenciomica_eval/domain/value_objects.py` | `DeterminismRegime` valores corrigidos para minúsculas; `RankScore.__post_init__` com guarda `isinstance(value, float)` |
| `tests/unit/domain/test_value_objects.py` | Testes de `DeterminismRegime` atualizados; dois novos grupos de testes para `RankScore` com non-float |

---

## Correções Implementadas

### 1. `DeterminismRegime` — valores em minúsculas

**Antes**:
```python
JUDGE = "JUDGE"
GENERATOR = "GENERATOR"
```

**Depois**:
```python
JUDGE = "judge"
GENERATOR = "generator"
```

**Evidência arquitetural**: `docs/arquitetura_detalhada_validacao_inteligenciomica.md:241`:
> `judge` (batch-invariant) ou `generator` (realista)

### 2. `RankScore` — rejeição de non-float com erro de domínio

**Antes**: apenas `math.isinf(self.value)` — `int` era silenciosamente aceito; `str`/`None` lançavam `TypeError` genérico (sem contrato de domínio).

**Depois**:
```python
def __post_init__(self) -> None:
    if not isinstance(self.value, float):   # rejeita int, bool, str, None …
        raise InteligenciomicaEvalError(
            f"RankScore.value must be a float, got {type(self.value).__name__!r}"
        )
    if math.isinf(self.value):
        raise InteligenciomicaEvalError(
            f"RankScore must be a finite float or NaN, got: {self.value!r}"
        )
```

`isinstance(x, float)` retorna `False` para `int`, `bool`, `str`, `None`, listas e dicts. `bool` é subclasse de `int`, não de `float` — também corretamente rejeitado.

---

## Novos Testes Adicionados

| Teste | Cobertura |
|-------|-----------|
| `test_rank_score_rejects_non_float_with_domain_error` | `int` e `bool` → `InteligenciomicaEvalError("must be a float")` |
| `test_rank_score_rejects_wrong_type_with_domain_error` | `str`, `None`, `list`, `dict` → mesmo erro |
| `test_determinism_regime_judge_value` (atualizado) | `== "judge"` |
| `test_determinism_regime_generator_value` (atualizado) | `== "generator"` |

---

## Validação Final

```
uv run ruff check src/ tests/unit/domain/test_value_objects.py → All checks passed
uv run ruff format --check src/ tests/              → Already formatted
uv run mypy --strict src/                           → Success: no issues found
uv run lint-imports                                 → 4 kept, 0 broken
uv run pytest --cov=src -n auto --cov-fail-under=85

  131 passed in 1.58s
  value_objects.py: 100% line + branch (72 stmts, 18 branches)
  TOTAL: 98.08% ✓
```

---

## Status dos Critérios de Aceitação (pós-correção)

| Critério | Status |
|----------|--------|
| Inventário completo de VOs | ✅ |
| Invariantes validadas em `__post_init__` | ✅ |
| `DeterminismRegime` com valores `"judge"/"generator"` | ✅ corrigido |
| `RankScore` rejeita non-float com `InteligenciomicaEvalError` | ✅ corrigido |
| Property-based tests presentes | ✅ |
| Cobertura do módulo >= 95% | ✅ 100% |
| import-linter: 0 contratos quebrados | ✅ |
