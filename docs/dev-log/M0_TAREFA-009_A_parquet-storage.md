# M0_TAREFA-009_A — ParquetStorage (infrastructure/repositories)

**Data**: 2026-05-24
**Milestone**: M0 — Fundação
**Épico**: E0
**Skill**: data-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Implementar `ParquetStorage` em `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py`, que realiza persistência e leitura idempotente de linhas tidy do schema §5.3 em Parquet particionado, implementando `ResultWriterPort` e `ResultReaderPort`.

---

## Arquivos Criados / Modificados

| Arquivo | Ação | Descrição |
|---|---|---|
| `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py` | Criado | Implementação completa: schema, mapeador, `ParquetStorage` |
| `tests/unit/repositories/__init__.py` | Criado | Pacote de testes unitários de repositórios |
| `tests/unit/repositories/test_row_mapper.py` | Criado | 41 testes unitários do mapeador `to_row`/`from_row` |
| `tests/integration/repositories/__init__.py` | Criado | Pacote de testes de integração de repositórios |
| `tests/integration/repositories/test_parquet_storage.py` | Criado | 31 testes de integração com `tmp_path` (sem serviços externos) |

---

## Decisões Técnicas

### 1. NaN → NULL para métricas (§5.4 `WHERE IS NULL`)

Os campos de métricas (`answer_correctness`, …, `rubric_biomed_score`) e `final_score` são `nullable=True` em PyArrow. NaN no `MetricVector` é mapeado para `None`/NULL no Parquet na escrita (`_nan_to_none`), e NULL é mapeado de volta para NaN na leitura (`_none_to_nan`). Isso:
- Habilita o filtro `WHERE answer_correctness IS NULL` de §5.4 (passada de julgamento seleciona linhas geradas-mas-não-julgadas).
- Mantém a distinção semântica entre float NULL (métrica não computada) e int8 NULL (`critical_failure_flag` não anotado): tipos de coluna diferentes no Parquet garantem a distinção mesmo que ambos sejam `None` no dict Python.

### 2. `nullable=False` para colunas de proveniência

Campos como `run_id`, `round_id`, `judge_model`, etc. são `nullable=False` no schema. Quando não disponíveis na `EvaluationResult` (M0), são preenchidos com strings vazias/padrão via `RowProvenance`. Isso evita NULL onde a semântica é "ainda não configurado", não "ausente".

### 3. Idempotência: one-file-per-row, first-write-wins (ADR-009)

Cada linha é escrita em `{partition_dir}/{row_id_hex}.parquet`. A estratégia é **first-write-wins**: `append` de um `row_id` já existente é silenciosamente ignorado. `exists()` verifica presença do arquivo + `generated_answer IS NOT NULL` (critério de completude: a passada de geração concluiu).

### 4. `ParquetFile.read()` em vez de `pq.read_table()` para leitura de arquivo individual

`pq.read_table(path)` dentro de diretório com Hive partitioning infere automaticamente as colunas de partição como `dictionary<string>`, conflitando com as mesmas colunas armazenadas no arquivo como `string`. A solução é usar `pq.ParquetFile(path).read()`, que lê o arquivo diretamente sem inferência Hive.

### 5. `RowProvenance` como dataclass imutável

Os campos de proveniência que não existem em `EvaluationResult` (config-level: judge_model, embedding_model, etc.) são agrupados em `RowProvenance`. O `ParquetStorage` recebe esses campos no construtor e cria uma instância única que é repassada a `to_row`. Isso torna o mapeador puro e testável de forma independente.

### 6. Particionamento físico: Hive-style explícito

Diretórios criados em `{base_dir}/round_id={r}/experiment_phase={p}/base={b}/llm={l}/`. Cada arquivo dentro é nomeado pelo `row_id` SHA-256 hexadecimal (64 chars). A busca por `row_id` usa `rglob(f"{row_id_hex}.parquet")` — adequado para a escala de centenas a poucos milhares de linhas do M0.

### 7. `update_metrics` — read-modify-write em arquivo único

Localiza o arquivo pelo `row_id`, lê com `ParquetFile.read()`, atualiza as 9 colunas de métrica (8 métricas + `metric_nan_fields`) via `table.set_column()`, e grava de volta no mesmo path. `final_score` e demais colunas ficam intocados. Thread safety não garantida (M0 scope).

---

## Problemas Encontrados e Soluções

### `ArrowTypeError: Field round_id incompatible types: string vs dictionary`

**Problema**: `pq.read_table(file_path)` detectou o diretório pai como Hive-particionado e inferiu `round_id`, `experiment_phase`, `base`, `llm` como `dictionary<string>`, conflitando com as colunas armazenadas diretamente no arquivo como `string`.

**Solução**: Substituir por `pq.ParquetFile(file_path).read()` nas operações de leitura de arquivo individual (`exists`, `update_metrics`, `load`). Este método lê o arquivo diretamente sem envolver o mecanismo de dataset/Hive do PyArrow.

---

## Validação (DoD)

| Gate | Resultado |
|---|---|
| `ruff check` | ✅ Sem erros |
| `ruff format --check` | ✅ Formatado |
| `mypy --strict src/` | ✅ 0 erros |
| `lint-imports` | ✅ 4/4 contratos KEPT |
| `pytest` total | ✅ 471/471 passed |
| Cobertura total | ✅ 96.43% (threshold: 85%) |
| Cobertura `parquet_storage.py` | ✅ 93% |
| Schema §5.3 completo | ✅ 40 campos, tipos pyarrow conforme spec |
| Particionamento `round_id/phase/base/llm` | ✅ Verificado por teste de integração |
| Roundtrip `append → load` | ✅ Incluindo NaN/None preservation |
| `exists(row_id)` correto | ✅ True após append, False antes |
| append duplicado sem duplicação | ✅ First-write-wins confirmado |
| `update_metrics` sem tocar outras colunas | ✅ Testado |
| `StorageError` em I/O failure | ✅ Testado com arquivo corrompido |
| Port contracts (`isinstance`) | ✅ `ResultWriterPort` e `ResultReaderPort` |

---

## Critérios de Aceitação

- [x] Schema do §5.3 materializado (todos os campos e tipos); particionamento round/phase/base/llm.
- [x] Roundtrip `append → load` reconstrói `EvaluationResult` equivalente (NaN/None preservados).
- [x] `exists(row_id)` correto; reexecutar `append` do mesmo `row_id` NÃO duplica.
- [x] `update_metrics` completa métricas de linha gerada-mas-não-julgada (§5.4) sem tocar o resto.
- [x] Falha de I/O ⇒ `StorageError`; cobertura ≥ 80% (adapter de I/O) — obtido 93%.

---

## Observações para Próximas Tarefas

- **Campos de proveniência incompletos (M1+)**: `run_id`, `judge_model`, `embedding_model`, `chunk_strategy`, `prompt_version`, `vllm_version`, `ragas_version`, `config_hash` estão no schema mas precisam ser preenchidos pelos adapters de geração/julgamento (TAREFA-101, TAREFA-201). Por ora ficam com defaults `""` / `"unknown"`.
- **`latency_ms`, `tokens_in`, `tokens_out`**: também ausentes da `EvaluationResult` atual. Serão preenchidos pelo `GeneratorAdapter` (M1).
- **`rubric_feedback`**: não armazenado em `EvaluationResult`; será adicionado pelo `RubricJudgeAdapter` (M2).
- **Thread safety**: A atual estratégia file-per-row é safe para pipelines single-process. Para pipelining paralelo (M3+), considerar write via tmpfile + rename atômico ou lock de partição.
- **Escala**: `rglob` para `exists()` é O(número de partições). Para M3+ com milhares de linhas, considerar um índice em memória populado no `__init__` via scan inicial do `base_dir`.
