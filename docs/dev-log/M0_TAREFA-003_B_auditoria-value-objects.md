# M0_TAREFA-003_B — Auditoria dos Value Objects

**Data**: 2026-05-23
**Milestone**: M0 — Bootstrap e Estrutura Base
**Épico**: E0
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / S

## Objetivo

Auditar a TAREFA-003 contra `docs/arquitetura_detalhada_validacao_inteligenciomica.md` §4.1/§5.2/§5.3, ADR-009, `python-clean-architecture` §2 e o critério de property-based testing.

## Arquivos Inspecionados

- `src/inteligenciomica_eval/domain/value_objects.py`
- `src/inteligenciomica_eval/domain/errors.py`
- `tests/unit/domain/test_value_objects.py`
- `tests/unit/test_imports.py`
- `.importlinter`

## Resultado

**PASS**

As duas divergências materiais identificadas na auditoria anterior foram corrigidas: `DeterminismRegime` agora serializa como `judge/generator`, conforme o contrato arquitetural, e `RankScore` passou a rejeitar explicitamente valores que não sejam `float` com `InteligenciomicaEvalError`, incluindo `int`, `str`, `None` e `bool`.

## Divergências

| Critério | Arquivo:linha | Gravidade |
|----------|---------------|-----------|
| Nenhuma divergência encontrada na revalidação | — | — |

## Verificação Item a Item

| Item | Status | Evidência |
|------|--------|-----------|
| 1. Todos os VOs presentes | ✅ | `BaseId`, `LLMId`, `Seed`, `FinalScore`, `RankScore`, `MetricVector`, `RowId`, `DeterminismRegime` em `src/inteligenciomica_eval/domain/value_objects.py:21-233` |
| 2. `BaseId` aceita `{IDx_400k, ID_230K, fixed}` e rejeita o resto com `InvalidBaseIdError` | ✅ | Conjunto aceito em `src/inteligenciomica_eval/domain/value_objects.py:17,44-46`; testes em `tests/unit/domain/test_value_objects.py:53-80` |
| 3. `FinalScore` aceita `[0,1] ∪ {NaN}` e rejeita fora disso com `ScoreOutOfRangeError` | ✅ | Validação em `src/inteligenciomica_eval/domain/value_objects.py:88-105`; testes de faixa e property-based em `tests/unit/domain/test_value_objects.py:158-208` |
| 4. `RankScore` permite negativo e NaN, rejeita inf/não-float, sem clamp indevido em `[0,1]` | ✅ | Validação explícita de tipo e `±inf` em `src/inteligenciomica_eval/domain/value_objects.py:111-135`; testes em `tests/unit/domain/test_value_objects.py:216-255` |
| 5. `MetricVector` é frozen, campos corretos e `nan_fields()` funciona | ✅ | Dataclass frozen em `src/inteligenciomica_eval/domain/value_objects.py:130-178`; testes em `tests/unit/domain/test_value_objects.py:245-325` |
| 6. `RowId.from_cell` é determinístico e usa os 6 campos do ADR-009; mudar 1 campo muda o hash | ✅ | Payload usa `run_id`, `phase`, `base`, `llm`, `seed`, `question_id` em `src/inteligenciomica_eval/domain/value_objects.py:204-233`; testes de determinismo/mutação em `tests/unit/domain/test_value_objects.py:342-375,428-501`; ADR em `docs/arquitetura_detalhada_validacao_inteligenciomica.md:516-520` |
| 7. Cobertura >= 95% line+branch no módulo; há property-based test | ✅ | `value_objects.py` com 100% line+branch; property-based para `FinalScore` e `RowId` em `tests/unit/domain/test_value_objects.py:193-203,428-501` |
| 8. Domínio puro, só stdlib, sem logging, `import-linter` OK | ✅ | Imports do módulo em `src/inteligenciomica_eval/domain/value_objects.py:1-15` usam só stdlib + `domain.errors`; `tests/unit/test_imports.py:6-22`; `uv run lint-imports` retornou `4 kept, 0 broken` |

## Revalidação das Falhas Anteriores

- `DeterminismRegime` foi alinhado ao contrato da arquitetura e agora expõe `judge` e `generator` em `src/inteligenciomica_eval/domain/value_objects.py:21-28`, com cobertura em `tests/unit/domain/test_value_objects.py:33-45`.
- `RankScore` agora rejeita tipos não-`float` com erro de domínio claro em `src/inteligenciomica_eval/domain/value_objects.py:127-135`, e os testes cobrem `int`, `bool`, `str`, `None`, `list` e `dict` em `tests/unit/domain/test_value_objects.py:241-255`.

## Observação Específica sobre `Seed`

A escolha de exceção para `Seed` é coerente com o domínio: `InvalidSeedError` foi adicionada em `src/inteligenciomica_eval/domain/errors.py:62-74`, e `Seed` a usa com mensagem clara em `src/inteligenciomica_eval/domain/value_objects.py:70-85`. Não há uso de `ValueError` ou `Exception` genérico neste VO.

## Comandos Executados

```bash
uv run pytest tests/unit/domain/test_value_objects.py --cov=inteligenciomica_eval.domain.value_objects --cov-branch --cov-report=term-missing
uv run lint-imports
```

## Resultados dos Comandos

- `uv run pytest tests/unit/domain/test_value_objects.py --cov=inteligenciomica_eval.domain.value_objects --cov-branch --cov-report=term-missing` → `88 passed`, cobertura de `src/inteligenciomica_eval/domain/value_objects.py`: `100%` line, `100%` branch.
- `uv run lint-imports` → `Contracts: 4 kept, 0 broken`.

## Critérios de Aceitação

- Inventário de VOs completo: ✅
- Invariantes centrais de `BaseId`, `Seed`, `FinalScore`, `MetricVector`, `RowId`: ✅
- Property-based tests presentes: ✅
- Cobertura do módulo >= 95%: ✅
- Conformidade integral de contrato para `DeterminismRegime` e rejeição de não-float em `RankScore`: ✅

## Observações para Próximas Tarefas

- O módulo está aderente aos critérios auditados e apto para uso pelas próximas tarefas do milestone M0.
