# M0_TAREFA-011_B — Auditoria fakes + factories

**Data**: 2026-05-24
**Milestone**: M0 — Bootstrap e Fundação
**Épico**: E0
**Skill**: code-reviewer + test-engineer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Auditar a implementação da TAREFA-011 contra `docs/arquitetura_detalhada_validacao_inteligenciomica.md`
§5.1/§11.2/§14.2 e a skill `test-engineer` §6, sem reescrever a implementação.

## Escopo / Premissas

- A auditoria foi feita sobre o estado atual do workspace para `tests/fakes/`,
  `tests/factories/` e `tests/unit/fakes/test_fakes_satisfy_ports.py`.
- A prova de compatibilidade estrutural considerou:
  - `isinstance(..., Protocol)` para todos os ports `@runtime_checkable`.
  - `uv run mypy --strict tests/fakes tests/factories tests/unit/fakes/test_fakes_satisfy_ports.py`.

## Resultado

**PASS**

Nenhum dos 11 ports da §5.1 ficou sem fake. Não encontrei divergências bloqueadoras,
importantes ou sugestões de correção no escopo auditado.

## Tabela de divergências

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| Nenhuma divergência encontrada no escopo auditado | — | — |

## Verificação item a item

### 1. Há um fake para cada um dos 11 ports da §5.1?

**Sim.**

Mapa completo:

| Port (§5.1) | Fake | Evidência |
|---|---|---|
| `RetrieverPort` | `StubRetriever` | `src/inteligenciomica_eval/domain/ports.py:261`; `tests/fakes/retrieval.py:13`; `tests/unit/fakes/test_fakes_satisfy_ports.py:75-76` |
| `GeneratorPort` | `FakeGenerator` | `ports.py:288`; `tests/fakes/generation.py:31`; `test_fakes_satisfy_ports.py:78-79` |
| `MetricSuitePort` | `FakeMetricSuite` | `ports.py:319`; `tests/fakes/metrics.py:38`; `test_fakes_satisfy_ports.py:81-82` |
| `RubricJudgePort` | `FakeRubricJudge` | `ports.py:338`; `tests/fakes/metrics.py:68`; `test_fakes_satisfy_ports.py:84-85` |
| `DeterministicMetricPort` | `FakeDeterministicMetric` | `ports.py:358`; `tests/fakes/metrics.py:98`; `test_fakes_satisfy_ports.py:87-90` |
| `GoldChunkReaderPort` | `FakeGoldChunkReader` | `ports.py:379`; `tests/fakes/data_readers.py:22`; `test_fakes_satisfy_ports.py:92-93` |
| `ResultWriterPort` | `InMemoryResultWriter` | `ports.py:398`; `tests/fakes/storage.py:33`; `test_fakes_satisfy_ports.py:95-97` |
| `ResultReaderPort` | `InMemoryResultReader` | `ports.py:434`; `tests/fakes/storage.py:93`; `test_fakes_satisfy_ports.py:99-101` |
| `StatsPort` | `FakeStats` | `ports.py:454`; `tests/fakes/data_readers.py:85`; `test_fakes_satisfy_ports.py:103-104` |
| `AnnotationReaderPort` | `FakeAnnotationReader` | `ports.py:499`; `tests/fakes/data_readers.py:59`; `test_fakes_satisfy_ports.py:106-107` |
| `VLLMServerManagerPort` | `FakeVLLMServerManager` | `ports.py:518`; `tests/fakes/servers.py:47`; `test_fakes_satisfy_ports.py:109-110` |

Conclusão: **11/11 ports cobertos**.

### 2. Cada fake é compatível com seu Protocol? `mypy --strict` aceita?

**Sim.**

- Compatibilidade runtime por `@runtime_checkable` coberta em
  `tests/unit/fakes/test_fakes_satisfy_ports.py:72-110`.
- Compatibilidade estática validada por `mypy --strict` sobre os próprios fakes e
  o test file: `Success: no issues found in 10 source files`.
- Os ports continuam tipados como `Protocol` com `@runtime_checkable` em
  `src/inteligenciomica_eval/domain/ports.py:255-257`.

### 3. `InMemoryResultWriter` / `InMemoryResultReader`: `exists` / `update_metrics` / `load` espelham o contrato do `ParquetStorage`?

**Sim, no escopo do contrato do domínio e da idempotência por `row_id`.**

- `ParquetStorage.append()` é last-write-wins por `row_id`:
  `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:330-335`,
  `:397-405`.
- `InMemoryResultWriter.append()` também sobrescreve por `row_id`:
  `tests/fakes/storage.py:54-64`.
- O comportamento é testado explicitamente em
  `tests/unit/fakes/test_fakes_satisfy_ports.py:312-319`.
- `ParquetStorage.update_metrics()` altera apenas as colunas de métricas:
  `parquet_storage.py:438-490`.
- `InMemoryResultWriter.update_metrics()` preserva os demais campos e troca apenas
  `metrics` via `dataclasses.replace`:
  `tests/fakes/storage.py:65-79`;
  prova em `test_fakes_satisfy_ports.py:390-404`.
- `ParquetStorage.load()` filtra por `round_id` e `phase`:
  `parquet_storage.py:523-563`.
- `InMemoryResultReader.load()` replica os mesmos filtros:
  `tests/fakes/storage.py:103-119`;
  prova em `test_fakes_satisfy_ports.py:334-382`.
- `exists()` continua orientado a `row_id`:
  `parquet_storage.py:492-518`;
  `tests/fakes/storage.py:81-90`;
  prova em `test_fakes_satisfy_ports.py:299-310`.

Observação: o `ParquetStorage.exists()` checa arquivo presente e `generated_answer`
não-nulo (`parquet_storage.py:493-513`). No fake, a presença da linha já implica uma
`EvaluationResult` válida em memória, então a simplificação não muda a semântica
observável dos testes de unit.

### 4. Fakes de métrica permitem injetar `NaN`?

**Sim.**

- `FakeMetricSuite(inject_nan=True)` retorna `Layer1Metrics` todo em `NaN`:
  `tests/fakes/metrics.py:47-65`.
- `FakeRubricJudge(inject_nan=True)` retorna `RubricResult.score = NaN`:
  `tests/fakes/metrics.py:77-95`.
- `FakeDeterministicMetric(inject_nan=True)` retorna `bertscore_f1 = NaN`:
  `tests/fakes/metrics.py:106-125`.
- A cobertura dos caminhos ADR-007 está em
  `tests/unit/fakes/test_fakes_satisfy_ports.py:551-573`.

### 5. Fakes são determinísticos e sem I/O/rede?

**Sim.**

- A arquitetura exige fakes in-memory e sem GPU/rede em §11.2:
  `docs/arquitetura_detalhada_validacao_inteligenciomica.md:794-796`.
- `StubRetriever`, `FakeGenerator`, `FakeMetricSuite`, `FakeRubricJudge`,
  `FakeDeterministicMetric`, `FakeStats` e `FakeVLLMServerManager` têm comportamento
  fixo ou derivado deterministicamente dos inputs:
  `tests/fakes/retrieval.py:13-49`,
  `tests/fakes/generation.py:31-97`,
  `tests/fakes/metrics.py:38-125`,
  `tests/fakes/data_readers.py:85-144`,
  `tests/fakes/servers.py:47-99`.
- Os testes verificam repetibilidade explícita em vários pontos:
  `tests/unit/fakes/test_fakes_satisfy_ports.py:138-144`,
  `:163-185`,
  `:246-250`,
  `:267-269`,
  `:286-290`,
  `:455-480`,
  `:533-540`.
- Não há imports de infra real nem libs de I/O/rede em `tests/fakes/` e
  `tests/factories/`; os módulos importam apenas stdlib + `inteligenciomica_eval.domain`.

### 6. Factories geram entidades válidas com overrides e são determinísticas?

**Sim.**

- `make_row_id()` usa `RowId.from_cell(...)`, portanto o `row_id` é determinístico por
  componentes da célula: `tests/factories/factories.py:30-59`;
  `src/inteligenciomica_eval/domain/value_objects.py:212-241`.
- `make_question()`, `make_generated_answer()`, `make_metric_vector()`,
  `make_evaluation_result()` e `make_config_aggregate()` constroem diretamente os tipos
  de domínio válidos e aceitam overrides relevantes:
  `tests/factories/factories.py:62-250`.
- As invariantes de domínio são as mesmas das entidades/VOs reais, então uma factory
  inválida falharia na própria construção:
  `src/inteligenciomica_eval/domain/entities.py:26-240`;
  `src/inteligenciomica_eval/domain/value_objects.py:31-241`.
- Não há fonte de aleatoriedade, relógio ou contador global nas factories; os defaults
  são fixos e os resultados só variam pelos argumentos passados.

### 7. DoD §14.2; `import-linter`; fakes não puxam infra real?

**Sim.**

- `from __future__ import annotations` está no topo dos módulos auditados:
  `tests/fakes/retrieval.py:1`,
  `tests/fakes/generation.py:1`,
  `tests/fakes/metrics.py:1`,
  `tests/fakes/storage.py:1`,
  `tests/fakes/data_readers.py:1`,
  `tests/fakes/servers.py:1`,
  `tests/factories/factories.py:1`,
  `tests/fakes/__init__.py:1`,
  `tests/factories/__init__.py:1`.
- As APIs públicas dos fakes/factories estão tipadas e documentadas.
- `uv run lint-imports` passou: `Contracts: 4 kept, 0 broken`.
- O `.importlinter` não define contratos para `tests/`, mas a inspeção direta dos
  imports em `tests/fakes/`/`tests/factories/` não mostra dependência de
  `infrastructure`, `pyarrow`, `openai`, `qdrant_client`, `ragas` ou equivalentes.

## Evidências de execução

### `pytest` focado nos fakes

```text
uv run pytest tests/unit/fakes/test_fakes_satisfy_ports.py -q
57 passed in 0.17s
```

### `mypy --strict` nos fakes/factories/testes

```text
uv run mypy --strict tests/fakes tests/factories tests/unit/fakes/test_fakes_satisfy_ports.py
Success: no issues found in 10 source files
```

### `lint-imports`

```text
uv run lint-imports
Contracts: 4 kept, 0 broken.
```

## Critérios de Aceitação

| Critério | Status |
|---|---|
| Fake tipado para cada um dos 11 ports da §5.1 | ✅ |
| Compatibilidade estrutural runtime (`isinstance`) | ✅ |
| Compatibilidade estática (`mypy --strict`) | ✅ |
| `InMemoryResultWriter`/`Reader` espelham contrato essencial do `ParquetStorage` | ✅ |
| Injeção de `NaN` para ADR-007 | ✅ |
| Fakes determinísticos e sem I/O/rede | ✅ |
| Factories válidas, com overrides, determinísticas | ✅ |
| `pytest` dos fakes e `lint-imports` confirmados | ✅ |

## Observações para Próximas Tarefas

- O gate de `import-linter` segue centrado em `src/`; se o projeto quiser transformar
  a restrição "tests não importam infra real" em regra automática, isso exigirá um
  contrato adicional específico para `tests/`.
