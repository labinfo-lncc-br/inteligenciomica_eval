# M2_TAREFA-022_B — Auditoria batch_invariant

**Data**: 2026-05-29
**Milestone**: M2 — Avaliação automática (Camadas 1+2, juiz determinístico)
**Épico**: E2
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / S
**Resultado**: PASS / Approve

## Objetivo

Auditar a implementação da TAREFA-022-A contra o Prompt B de
`docs/prompts_m2_tarefas_022_028.md`, verificando o contrato §4.3 / §5.3 para
`batch_invariant` e a propagação de `DeterminismRegime.JUDGE` do adapter até o
Parquet.

## Arquivos Auditados

- `src/inteligenciomica_eval/domain/entities.py`
- `src/inteligenciomica_eval/domain/value_objects.py`
- `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py`
- `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py`
- `tests/contract/test_batch_invariant_contract.py`
- `tests/contract/BATCH_INVARIANT_CHECKLIST.md`
- `pyproject.toml`
- `docs/dev-log/M2_TAREFA-022_A_contrato-batch-invariant.md`

## Veredito

Nenhuma divergência material encontrada. A implementação atende ao Prompt B.

## Critérios do Prompt B

| Critério | Evidência | Resultado |
|---|---|---|
| 1. `PrometheusJudgeAdapter.determinism_regime == JUDGE` | `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py:85-87` | PASS |
| 2. `EvaluationResult.batch_invariant` existe e implementa o invariante §4.3 | `src/inteligenciomica_eval/domain/entities.py:165-184`, `src/inteligenciomica_eval/domain/entities.py:233-238` | PASS |
| 3. Schema Parquet inclui `batch_invariant` obrigatório | `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:42-58` | PASS |
| 4a. Teste do regime no adapter sem rede real | `tests/contract/test_batch_invariant_contract.py:73-85` | PASS |
| 4b. `with_metrics(..., JUDGE) -> batch_invariant=True` | `tests/contract/test_batch_invariant_contract.py:92-105` | PASS |
| 4c. Round-trip Parquet real com `True` persistido | `tests/contract/test_batch_invariant_contract.py:112-130` | PASS |
| 4d. Invariante validada/documentada | `tests/contract/test_batch_invariant_contract.py:155-200`, `src/inteligenciomica_eval/domain/entities.py:169-178` | PASS |
| 4e. `GENERATOR -> batch_invariant=False` round-trip | `tests/contract/test_batch_invariant_contract.py:132-147` | PASS |
| 5. Checklist gerado e sem `⚠ ausente` | `tests/contract/BATCH_INVARIANT_CHECKLIST.md:8-16` | PASS |
| 6. Sem mudança funcional indevida nos adapters de M1 | Diff restrito a `determinism_regime` no adapter e refactor semântico-preservante em `to_row` (`parquet_storage.py:203-205`) | PASS |
| 7. `lint-imports` e `mypy --strict` OK; DoD §14.2 | comandos executados nesta auditoria; marker `contract` em `pyproject.toml:143` | PASS |

## Divergências

Nenhuma.

## Probes Executados

| Comando | Resultado |
|---|---|
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/contract/ -q` | PASS — `8 passed in 0.59s` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` | PASS — `4 kept, 0 broken` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src` | PASS — `Success: no issues found in 30 source files` |

## Observações

- A decisão do cenário (d) foi implementada de forma defensável: o invariante é
  estrutural, porque `batch_invariant` é property derivada de
  `determinism_regime`. Isso torna a inconsistência do §4.3 irrepresentável no
  domínio, o que elimina a necessidade de exceção em runtime ou `WARNING` no
  writer.
- O schema Parquet já tinha `batch_invariant` obrigatório desde M0/TAREFA-009; a
  TAREFA-022 fechou corretamente as lacunas restantes no domínio e no adapter.
- Risco residual baixo: a persistência via `ResultWriterPort.update_metrics(...)`
  com `regime` só será exercida de verdade na TAREFA-026, quando o use case passar
  a atualizar linhas existentes com o regime do juiz.

## Conclusão

Veredito final: **PASS / Approve**.
