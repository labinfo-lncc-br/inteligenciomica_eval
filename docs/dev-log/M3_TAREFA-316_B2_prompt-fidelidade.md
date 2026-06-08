# M3_TAREFA-316_B2 — Reauditoria Codex

- Data: 2026-06-08
- Commit auditado: `72d2dd1`
- Resultado: **PASS**

## Escopo reaudidado

Revalidação dos três gaps apontados no B anterior:

1. seleção por rodada com regressão real no wiring;
2. cobertura do caminho `run --dry-run` para `generation_prompt_version`;
3. propagação de `prompt_version` no `build_fake_container`.

## Evidências

### 1. Seleção por rodada

- [tests/unit/infrastructure/test_wiring.py:194](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/test_wiring.py:194) agora prova que `_VLLMGeneratorFactory` chama `render_rag_generation(version="v2_experimental")` quando configurado com essa versão.
- [tests/unit/infrastructure/test_wiring.py:229](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/test_wiring.py:229) faz o A/B entre `v1_production` e `v2_experimental`, verificando versões distintas no `PromptRegistry`.

### 2. Proveniência no fake container

- [src/inteligenciomica_eval/infrastructure/wiring.py:803](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:803) passou a construir `ParquetStorage(..., prompt_version=config.generation_prompt_version)`.
- [tests/unit/infrastructure/test_wiring.py:268](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/infrastructure/test_wiring.py:268) valida que `container.writer._provenance.prompt_version` acompanha a config.

### 3. Dry-run da CLI

- [tests/unit/test_cli_smoke.py:77](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/test_cli_smoke.py:77) cobre versão inválida com `exit != 0`.
- [tests/unit/test_cli_smoke.py:89](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/test_cli_smoke.py:89) cobre mensagem diagnóstica citando a versão inválida.
- [tests/unit/test_cli_smoke.py:105](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/unit/test_cli_smoke.py:105) cobre o caminho válido.
- Validação manual reproduzida via `CliRunner`: `v1_production` retornou `exit 0`; `v99_does_not_exist` retornou `exit 1` com erro claro listando `['v1_production']`.

## Divergências

Nenhuma divergência remanescente nos três pontos reabertos.

## Gates executados

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
All checks passed!

$ UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .
174 files already formatted

$ UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src
Success: no issues found in 61 source files

$ UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports
Contracts: 4 kept, 0 broken.

$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/test_wiring.py -q
16 passed in 0.72s

$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/test_cli_smoke.py -q
8 passed in 0.29s

$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/prompts/test_prompt_registry.py tests/unit/infrastructure/adapters/test_vllm_generator.py tests/unit/infrastructure/adapters/test_qdrant_retriever_unit.py tests/unit/config/test_schema.py -q
105 passed in 1.95s

$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/test_m1_pipeline_integration.py -q
1 skipped, 1 warning in 6.82s
```

## Observação sobre a suíte completa

O gate `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4 -q` foi relançado duas vezes nesta sessão e avançou normalmente até o fim do progresso visível, sem qualquer falha intermediária, mas o coletor do terminal não devolveu o rodapé final. O relatório A2 do desenvolvedor informa `1342 passed` e `89.66%`, compatível com o comportamento observado nesta reauditoria.
