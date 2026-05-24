# M0_TAREFA-011_A — Fakes de todos os ports + factories

**Data**: 2026-05-24
**Milestone**: M0 — Foundation
**Épico**: E0
**Skill**: test-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Implementar fakes in-memory e determinísticos para todos os ports da §5.1, além de
factories de dados de teste, prontos para uso nos use cases (M1+) e no E2E stub
(TAREFA-012).

---

## Arquivos Criados / Modificados

### Criados

| Arquivo | Conteúdo |
|---------|----------|
| `tests/fakes/retrieval.py` | `StubRetriever` — RetrieverPort configurável por pergunta |
| `tests/fakes/generation.py` | `FakeGenerator` + `GenerateCall` — GeneratorPort determinístico com registro de chamadas |
| `tests/fakes/metrics.py` | `FakeMetricSuite`, `FakeRubricJudge`, `FakeDeterministicMetric` — suportam `inject_nan=True` para ADR-007 |
| `tests/fakes/storage.py` | `InMemoryResultStore`, `InMemoryResultWriter`, `InMemoryResultReader` — ResultWriter/ReaderPort com dict compartilhado |
| `tests/fakes/servers.py` | `FakeVLLMServerManager` + records `StartCall`/`WaitHealthyCall`/`StopCall` |
| `tests/fakes/data_readers.py` | `FakeGoldChunkReader`, `FakeAnnotationReader`, `FakeStats` |
| `tests/factories/factories.py` | `make_row_id`, `make_question`, `make_generated_answer`, `make_metric_vector`, `make_evaluation_result`, `make_config_aggregate` |
| `tests/unit/fakes/__init__.py` | Pacote para testes de fakes |
| `tests/unit/fakes/test_fakes_satisfy_ports.py` | 57 testes de compatibilidade estrutural e comportamento |

### Modificados

| Arquivo | Alteração |
|---------|-----------|
| `tests/fakes/__init__.py` | Re-exporta todos os fakes via imports relativos |
| `tests/factories/__init__.py` | Re-exporta todas as factories via imports relativos |
| `tests/factories/factories.py` | Adicionado `question_id` como parâmetro direto de `make_generated_answer` |

---

## Decisões Técnicas

### D1 — InMemoryResultStore como estado compartilhado
`InMemoryResultWriter` e `InMemoryResultReader` operam sobre um `InMemoryResultStore`
injetado. Isso espelha o comportamento real do `ParquetStorage` (writer e reader apontam
para o mesmo diretório) e permite que testes E2E controlem o escopo do estado (por
instância de store, não por classe).

### D2 — round_id no writer, não no store
O `round_id` é associado a cada linha no momento do `append()`, guardado junto ao
`EvaluationResult` em `_StoredRow`. O `load()` do reader filtra por `round_id` e
por `phase` (via `result.answer.phase`), exatamente como o `ParquetStorage` faz via
partições Hive.

### D3 — inject_nan ao invés de None
As factories de métricas (`FakeMetricSuite`, `FakeRubricJudge`, `FakeDeterministicMetric`)
usam o parâmetro `inject_nan: bool = False` em vez de aceitar `None` como valor
especial. Isso torna a intenção explícita e evita ambiguidade com `fixed=None` (usar
default).

### D4 — Template determinístico no FakeGenerator
O texto de resposta do `FakeGenerator` é `f"Fake answer for [{llm}|seed={seed}]: {question}"`,
tornando cada tripla `(llm, question, seed)` única e reprodutível sem necessidade de
estado aleatório.

### D5 — Imports relativos nos `__init__.py` de fakes/factories
Pytest adiciona `tests/` ao `sys.path` (primeiro diretório sem `__init__.py` ao subir
da árvore de test files). Os `__init__.py` usam imports relativos (`from .module import`)
e os test files importam como `from fakes import ...` e `from factories import ...`.

### D6 — Factories como funções simples
Usadas funções builder com `**kwargs`-estilo e defaults, em vez de polyfactory, para
maior legibilidade e nenhuma dependência de magia de classe. `polyfactory` permanece
disponível para uso em testes futuros.

---

## Problemas Encontrados e Soluções

### P1 — ModelSpec em ports, não em value_objects
O test file inicialmente importava `ModelSpec` de `value_objects`. Corrigido para
importar de `ports`, onde `ModelSpec` está definida.

### P2 — __all__ não-ordenado e imports desordenados
Ruff RUF022 e I001 sinalizaram `__all__` fora de ordem e bloco de imports não-ordenado
no test file. Corrigido com `ruff check --fix` e `ruff format`.

### P3 — Assertion incorreta em test_returns_default_chunk_for_unknown_question
O teste comparava `result.ids == result.chunks[0].id` (tuple vs string). Corrigido para
`result.ids == (result.chunks[0].id,)`.

### P4 — `__import__` em teste de round_id
A versão inicial de `test_load_filters_by_round_id` usava `__import__` para evitar
re-importar `make_generated_answer`. Resolvido adicionando o parâmetro `question_id`
direto à função `make_generated_answer` e importando normalmente.

---

## Validação (DoD)

```
uv run ruff check .           → All checks passed!
uv run ruff format --check .  → 59 files already formatted
uv run mypy --strict src      → Success: no issues found in 22 source files
uv run lint-imports           → Contracts: 4 kept, 0 broken.
uv run pytest tests/unit/fakes/ -v → 57 passed in 0.16s
uv run pytest --cov=src --cov-fail-under=85 -n auto -q → 533 passed, coverage 96.43%
```

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| Fake tipado por CADA port da §5.1 | ✅ 11 ports cobertos |
| Todos passam no teste de compatibilidade estrutural com Protocol | ✅ 11 testes isinstance |
| InMemoryResultWriter/Reader: exists/update_metrics/load corretos | ✅ 9 testes dedicados |
| Fakes de métricas injetam NaN (caminho ADR-007) | ✅ TestNaNInjection (3 testes) |
| Factories produzem entidades válidas com overrides; determinísticas | ✅ 6 factories com defaults + overrides |
| `from __future__ import annotations` em todos os arquivos | ✅ |
| Type hints em todas as assinaturas públicas | ✅ |
| Docstrings Google-style | ✅ |
| Sem I/O real / rede / disco nos fakes | ✅ |
| Não importa infra real (qdrant/openai/pyarrow) | ✅ |

---

## Observações para Próximas Tarefas

- **TAREFA-012 (E2E stub)**: usar `InMemoryResultWriter` + `InMemoryResultReader` (mesmo
  `InMemoryResultStore`) em vez de `ParquetStorage`. `StubRetriever` e `FakeGenerator`
  eliminam dependências de rede.
- `make_generated_answer(phase="B", base="fixed", ...)` é o padrão para criar respostas
  de Experimento B (a validação `phase B → base must be "fixed"` está em `GeneratedAnswer.__post_init__`).
- `FakeStats` retorna formula passada no campo `MLMReport.formula` — permite asserções
  sobre o valor exato do parâmetro em testes de use cases estatísticos (M4+).
- A adição de `question_id` como parâmetro de `make_generated_answer` torna conveniente
  criar múltiplas respostas para questions distintas sem construir `Question` explicitamente.
