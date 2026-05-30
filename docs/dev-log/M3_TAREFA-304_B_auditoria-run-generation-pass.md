# M3_TAREFA-304_B — Auditoria do `RunGenerationPassUseCase`

**Data**: 2026-05-30
**Milestone**: M3 — Orquestração experimental
**Épico**: E3
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Auditar a implementação da TAREFA-304A contra o Prompt B do marco M3, o contrato atual
em `domain/ports.py`, ADR-004/009 e o padrão de arquitetura do projeto.

## Arquivos Auditados

| Arquivo | Papel |
|---------|-------|
| `src/inteligenciomica_eval/application/use_cases/run_generation_pass.py` | Implementação do use case de geração. |
| `tests/unit/application/use_cases/test_run_generation_pass.py` | Suíte unitária da passada 1. |
| `docs/dev-log/M3_TAREFA-304_A_run-generation-pass.md` | Relatório de implementação do desenvolvedor. |

## Veredito

- PASS / Approve

## Resultado da Auditoria

Não encontrei divergências bloqueadoras ou importantes no diff da 304A. O use case
permanece na camada `application`, não importa `infrastructure`, aplica idempotência via
`writer.exists()`, trata `GenerationError` por célula com retry e mantém a saída da
Passada 1 sem métricas computadas.

## Tabela de Critérios

| Critério | Evidência | Gravidade | Resultado |
|---|---|---:|---|
| Use case depende de ports + contrato estrutural de config, sem importar `infrastructure` | `src/inteligenciomica_eval/application/use_cases/run_generation_pass.py:13-25`, `:37-59`, `:83-95`, `:134-149` | — | OK |
| Idempotência por `writer.exists(row_id)` antes de gerar | `src/inteligenciomica_eval/application/use_cases/run_generation_pass.py:204-241` | — | OK |
| `GenerationError` não aborta as demais células; retries respeitam `max_retries` | `src/inteligenciomica_eval/application/use_cases/run_generation_pass.py:285-360` | — | OK |
| `canonical_contexts` é exigido no Experimento B e o uso é injetado | `src/inteligenciomica_eval/application/use_cases/run_generation_pass.py:151-180`, `:327-343` | — | OK |
| Linhas geradas saem com `MetricVector` totalmente `NaN`, `final_score=NaN` e `determinism_regime=GENERATOR` | `src/inteligenciomica_eval/application/use_cases/run_generation_pass.py:65-74`, `:355-372` | — | OK |
| `GenerationPassReport` contém todos os campos e é imutável | `src/inteligenciomica_eval/application/use_cases/run_generation_pass.py:98-118`, `tests/unit/application/use_cases/test_run_generation_pass.py:474-502` | — | OK |
| Cobertura de casos principais e de borda no teste unitário | `tests/unit/application/use_cases/test_run_generation_pass.py:184-520` | — | OK |
| `lint-imports` permanece verde | execução local | — | OK |

## Evidência de Testes

```text
.venv/bin/pytest tests/unit/application/use_cases/test_run_generation_pass.py -q
-> 27 passed in 0.14s

.venv/bin/lint-imports
-> Contracts: 4 kept, 0 broken
```

## Observações

- O uso de `questions: Sequence[Question]` e `canonical_contexts` como argumentos do
  use case é um desvio consciente da assinatura literal da spec, mas está alinhado com
  o próprio fluxo descrito para a TAREFA-309 e com a restrição de não importar
  `infrastructure` em `application`.
- Não há achados adicionais a corrigir nesta rodada.
