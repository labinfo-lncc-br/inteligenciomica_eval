# M3_TAREFA-307_A — RunExperimentUseCase

**Data**: 2026-05-30
**Milestone**: M3 — Passadas de Avaliação
**Épico**: E3
**Skill**: backend-engineer
**Prioridade / Tamanho**: P0 / L

## Objetivo

Implementar `RunExperimentUseCase` em
`src/inteligenciomica_eval/application/use_cases/run_experiment.py` — orquestrador
top-level que executa o ciclo completo A+B: Passada 1 (geração, por onda de modelo) →
Passada 2 (métricas) → Passada 3 (juiz) → agregação e ranking.

Adicionar `GeneratorFactory` Protocol em `domain/ports.py` (Nota M3 item 5).

## Arquivos Criados / Modificados

| Arquivo | Ação | Descrição |
|---------|------|-----------|
| `src/inteligenciomica_eval/domain/ports.py` | Modificado | Adicionado `GeneratorFactory` Protocol ao final |
| `src/inteligenciomica_eval/application/use_cases/run_experiment.py` | Criado | `ExperimentConfigView`, `ExperimentReport`, `RunExperimentUseCase` |
| `tests/unit/application/use_cases/test_run_experiment.py` | Criado | 23 testes em 8 classes |
| `docs/dev-log/M3_TAREFA-307_A_run-experiment-use-case.md` | Criado | Este relatório |

## Decisões Técnicas

### 1. `GeneratorFactory` em `domain/ports.py`

Protocol `@runtime_checkable` com `__call__(self, url: str) -> GeneratorPort`.
Adicionado ao final de `domain/ports.py` conforme Nota M3 item 5 (única localização
autorizada). O wiring (TAREFA-309) fornecerá a implementação concreta.

### 2. `ExperimentConfigView` Protocol local

`RoundConfig` é Pydantic/infrastructure — import-linter Contract 2/4 proíbe
`application` de importar `infrastructure`. Definido Protocol local com todos os campos
necessários: `phases`, `bases`, `seeds`, `llms`, `temperature`, `round_id`,
`startup_timeout_s`, `failure_threshold`, `top_k`, `canonical_context_base`,
`canonical_top_k`, `model_registry: tuple[ModelWaveSpec, ...]`,
`model_spec_map: dict[str, ModelSpec]`.

Mesmo padrão de `RunConfigView` (TAREFA-304) e `RoundConfigView` (TAREFA-303).

### 3. `execute` recebe `questions: Sequence[Question]`

Não há port de dataset na arquitetura. O caller (TAREFA-309) carrega as perguntas e
as passa como argumento. Mesmo desvio documentado em `RunGenerationPassUseCase`
(TAREFA-304, desvio 2).

### 4. `retriever: RetrieverPort` no construtor

Para construir `canonical_contexts` do Experimento B antes da Passada 1 (spec §1b —
"retriever injetado"). Um `search` por pergunta usando `canonical_context_base` e
`canonical_top_k` da config.

### 5. Substituição de `_generator` por onda

`gen_pass_uc._generator` é atribuído diretamente com o `GeneratorPort` criado pela
factory antes de cada onda. Alternativa mais limpa a criar nova instância de
`RunGenerationPassUseCase` por onda (que exigiria expor todos os seus sub-componentes
no construtor de `RunExperimentUseCase`). Mypy aceita sem `# type: ignore` — `_generator`
é atributo de instância, não propriedade protegida por descriptores.

### 6. `_single_model_wave_plan` helper

Para cada modelo em uma onda, cria `WavePlan` com uma única `Wave` contendo apenas esse
modelo — passado ao `gen_pass_uc.execute` para que o use case interno processe somente
o modelo cujo servidor está ativo. `cells_in_wave=0` e `total_cells=0` são seguros
pois esses campos são usados apenas para display/reporting, não para lógica de iteração.

### 7. Graceful shutdown (RNF7)

`SIGTERM`/`SIGINT` → `_shutdown_requested = True` via `loop.add_signal_handler`.
Check no início de cada iteração de onda (completa a onda corrente antes de parar).
Servidor ativo encerrado em bloco `finally` externo. Relatório parcial retornado com
`n_evaluated=0`, `n_judged=0`, `aggregates=()`, `rank_scores=()`.

### 8. `_find_judge_spec`

Localiza o juiz pelo flag `is_judge=True` em `model_registry`, depois busca
`ModelSpec` completo em `model_spec_map`. Levanta `RuntimeError` se não encontrado
(wiring error, não erro de domínio).

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| `GenerationPassReport` e `MetricsPassReport` importados mas não usados no arquivo principal | Removidos — apenas os tipos dos reports de judge (`JudgePassReport`) são necessários na assinatura de `_run_judge_pass` |
| `# type: ignore[attr-defined]` causava `unused-ignore` no mypy | Removido — mypy não bloqueia acesso a atributos `_` prefixados em instâncias externas |
| `InMemoryResultReader.__init__()` não aceita `round_id` | Construtor correto usa apenas `store` sem `round_id` |
| `ServerStartTimeoutError.__init__` requer `server_name` + `timeout_seconds` posicionais | Corrigido na construção do fake: `ServerStartTimeoutError(handle.model, float(timeout_s), ...)` |
| Teste golden usava `critical_failure_rate=NaN` → `RankScore(NaN)` → `math.isfinite` falhava | Corrigido para `critical_failure_rate=0.05` (ADR-007: NaN propaga, comportamento correto) |

## Validação (DoD)

```
ruff check .                → All checks passed!
ruff format --check .       → 114 files already formatted
mypy --strict src           → Success: no issues found in 42 source files
lint-imports                → 4 kept, 0 broken
pytest test_run_experiment  → 23 passed
pytest suíte completa -n 4  → 902 passed, 15 skipped, 96.59% coverage
```

## Critérios de Aceitação

| Critério | Status | Evidência |
|----------|--------|-----------|
| ServerStartTimeoutError em onda → failed_waves; demais ondas continuam | ✅ | `TestServerStartTimeoutError` (3 testes) |
| Shutdown gracioso: flag→onda corrente completa→para→servidores fechados | ✅ | `TestGracefulShutdown` (3 testes) |
| Juiz iniciado APÓS toda geração (nunca simultâneo) | ✅ | `TestJudgeAfterAllGeneration::test_judge_start_after_gen_stops` |
| ExperimentReport com aggregates + rank_scores golden | ✅ | `TestExperimentReportGolden::test_aggregates_and_rank_scores_populated` |
| canonical_contexts via retriever para todas as perguntas (Exp. B) | ✅ | `TestCanonicalContexts` (3 testes) |
| `application` NÃO importa `infrastructure` | ✅ | lint-imports 4/0 |
| `GeneratorFactory` em `domain/ports.py` | ✅ | `src/inteligenciomica_eval/domain/ports.py` (último Protocol) |

## Observações para Próximas Tarefas

- **TAREFA-308** (`AnnotationWorkflowUseCase`): pode reusar o padrão Protocol local
  de `ExperimentConfigView` se precisar de campos de config sem importar infrastructure.
- **TAREFA-309** (wiring + CLI): deve montar `ExperimentConfigView` concreto que satisfaça
  o Protocol: `model_registry: tuple[ModelWaveSpec, ...]` vem do `ModelRegistryConfig`
  convertido; `model_spec_map: dict[str, ModelSpec]` constrói `ModelSpec` a partir de
  `ModelEntry` + atribuição de porta por modelo; `generator_factory` instancia
  `VLLMGeneratorAdapter(url=url)`; `canonical_context_base`/`canonical_top_k` vêm de
  `RoundConfig.experiment_b`.
- `_shutdown_requested` é resetado no início de cada `execute` — seguro para re-uso
  do mesmo `RunExperimentUseCase` em múltiplas rodadas.
