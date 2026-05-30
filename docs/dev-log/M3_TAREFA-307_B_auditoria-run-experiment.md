# M3_TAREFA-307_B — Auditoria de RunExperimentUseCase

**Data**: 2026-05-30
**Milestone**: M3 — Orquestração experimental
**Épico**: E3
**Skill**: code-reviewer
**Resultado**: FAIL

## Escopo auditado

- `src/inteligenciomica_eval/application/use_cases/run_experiment.py`
- `src/inteligenciomica_eval/domain/ports.py`
- `tests/unit/application/use_cases/test_run_experiment.py`
- `docs/prompts_m3_tarefas_301_310.md`

## Achados

### 1. `rank_calc` injetado não é usado para compor `rank_scores`

- **Local**: `src/inteligenciomica_eval/application/use_cases/run_experiment.py:181-194`, `src/inteligenciomica_eval/application/use_cases/run_experiment.py:382-386`
- **Gravidade**: importante

O construtor recebe `rank_calc: RankScoreCalculator`, mas o valor nunca participa do cálculo final. Em vez de recomputar `rank_scores` a partir dos `ConfigAggregate`, o use case apenas copia `agg.rank_score` de `AggregationService`.

Isso cria um desvio do contrato da TAREFA-307 e deixa a dependência injetada sem efeito prático. O resultado atual continua correto enquanto `AggregationService` também calcular o `RankScore`, mas o orquestrador deixa de exercer explicitamente a camada de domínio como o prompt pede.

Sugestão: recomputar `rank_scores` a partir dos agregados com `self._rank_calc.compute(...)`, ou remover o parâmetro do construtor e ajustar o contrato se a decisão arquitetural for delegar totalmente esse cálculo ao `AggregationService`.

### 2. `failed_waves` pode conter duplicatas para a mesma wave

- **Local**: `src/inteligenciomica_eval/application/use_cases/run_experiment.py:300-302`
- **Gravidade**: importante

O código faz `failed_waves.append(wave.wave_index)` a cada `ServerStartTimeoutError` por modelo. Como uma wave pode conter mais de um modelo, uma única wave com múltiplas falhas pode aparecer várias vezes no relatório, o que distorce a semântica de `failed_waves` e o contador derivado em logs.

Sugestão: registrar cada índice de wave no máximo uma vez, por exemplo com um `set` auxiliar ou com uma guarda antes do append.

## Verificação

- `.venv/bin/pytest tests/unit/application/use_cases/test_run_experiment.py -q` -> `23 passed`
- `.venv/bin/lint-imports` -> `4 kept, 0 broken`

## Observações

- O uso de `ExperimentConfigView`, `RetrieverPort` e `GeneratorFactory` mantém a camada `application` livre de imports de `infrastructure`.
- A sequência principal de execução está correta: geração por wave, métricas, juiz e agregação final.
