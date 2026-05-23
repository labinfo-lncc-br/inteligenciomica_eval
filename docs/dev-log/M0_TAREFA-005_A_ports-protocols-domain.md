# M0_TAREFA-005_A — Ports como Protocol (domain/ports.py)

**Data**: 2026-05-23
**Milestone**: M0 — Bootstrap e Domínio Core
**Épico**: E0
**Skill**: python-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Declarar todos os ports da §5.1 da arquitetura como `typing.Protocol` com
`@runtime_checkable` em `src/inteligenciomica_eval/domain/ports.py`, junto com os
DTOs auxiliares de domínio necessários às assinaturas (frozen dataclasses puros,
sem Pydantic). Fornecer testes de contrato que comprovem que stubs triviais
satisfazem cada Protocol via `isinstance`.

---

## Arquivos Criados / Modificados

| Arquivo | Ação |
|---------|------|
| `src/inteligenciomica_eval/domain/ports.py` | **Criado** — 11 Protocols + 15 DTOs |
| `tests/unit/domain/test_ports_contract.py` | **Criado** — 37 testes de contrato |

---

## Decisões Técnicas

### DTOs como `@dataclass(frozen=True, slots=True)`
Todos os DTOs usam `slots=True` para consistência com o restante do domínio
(value_objects.py, entities.py), exceto `FriedmanReport` e `MLMReport`, que
contêm `dict[str, float]` (campos mutáveis). Para estes dois, `slots=True` foi
omitido intencionalmente para sinalizar que os objetos contêm estado mutável
interno — embora a reatribuição do atributo seja proibida por `frozen=True`.

### `@runtime_checkable` em todos os Protocols
Exigido pela TAREFA-011 (fakes de teste). Permite `isinstance(stub, XxxPort)`
no nível de testes sem acoplamento estático — mantém o duck typing estrutural
do Protocol enquanto habilita verificação de compatibilidade em tempo de
execução.

### Separação DTO de domínio vs DTO de adapter
`EvaluationSample`, `Layer1Metrics`, `RubricResult`, `GenerationOutput`,
`ModelSpec` são aqui definidos como frozen dataclasses puras. A §5.2 da
arquitetura reserva Pydantic para a fronteira de adapter — nenhuma dependência
de Pydantic entra no módulo `domain/`.

### `ResultFrame` como wrapper de tupla (sem pandas/polars)
O port `ResultReaderPort.load()` retorna `ResultFrame(results: tuple[EvaluationResult, ...])`.
A conversão para DataFrame ocorre no adapter de infraestrutura — o domínio
permanece livre de dependências analíticas (ADR-001, ADR-002).

### Relatórios estatísticos: estrutura mínima M0
`WilcoxonReport`, `FriedmanReport`, `MLMReport` têm estrutura mínima coerente
com o que o M4 (StatsPort) precisará. Docstrings explicitam que o detalhamento
é responsabilidade do M4 para evitar premature design.

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| Ruff I001: imports não ordenados no arquivo de testes | `ruff check --fix` corrigiu automaticamente |
| `FriedmanReport` e `MLMReport` com campos `dict` — risco de mutação silenciosa | Omitido `slots=True`; docstring documenta a limitação; usage pattern é sempre create-once-return |

---

## Validação (DoD)

```
uv run ruff check src/inteligenciomica_eval/domain/ports.py \
                  tests/unit/domain/test_ports_contract.py
→ All checks passed!

uv run ruff format --check src/inteligenciomica_eval/domain/ports.py \
                           tests/unit/domain/test_ports_contract.py
→ 2 files already formatted

uv run mypy --strict src/inteligenciomica_eval/domain/ports.py
→ Success: no issues found in 1 source file

uv run lint-imports
→ 4 contracts: 4 kept, 0 broken

uv run pytest tests/unit/domain/test_ports_contract.py -v
→ 37 passed in 0.15s

uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n auto
→ 217 passed | coverage: 95.14% (domain/ports.py: 87%)
```

Cobertura de `ports.py` em 87%: os `...` (corpos de Protocol) nunca são
executados em runtime — são apenas marcadores de assinatura. O coverage
restante é coberto pelos stubs que invocam os métodos via `isinstance`.

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| Todos os 11 ports da §5.1 presentes com assinaturas idênticas | ✅ |
| `mypy --strict` passa sobre o módulo | ✅ |
| `import-linter`: domain sem importar infra/third-party | ✅ |
| `isinstance(stub, XxxPort)` retorna `True` para todos os ports | ✅ (11 testes) |
| DTOs instanciáveis com valores válidos | ✅ (20 testes) |
| Suite completa verde com cobertura ≥ 85% | ✅ (95.14%) |

---

## Observações para Próximas Tarefas

- **TAREFA-011** (fakes in-memory): os stubs de `test_ports_contract.py` servem
  de referência para a implementação dos fakes. As classes `_StubXxx` podem ser
  promovidas para `tests/fakes/` com estado em memória.
- **TAREFA-006+** (use cases): ao compor ports nos use cases, usar apenas os tipos
  exportados por `domain/ports.py` — nenhum import de adapter concreto.
- **M4 (StatsPort)**: `WilcoxonReport`, `FriedmanReport`, `MLMReport` precisarão
  de campos adicionais (ex.: correction method, confidence intervals). Atualizar
  os DTOs e os testes de contrato no milestone correspondente.
- `FriedmanReport.post_hoc` e `MLMReport.coef` são dicts mutáveis em dataclasses
  frozen — considerar `types.MappingProxyType` no M4 se a imutabilidade total
  se tornar requisito.
