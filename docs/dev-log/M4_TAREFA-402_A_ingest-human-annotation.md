# M4_TAREFA-402_A — IngestHumanAnnotationUseCase

**Data**: 2026-05-31
**Milestone**: M4 — Decisão executiva da Rodada 1
**Épico**: E5
**Skill**: python-engineer
**Prioridade / Tamanho**: P0 / S

## Objetivo

Implementar `IngestHumanAnnotationUseCase` em `application/use_cases/ingest_annotation.py`
e o flag `--ingest PATH [--force]` no subcomando `annotate` da CLI, conforme ADR-010
(workflow export→edit→ingest) e a nota de operacionalização M4 item 7.

## Arquivos Criados / Modificados

| Arquivo | Ação | Descrição |
|---------|------|-----------|
| `src/.../application/use_cases/ingest_annotation.py` | Criado | DTOs + use case |
| `src/.../domain/ports.py` | Modificado | `update_annotation` + `current_annotation_flag` em `ResultWriterPort` |
| `src/.../infrastructure/repositories/parquet_storage.py` | Modificado | Implementação dos dois novos métodos |
| `src/.../infrastructure/factories.py` | Modificado | `build_annotation_writer` adicionada |
| `src/.../cli.py` | Modificado | Flag `--ingest`, `--force` e função `_run_ingest_annotate` |
| `tests/fakes/storage.py` | Modificado | `update_annotation` + `current_annotation_flag` em `InMemoryResultWriter` |
| `tests/unit/domain/test_ports_contract.py` | Modificado | `_StubResultWriter` estendido com os dois novos métodos |
| `tests/unit/application/test_ingest_annotation.py` | Criado | 8 testes unitários (a–f + 2 extras) |
| `tests/integration/repositories/test_parquet_annotation.py` | Criado | 6 testes de integração roundtrip |

## Decisões Técnicas

### Extensão de contrato `ResultWriterPort` (delta de §5.1 — M4)

Dois métodos novos declarados e documentados como delta explícito:

- **`update_annotation(row_id, *, critical_failure_flag, critical_failure_note="")`**:
  persiste exclusivamente os campos de anotação sem tocar métricas ou proveniência.
  Implementação: lê o arquivo Parquet pelo `row_id`, aplica `set_column` nos dois
  campos e reescreve o arquivo (padrão já estabelecido em `update_metrics`).

- **`current_annotation_flag(row_id) -> int | None`**: retorna o valor atual do flag
  para verificação de idempotência no use case. Segue o mesmo padrão de `exists()`,
  que já é uma operação de leitura no `ResultWriterPort`. O campo `critical_failure_note`
  vazio é persistido como `None` (NULL no Parquet), mantendo a semântica nullable do schema.

### Verificação de idempotência (ADR-009)

O use case usa `current_annotation_flag(row_id)` para checar se a linha já foi anotada.
Se o resultado é não-null e `force=False`, conta em `n_skipped` e pula. Se `force=True`,
sobrescreve. Esse padrão mantém a lógica de negócio exclusivamente na camada application.

### Leitura direta do JSONL via `pathlib.Path.open`

Conforme spec: não cria adapter desnecessário. O use case lê linha por linha com
`json.loads`, validando cada registro independentemente — erros por linha nunca
abortam o processamento total.

### Tipo `bool` em JSON

`True`/`False` Python (JSON `true`/`false`) são subclasse de `int` em Python. A validação
`isinstance(flag_raw, bool)` rejeita-os explicitamente — somente `0` e `1` inteiros são
aceitos, pois `flag ∈ {0, 1, null}` segundo o spec (inteiros, não booleanos).

### CLI `--force`

Flag adicionado ao subcomando `annotate` como `--force/--no-force` (padrão: `False`).
Passado diretamente ao `IngestAnnotationInput.force`. A factory `build_annotation_writer`
segue a mesma convenção da `build_annotation_reader` — `data_dir = config.parent / "data"`.

## Problemas Encontrados e Soluções

1. **`make_evaluation_result` não aceita `row_id`**: a factory exige que o `row_id` seja
   passado via `answer=make_generated_answer(row_id=...)`. Corrigido nos testes unitários.

2. **Import path nos testes**: o pytest adiciona `tests/` ao sys.path, portanto
   `from factories.factories import ...` e `from fakes.storage import ...` (sem prefixo `tests.`).

3. **`_StubResultWriter` no teste de contratos**: como `ResultWriterPort` é
   `@runtime_checkable`, o `isinstance` verifica presença de todos os métodos.
   `_StubResultWriter` precisou ser estendido com `update_annotation` e
   `current_annotation_flag`.

## Validação (DoD)

```
uv run ruff check .                  → All checks passed
uv run ruff format --check .         → 121 files already formatted
uv run mypy --strict src             → OK (0 errors)
uv run lint-imports                  → 4 kept, 0 broken
uv run pytest tests/unit/application/test_ingest_annotation.py
        tests/integration/repositories/test_parquet_annotation.py -v
                                     → 14 passed
uv run pytest --cov=src --cov-fail-under=85 -n 4 -q
                                     → 952 passed, 15 skipped — 91.58% coverage
```

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| Flag inválido: WARNING + pular, sem abortar — testado | ✅ `test_invalid_flag_does_not_abort` |
| `flag=null`: pulado silenciosamente — testado | ✅ `test_null_flag_skipped_silently` |
| Idempotência `force=False` pula anotada — testado | ✅ `test_idempotency_force_false_skips` |
| `force=True` sobrescreve — testado | ✅ `test_idempotency_force_true_overwrites` |
| `row_id` inexistente → `n_missing_row_id`, sem exceção — testado | ✅ `test_missing_row_id_does_not_raise` |
| `update_annotation` declarado como delta de contrato M4 | ✅ Docstrings + este relatório |
| Roundtrip `update_annotation → load → flag correto` — testado | ✅ `test_update_annotation_roundtrip` |
| `mypy --strict`; `lint-imports`; cobertura ≥ 85% | ✅ 91.58% |
| Use case em `application/` NÃO importa de `infrastructure/` | ✅ lint-imports KEPT |

## Observações para Próximas Tarefas

- `factories.py`: `build_annotation_writer` segue a mesma convenção de `build_annotation_reader`
  (data_dir = `config.parent / "data"`). TAREFA-403 pode reutilizar esta fábrica.
- `current_annotation_flag` no `ResultWriterPort` é um precedente para outros métodos de
  leitura leve no writer port — avaliar se deve migrar para `ResultReaderPort` em M5.
- O CLI `annotate` agora tem 3 modos: M3-interativo, M3-CSV batch, M4-export, M4-ingest.
  A tabela Rich do `--ingest` usa cores para facilitar interpretação do sumário.
