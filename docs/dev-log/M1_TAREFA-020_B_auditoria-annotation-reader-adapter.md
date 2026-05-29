# M1_TAREFA-020_B — Auditoria AnnotationReaderAdapter

**Data**: 2026-05-28
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E2 — Adapters de Avaliação
**Skill**: code-reviewer, test-engineer
**Prioridade / Tamanho**: P1 / S
**Resultado**: PASS / Approve

## Objetivo

Auditar a implementação da TAREFA-020-A (`AnnotationReaderAdapter`) contra o Prompt B
das linhas 974-995 de `docs/prompts_m1_tarefas_013_021_corrigido.md`, verificando:

- assinatura `read(self, run_id: str) -> list[CriticalAnnotation]`;
- retorno `[]` para `run_id` ausente e para arquivo de anotações inexistente;
- arquivo inexistente como Camada 3 desabilitada, com log INFO e sem `StorageError`;
- `StorageError` na construção para JSONL malformado ou `flag` fora de `{0, 1}`;
- `reload()` síncrono com retorno `int` e recarga efetiva;
- ausência de `async`/threading;
- cobertura mínima, `mypy --strict` e `lint-imports`.

## Arquivos Criados / Modificados

| Arquivo | Ação | Observação |
|---------|------|------------|
| `docs/dev-log/M1_TAREFA-020_B_auditoria-annotation-reader-adapter.md` | Criado | Este relatório de auditoria |

Arquivos auditados:

- `docs/dev-log/M1_TAREFA-020_A_annotation-reader-adapter.md`
- `docs/prompts_m1_tarefas_013_021_corrigido.md`
- `src/inteligenciomica_eval/infrastructure/adapters/annotation_reader.py`
- `tests/unit/infrastructure/adapters/test_annotation_reader.py`
- `tests/fixtures/annotations.jsonl`
- `src/inteligenciomica_eval/domain/ports.py`
- `src/inteligenciomica_eval/domain/errors.py`
- `src/inteligenciomica_eval/domain/value_objects.py`

## Achados

Nenhum achado bloqueador ou importante foi identificado. A implementação atende aos seis
itens do Prompt B e aos critérios de aceitação da TAREFA-020.

## Critérios do Prompt B

| Critério Prompt B | Evidência arquivo:linha | Gravidade / Resultado |
|-------------------|-------------------------|-----------------------|
| 1. Assinatura `read(self, run_id: str) -> list[CriticalAnnotation]`; parâmetro `run_id: str`; retorno não-Optional | `annotation_reader.py:64-75`; `ports.py:530-546`; probe `read_signature=(self, run_id: 'str') -> 'list[CriticalAnnotation]'`; `isinstance(adapter, AnnotationReaderPort)=True` | PASS |
| 2. `read(run_id)` retorna `[]` para run ausente; arquivo ausente loga INFO + dicionário vazio, sem `StorageError` | `annotation_reader.py:75`; `_load` em `annotation_reader.py:99-103`; testes `test_unknown_run_returns_empty_list` em `test_annotation_reader.py:87-92` e `test_missing_file_reads_empty_without_error` em `test_annotation_reader.py:105-114`; probe `missing_file_read=[]` e evento `annotation file not found, Camada 3 disabled` | PASS |
| 3. Arquivo malformado ou `flag` fora de `{0,1}` levanta `StorageError` na construção, não em `read()` | `__init__` carrega em `annotation_reader.py:56-58`; parsing em `annotation_reader.py:122-144`; testes em `test_annotation_reader.py:122-152`; probe confirmou `StorageError` para JSON inválido, campo ausente, `flag=2` e `row_id` inválido | PASS |
| 4. `reload()` existe, retorna `int` e recarrega o arquivo | `annotation_reader.py:77-93`; testes `TestReload` em `test_annotation_reader.py:169-197`; probe `reload_switch_total=2`, run antigo ausente após troca e novo run carregado | PASS |
| 5. É síncrono, sem `async` e sem threading | `annotation_reader.py:64`, `annotation_reader.py:77`; testes `TestSynchronous` em `test_annotation_reader.py:205-210`; probe `read_is_async=False`, `reload_is_async=False`; `rg` não encontrou uso de `threading`, `to_thread` ou `run_in_executor` no adapter | PASS |
| 6. Cobertura >= 90%; `mypy --strict`; `lint-imports` | Gates executados abaixo; cobertura total 96.82%; `annotation_reader.py` 100% | PASS |

## Probes Executados

### Assinatura, port e retorno

```text
runtime_port= True
read_signature= (self, run_id: 'str') -> 'list[CriticalAnnotation]'
reload_signature= (self, annotation_file: 'pathlib.Path | None' = None) -> 'int'
read_is_async= False
reload_is_async= False
round_1_type= list
round_1_len= 2
items_are_critical_annotations= True
missing_run= []
```

### Arquivo ausente

```text
missing_file_read= []
log_events= ['annotation file not found, Camada 3 disabled']
reload_missing_total= 0
```

### Erros na construção

```text
invalid_json StorageError read True
missing_row_id StorageError read True
flag_2 StorageError read True
bad_row_id StorageError read True
```

### `reload()`

```text
initial_r1= 1
reload_switch_total= 2
old_run_after_switch= []
new_r2_len= 1
new_r3_note= None
```

## Validação (DoD)

| Comando / Probe | Resultado |
|-----------------|-----------|
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` | PASS — `All checks passed!` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .` | PASS — `82 files already formatted` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src` | PASS — `Success: no issues found in 30 source files` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict tests/unit/infrastructure/adapters/test_annotation_reader.py` | PASS — `Success: no issues found in 1 source file` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` | PASS — 69 files, 178 dependencies, 4 contracts kept, 0 broken |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -v tests/unit/infrastructure/adapters/test_annotation_reader.py tests/unit/domain/test_ports_contract.py tests/unit/fakes/test_fakes_satisfy_ports.py` | PASS — 113 passed |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n 4` | PASS — 697 passed, 7 skipped, 96.82%; `annotation_reader.py` 100% |
| Probe de assinatura/port/retorno | PASS |
| Probe de arquivo ausente | PASS |
| Probe de erros na construção | PASS |
| Probe de `reload()` | PASS |
| Probe de sincronicidade / ausência de threading | PASS |

Warnings observados:

- `pytest-benchmark` avisa que benchmarks são desabilitados sob `xdist`.
- `ragas_metrics.py` emite `DeprecationWarning` de `langchain-community`.
- `bert_score` emite `UserWarning` de NumPy array não gravável ao carregar baseline.

Nenhum warning acima é bloqueador para a TAREFA-020.

## Conclusão

O `AnnotationReaderAdapter` implementa corretamente o contrato síncrono de
`AnnotationReaderPort`, trata arquivo ausente como Camada 3 desabilitada, materializa
anotações em `CriticalAnnotation` no construtor e falha cedo com `StorageError` para
entradas malformadas. `reload()` recarrega/troca o arquivo e retorna a contagem total.

Veredito: **PASS / Approve**.
