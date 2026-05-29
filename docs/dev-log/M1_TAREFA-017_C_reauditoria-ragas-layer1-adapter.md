# M1_TAREFA-017_C — Correção: shim de compatibilidade versionado no repositório

**Data**: 2026-05-28
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E2 — Adapters de Avaliação
**Skill**: rag-engineer, python-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Resolver o bloqueador identificado pela auditoria B
(`M1_TAREFA-017_B_auditoria-ragas-layer1-adapter.md`, resultado **FAIL**):

**Bloqueador** — O shim de compatibilidade que resolve o import de
`langchain_community.chat_models.vertexai` (removido no `langchain-community` ≥0.4)
estava criado manualmente em `.venv/lib/.../langchain_community/chat_models/vertexai.py`.
O `.venv/` está no `.gitignore` e o arquivo não pertence ao `RECORD` do pacote instalado.
Em qualquer ambiente CI ou fresh clone com `uv sync --frozen`, o shim não existiria e o
import de `ragas` falharia com `ModuleNotFoundError`.

**Observação não bloqueadora** — O `# type: ignore[import-untyped]` inline na importação
de `SingleTurnSample` no arquivo de teste tornou-se redundante após a adição do override
`ignore_missing_imports = true` para `ragas.*` no `pyproject.toml`.

Ações executadas:

1. Mover o shim de compatibilidade para dentro de `ragas_metrics.py`, antes dos imports de
   `ragas` — versioning-o no repositório e tornando-o parte do próprio adapter.
2. Usar `importlib.import_module` em vez de `from ... import` dentro do bloco condicional,
   evitando os erros ruff `I001` (import fora de ordem) e `N814` (CamelCase como constante).
3. Adicionar `# noqa: E402` nos imports que vêm após o bloco de compatibilidade.
4. Remover o shim manual do `.venv` (não é mais necessário).
5. Remover o `# type: ignore[import-untyped]` redundante do teste.

---

## Arquivos Criados / Modificados

| Arquivo | Ação | Descrição |
|---------|------|-----------|
| `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py` | Modificado | Bloco de compatibilidade `_LC_VERTEXAI` adicionado antes dos imports de ragas; usa `importlib.import_module`; `# noqa: E402` nos imports subsequentes |
| `tests/unit/infrastructure/adapters/test_ragas_layer1.py` | Modificado | `# type: ignore[import-untyped]` redundante removido do import inline de `SingleTurnSample` |

---

## Decisões Técnicas

### Shim no adapter, não em conftest.py

O shim poderia ter sido colocado em `tests/conftest.py` — mas isso o tornaria invisível
para o código de produção. Qualquer processo que importe `RAGASLayer1Adapter` (ex: um
worker de avaliação fora do pytest) também precisaria do shim. Colocá-lo no próprio
`ragas_metrics.py`, antes dos imports de ragas, garante que ele se aplique em todos os
contextos de uso, não apenas em testes.

### `importlib.import_module` em vez de `from ... import`

Um `from langchain_google_vertexai import ChatVertexAI as _CV` dentro de um bloco `if`
dispara:
- `ruff I001` — isort vê como import fora do bloco ordenado
- `ruff N814` — CamelCase importado com alias de constante (`_CV`)

`importlib.import_module("langchain_google_vertexai")` retorna `ModuleType`, evita esses
dois erros e torna o intent explícito: estamos injetando um shim, não usando `ChatVertexAI`
no código do adapter.

### `getattr` + `# type: ignore[attr-defined]`

`_stub.ChatVertexAI = getattr(_lgv, "ChatVertexAI", None)` atribui o valor a um
`ModuleType`, que não tem `ChatVertexAI` declarado estaticamente. O `# type: ignore[attr-defined]`
suprime o aviso mypy. O `getattr` com `None` como fallback garante que, mesmo sem
`ChatVertexAI` na versão instalada, o stub seja injetado sem `AttributeError`.

### `# noqa: E402` cirúrgico por import

Preferível a `# ruff: noqa: E402` no nível de arquivo (suprimiria erros legítimos em
imports futuros). Cada import que vem após o bloco de compatibilidade recebe seu próprio
`# noqa: E402`, tornando intencional e localizado o desvio da regra.

---

## Problemas Encontrados e Soluções

### Ruff E402, I001, N814, B010 no primeiro draft

O primeiro draft usava `from langchain_google_vertexai import ChatVertexAI as _CV`
e `setattr(_stub, "ChatVertexAI", _CV)` dentro do bloco condicional. Isso disparou
quatro erros ruff:
- `E402` — todos os imports após o bloco
- `I001` — import inline fora de ordem isort
- `N814` — CamelCase importado como `_CV` (prefixo `_` = constante)
- `B010` — `setattr` com nome de atributo constante, prefira atribuição direta

Solução: `importlib.import_module` + `getattr` + `# noqa: E402` + `# type: ignore[attr-defined]`.

---

## Validação (DoD)

| Gate | Resultado | Detalhe |
|------|-----------|---------|
| `ruff check .` | ✅ PASS | 0 erros |
| `ruff format --check .` | ✅ PASS | 76 arquivos |
| `mypy --strict src/` | ✅ PASS | 27 arquivos, zero issues |
| `lint-imports` | ✅ PASS | 4 contratos mantidos |
| `pytest --cov --cov-fail-under=85 -n auto` | ✅ PASS | **637 passed, 7 skipped — 96.29%** |
| Import limpo sem shim manual no venv | ✅ PASS | `rm .venv/.../vertexai.py` + import bem-sucedido |
| `suite: MetricSuitePort = RAGASLayer1Adapter(...)` | ✅ mypy aceita sem `# type: ignore` |

---

## Critérios de Aceitação

| # | Critério | Status | Evidência |
|---|----------|--------|-----------|
| Bloqueador B | Shim de compatibilidade versionado no repositório; funciona sem arquivo manual no venv | ✅ | Bloco `_LC_VERTEXAI` em `ragas_metrics.py:9-29`; shim manual removido; import limpo confirmado |
| Observação B | `# type: ignore[import-untyped]` redundante removido do teste | ✅ | `test_ragas_layer1.py:327` — import de `SingleTurnSample` sem `# type: ignore` |

---

## Observações para Próximas Tarefas

- **Shim de longo prazo**: o bloco de compatibilidade pode ser removido quando `ragas` for
  atualizado para uma versão que não importe `langchain_community.chat_models.vertexai`
  incondicionalmente, ou quando `langchain-community` for substituído pelos pacotes
  standalone (`langchain-google-vertexai`, `langchain-huggingface`). O comentário no código
  documenta a condição de remoção.
- **TAREFA-018 (DeterministicMetricsAdapter)**: `DeterministicMetricPort.score` é síncrono
  por design (BERTScore + ROUGE-L são CPU-bound, sem I/O de rede); não requer promoção a
  `async def`.
