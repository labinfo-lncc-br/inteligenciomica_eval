# M3_TAREFA-303_B — Auditoria do WaveSchedulerService + `--dry-run`

## Prompt auditado

- TAREFA-303 — Prompt B
- Data: 2026-05-30
- Auditor: ChatGPT Codex (`code-reviewer`)

## Veredito

- PASS / Approve

## Escopo auditado

- `src/inteligenciomica_eval/application/services/wave_scheduler.py`
- `src/inteligenciomica_eval/infrastructure/config/model_registry.py`
- `src/inteligenciomica_eval/cli.py`
- `tests/unit/application/services/test_wave_scheduler.py`
- `tests/unit/cli/test_dry_run.py`
- `tests/unit/config/test_model_registry.py`
- `docs/dev-log/M3_TAREFA-303_A_wave-scheduler-dry-run.md`

## Resultado da auditoria

Não encontrei divergências bloqueadoras nem importantes no diff da 303A. O serviço de
aplicação permanece isolado de `infrastructure`, o planejamento das ondas é determinístico
e os testes cobrem o caminho feliz, os casos de borda principais e o comportamento do CLI
`--dry-run`.

## Tabela de critérios

| Critério | Evidência | Gravidade | Resultado |
|---|---|---:|---|
| `WaveSchedulerService` recebe VO de domínio e não importa `ModelRegistryConfig` | `src/inteligenciomica_eval/application/services/wave_scheduler.py:27-39`, `:100-145` | — | OK |
| Juiz é excluído das ondas de geração | `src/inteligenciomica_eval/application/services/wave_scheduler.py:121-128` | — | OK |
| Ordenação determinística por VRAM desc + nome | `src/inteligenciomica_eval/application/services/wave_scheduler.py:131-137` | — | OK |
| Cálculo de `cells_in_wave` respeita fases A/B e `n_questions` configurável | `src/inteligenciomica_eval/application/services/wave_scheduler.py:147-160` | — | OK |
| DTOs `Wave` e `WavePlan` são frozen | `src/inteligenciomica_eval/application/services/wave_scheduler.py:42-73` | — | OK |
| `to_wave_spec()` é canônico e aditivo no registry | `src/inteligenciomica_eval/infrastructure/config/model_registry.py:179-200` | — | OK |
| `--dry-run` imprime mapa de ondas, total em 3 passadas e aviso de serial | `src/inteligenciomica_eval/cli.py:143-223` | — | OK |
| `--dry-run` não toca rede/GPU e trata registry ausente com skip gracioso | `src/inteligenciomica_eval/cli.py:143-163` | — | OK |
| Registry e testes de config permanecem consistentes com `to_wave_spec()` | `tests/unit/config/test_model_registry.py:1-200` | — | OK |

## Evidência de testes

```text
.venv/bin/pytest tests/unit/application/services/test_wave_scheduler.py tests/unit/cli/test_dry_run.py tests/unit/config/test_model_registry.py -q
-> 54 passed in 0.28s
```

## Observações

- A revisão não identificou regressão funcional no escopo da tarefa.
- O único ponto a monitorar é a cobertura explícita do ramo de aviso por capacidade de VRAM
  no CLI, que hoje está validado por testes de comportamento geral, mas não por uma asserção
  dedicada de string do `Panel` amarelo.

## Reauditoria 2

- 2026-05-30: executada sobre o reforço de teste em `tests/unit/cli/test_dry_run.py`.
- Mudança auditada: `TestDryRunWaveMap::test_capacity_warning_when_reassigned_gpu_too_small`
  agora afirma também o conteúdo textual do `Panel` de capacidade, além do título.
- Resultado: o reforço fecha o risco residual apontado na rodada anterior. Veredito
  **permanece PASS**.

## Execução confirmada

```text
.venv/bin/pytest tests/unit/cli/test_dry_run.py -q
-> 18 passed in 0.24s
```
