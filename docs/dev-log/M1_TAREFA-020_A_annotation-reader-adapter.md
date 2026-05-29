# M1_TAREFA-020_A — AnnotationReaderAdapter

**Data**: 2026-05-28
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E2 — Adapters de Avaliação
**Skill**: python-engineer
**Prioridade / Tamanho**: P1 / S

## Objetivo

Implementar o `AnnotationReaderAdapter` em
`src/inteligenciomica_eval/infrastructure/adapters/annotation_reader.py`, que lê anotações
humanas de falhas críticas (Camada 3, §5.3 / ADR-010) de um arquivo JSONL produzido
offline pelo especialista biomédico. Implementa `AnnotationReaderPort.read(run_id) ->
list[CriticalAnnotation]`, síncrono.

## Arquivos Criados / Modificados

| Arquivo | Ação | Observação |
|---------|------|------------|
| `src/.../adapters/annotation_reader.py` | **Criado** | Adapter síncrono (100% cobertura) |
| `tests/unit/.../adapters/test_annotation_reader.py` | **Criado** | 18 testes (fixture + tmp_path) |
| `tests/fixtures/annotations.jsonl` | **Criado** | 3 anotações (round_1×2, round_2×1; uma com `note: null`) |

## Decisões Técnicas

### 1. Carga ansiosa na construção (não lazy)

A spec (linha 935-936) exige carregar o arquivo **na construção** em
`dict[str, list[CriticalAnnotation]]` (run_id → anotações). Difere do `GoldChunkReaderAdapter`
(lazy): erros de formato aparecem cedo (no `__init__`), não na primeira `read()` — atende
ao item 3 do Prompt B ("StorageError NA CONSTRUÇÃO, não em read()").

### 2. Arquivo ausente = Camada 3 desabilitada (não é erro)

Camada 3 é offline e parcial (linha 929, 962). Se o arquivo não existir: loga
`INFO "annotation file not found, Camada 3 disabled"` e inicia com dict vazio →
`read(qualquer)` retorna `[]`. **Não** levanta `StorageError` (distinção do
`GoldChunkReaderAdapter`, onde arquivo ausente é erro).

### 3. `read` sempre retorna `list` — nunca `None`

Contrato §5.1: `list[CriticalAnnotation]`. `read(run_id)` devolve `list(self._by_run.get(run_id, []))`
— cópia fresca (mutação pelo caller não afeta o estado interno, comprovado por
`test_read_returns_fresh_copy`); `[]` para run_id inexistente.

### 4. Validação convertendo para o domínio

- `row_id` (str hex) → `RowId(value=...)`. Como `RowId.__post_init__` exige digest
  SHA-256 de 64 chars hex minúsculos, um `row_id` inválido levanta `ValueError`, capturado
  e reembrulhado em `StorageError`.
- `flag ∈ {0, 1}` — `StorageError` na construção se outro valor (não usa
  `InvalidCriticalFailureFlagError`, pois a spec/Prompt B pedem `StorageError`
  uniformemente para qualquer linha malformada).
- `note` opcional: `record.get("note")` → ausente ou `null` vira `None`.
- `StorageError` em `json.JSONDecodeError`/`KeyError`/`TypeError`/`ValueError`, com
  `lineno` e nome do arquivo na mensagem.

### 5. `reload(annotation_file=None) -> int`

Recarrega o arquivo corrente (ou um novo, se fornecido) e retorna a **contagem total** de
anotações somada sobre todos os run_id. Permite trocar o arquivo em runtime
(`test_reload_switches_file`) e captar anotações novas (`test_reload_picks_up_new_annotations`).

### 6. Síncrono (Nota M1 item 1)

Leitura local de arquivo, sem I/O de rede — sem `async`, sem threading. `read`/`reload`
não são coroutine functions (`TestSynchronous`).

## Validação (DoD)

```
uv run ruff check .            → All checks passed!
uv run ruff format --check .   → 82 files already formatted
uv run mypy --strict src       → Success: no issues found in 30 source files
uv run mypy --strict tests/.../test_annotation_reader.py → Success
uv run lint-imports            → 4 kept, 0 broken
uv run pytest tests/.../test_annotation_reader.py → 18 passed
uv run pytest --cov ... -n 4   → 697 passed, 7 skipped — 96.82% total; annotation_reader.py 100% (47/47, 10 branches)
```

Cobertura do adapter **100%** — acima do mínimo ≥ 90% exigido pela tarefa.

## Critérios de Aceitação (TAREFA-020)

| Critério | Evidência | Resultado |
|----------|-----------|-----------|
| `isinstance(adapter, AnnotationReaderPort)` | `TestProtocolConformance.test_satisfies_port` | PASS |
| `read(run_id)` → `list[CriticalAnnotation]`; `[]` para run inexistente | `TestRead.test_returns_annotations_for_run` / `test_unknown_run_returns_empty_list` | PASS |
| Arquivo ausente → `[]` sem exceção (loga INFO) | `TestMissingFile.test_missing_file_reads_empty_without_error` | PASS |
| `flag=2` → `StorageError` na construção (não em `read`) | `TestMalformed.test_flag_out_of_domain_raises_on_construction` | PASS |
| `reload()` → contagem total correta | `TestReload.test_reload_returns_total_count` (=3) | PASS |

## Observações para Próximas Tarefas

- Pronto para auditoria (Prompt B). Foco esperado: itens 1-3 (assinatura `read(run_id) ->
  list`, `[]` vs exceção, `StorageError` na construção).
- A TAREFA-021 (gate de integração M1) usará este adapter na Camada 3 do pipeline
  end-to-end.
