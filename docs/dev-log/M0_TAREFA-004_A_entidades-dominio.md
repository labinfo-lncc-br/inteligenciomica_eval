# M0_TAREFA-004_A — Entidades de Domínio

**Data**: 2026-05-23
**Milestone**: M0 — Bootstrap e Estrutura Base
**Épico**: E0
**Skill**: python-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Criar as entidades de domínio em `src/inteligenciomica_eval/domain/entities.py`:
`Question`, `GeneratedAnswer` e o agregado raiz `EvaluationResult`, com invariantes
completas conforme §4.3/§5.3 e ADR-009.

---

## Arquivos Criados / Modificados

| Ação       | Arquivo                                                              |
|------------|----------------------------------------------------------------------|
| Criado     | `src/inteligenciomica_eval/domain/entities.py`                      |
| Criado     | `tests/unit/domain/test_entities.py`                                |
| Modificado | `src/inteligenciomica_eval/domain/errors.py` — 3 novas exceções     |

---

## Entidades Implementadas

### `Question` (entidade imutável)
- Campos: `question_id: str`, `text: str`, `ground_truth: str`
- Invariante: todos os campos não-vazios → `InteligenciomicaEvalError`

### `GeneratedAnswer` (entidade com identidade por `RowId`)
- Identidade: `row_id: RowId` (ADR-009)
- Campos completos conforme spec, incluindo tuplas de retrieval imutáveis
- Invariantes:
  - `phase ∈ {"A", "B"}` → `InvalidPhaseError`
  - `len(chunk_ids) == len(chunks_text) == len(scores)` → `RetrievalTupleLengthMismatchError`
  - Experimento B (`phase=="B"`) exige `base.value == "fixed"` → `InteligenciomicaEvalError`

### `EvaluationResult` (agregado raiz, §4.3)
- Compõe `GeneratedAnswer` + `MetricVector` + `FinalScore` + `DeterminismRegime` + flags de falha crítica
- Invariantes:
  - `determinism_regime` deve ser `DeterminismRegime` instance → `InteligenciomicaEvalError`
  - `critical_failure_flag ∈ {0, 1}` quando não-`None` → `InvalidCriticalFailureFlagError`
- Métodos puros:
  - `is_failure(threshold) -> bool`: `final_score.value < threshold` (strict)
  - `is_critical_failure() -> bool`: `flag == 1` (`None` e `0` retornam `False`)
  - `with_metrics(metrics, final_score, regime) -> EvaluationResult`: via `dataclasses.replace()`
  - `with_human_annotation(flag, note) -> EvaluationResult`: via `dataclasses.replace()`

---

## Novas Exceções Adicionadas a `errors.py`

| Exceção | Atributos | Uso |
|---------|-----------|-----|
| `InvalidPhaseError(phase)` | `.phase` | `GeneratedAnswer` — phase inválida |
| `RetrievalTupleLengthMismatchError(ids, text, scores)` | `.chunk_ids_len`, `.chunks_text_len`, `.scores_len` | `GeneratedAnswer` — tuplas de retrieval desalinhadas |
| `InvalidCriticalFailureFlagError(flag)` | `.flag` | `EvaluationResult` — flag fora de {0,1} |

---

## Decisões Técnicas

### 1. Mutação imutável via `dataclasses.replace()`
`with_metrics` e `with_human_annotation` usam `dataclasses.replace(self, ...)`, que chama
`__init__` (e portanto `__post_init__`) na nova instância. Isso garante que qualquer
combinação inválida de campos seja rejeitada mesmo ao fazer mutação — ex.:
`with_human_annotation(flag=2, note=None)` levanta `InvalidCriticalFailureFlagError`.

### 2. Validação estrutural de `DeterminismRegime`
`__post_init__` valida `isinstance(self.determinism_regime, DeterminismRegime)`.
A ligação semântica (métricas de juiz → regime JUDGE) é responsabilidade do use case
conforme spec ("a ligação semântica métrica→regime é responsabilidade do use case").

### 3. Semântica de `is_failure` com NaN
`float("nan") < threshold` retorna `False` em Python. Portanto, `is_failure(0.6)` com
score NaN retorna `False` (não-falha). Esta semântica é consistente com a definição
§7.2 (score ainda não computado não pode ser falha).

### 4. Sem validação de `generated_answer` não-vazio
A spec lista explicitamente as invariantes de `GeneratedAnswer` sem mencionar
`generated_answer` não-vazio. Seguindo YAGNI, não foi adicionada validação extra.

### 5. `slots=True` em todas as entidades
Performance e imutabilidade reforçada. Compatível com `dataclasses.replace()` em Python 3.11+.

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| Pre-commit hook `ruff-format` reformatou `errors.py` e `entities.py` no primeiro `git commit`, causando falha do hook | Re-staged os dois arquivos reformatados e criou novo commit; segunda tentativa passou em todos os hooks |

**Detalhe**: ruff format colapsou a condição multilinhas em `EvaluationResult.__post_init__` (`not in (0, 1,)`) e condensou strings de `__init__` em `InvalidPhaseError` e `InvalidCriticalFailureFlagError`. O comportamento correto é sempre rodar `uv run ruff format` antes de `git add` para evitar a iteração extra.

---

## Validação (DoD)

```
uv run ruff check src/inteligenciomica_eval/domain/entities.py     → All checks passed
uv run ruff format src/inteligenciomica_eval/domain/entities.py    → 1 file reformatted (pre-commit)
uv run mypy --strict src/inteligenciomica_eval/domain/entities.py  → Success: no issues found
uv run lint-imports                                                → 4 kept, 0 broken
uv run pytest --cov=src --cov-fail-under=85 -n auto

  180 passed in 2.16s
  entities.py:  100% line+branch (60 stmts, 16 branches)
  errors.py:    100%
  TOTAL:        98.66% ✓
```

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| `Question` — campos não-vazios validados | ✅ |
| `GeneratedAnswer` — phase `{"A","B"}` validada | ✅ |
| `GeneratedAnswer` — tuplas de retrieval desalinhadas falham | ✅ |
| `GeneratedAnswer` — Experimento B exige `base="fixed"` | ✅ |
| `EvaluationResult` — flag fora de `{0,1,None}` falha | ✅ |
| `with_metrics`/`with_human_annotation` retornam nova instância | ✅ |
| Original não mutado após `with_*` | ✅ |
| `is_failure` correto nas bordas (`==` threshold = `False`) | ✅ |
| `is_critical_failure` — `None` e `0` = `False`; `1` = `True` | ✅ |
| Cobertura 100% line+branch em `entities.py` | ✅ |
| import-linter: 0 contratos quebrados | ✅ |

---

## Observações para Próximas Tarefas

- **TAREFA-005** (use cases / serviços de domínio) pode instanciar `EvaluationResult`
  inicial com `metrics=MetricVector(all NaN)`, `final_score=FinalScore(NaN)` e
  `regime=DeterminismRegime.GENERATOR`, e depois usar `with_metrics(...)` após julgamento.
- A validação `isinstance(self.determinism_regime, DeterminismRegime)` ficará ligeiramente
  redundante quando o use case garantir regime correto via tipagem — mas é útil como
  guarda de contrato em produção.
- `_make_row_id()` existe no arquivo de testes mas está definida e não usada diretamente
  (a factory `_make_answer` constrói o RowId internamente). Pode ser removida em auditoria.
