# M3_TAREFA-316_B — Auditoria da fidelidade do prompt

**Data**: 2026-06-08  
**Auditor**: ChatGPT Codex  
**Commit auditado**: `09455c0`

## Resultado

**FAIL**

## Divergências

| Critério | Arquivo:linha | Gravidade | Achado |
|---|---|---:|---|
| Testes obrigatórios da seleção por rodada e proveniência | `tests/unit/infrastructure/adapters/test_vllm_generator.py:412` | ⚠️ | A seção intitulada `Seleção por rodada — prompt_version muda com generation_prompt_version` não testa isso. O único teste nessa seção é `test_default_render_fn_symbol_is_exported`, que só verifica que `_default_render_fn` é chamável. Não há regressão provando que trocar `generation_prompt_version` altera o bundle usado no wiring nem que `prompt_version` gravado no Parquet passa a refletir essa versão. |
| Teste obrigatório do `--dry-run` para validação da versão do bundle | `tests/unit/config/test_schema.py:356` | ⚠️ | Há validação de `load_round_config()` para versão válida/inválida, mas não há teste explícito do caminho de CLI `run --dry-run` cobrindo `generation_prompt_version`. O Prompt B pedia cobertura específica do dry-run. A suíte atual prova o schema, não o comportamento do comando. |
| Relatório A afirma cobertura que o diff não entrega | `docs/dev-log/M3_TAREFA-316_A_prompt-fidelidade.md:124` | ⚠️ | O relatório A marca como atendidos `seleção por rodada` e `dry-run valida versão`, mas esses testes não aparecem no diff desta tarefa. O relatório de execução ficou mais forte do que a evidência versionada. |

## Verificações item a item

1. **ADR-015**: presente e coerente em `docs/adr/ADR-015-prompt-geracao-versionado.md`.
2. **Bundle `v1_production`**:
   - `system.txt` bate verbatim com `system_prompt.txt` local (`diff -u` sem diferenças).
   - `user.j2` reproduz o wrapper esperado com `{{ context }}` e `{{ question }}`.
3. **`render_rag_generation`**:
   - contexto `"[PMID:{source}] {text}"` com `"\n\n"` em `registry.py`;
   - `source=""` vira `"N/A"`;
   - versão inexistente levanta `ValueError` com lista disponível;
   - `render_biomed_rubric()` permaneceu intacto.
4. **`Chunk.source`**: campo aditivo com default `""`, sem violação do import-linter.
5. **`QdrantRetrieverAdapter`**: preenche `source` de `payload["source"]`; `id` segue sendo o id do ponto.
6. **`VLLMGeneratorAdapter`**:
   - envia exatamente `messages=[system, user]`;
   - aplica strip de `<think>` com `re.DOTALL` antes de `GenerationOutput`;
   - mantém `batch_invariant=False`;
   - logs só com tamanhos/contagem, sem prompt cru.
7. **`RoundConfig.generation_prompt_version`**:
   - default `v1_production`;
   - validado contra `list_rag_versions()` em `load_round_config()`;
   - erro cita a lista de versões.
8. **Wiring / proveniência**:
   - `build_container()` injeta `config.generation_prompt_version` no renderer do gerador;
   - `ParquetStorage(... prompt_version=config.generation_prompt_version)` está correto no código;
   - `experiment_round1.yaml` inclui o campo e comentário.
9. **Testes**:
   - cobrem `system+user`, strip de `<think>`, fidelidade ao fixture e `Chunk.source`;
   - **não** cobrem explicitamente a seleção por rodada até o storage nem o `--dry-run` com `generation_prompt_version`.
10. **Restrições DoD**:
   - `GeneratorPort.generate` não mudou;
   - adapters do juiz e pipeline A não foram tocados;
   - não encontrei segredo nos bundles.

## Gates executados

### Ruff

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
All checks passed!
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .
174 files already formatted
```

### Mypy

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src
Success: no issues found in 61 source files
```

### Import Linter

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports
Contracts: 4 kept, 0 broken.
```

### Testes focais da tarefa

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/prompts/test_prompt_registry.py tests/unit/infrastructure/adapters/test_vllm_generator.py tests/unit/infrastructure/adapters/test_qdrant_retriever_unit.py tests/unit/config/test_schema.py -q
105 passed in 1.86s
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/test_m1_pipeline_integration.py -q
1 skipped, 1 warning in 6.95s
```

### Cobertura

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4 -q
1312 passed, 6 skipped, 21 warnings in 160.58s (0:02:40)
Required test coverage of 85% reached. Total coverage: 89.64%
```

## Observações

- A verificação de empacotamento no wheel não pôde ser reproduzida localmente nesta sessão porque `uv build` tentou resolver `hatchling` via rede e falhou por DNS. No código-fonte, não há indício de exclusão explícita de `infrastructure/prompts/rag/**`, e `PackageLoader` está configurado corretamente, mas esta parte não ficou verificada por build real no sandbox atual.
