# M0_TAREFA-007_B — Auditoria RankScoreCalculator

**Data**: 2026-05-23
**Milestone**: M0 — Bootstrap e Domínio Core
**Épico**: E0
**Skill**: code-reviewer, ml-engineer, test-engineer
**Prioridade / Tamanho**: P0 / S

## Objetivo

Auditar a implementação da `TAREFA-007` contra a arquitetura (§4.4), a fórmula
§7.3 registrada no dev-log da tarefa, ADR-007, os testes unitários/property-based
e o golden dataset de `src/inteligenciomica_eval/domain/services/rank_score.py`.

## Arquivos Criados / Modificados

| Arquivo | Papel |
|---|---|
| `docs/dev-log/M0_TAREFA-007_B_auditoria-rank-score.md` | Relatório desta auditoria |

## Decisões Técnicas

- A arquitetura usada como baseline foi `docs/arquitetura_detalhada_validacao_inteligenciomica.md:263-270`, que exige `RankScoreCalculator` puro, sem I/O, e permite valor negativo.
- A fórmula de referência para §7.3 foi tomada de `docs/dev-log/M0_TAREFA-007_A_rank-score-calculator.md:13-20`, onde a tarefa implementada registra explicitamente os pesos e o termo subtrativo.
- O tratamento de NaN foi auditado contra ADR-007 em `docs/arquitetura_detalhada_validacao_inteligenciomica.md:498-504`.

## Problemas Encontrados e Soluções

Nenhuma divergência material foi encontrada no diff auditado.

## Validação (DoD)

| Gate | Resultado |
|---|---|
| `uv run pytest tests/unit/domain/services/test_rank_score.py --cov=inteligenciomica_eval.domain.services.rank_score --cov-report=term-missing` | ✅ 34 passed; cobertura do módulo `rank_score.py` = **100%** |
| `uv run lint-imports` | ✅ 4 contratos kept, 0 broken |

> Nota: houve uma primeira execução de `pytest --cov` com alvo incorreto
> (`--cov=src/inteligenciomica_eval/domain/services/rank_score.py`), que mediu 0%.
> A rerodagem com o nome importável do módulo confirmou a cobertura real de 100%.

## Critérios de Aceitação

**Status final da auditoria**: **PASS**

| Critério | Status | Evidência |
|---|---|---|
| 1. Fórmula bate exatamente com §7.3; penalização é subtrativa | ✅ PASS | Pesos canônicos em `src/inteligenciomica_eval/domain/services/rank_score.py:22-27`; fórmula em `:56-63`; cálculo efetivo em `:137-142`; referência documental em `docs/dev-log/M0_TAREFA-007_A_rank-score-calculator.md:17-20` |
| 2. `RankScore` pode ser negativo, sem clamp; há teste disso | ✅ PASS | Arquitetura permite negativo em `docs/arquitetura_detalhada_validacao_inteligenciomica.md:265-270`; VO aceita negativos em `src/inteligenciomica_eval/domain/value_objects.py:112-135`; testes negativos em `tests/unit/domain/services/test_rank_score.py:125-147`; casos golden negativos em `tests/golden/rank_score_cases.json:14-23,46-56` |
| 3. Pesos são injetáveis por config; ausência de `sum==1` está justificada; pesos inválidos falham | ✅ PASS | Injeção via `__init__(weights: Mapping[str, float])` em `src/inteligenciomica_eval/domain/services/rank_score.py:94-107`; justificativa textual do contraste com `FinalScoreCalculator` em `:15-21,65-69`; contraste com validação de soma em `src/inteligenciomica_eval/domain/services/final_score.py:52-77`; falha para peso neg/NaN/inf em `tests/unit/domain/services/test_rank_score.py:77-91` |
| 4. Qualquer NaN em insumo retorna `RankScore(NaN)`, sem imputação | ✅ PASS | Propagação explícita em `src/inteligenciomica_eval/domain/services/rank_score.py:120-126`; ADR-007 em `docs/arquitetura_detalhada_validacao_inteligenciomica.md:498-504`; testes em `tests/unit/domain/services/test_rank_score.py:170-197`; golden NaN em `tests/golden/rank_score_cases.json:57-78` |
| 5. Serviço é puro/determinístico, sem I/O/logging/estado externo | ✅ PASS | Arquitetura exige pureza em `docs/arquitetura_detalhada_validacao_inteligenciomica.md:263-270`; implementação usa só `math`, `Mapping`, `dataclass` e tipos de domínio em `src/inteligenciomica_eval/domain/services/rank_score.py:1-11`; determinismo exercitado em `tests/unit/domain/services/test_rank_score.py:317-338` |
| 6. Golden tem >=5 casos, inclui negativo e NaN; monotonicidade foi testada | ✅ PASS | Arquivo golden com 7 casos em `tests/golden/rank_score_cases.json:1-79`; verificação de quantidade em `tests/unit/domain/services/test_rank_score.py:209-235`; monotonicidade de `CriticalFailureRate` em `tests/unit/domain/services/test_rank_score.py:245-278` |
| 7. Cobertura >=95%, `import-linter` OK, DoD §14.2 atendido | ✅ PASS | Cobertura do módulo = 100% no `pytest --cov`; `lint-imports` com 4/4 contratos kept; DoD transversal em `docs/arquitetura_detalhada_validacao_inteligenciomica.md:907-918`; arquivo com `from __future__ import annotations` e docstrings públicas em `src/inteligenciomica_eval/domain/services/rank_score.py:1,32-45,53-92,109-119` |

### Tabela de divergências

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| Nenhuma divergência encontrada | — | — |

### Recomputação manual independente

Caso negativo `case_05_high_critical_negative`
(`tests/golden/rank_score_cases.json:47-55`):

`0.50*0.1 + 0.20*(1-0.9) + 0.15*0.1 - 0.15*1.0`

= `0.05 + 0.02 + 0.015 - 0.15`

= **`-0.065`**

O valor esperado do golden está correto e confirma que o termo
`critical_failure_penalty` é subtrativo e não sofre clamp.

Também conferi `case_04_mixed_moderate`
(`tests/golden/rank_score_cases.json:36-44`):

`0.50*0.5 + 0.20*(1-0.5) + 0.15*0.4 - 0.15*0.3`

= `0.25 + 0.10 + 0.06 - 0.045`

= **`0.365`**

## Observações para Próximas Tarefas

- No nível de serviço, a injeção de pesos está pronta; a leitura da config em si
  pertence às camadas superiores e não foi parte deste diff.
- A implementação está apta para ser usada pela futura `AggregationService`,
  que deverá produzir `RankScoreInputs` preservando a semântica de NaN do ADR-007.
