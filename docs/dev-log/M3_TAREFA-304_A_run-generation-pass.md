# M3_TAREFA-304_A — RunGenerationPassUseCase (Passada 1 de Geração)

**Data**: 2026-05-30
**Milestone**: M3 — Orquestração experimental
**Épico**: E3
**Skill**: backend-engineer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Implementar `RunGenerationPassUseCase` em
`src/inteligenciomica_eval/application/use_cases/run_generation_pass.py` — Passada 1 da
arquitetura de 3 passadas (ADR-004): recuperação de contextos + geração de texto +
persistência idempotente por célula `{fase × base × llm × seed × pergunta}` (ADR-009).

## Arquivos Criados / Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/.../application/use_cases/__init__.py` | **Novo** (pacote). |
| `src/.../application/use_cases/run_generation_pass.py` | **Novo**: `RunGenerationPassUseCase`, DTOs `GenerationPassReport`, Protocol `RunConfigView`/`_RetrievalView`. |
| `tests/unit/application/use_cases/__init__.py` | **Novo**. |
| `tests/unit/application/use_cases/test_run_generation_pass.py` | **Novo**: 27 testes (5 classes). |

## Decisões Técnicas

1. **`config: RunConfigView` (Protocol estrutural), NÃO `RoundConfig`.**
   A spec pede `config: RoundConfig`, mas `RoundConfig` é **infrastructure** e a camada
   `application` não pode importá-la (import-linter Contract 2/4; mesmo padrão do
   `RoundConfigView` de TAREFA-303). Definido `RunConfigView` (em application) com
   `phases/bases/seeds/temperature/retrieval`, que o `RoundConfig` Pydantic satisfaz por
   **duck-typing** (inversão de dependência, ADR-001). `_RetrievalView` Protocol aninhado
   expõe `top_k: int` — satisfeito por `RetrievalConfig.top_k`.

2. **`execute` recebe `questions: Sequence[Question]` explicitamente.**
   A spec mostra `execute(*, run_id, wave_plan)`, mas perguntas têm que vir de algum
   lugar. `RoundConfig` não carrega questões e não existe port de dataset em M3.
   Decisão: `questions` como parâmetro do `execute` (o orquestrador de TAREFA-309 as
   carrega e injeta). `canonical_contexts: dict[str, list[Chunk]] | None = None` também
   como parâmetro — a spec já documenta este argumento explicitamente.

3. **Retrieval fora do loop de retry.**
   A recuperação (Experimento A) é executada uma única vez por célula, antes do loop
   de retry de geração. É determinística (mesma base + pergunta + top_k → mesmos chunks)
   e o erro esperado é `GenerationError`, não `RetrievalError`. Esta separação evita
   chamadas desnecessárias ao Qdrant e alinha com a semântica do retry (spec item 1.d).

4. **`max_retries` no construtor (default 3), não em `config`.**
   Injetável para testes (zero fakes de configuração necessários para cenários de erro).
   Mesma convenção de `_retry_stop`/`_retry_wait` dos adapters de M1.

5. **`reader: ResultReaderPort` no construtor, não usado.**
   A spec lista `reader` para "verificar idempotência", mas `writer.exists(row_id)` é
   a interface correta (conforme o spec workflow). `reader` é mantido no construtor por
   compatibilidade de assinatura — reservado para uso em passadas futuras (ex.: load de
   rows existentes em batch).

6. **Constante `_ALL_NAN_METRICS`.**
   `MetricVector` não tem valores padrão; para não repetir 8 campos NaN em cada célula,
   uma instância módulo-level `_ALL_NAN_METRICS` é reutilizada (frozen dataclass = seguro).

7. **import-linter: `.importlinter` NÃO mudou.**
   Os contratos usam pacotes-raiz (`inteligenciomica_eval.application`), que já cobrem
   `application/use_cases/`. `lint-imports` permaneceu 4/0.

## Problemas Encontrados e Soluções

- **RUF002/RUF003**: `×` (sinal de multiplicação) em docstrings e comentários →
  substituídos por `x` (mesma correção de TAREFA-303).
- **RUF059**: variáveis `store` não usadas em 3 testes onde só o `uc` importava →
  rebatizadas para `_`.
- **I001**: ordenação de imports no arquivo de testes após ruff --fix → corrigida.
- **Linhas não cobertas** (97%): linha 245 (log de progresso a cada 10 células — dispararia
  com ≥ 10 células, nenhum teste produz isso), linha 392 (`return None` inalcançável
  pós-retry, guard de tipo). Ambas aceitáveis.

## Validação (DoD §14.2)

```text
ruff check .                    -> All checks passed!
ruff format --check .           -> 108 files already formatted
mypy --strict src               -> Success: no issues found in 39 source files
lint-imports                    -> Contracts: 4 kept, 0 broken
pytest --cov -n 4 --cov-fail-under=85
  -> 840 passed, 15 skipped — coverage 97.46%
  -> run_generation_pass.py: 101 stmts, 2 missed = 97%
```

## Critérios de Aceitação (tabela TAREFA-304)

| Critério | Estado | Evidência (teste) |
|----------|--------|-------------------|
| Célula existente → skip; n_skipped correto (ADR-009) | ✅ | `TestIdempotency::test_existing_cell_is_skipped`, `test_skip_incremented_not_generated` |
| Experimento B sem canonical_contexts → ConfigValidationError | ✅ | `TestPhaseB::test_phase_b_without_canonical_raises` |
| GenerationError não aborta demais células | ✅ | `TestErrorHandling::test_generation_error_does_not_abort_other_cells` |
| Após max_retries → failed_cells; linha NÃO persiste | ✅ | `test_max_retries_exhausted_adds_to_failed_cells`, `test_max_retries_exhausted_attempts_correct_count` |
| Experimento B usa canonical_contexts; A chama retriever | ✅ | `test_phase_b_uses_canonical_not_retriever`, `test_uses_retriever_for_contexts` |
| Linhas geradas têm MetricVector com todos campos NaN | ✅ | `TestGeneratedRowIntegrity::test_all_metric_fields_are_nan` |
| `determinism_regime=GENERATOR` em todas as linhas | ✅ | `test_determinism_regime_is_generator` |
| GenerationPassReport com todos campos preenchidos | ✅ | `TestGenerationPassReport::test_report_fields_populated` |
| `application` NÃO importa `infrastructure` | ✅ | `lint-imports` 4/0 |

## Observações para Próximas Tarefas

- **Desvios conscientes a sinalizar ao Codex (Prompt B)**:
  1. `config: RunConfigView` (Protocol estrutural) em vez de `RoundConfig` — application
     não importa infrastructure (import-linter Contract 2/4; mesmo padrão TAREFA-303).
  2. `questions: Sequence[Question]` como parâmetro de `execute()` — spec mostra apenas
     `run_id, wave_plan` mas questões não têm origem no `RoundConfig`; o orquestrador
     (TAREFA-309) as injetará.
  3. Retrieval fora do loop de retry (uma chamada por célula, geração retriada).
  4. `reader: ResultReaderPort` no construtor mas sem uso no body (reservado).
  5. Linhas 245/392 sem cobertura: log de progresso (threshold 10 células) e `return None`
     inalcançável (guard de tipo). 97% cobertura no arquivo.
  6. `.importlinter` não mudou — contratos de pacote-raiz já cobrem `use_cases/`.

- **TAREFA-305+** (métricas, juiz): o `GenerationPassReport` desta passada serve de
  insumo para o `RunMetricsPassUseCase` — ele carrega as linhas geradas pelo
  `run_id`/`round_id` para computar métricas na Passada 2.
- **TAREFA-309 (wiring)**: ao montar o container, passar `RoundConfig` diretamente como
  `RunConfigView` (satisfação por duck-typing; sem cast explícito).
