# M4_TAREFA-402_B — Auditoria do IngestHumanAnnotationUseCase

**Data**: 2026-06-01
**Milestone**: M4 — Decisão executiva da Rodada 1 (Camada 3 + Agregação + Estatística + Relatório)
**Épico**: E5
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / S

## Objetivo

Auditar a implementação da TAREFA-402A contra o prompt B de `docs/m4_tarefa_402.md`, verificando contrato, separação de camadas, persistência Parquet, cobertura de testes exigida e evidências de validação.

## Arquivos Revisados

- `src/inteligenciomica_eval/application/use_cases/ingest_annotation.py`
- `src/inteligenciomica_eval/domain/ports.py`
- `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py`
- `src/inteligenciomica_eval/infrastructure/factories.py`
- `src/inteligenciomica_eval/cli.py`
- `tests/unit/application/test_ingest_annotation.py`
- `tests/integration/repositories/test_parquet_annotation.py`
- `tests/unit/test_cli_annotate_export.py`
- `tests/fakes/storage.py`
- `tests/unit/domain/test_ports_contract.py`

## Decisões Técnicas Observadas

- O use case lê o JSONL diretamente via `Path.open`, em linha com a simplificação pedida no prompt.
- `ResultWriterPort` foi estendido com `update_annotation` e `current_annotation_flag`, com documentação explícita do delta de contrato M4.
- `ParquetStorage.update_annotation()` faz roundtrip local do arquivo Parquet sem `NotImplementedError` residual.
- O tratamento explícito de `bool` como inválido evita aceitar `true`/`false` JSON como `1`/`0`.

## Problemas Encontrados e Soluções

### ⚠️ Importante — fluxo público `annotate --ingest` ficou sem teste dedicado

**Arquivo**: `tests/unit/test_cli_annotate_export.py:255`

O PR altera a CLI pública com um novo modo `annotate --ingest`, mas os testes de CLI cobrem apenas `--export` e a exclusividade `--export + --ingest`. Não há teste exercitando `_run_ingest_annotate`, o encaminhamento de `--force`, nem a tabela-resumo final.

**Impacto**: a principal superfície de uso da TAREFA-402 é a CLI; hoje o comportamento do use case e do repositório está coberto, mas o caminho real do usuário permanece sem proteção contra regressões de wiring, tratamento de erro e parsing de opções.

**Correção esperada**: adicionar testes unitários de CLI para pelo menos:
- sucesso com `--ingest`
- propagação de `--force`
- erro amigável quando o arquivo JSONL não existe

## Validação (DoD)

- `uv run pytest tests/unit/application/test_ingest_annotation.py tests/integration/repositories/test_parquet_annotation.py -v` → **14 passed**
- `uv run lint-imports` → **4 contratos OK / 0 quebrados**
- Evidência fornecida pela execução 402A:
  - `ruff` ✅
  - `mypy --strict src` ✅
  - cobertura global **91.58%** ✅
  - suíte completa **952 passed** ✅

## Critérios de Aceitação

| Critério | Evidência | Status |
|---|---|---|
| Use case implementado sem importar `infrastructure` | `src/inteligenciomica_eval/application/use_cases/ingest_annotation.py:9-10` | PASS |
| Flag inválido gera WARNING, pula e conta em `n_invalid` | `src/inteligenciomica_eval/application/use_cases/ingest_annotation.py:101-109`; `tests/unit/application/test_ingest_annotation.py:82-112` | PASS |
| `flag=null` é pulado silenciosamente | `src/inteligenciomica_eval/application/use_cases/ingest_annotation.py:97-99`; `tests/unit/application/test_ingest_annotation.py:118-135` | PASS |
| Idempotência com `force=False` e sobrescrita com `force=True` | `src/inteligenciomica_eval/application/use_cases/ingest_annotation.py:134-148`; `tests/unit/application/test_ingest_annotation.py:142-188` | PASS |
| `row_id` inexistente conta em `n_missing_row_id` sem exceção | `src/inteligenciomica_eval/application/use_cases/ingest_annotation.py:124-132`; `tests/unit/application/test_ingest_annotation.py:195-209` | PASS |
| `update_annotation` adicionado ao `ResultWriterPort` e documentado como delta M4 | `src/inteligenciomica_eval/domain/ports.py:525-562` | PASS |
| Implementação real em `ParquetStorage` sem stub | `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:523-573` | PASS |
| Roundtrip `update_annotation -> load` correto no Parquet | `tests/integration/repositories/test_parquet_annotation.py:95-117` | PASS |
| `lint-imports` OK | execução local da auditoria | PASS |
| `mypy --strict` e cobertura >= 85% | evidência fornecida pela 402A | PASS |
| CLI `annotate --ingest` coberta por teste | ausência de teste dedicado; apenas exclusividade em `tests/unit/test_cli_annotate_export.py:255-283` | FAIL |

## Parecer Final

**FAIL**

Implementação e persistência estão corretas no núcleo da tarefa, mas a alteração da CLI pública `annotate --ingest` ficou sem teste dedicado. Antes do aceite final da TAREFA-402, recomendo adicionar cobertura de CLI para o novo fluxo e então repetir a auditoria.

## Observações para Próximas Tarefas

- O nome do arquivo de prompt usa `application/ingest_annotation.py`, mas a implementação seguiu o padrão já existente do repositório em `application/use_cases/`. A escolha é coerente com a estrutura atual e não foi tratada como divergência.
- Não houve necessidade de atualizar `CLAUDE.md` nesta rodada: a auditoria não introduziu novo padrão arquitetural, apenas exigência de cobertura para a nova superfície de CLI.
