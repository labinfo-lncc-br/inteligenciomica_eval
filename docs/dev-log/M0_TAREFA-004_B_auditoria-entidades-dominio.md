# M0_TAREFA-004_B — Auditoria de entidades de domínio

**Data**: 2026-05-23
**Milestone**: M0 — Bootstrap e contratos (esqueleto executável com stubs)
**Épico**: E0
**Skill**: code-reviewer + python-clean-architecture
**Prioridade / Tamanho**: P0 / S

## Objetivo

Auditar o diff da TAREFA-004 (commit `ef19d23`) contra `docs/arquitetura_detalhada_validacao_inteligenciomica.md` §4.1/§4.3/§5.3, ADR-003, ADR-009 e o critério transversal de DoD §14.2, sem reescrever a implementação.

## Arquivos Criados / Modificados

| Arquivo | Papel na auditoria |
|---|---|
| `src/inteligenciomica_eval/domain/entities.py` | Implementação auditada |
| `tests/unit/domain/test_entities.py` | Evidência de cobertura dos invariantes |
| `src/inteligenciomica_eval/domain/errors.py` | Exceções específicas usadas pelas entidades |
| `tests/unit/test_imports.py` | Evidência de importabilidade do módulo |
| `docs/dev-log/M0_TAREFA-004_B_auditoria-entidades-dominio.md` | Relatório desta execução |

## Decisões Técnicas

- Escopo do PR auditado: commit `ef19d23` (`feat(M0-TAREFA-004): entidades de domínio Question, GeneratedAnswer e EvaluationResult`).
- Interpretação da coerência de determinismo: em `EvaluationResult`, o contrato exposto é `determinism_regime`; a coerência semântica com `batch_invariant` permanece corretamente delegada à escrita/use case, em linha com `§4.3` e `ADR-003`.

## Problemas Encontrados e Soluções

**PASS**

Nenhuma divergência material foi identificada no diff auditado.

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| Nenhuma divergência material encontrada | — | — |

## Validação (DoD)

### Checagem item a item

| Item | Status | Evidência |
|---|---|---|
| 1. `Question`, `GeneratedAnswer`, `EvaluationResult` presentes, `frozen`, com campos da spec | ✅ | `Question` em `src/inteligenciomica_eval/domain/entities.py:26`, `GeneratedAnswer` em `:55`, `EvaluationResult` em `:109`; todos com `@dataclass(frozen=True, slots=True)` e campos coerentes com `§4.1`/`§5.3` |
| 2. `GeneratedAnswer` valida 3 tuplas de retrieval com mesmo comprimento; `phase ∈ {A,B}`; fase B exige `base="fixed"` | ✅ | Guardas em `src/inteligenciomica_eval/domain/entities.py:91-106`; cobertura em `tests/unit/domain/test_entities.py:162-224` |
| 3. `EvaluationResult` é agregado raiz com `GeneratedAnswer + MetricVector + FinalScore + DeterminismRegime +` anotação humana opcional | ✅ | Composição em `src/inteligenciomica_eval/domain/entities.py:136-141`, alinhada a `§4.3` e `§5.3` |
| 4. Invariantes de `§4.3` presentes (`flag ∈ {0,1}` quando não-`None`; regime obrigatório/válido; coerência de determinismo exposta) | ✅ | `critical_failure_flag` validado em `src/inteligenciomica_eval/domain/entities.py:151-159`; `determinism_regime` obrigatório e tipado em `:146-150`; exposição do regime em `:139` |
| 5. `with_metrics` / `with_human_annotation` retornam nova instância, sem mutação in-place | ✅ | Uso de `dataclasses.replace()` em `src/inteligenciomica_eval/domain/entities.py:212-217,236-240`; testes em `tests/unit/domain/test_entities.py:361-420` |
| 6. `is_failure` usa `< threshold`; `is_critical_failure` trata `None` corretamente | ✅ | Implementação em `src/inteligenciomica_eval/domain/entities.py:165-187`; testes em `tests/unit/domain/test_entities.py:301-353` |
| 7. Domínio puro, sem I/O/logging; import-linter OK; ramos de invariante cobertos; DoD §14.2 atendido no escopo auditado | ✅ | Imports apenas de `dataclasses` + domínio em `src/inteligenciomica_eval/domain/entities.py:1-20`; `uv run lint-imports` verde; testes de erro/borda em `tests/unit/domain/test_entities.py`; `from __future__ import annotations` no topo (`entities.py:1`, `test_entities.py:1`); docstrings públicas presentes |

### Comandos executados

```bash
uv run pytest tests/unit/domain/test_entities.py -q
uv run lint-imports
uv run ruff check src/inteligenciomica_eval/domain/entities.py tests/unit/domain/test_entities.py
uv run ruff format --check src/inteligenciomica_eval/domain/entities.py tests/unit/domain/test_entities.py
uv run mypy --strict src
```

### Resultado dos comandos

- `pytest`: `49 passed in 0.14s`
- `lint-imports`: `4 kept, 0 broken`
- `ruff check`: `All checks passed!`
- `ruff format --check`: `2 files already formatted`
- `mypy --strict src`: `Success: no issues found in 14 source files`

## Critérios de Aceitação

| Critério | Status |
|---|---|
| Invariantes do agregado (`§4.3`) implementadas | ✅ |
| Entidades do domínio criadas (`Question`, `GeneratedAnswer`, `EvaluationResult`) | ✅ |
| Testes unitários cobrindo happy path, borda e erro | ✅ |
| Domínio isolado de I/O / infra | ✅ |

## Observações para Próximas Tarefas

- `TAREFA-005` pode consumir `EvaluationResult.with_metrics(...)` como ponto oficial para completar a segunda passada (`§5.4`), preservando a imutabilidade do agregado.
- A coerência operacional entre `determinism_regime` e a coluna física `batch_invariant` deve ser garantida no writer/use case, não replicada na entidade, para manter o domínio puro e aderente ao contrato de `§4.3`.
