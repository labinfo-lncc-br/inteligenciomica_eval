# M3_TAREFA-316_A — Fidelidade do prompt de geração + prompt selecionável por rodada

**Data**: 2026-06-08
**Milestone**: M3 — Orquestração das 4 GPUs (feature work pós-saneamento)
**Épico**: E2 (geração) / E3 (orquestração)
**Skill**: rag-engineer, python-engineer, test-engineer
**Prioridade / Tamanho**: P0 / M
**ADR**: ADR-015 (novo — prompt de geração versionado)

---

## Objetivo

Tornar o gerador do eval **fiel ao prompt de produção** (messages system+user,
contexto com PMID, strip de `<think>`) e transformar o prompt num **fator selecionável
por rodada** (D1 — bundle versionado `{system, user}` em `infrastructure/prompts/rag/`).

---

## Arquivos Criados / Modificados

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `docs/adr/ADR-015-prompt-geracao-versionado.md` | Criado | Decisão D1–D5 |
| `src/…/infrastructure/prompts/rag/v1_production/system.txt` | Criado | Cópia verbatim do system_prompt.txt de produção |
| `src/…/infrastructure/prompts/rag/v1_production/user.j2` | Criado | Wrapper verbatim de `_build_prompt_with_context` |
| `tests/fixtures/production_messages_fixture.json` | Criado | Fixture de referência para teste de fidelidade |
| `src/…/domain/ports.py` | Modificado | `Chunk.source: str = ""` (campo aditivo) |
| `src/…/infrastructure/prompts/registry.py` | Modificado | `render_rag_generation` + `list_rag_versions` |
| `src/…/infrastructure/adapters/qdrant_retriever.py` | Modificado | Preenche `source` de `payload["source"]` |
| `src/…/infrastructure/adapters/vllm_generator.py` | Modificado | `render_fn`, messages system+user, strip `<think>` |
| `src/…/infrastructure/config/schema.py` | Modificado | `generation_prompt_version` + validação em `load_round_config` |
| `src/…/infrastructure/wiring.py` | Modificado | `_VLLMGeneratorFactory` recebe registry+version; `prompt_version=config.generation_prompt_version` |
| `config/experiment_round1.yaml` | Modificado | Campo `generation_prompt_version: "v1_production"` + comentário |
| `tests/unit/infrastructure/adapters/test_vllm_generator.py` | Modificado | `render_fn` em vez de `prompt_fn`; novos testes system+user, strip `<think>`, fidelidade |
| `tests/unit/infrastructure/prompts/test_prompt_registry.py` | Modificado | 13 novos testes: `list_rag_versions`, `render_rag_generation`, erro de versão inexistente |
| `tests/unit/infrastructure/adapters/test_qdrant_retriever_unit.py` | Modificado | 3 novos testes para `Chunk.source` |
| `tests/unit/config/test_schema.py` | Modificado | 2 novos testes: default passa, versão inválida falha |

---

## Decisões Técnicas

### D1 — Bundle versionado `{system.txt, user.j2}`
- `system.txt` = texto puro (sem variáveis Jinja2) carregado via `loader.get_source()`
- `user.j2` = template Jinja2 com `{{ context }}` e `{{ question }}`
- Contexto: `"\n\n".join(f"[PMID:{c.source or 'N/A'}] {c.text}" for c in contexts)`
- Empacotamento: hatchling inclui todos os arquivos do pacote por padrão — nenhuma
  alteração no `pyproject.toml` necessária

### D2 — `render_fn` substitui `prompt_fn`
- `VLLMGeneratorAdapter.__init__` agora aceita
  `render_fn: Callable[[str, Sequence[Chunk]], tuple[str, str]] | None`
- Default: `_default_render_fn` (lazy import do registry, bundle `v1_production`)
- Injeção para testes: `render_fn=lambda q, ctx: ("SYS", "USER")` — padrão existente mantido

### D3 — Strip de `<think>`
- `_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)`
- Aplicado à saída bruta ANTES de montar `GenerationOutput`
- Idêntico ao `re.sub` do `orchestrator_service.py`

### D4 — `prompt_version` no Parquet = `config.generation_prompt_version`
- Antes: `prompt_registry.prompt_version` (git-describe — não correspondia ao prompt RAG)
- Depois: `config.generation_prompt_version` (ex.: `"v1_production"`)
- Mudança em `wiring.py` linha `storage = ParquetStorage(..., prompt_version=...)`

### D5 — Validação de `generation_prompt_version` no carregamento
- `load_round_config` chama `get_default_registry().list_rag_versions()` após validação Pydantic
- Versão inválida → `ConfigValidationError("generation_prompt_version", msg_com_lista)`
- Lazy import evita dependência do schema no registry em import time

### Logging
- `vllm_generation_completed` agora inclui `system_len`, `user_len`, `num_chunks`
- System/user NÃO logados crus (ADR-008 / política TAREFA-314)

---

## Problemas Encontrados e Soluções

1. **`noqa: PLC0415` inválido** — ruff não habilitava essa regra; removido.
2. **`Sequence` não importado no wiring.py** — adicionado a `from collections.abc import`.
3. **`type: ignore[type-arg]` desnecessário** — mypy aceitou sem annotation extra; removido.

---

## Validação (DoD)

### Gates executados

```
uv run ruff check .          → All checks passed!
uv run ruff format --check . → 170 files already formatted (após format aplicado)
uv run mypy --strict src     → Success: no issues found in 61 source files
uv run lint-imports          → 4 contracts: 4 kept, 0 broken
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n 4
    → 1336 passed, 16 skipped
    → Total coverage: 89.64% (gate 85% ✅)
```

### Testes novos/modificados

| Arquivo | Novos testes | Total |
|---------|-------------|-------|
| `test_vllm_generator.py` | 14 (system+user, strip `<think>`, fidelidade) | ~30 |
| `test_prompt_registry.py` | 13 (`list_rag_versions`, `render_rag_generation`) | ~30 |
| `test_qdrant_retriever_unit.py` | 3 (`Chunk.source`) | ~21 |
| `test_schema.py` | 2 (`generation_prompt_version`) | ~37 |

### Critérios de Aceitação

- [x] ADR-015 presente, status Aprovado, descreve bundle versionado
- [x] Bundle `v1_production/system.txt` = cópia verbatim do `system_prompt.txt` de produção
- [x] Bundle `v1_production/user.j2` = wrapper verbatim de `_build_prompt_with_context`
- [x] `render_rag_generation`: contexto `[PMID:{source}] {text}`; source vazio → `N/A`
- [x] Versão inexistente → `ValueError` com lista de disponíveis
- [x] `render_biomed_rubric` intacto
- [x] `Chunk.source` aditivo, default `""`; import-linter verde
- [x] `QdrantRetrieverAdapter` preenche `source` de `payload["source"]`
- [x] `VLLMGeneratorAdapter` envia `messages=[system, user]`; strip `<think>` (DOTALL)
- [x] `batch_invariant=False`; system/user NÃO logados crus
- [x] `RoundConfig.generation_prompt_version` default `"v1_production"`; validado no carregamento
- [x] Wiring usa `config.generation_prompt_version`; `prompt_version` no Parquet = bundle version
- [x] `experiment_round1.yaml` com campo + comentário
- [x] Testes: system+user, strip `<think>`, fidelidade contra fixture, seleção por rodada,
        retriever preenche source, dry-run valida versão
- [x] Cobertura ≥ 85% (89.64%)
- [x] `from __future__ import annotations` em todos os arquivos novos/modificados
- [x] mypy --strict limpo; ruff limpo; import-linter limpo

---

## Observações para Próximas Tarefas

- **Fixture `production_messages_fixture.json`**: derivado do formato de produção com
  PMIDs reais; útil como referência de regressão se o bundle `v1_production` for alterado.
- **Novas redações de prompt**: criar `infrastructure/prompts/rag/<nova_versão>/` com
  `system.txt` e `user.j2`, depois setar `generation_prompt_version: <nova_versão>` no YAML.
- **`vllm_generator.py` cobertura 96%** — as linhas 33-37 (`_default_render_fn` lazy import)
  não são exercidas pelos testes unitários (que injetam `render_fn`); são cobertas pelos
  testes de integração M1 quando o adapter real é instanciado sem injeção.
