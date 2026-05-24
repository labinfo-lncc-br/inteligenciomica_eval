# M0_TAREFA-009_B — Auditoria ParquetStorage

**Data**: 2026-05-24
**Milestone**: M0 — Bootstrap e Fundação
**Épico**: E0
**Skill**: code-reviewer + data-engineer + python-clean-architecture
**Prioridade / Tamanho**: P0 / M

## Objetivo

Auditar a implementação da TAREFA-009 em `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py`
contra `docs/arquitetura_detalhada_validacao_inteligenciomica.md` §5.3/§5.4, ADR-002, ADR-009,
DoD §14.2, a skill `data-engineer` e o baseline `python-clean-architecture` §1, sem reescrever a implementação.

## Escopo / Premissas

- O workspace não contém um commit/PR isolado; a auditoria foi feita sobre o diff local atual da TAREFA-009.
- A referência textual "Nota de operacionalização adicional, item 3" não foi localizada no repositório. Onde o prompt explicita a expectativa de `last-write-wins documentado`, tratei isso como requisito adicional do escopo.
- Os achados abaixo citam `arquivo:linha`.

## Resultado

**PASS**

Os bloqueios anteriores de schema foram corrigidos, os ports seguem compatíveis, o roundtrip continua fiel para o agregado de domínio, o particionamento físico está correto, a estratégia de overwrite agora é `last-write-wins` com teste dedicado, e os gates focados (`pytest`, cobertura, `lint-imports`, `ruff`, `mypy`) estão verdes.

## Tabela de divergências

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| A docstring da classe `ParquetStorage` ainda descreve `append` como `first-write-wins`, embora a implementação e a docstring do método já tenham migrado para `last-write-wins`; é inconsistência documental, não funcional | `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:330-333` | Média |

## Verificação item a item

### 1. Implementa `ResultWriterPort` e `ResultReaderPort` com as assinaturas da TAREFA-005?

**Sim.**

- `append(self, result: EvaluationResult) -> None`: `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:396`
- `update_metrics(self, row_id: RowId, metrics: MetricVector) -> None`: `parquet_storage.py:433`
- `exists(self, row_id: RowId) -> bool`: `parquet_storage.py:487`
- `load(self, *, round_id: str, phase: str | None = None) -> ResultFrame`: `parquet_storage.py:518`
- As assinaturas batem com os Protocols em `src/inteligenciomica_eval/domain/ports.py:398-450`.
- A conformidade estrutural foi exercitada por `isinstance()` em `tests/integration/repositories/test_parquet_storage.py:505-516`.

### 2. O schema bate com a TABELA do §5.3?

**Sim.**

- `row_id`, `ragas_version`, `config_hash`, `metric_nan_fields`, `retry_count` existem: `parquet_storage.py:44,60-61,81-82`
- `retrieved_chunk_ids` e `retrieved_chunks_text` usam `list<string>`: `parquet_storage.py:65-66`
- `retrieval_scores` usa `list<float32>`: `parquet_storage.py:67`
- `critical_failure_flag` usa `int8 nullable`: `parquet_storage.py:78`
- `timestamp` usa `timestamp("us", tz="UTC")`: `parquet_storage.py:86`
- Os campos antes divergentes agora estão coerentes com §5.3:
  - `generated_answer` `nullable=False`: `parquet_storage.py:68`
  - `rubric_feedback` `nullable=False`: `parquet_storage.py:77`
  - `latency_ms`, `tokens_in`, `tokens_out` `nullable=False`: `parquet_storage.py:83-85`
- Os campos exigidos por §5.3 `row_id`, `metric_nan_fields`, `retry_count`, `config_hash`, `ragas_version` estão presentes e tipados corretamente: `parquet_storage.py:44,60-61,81-82`

### 3. O mapeador `to_row`/`from_row` é dedicado e faz roundtrip fiel? NaN e None ficam distintos?

**Sim.**

- O mapeador é dedicado e separado do repositório: `to_row()` em `parquet_storage.py:167-236`; `from_row()` em `:239-294`
- NaN de métricas/final score é serializado como `None` e reconstruído como `float("nan")`: `_nan_to_none()` / `_none_to_nan()` em `:147-154`; uso em `to_row()` `:215-228` e `from_row()` `:269-279`
- `critical_failure_flag=None` permanece distinto de métrica `NaN` por tipo de coluna: `parquet_storage.py:225-228,284-285`
- `generated_answer` deixou de ter fallback silencioso para `""`; a desserialização agora respeita o campo obrigatório: `parquet_storage.py:257-267`
- O roundtrip está coberto em `tests/unit/repositories/test_row_mapper.py:392-479` e em `tests/integration/repositories/test_parquet_storage.py:256-369`
- A distinção NaN vs `None` está testada explicitamente em `tests/unit/repositories/test_row_mapper.py:463-479`

### 4. Particionamento físico = `round_id/experiment_phase/base/llm`?

**Sim.**

- Escrita em `append()`: `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:417-423`
- A arquitetura define esse layout em `docs/arquitetura_detalhada_validacao_inteligenciomica.md:432`
- Teste de integração cobre o diretório esperado: `tests/integration/repositories/test_parquet_storage.py:172-186`

### 5. Idempotência (ADR-009): `exists(row_id)` correto; append duplicado não cria duplicata; `update_metrics` completa sem reescrever o resto?

**Sim, com uma ressalva documental.**

- `exists(row_id)` está consistente com o ADR-009 e com §5.4: procura o arquivo e só considera completo se `generated_answer IS NOT NULL`: `parquet_storage.py:487-512`; ADR em `docs/arquitetura_detalhada_validacao_inteligenciomica.md:516-523`; contrato geração→julgamento em `docs/arquitetura_detalhada_validacao_inteligenciomica.md:434-436`
- `append` duplicado não cria duplicata física e agora sobrescreve o arquivo existente (`last-write-wins`): implementação em `parquet_storage.py:396-431`; testes em `tests/integration/repositories/test_parquet_storage.py:202-225`
- `update_metrics` atualiza só as 8 métricas + `metric_nan_fields`, preservando o restante das colunas: `parquet_storage.py:460-480`; teste em `tests/integration/repositories/test_parquet_storage.py:377-465`
- A semântica `last-write-wins` está documentada na docstring do método `append()`: `parquet_storage.py:397-407`

Ressalva:

- A docstring da classe ainda menciona `first-write-wins`: `parquet_storage.py:330-333`

### 6. Falhas de I/O viram `StorageError` sem vazar info sensível?

**Sim, dentro do escopo auditado.**

- O adapter encapsula falhas de I/O em `StorageError` em `append`, `update_metrics`, `exists` e `load`: `parquet_storage.py:428-434,484-488,512-513,558-560`
- `StorageError` é exceção específica de domínio, conforme DoD §14.2: `src/inteligenciomica_eval/domain/errors.py:247-258`; DoD em `docs/arquitetura_detalhada_validacao_inteligenciomica.md:911-917`
- Há sanitização por `_safe_msg()`: `parquet_storage.py:157-159`
- O wrapping para arquivo corrompido segue coberto em `tests/integration/repositories/test_parquet_storage.py:473-497`
- A redaction agora tem testes dedicados em `tests/unit/repositories/test_row_mapper.py:487-509`

### 7. `import-linter`: `domain`/`application` não importam este módulo nem `pyarrow`; direção infra -> domain?

**Sim.**

- O módulo auditado importa `pyarrow` apenas na infraestrutura: `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:10-11`
- Os contratos proíbem `pyarrow` e `infrastructure` em `domain`/`application`: `.importlinter:8-29,34-54`
- Execução confirmada: `uv run lint-imports` → `Contracts: 4 kept, 0 broken`

### 8. Logging estruturado sem despejar textos longos? Cobertura >=80%? DoD §14.2?

**Sim.**

- Logging estruturado com `structlog` e eventos curtos: `parquet_storage.py:31,386-390,425-427,480`
- `row_id` é truncado para 12 chars nos logs, reduzindo ruído: `parquet_storage.py:425-427,480`
- `from __future__ import annotations` no topo: `parquet_storage.py:1`, `tests/unit/repositories/test_row_mapper.py:1`, `tests/integration/repositories/test_parquet_storage.py:1`
- Docstrings públicas presentes nas funções/classes auditadas: `parquet_storage.py:111-126,148,153,158,171-184,240-250,303-309,324-351,397-407,434-445,488-500,520-529,565-571`
- Cobertura focada do módulo: **93%**, acima de 80%
- `ruff check`, `ruff format --check`, `mypy --strict src` e `lint-imports`: OK

## Evidências de execução

### `pytest` focado

```text
uv run pytest tests/integration/repositories/test_parquet_storage.py tests/unit/repositories/test_row_mapper.py -q
77 passed in 0.66s
```

### Cobertura focada do adapter

```text
uv run pytest tests/integration/repositories/test_parquet_storage.py tests/unit/repositories/test_row_mapper.py --cov=inteligenciomica_eval.infrastructure.repositories.parquet_storage --cov-report=term-missing --cov-fail-under=0 -q

Name                                                                       Stmts   Miss Branch BrPart  Cover   Missing
----------------------------------------------------------------------------------------------------------------------
src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py     134      9     16      1    93%   431-434, 487-488, 513, 547, 559
----------------------------------------------------------------------------------------------------------------------
TOTAL                                                                        134      9     16      1    93%
77 passed in 0.88s
```

### `lint-imports`

```text
uv run lint-imports
Contracts: 4 kept, 0 broken.
```

### Gates adicionais de DoD

```text
uv run ruff check src tests
All checks passed!

uv run ruff format --check src tests
50 files already formatted

uv run mypy --strict src
Success: no issues found in 22 source files
```

## Conclusão

O adapter está **aprovado** para a TAREFA-009 no escopo auditado. Os bloqueios de schema do §5.3 foram corrigidos, a semântica `last-write-wins` foi implementada e provada por teste, a sanitização de mensagens passou a ter cobertura explícita, e os gates técnicos exigidos pela auditoria estão verdes. O único ponto residual é a docstring da classe `ParquetStorage`, que ainda descreve a política antiga de overwrite e deveria ser alinhada ao comportamento atual.
