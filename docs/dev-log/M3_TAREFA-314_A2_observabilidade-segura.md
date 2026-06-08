# M3_TAREFA-314_A2 — Observabilidade Segura (ciclo de correção pós-auditoria B)

**Data**: 2026-06-08
**Milestone**: M3 — Orquestração das 4 GPUs (hardening E9)
**Épico**: E9
**Skill**: backend-engineer, security-auditor, test-engineer
**Ciclo**: A2 — correções dos achados da auditoria B (ChatGPT Codex)

---

## Achados Corrigidos

### 🛑 B1 — `prometheus_judge.py:213` — `raw_content` residual no ramo `score_out_of_range`

O ciclo A1 corrigira apenas o bloco `except (json.JSONDecodeError, ...)` dentro de
`_parse_response`. O segundo bloco de log (`if not (0.0 <= score <= 1.0)`) ainda
continha `raw_content=content[:500]` — confirmado reproduzindo `{"score": 1.5, ...}`.

**Correção:**

```python
# ANTES (linha 216 — ramo score fora de range):
raw_content=content[:500],

# DEPOIS:
raw_len=len(content),
raw_snippet=content[:120],
```

**Verificação pós-fix:**
```bash
grep -n "raw_content" src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py
# Saída vazia — PASS
```

### ⚠️ B2 — Teste ausente para ramo `score_out_of_range`

O teste `test_nan_on_score_out_of_range` (existente) apenas verificava call_count e
retorno NaN — não inspecionava os campos do log. O achado passou sem detecção porque
nenhum teste exercia o log desse ramo específico.

**Novo teste adicionado** em `TestPayloadSecurity`:

```python
async def test_score_out_of_range_log_no_raw_content(self) -> None:
    """Ramo score fora de [0.0, 1.0] NÃO deve logar raw_content."""
    payload = '{"score": 1.5, "feedback": "score inválido"}'
    # Verifica: nenhum evento prometheus_judge_parse_failure tem raw_content
    # Verifica: raw_len e raw_snippet presentes, snippet ≤ 120 chars
```

Este teste falharia **antes** desta correção.

### ⚠️ B3 — `security_review.md` desatualizado

O `security_review.md` descrevia apenas o mascaramento do `RAGASLayer1Adapter` (ciclo B
da TAREFA-605). Não documentava:
- helper único `mask_url` em `infrastructure/masking.py`
- mascaramento total dos probes em `endpoint_probe.py`
- redução de payload do juiz em `prometheus_judge.py`

**Correções ao `security_review.md`:**
- Cabeçalho atualizado com data e referência à TAREFA-314
- Linha S7 da tabela atualizada para descrever mascaramento total
- Nova seção **S7-bis** adicionada com todos os detalhes da TAREFA-314

---

## Arquivos Modificados (A2)

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `src/.../adapters/prometheus_judge.py` | Modificado | Remove `raw_content` do ramo `score_out_of_range` |
| `tests/.../adapters/test_prometheus_judge.py` | Modificado | Novo teste `test_score_out_of_range_log_no_raw_content` |
| `docs/security_review.md` | Modificado | Cabeçalho, S7 e nova seção S7-bis |

---

## Validação (DoD A2)

### Gates de qualidade

```
ruff check .          → All checks passed!
ruff format --check . → 173 files already formatted
mypy --strict src/    → Success: no issues found in 61 source files
lint-imports          → 4 kept, 0 broken
```

### Suíte de testes

```
uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4 -q

1274 passed, 6 skipped, 21 warnings in 30.17s
TOTAL coverage: 89.61% (≥ 85% ✓)
```

### Teste novo (PASS)

```
tests/unit/infrastructure/adapters/test_prometheus_judge.py::TestPayloadSecurity::test_score_out_of_range_log_no_raw_content PASSED
```

Este teste falharia se revertido para `raw_content=content[:500]`.

---

## Critérios de Aceitação A2

- [x] `prometheus_judge.py` sem nenhuma ocorrência de `raw_content` (grep vazio)
- [x] Todos os 3 ramos de `prometheus_judge_parse_failure` usam `raw_len`+`raw_snippet`
- [x] `test_score_out_of_range_log_no_raw_content` PASS (falharia antes)
- [x] `security_review.md` descreve mascaramento **total**: helper único + probes + juiz
- [x] Gates verdes; 1274 passed, 89.61%
