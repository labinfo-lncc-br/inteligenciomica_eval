# M6_TAREFA-604_B — Auditoria Codex do manual de operação

**Data**: 2026-06-03  
**Prompt**: `M6-604B`  
**Papel**: `code-reviewer`  
**Resultado**: **FAIL / Request changes**

## Verificações executadas

- Leitura do prompt em `docs/m6_tarefas_604.md`
- Leitura dos artefatos entregues:
  - `docs/operations_manual.md`
  - `scripts/validate_manual.py`
  - `README.md`
  - `docs/dev-log/M6_TAREFA-604_A_operations-manual.md`
- Cruzamento com implementação real:
  - `src/inteligenciomica_eval/cli.py`
  - `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py`
  - `config/model_registry.yaml`
- Execução do smoke-test:

```text
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/validate_manual.py

  ielm-eval version              OK
  ielm-eval run                  OK
  ielm-eval status               OK
  ielm-eval annotate             OK
  ielm-eval analyze              OK
  ielm-eval report               OK
  ielm-eval validate-judge       OK

PASS — todos os subcomandos validados existem na CLI.
```

## Divergências

| Critério | Seção / arquivo:linha | Gravidade | Divergência |
|---|---|---|---|
| Execução da Rodada 1 documenta comportamento real | `docs/operations_manual.md:276-283`, `src/inteligenciomica_eval/cli.py:108-112` | **BLOQUEADOR** | O manual afirma que `ielm-eval run --config ...` é a execução completa da Rodada 1 e marca a limitação apenas como dependência de hardware GH200. O código atual, porém, aborta sempre que `--dry-run` não é usado, com a mensagem `Full run not yet implemented`. O documento operacional está descrevendo um fluxo que a CLI atual não suporta. |
| Path/estrutura dos Parquets gerados | `docs/operations_manual.md:314-325`, `docs/operations_manual.md:539`, `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:330-337`, `:419-427`, `:657-667` | **IMPORTANTE** | A seção 5 documenta arquivos em `config/data/round-1/A/<run_id>_A_<llm_id>_<base_id>.parquet`, mas o storage real persiste por partições Hive em `round_id=<...>/experiment_phase=<...>/base=<...>/llm=<...>/<row_id>.parquet`. O operador será direcionado ao caminho e ao padrão de nomes errados tanto para inspeção quanto para troubleshooting. |
| Smoke-test não valida blocos `curl` como prometido | `scripts/validate_manual.py:3-8`, `:141-172` | **IMPORTANTE** | O docstring afirma que blocos `curl http://localhost:...` são aceitos com validação sintática sem conexão. Na implementação isso não acontece: o script apenas coleta subcomandos `ielm-eval` e ignora completamente linhas `curl`. A proteção pedida no prompt contra comandos `curl` malformados não foi implementada. |

## Checklist do prompt B

| Item | Status | Evidência |
|---|---|---|
| 1. 11 seções presentes | ✅ | `docs/operations_manual.md` contém as Seções 1–11 |
| 2. Placeholders sem justificativa | ⚠️ | Não há `<a-definir>`, mas há marcadores `[PENDENTE: ...]` justificados; sem bloqueio adicional |
| 3. Sem segredos/credenciais embutidas | ✅ | Manual usa `localhost` e nomes de env vars |
| 4. Regra GPU juiz=3 / geradores=0–2 em 2 ondas | ✅ | `docs/operations_manual.md:163-176`, consistente com `config/model_registry.yaml` |
| 5. Retomada por `row_id` | ✅ | Descrição em `docs/operations_manual.md:301-309`, consistente com ADR-009 e storage last-write-wins |
| 6. Ingestão humana usa `--ingest` | ✅ | `docs/operations_manual.md:399-404` |
| 7. Troubleshooting não usa `--force-rows` | ✅ | Não há uso da flag inexistente |
| 8. Seção 9 marcada PENDENTE e sem `ielm-eval` executável | ✅ | `docs/operations_manual.md:449-462`; guard implementado em `scripts/validate_manual.py:64-88` |
| 9. `validate_manual.py` extrai blocos e testa subcomandos via `--help` | ✅ | `scripts/validate_manual.py:42-122` |
| 9b. `validate_manual.py` roda em CPU sem GPU/rede | ✅ | Confirmado pela execução acima |
| 10. README atualizado com link | ✅ | `README.md:54-58` |

## Recomendação

**Request changes**.

Prioridade de correção:

1. Corrigir a Seção 5 para refletir o estado real da CLI `run` atual, ou habilitar de fato o full run antes de documentá-lo como procedimento operacional.
2. Ajustar a documentação dos paths de Parquet e do troubleshooting para o layout real do `ParquetStorage`.
3. Implementar no `scripts/validate_manual.py` a verificação sintática mínima prometida para blocos `curl http://localhost:...`, ou reduzir explicitamente o escopo documentado do smoke-test.
