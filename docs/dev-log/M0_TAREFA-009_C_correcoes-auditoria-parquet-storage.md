# M0_TAREFA-009_C — Correções pós-auditoria ParquetStorage

**Data**: 2026-05-24
**Milestone**: M0 — Bootstrap e Fundação
**Épico**: E0
**Skill**: data-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Corrigir as divergências identificadas na auditoria `M0_TAREFA-009_B` (resultado: FAIL) e revalidar todos os gates do DoD §14.2.

---

## Divergências corrigidas

### BLOQUEADOR 1 — `generated_answer` nullable errado

**Problema**: `generated_answer` estava `nullable=True` no schema, mas §5.3 o define como `string` obrigatório. Além disso, `from_row()` silenciava NULL com `or ""`, perdendo fidelidade semântica.

**Correção**:
- `EVAL_SCHEMA`: `pa.field("generated_answer", pa.string(), nullable=False)`
- `from_row()`: removido o branch `if generated is not None else ""`; campo agora é simplesmente `str(row["generated_answer"])`, consistente com `nullable=False`.

**Arquivo**: `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:68,265`

---

### BLOQUEADOR 2 — `rubric_feedback` nullable errado e valor `None`

**Problema**: `rubric_feedback` estava `nullable=True` e `to_row()` sempre gravava `None`, divergindo de §5.3 (`string` obrigatório).

**Correção**:
- `EVAL_SCHEMA`: `pa.field("rubric_feedback", pa.string(), nullable=False)`
- `to_row()`: `"rubric_feedback": ""` (string vazia como placeholder até M2+ preencher via `RubricJudgeAdapter`)

**Arquivo**: `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:77,224`

---

### BLOQUEADOR 3 — `latency_ms`, `tokens_in`, `tokens_out` nullable errado e valor `None`

**Problema**: Os três campos estavam `nullable=True` e `to_row()` gravava `None`, divergindo de §5.3 (`int32` obrigatório).

**Correção**:
- `EVAL_SCHEMA`: `nullable=False` para os três campos
- `to_row()`: `"latency_ms": 0, "tokens_in": 0, "tokens_out": 0` (placeholder inteiro até M1+ preencher via `GeneratorAdapter`)

**Arquivo**: `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:83-85,232-234`

---

### ALTA — Estratégia `first-write-wins` → `last-write-wins`

**Problema**: O prompt da TAREFA-009 especifica explicitamente "estratégia last-write-wins por row_id na partição (documente)". A implementação usava `first-write-wins` (append retornava sem escrever se o arquivo existia). A auditoria identificou divergência entre a semântica implementada e a especificada.

**Correção**:
- `append()`: removido o `if self.exists(...): return` inicial
- `append()` agora **sempre escreve** o arquivo, sobrescrevendo se existir (last-write-wins)
- Logging diferenciado: `row_overwritten` quando o arquivo pré-existia, `row_appended` quando novo
- Docstring atualizada: responsabilidade de consultar `exists()` antes de invocar `append()` é explicitamente do pipeline (use-case), não do storage
- Novo teste de integração `test_append_last_write_wins_updates_data` verifica que dados de overwrite são persistidos corretamente

**Semântica resultante**:
- `exists(row_id)` — consulta do pipeline para decidir se pula a computação upstream
- `append(result)` — persiste incondicionalmente (last-write-wins)
- `update_metrics(row_id, metrics)` — atualiza apenas colunas de métrica (inalterado)

**Arquivo**: `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:396-434`

---

### MÉDIA — Falta de teste de `_safe_msg`

**Problema**: A sanitização de mensagens de erro existia em `_safe_msg()`, mas não havia testes provando que paths absolutos não vazam em `StorageError`.

**Correção**: Adicionada classe `TestSafeMsg` em `tests/unit/repositories/test_row_mapper.py` com 4 testes:
- `test_absolute_unix_path_redacted` — path `/home/...` → `<path>`
- `test_nested_hive_path_redacted` — path Hive `/var/.../round_id=round_1/...` → `<path>`
- `test_message_without_paths_unchanged` — mensagem sem path não é alterada
- `test_multiple_paths_all_redacted` — múltiplos paths todos substituídos

---

## Arquivos modificados

| Arquivo | Mudança |
|---|---|
| `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py` | Schema (3 campos), `to_row` (3 defaults), `from_row` (remove None branch), `append` (last-write-wins) |
| `tests/unit/repositories/test_row_mapper.py` | +`TestSafeMsg` (4 testes), import `_safe_msg` |
| `tests/integration/repositories/test_parquet_storage.py` | Atualizado comentário em `test_append_twice_no_duplicate`, +`test_append_last_write_wins_updates_data` |

---

## Validação (DoD §14.2)

| Gate | Resultado |
|---|---|
| `ruff check` | ✅ Sem erros |
| `ruff format --check` | ✅ Formatado |
| `mypy --strict src` | ✅ 0 erros (22 arquivos) |
| `lint-imports` | ✅ 4/4 contratos KEPT |
| `pytest` total | ✅ **476/476 passed** |
| Cobertura total | ✅ 96.43% (threshold: 85%) |
| Cobertura `parquet_storage.py` | ✅ 93% |
| Schema §5.3 materializado | ✅ `generated_answer`, `rubric_feedback`, `latency_ms/tokens_in/tokens_out` agora `nullable=False` |
| Estratégia documentada | ✅ `last-write-wins` implementada e testada |
| Redação de paths em `StorageError` | ✅ Provada por `TestSafeMsg` |
