# M0_TAREFA-006_B — Auditoria FinalScoreCalculator

**Data**: 2026-05-23
**Milestone**: M0 — Bootstrap e Domínio Core
**Épico**: E0
**Skill**: code-reviewer, ml-engineer, test-engineer
**Prioridade / Tamanho**: P0 / S

## Objetivo

Auditar a implementação da `TAREFA-006` contra a arquitetura (§4.4), os critérios
da tarefa em `docs/arquitetura_detalhada_validacao_inteligenciomica.md`, ADR-007
e os testes unitários/golden/property-based do módulo
`src/inteligenciomica_eval/domain/services/final_score.py`.

## Arquivos Criados / Modificados

| Arquivo | Papel |
|---|---|
| `docs/dev-log/M0_TAREFA-006_B_auditoria-final-score.md` | Relatório desta auditoria |

## Decisões Técnicas

- A auditoria foi feita sobre o diff local da tarefa, que adiciona
  `final_score.py`, os testes unitários/golden associados e a exportação em
  `domain/services/__init__.py`.
- A fórmula de referência usada foi a configuração canônica documentada em
  `docs/arquitetura_detalhada_validacao_inteligenciomica.md:841-846`, coerente
  com §4.4 (`docs/arquitetura_detalhada_validacao_inteligenciomica.md:263-267`).
- O critério de NaN foi auditado contra ADR-007
  (`docs/arquitetura_detalhada_validacao_inteligenciomica.md:498-504`).

## Problemas Encontrados e Soluções

Nenhuma divergência foi encontrada na implementação auditada.

## Validação (DoD)

| Gate | Resultado |
|---|---|
| `uv run pytest tests/unit/domain/services/test_final_score.py --cov=inteligenciomica_eval.domain.services.final_score --cov-branch --cov-report=term-missing` | ✅ 40 passed; cobertura do módulo `final_score.py` = **100%** |
| `uv run lint-imports` | ✅ 4 contratos kept, 0 broken |
| `uv run ruff check .` | ✅ all checks passed |
| `uv run ruff format --check .` | ✅ 33 files already formatted |
| `uv run mypy --strict src` | ✅ no issues found |

> Nota: houve uma primeira execução de `pytest --cov` com alvo incorreto de cobertura
> (caminho de arquivo em vez de módulo Python), que retornou 0%. A rerodagem com
> `--cov=inteligenciomica_eval.domain.services.final_score` confirmou 100%.

## Critérios de Aceitação

**Status final da auditoria**: **PASS**

| Critério | Status | Evidência |
|---|---|---|
| 1. Fórmula bate exatamente com §7.1; métricas corretas; `answer_similarity` e `bertscore_f1` fora | ✅ PASS | `src/inteligenciomica_eval/domain/services/final_score.py:22-29` define os 6 pesos esperados; `:44-45` documenta exclusão das métricas auxiliares; `tests/unit/domain/services/test_final_score.py:178-202` e `tests/golden/final_score_cases.json:93-105` cobrem anti-double-counting |
| 2. Pesos vêm da config e soma inválida falha na construção | ✅ PASS | `FinalScoreCalculator.__init__(weights: Mapping[str, float])` em `src/inteligenciomica_eval/domain/services/final_score.py:62-77`; erro `WeightsDoNotSumToOneError` em `:73-76`; testes em `tests/unit/domain/services/test_final_score.py:61-76` |
| 3. NaN propaga para `FinalScore(NaN)` quando peso > 0; sem imputação | ✅ PASS | `src/inteligenciomica_eval/domain/services/final_score.py:94-100`; testes em `tests/unit/domain/services/test_final_score.py:160-202`; caso golden NaN em `tests/golden/final_score_cases.json:78-90` |
| 4. Serviço é puro, sem I/O/logging/estado mutável; determinístico | ✅ PASS | `src/inteligenciomica_eval/domain/services/final_score.py:1-101` só usa stdlib + domínio; sem I/O, sem logging, sem estado global mutável; determinismo reforçado por `tests/unit/domain/services/test_final_score.py:331-358` |
| 5. Golden com >=5 casos, bordas e NaN; valores conferem | ✅ PASS | 7 casos em `tests/golden/final_score_cases.json:1-107`; bordas em `:2-30`; NaN em `:77-105`; execução em `tests/unit/domain/services/test_final_score.py:229-255` |
| 6. Property-based presente para faixa [0,1] e monotonicidade fraca | ✅ PASS | `tests/unit/domain/services/test_final_score.py:265-328` cobre intervalo e monotonicidade |
| 7. Cobertura >=95% do módulo; import-linter OK; DoD §14.2 | ✅ PASS | `pytest --cov` confirmou 100%; `lint-imports` confirmou 4/4 contratos; `ruff`, `format` e `mypy` passaram; arquivo segue `from __future__ import annotations` e docstrings públicas em `src/inteligenciomica_eval/domain/services/final_score.py:1,33-60,79-92` |

### Tabela de divergências

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| Nenhuma divergência encontrada | — | — |

### Recomputação manual independente

Caso golden `case_04_mixed_moderate`
(`tests/golden/final_score_cases.json:48-60`):

`0.45*0.80 + 0.20*0.60 + 0.15*0.70 + 0.10*0.50 + 0.05*0.40 + 0.05*0.30`

= `0.36 + 0.12 + 0.105 + 0.05 + 0.02 + 0.015`

= **`0.670`**

O valor esperado do golden (`0.67`) está correto.

Também conferi `case_05_mixed_high`
(`tests/golden/final_score_cases.json:63-75`):

`0.45*0.90 + 0.20*0.80 + 0.15*0.70 + 0.10*0.60 + 0.05*0.50 + 0.05*0.40`

= `0.405 + 0.16 + 0.105 + 0.06 + 0.025 + 0.02`

= **`0.775`**

## Observações para Próximas Tarefas

- O serviço já aceita pesos injetados por `Mapping[str, float]`, então a integração
  com config pode ocorrer fora do domínio sem alterar a matemática do serviço.
- Não encontrei desvio entre implementação, testes e ADR-007; a próxima tarefa pode
  assumir `FinalScoreCalculator` como base estável para agregação/ranking.
