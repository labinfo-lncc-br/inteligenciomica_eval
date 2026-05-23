# M0_TAREFA-003_A — Value Objects e Invariantes de Domínio

**Data**: 2026-05-23
**Milestone**: M0 — Bootstrap e Estrutura Base
**Épico**: E0
**Skill**: python-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Criar os Value Objects (VOs) de domínio em
`src/inteligenciomica_eval/domain/value_objects.py`, como `@dataclass(frozen=True)`,
validando invariantes em `__post_init__` e levantando exceções de TAREFA-002.
Incluir `DeterminismRegime` (enum) e `RowId` com `from_cell()` (ADR-009).

---

## Arquivos Criados / Modificados

| Ação      | Arquivo                                                              |
|-----------|----------------------------------------------------------------------|
| Criado    | `src/inteligenciomica_eval/domain/value_objects.py`                 |
| Criado    | `tests/unit/domain/test_value_objects.py`                           |
| Modificado| `src/inteligenciomica_eval/domain/errors.py` — adicionado `InvalidSeedError` |
| Modificado| `tests/unit/test_imports.py` — importação de `domain.value_objects` |

---

## Value Objects Implementados

| VO                 | Invariante                                          | Exceção levantada          |
|--------------------|-----------------------------------------------------|----------------------------|
| `BaseId`           | `value ∈ {"IDx_400k", "ID_230K", "fixed"}`          | `InvalidBaseIdError`        |
| `LLMId`            | não-vazio, sem espaços                              | `InvalidLLMIdError`         |
| `Seed`             | `value >= 0`                                        | `InvalidSeedError` (nova)   |
| `FinalScore`       | `isnan(value)` OR `0.0 <= value <= 1.0`             | `ScoreOutOfRangeError`      |
| `RankScore`        | finito OU NaN; rejeita ±inf                         | `InteligenciomicaEvalError` |
| `MetricVector`     | container imutável (sem validação de campo)         | —                           |
| `RowId`            | hex SHA-256 64 chars minúsculos                     | `ValueError`                |
| `DeterminismRegime`| enum `{JUDGE, GENERATOR}`                          | —                           |

---

## Decisões Técnicas

### 1. `InvalidSeedError` adicionado a `errors.py`
O spec pediu "levante um erro de domínio claro". Adicionada `InvalidSeedError(seed: int)`
na seção de domínio/validação de `errors.py`. Guarda o atributo `.seed` para rastreabilidade.

### 2. `nan_fields()` com lista explícita de campos
A alternativa `dataclasses.fields(self)` + `getattr(self, f.name)` dispararia erro
`Any` no mypy strict (getattr retorna `Any`). Lista explícita de tuples `(name, self.field)`
evita o `Any` e preserva 100% de cobertura.

### 3. `RowId.from_cell()` usa separador `|`
Separador nulo (`\x00`) foi testado e rejeitado: não previne colisão por injeção quando os
valores dos campos contêm o próprio separador. Separador `|` é suficiente para os
identificadores controlados do domínio (nomes de modelos, run IDs, bases) que jamais
contêm `|`. Docstring documenta explicitamente essa precondição.

### 4. Frozen dataclasses com `slots=True`
Todos os VOs usam `@dataclass(frozen=True, slots=True)` para imutabilidade garantida em
runtime e menor footprint de memória. Compatível com Python 3.11+.

### 5. `RankScore` rejeita ±inf com `InteligenciomicaEvalError` base
Não existe exceção semântica mais específica para "inf não-permitido em rank". Usar
`ScoreOutOfRangeError(inf, -inf, inf)` seria semanticamente incoerente. Opção adotada:
instanciar `InteligenciomicaEvalError` diretamente com mensagem clara ("finite or NaN").

---

## Problemas Encontrados e Soluções

| Problema                                   | Solução                                                  |
|--------------------------------------------|----------------------------------------------------------|
| Lint B017: `pytest.raises(Exception)`      | Substituído por `dataclasses.FrozenInstanceError` (3.11+)|
| Lint C420: dict comprehension desnecessário | `dict.fromkeys(_METRIC_FIELD_NAMES, 0.5)`               |
| Teste de injeção de separador incorreto    | Teste removido; comportamento do separador documentado   |
| Coverage path inválido no pytest           | Usando `--cov=src` em vez de nome de módulo              |

---

## Validação (DoD)

```
uv run ruff check src/inteligenciomica_eval/domain/value_objects.py
  → All checks passed

uv run ruff format --check src/inteligenciomica_eval/domain/value_objects.py
  → Already formatted

uv run mypy --strict src/inteligenciomica_eval/domain/value_objects.py
  → Success: no issues found

uv run lint-imports
  → Contracts: 4 kept, 0 broken

uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n auto
  → 122 passed in 1.82s
  → value_objects.py: 100% (line + branch)
  → errors.py: 100%
  → TOTAL: 98.04% ✓
```

---

## Critérios de Aceitação

| Critério                                                               | Status |
|------------------------------------------------------------------------|--------|
| Invariantes validadas em `__post_init__` para todos os VOs             | ✅     |
| Cada VO com teste de caso válido + caso que levanta exceção correta     | ✅     |
| Cobertura line+branch >= 95% do módulo `value_objects.py`              | ✅ 100% |
| Property-based: `FinalScore` aceita exatamente `[0,1]∪{NaN}`          | ✅     |
| Property-based: `RowId.from_cell` determinístico (mesmos insumos → mesmo hash) | ✅ |
| Property-based: insumo diferente (seed) → hash diferente              | ✅     |
| `nan_fields()` retorna exatamente os campos NaN                        | ✅     |
| `from __future__ import annotations` em todos os arquivos              | ✅     |
| Sem libs de I/O no domínio (apenas stdlib: math, hashlib, re, dataclasses, enum) | ✅ |
| import-linter: 4 contratos kept, 0 broken                             | ✅     |

---

## Observações para Próximas Tarefas

- **TAREFA-004/005** podem importar `BaseId`, `LLMId`, `Seed`, `MetricVector`,
  `FinalScore`, `RankScore`, `RowId`, `DeterminismRegime` diretamente de `value_objects`.
- `RowId.from_cell()` aceita strings arbitrárias em todos os campos exceto `seed` (int).
  Se `base` e `llm` forem passados como VOs (`BaseId`, `LLMId`), extrair `.value` antes.
- `MetricVector` não valida limites dos campos individuais (cada métrica tem escala
  própria — RAGAS retorna [0,1], BERTScore pode sair levemente desse range). Validação
  de range por métrica deve ser feita na camada de application ou adapter.
- `InvalidSeedError` foi adicionado ao `errors.py` fora do escopo original de TAREFA-002.
  O `test_errors.py` existente não precisa ser atualizado (testa a classe base, não o inventário).
