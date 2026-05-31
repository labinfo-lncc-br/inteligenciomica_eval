# M3_TAREFA-307_B — Auditoria de RunExperimentUseCase

**Data**: 2026-05-30
**Milestone**: M3 — Orquestração experimental
**Épico**: E3
**Skill**: code-reviewer
**Resultado**: PASS

## Escopo auditado

- `src/inteligenciomica_eval/application/use_cases/run_experiment.py`
- `tests/unit/application/use_cases/test_run_experiment.py`
- `src/inteligenciomica_eval/domain/ports.py`
- `docs/prompts_m3_tarefas_301_310.md`

## Verificação

1. O use case permanece na camada `application` e não importa `infrastructure`.
2. `GeneratorFactory` está declarado como `Protocol` em `domain/ports.py`.
3. O servidor juiz continua sendo iniciado apenas após a geração terminar.
4. `ServerStartTimeoutError` em uma onda não aborta a rodada inteira e registra a wave em `failed_waves`.
5. O shutdown gracioso continua respeitando `_shutdown_requested` e limpa servidores no `finally`.
6. A agregação final recomputa `rank_scores` com `RankScoreCalculator`, em vez de apenas copiar o valor já armazenado no agregado.
7. `failed_waves` agora é deduplicado por wave e serializado de forma determinística.
8. `canonical_contexts` continuam sendo construídos via `RetrieverPort` antes da Passada 1 quando `B` está habilitada.

## Evidências

- `.venv/bin/pytest tests/unit/application/use_cases/test_run_experiment.py -q` -> `23 passed`
- `.venv/bin/lint-imports` -> `4 kept, 0 broken`

## Observações

- O desvio consciente em relação ao prompt A, `ExperimentConfigView` em vez de `RoundConfig`, segue documentado e mantém a camada `application` livre de dependências de `infrastructure`.
- A correção C encerra os dois achados da auditoria anterior sem introduzir regressões nos testes unitários do use case.
