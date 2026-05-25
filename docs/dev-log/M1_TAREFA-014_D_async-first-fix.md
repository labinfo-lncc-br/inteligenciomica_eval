# M1_TAREFA-014_D — Async-First Fix (pós-auditoria C)

**Data**: 2026-05-24
**Milestone**: M1 — Adapters de Recuperação e Geração
**Épico**: E1
**Skill**: python-engineer
**Prioridade / Tamanho**: P0 / S

## Objetivo

Corrigir os dois bloqueadores apontados na reauditoria C (`M1_TAREFA-014_C_reauditoria-notas-m1.md`):

1. **[Bloqueador]** `VLLMGeneratorAdapter.generate()` era `def` síncrono com `asyncio.run()` — viola Nota M1 item 1 e a restrição `Async` da TAREFA-014.
2. **[Importante]** Testes validavam apenas `_generate_async()` (privado) em vez do contrato público.

## Arquivos Criados / Modificados

| Arquivo | Ação |
|---|---|
| `src/inteligenciomica_eval/domain/ports.py` | `GeneratorPort.generate` → `async def` |
| `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py` | `generate` → `async def`; removido `asyncio.run()`, `import asyncio` e `_generate_async` |
| `tests/fakes/generation.py` | `FakeGenerator.generate` → `async def` |
| `tests/unit/domain/test_ports_contract.py` | `_StubGenerator.generate` → `async def`; teste de comportamento → `async def` + `await` |
| `tests/e2e/_harness.py` | `run_min_round` → `async def`; `generator.generate(...)` → `await generator.generate(...)` |
| `tests/e2e/test_min_round_stub.py` | `_run` + todos os 6 testes `@pytest.mark.e2e` → `async def`; todas as chamadas → `await` |
| `tests/unit/fakes/test_fakes_satisfy_ports.py` | `TestFakeGenerator`: 4 métodos → `async def`; todas as chamadas `gen.generate(...)` → `await` |
| `tests/unit/infrastructure/adapters/test_vllm_generator.py` | `adapter._generate_async(...)` → `adapter.generate(...)`; docstring atualizada |
| `docs/dev-log/M1_TAREFA-014_D_async-first-fix.md` | Criado |

## Decisões Técnicas

### 1. Port evolui para async — tensão arquitetural resolvida

A reauditoria C identificou uma tensão: `GeneratorPort` (domínio) era síncrono, mas Nota M1 exige adapters de rede async-first. A resolução adotada é tornar o próprio port `async def generate(...)`, propagando a política async para o contrato de domínio. Isso mantém consistência: o contrato reflete o regime de execução real exigido para adapters de rede.

### 2. `_generate_async` eliminado — sem duplicação de lógica

O método privado `_generate_async` existia apenas porque `generate` era um wrapper síncrono. Com `generate` agora `async def`, toda a lógica foi promovida diretamente para `generate` e `_generate_async` foi removido. Sem código morto.

### 3. `import asyncio` removido

O único uso de `asyncio` era `asyncio.run(...)` no wrapper síncrono. Com a remoção desse wrapper, a importação deixou de ser necessária.

### 4. Propagação em cascata — pytest-asyncio `asyncio_mode = "auto"`

Com `asyncio_mode = "auto"` já configurado em `pyproject.toml`, converter testes para `async def` é suficiente — não é necessário adicionar `@pytest.mark.asyncio` individualmente. O harness E2E (`run_min_round`) e o helper `_run` também se tornaram `async def` por transitividade.

## Problemas Encontrados e Soluções

Nenhum problema técnico durante a aplicação das mudanças. A cascata foi linear: port → adapter → fake → tests.

## Validação (DoD)

| Gate | Status | Evidência |
|---|---|---|
| `uv run ruff check .` | ✅ | `All checks passed!` |
| `uv run ruff format --check .` | ✅ | `69 files already formatted` |
| `uv run mypy --strict src` | ✅ | `Success: no issues found in 24 source files` |
| `uv run lint-imports` | ✅ | `4 kept, 0 broken` |
| `uv run pytest tests/unit/infrastructure/adapters/test_vllm_generator.py -v` | ✅ | `16 passed` |
| `uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n auto` | ✅ | `579 passed, 7 skipped`; cobertura total `96.39%`; `vllm_generator.py` com `98%` |

## Critérios de Aceitação

**Veredito**: PASS

| Critério | Status | Arquivo:linha |
|---|---|---|
| 1–8. Todos os critérios aprovados na auditoria B | ✅ | Inalterados |
| 9. Adapter é async-first (Nota M1 item 1 + restrição `Async` da tarefa) | ✅ | `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py:93` — `async def generate(...)` |
| 10. Testes exercitam o contrato público `generate()` diretamente | ✅ | `tests/unit/infrastructure/adapters/test_vllm_generator.py` — todas as 12 chamadas usam `await adapter.generate(...)` |

## Observações para Próximas Tarefas

- A tensão arquitetural documentada na reauditoria C foi resolvida: `GeneratorPort` agora é `async def`, alinhado com Nota M1 item 1.
- Futuros adapters de rede em M1 devem implementar `async def generate(...)` para satisfazer o port.
- O harness E2E é agora `async def run_min_round(...)` — callers precisam de `await`.
