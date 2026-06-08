# M3_TAREFA-316_A2 — Correção auditoria Codex B: regressões de seleção por rodada + dry-run

**Data**: 2026-06-08
**Milestone**: M3 — Orquestração das 4 GPUs
**Épico**: E2 (geração) / E3 (orquestração)
**Skill**: python-engineer, test-engineer
**Prioridade / Tamanho**: P0 / XS
**Ciclo**: A2 (correção pós-auditoria Codex B — FAIL → PASS)

---

## Objetivo

Fechar os 3 itens FAIL reportados pela auditoria Codex B da TAREFA-316:

1. Seção "Seleção por rodada" em `test_vllm_generator.py` sem regressões reais.
2. Caminho CLI `run --dry-run` com versão inválida sem teste explícito.
3. Dev-log A com checklist marcado mas sem cobertura demonstrável.

---

## Arquivos Criados / Modificados

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `src/…/infrastructure/wiring.py` | Modificado | Bug fix: `build_fake_container` agora passa `prompt_version=config.generation_prompt_version` ao `ParquetStorage` |
| `tests/unit/infrastructure/test_wiring.py` | Modificado | `TestVLLMGeneratorFactoryVersionPropagation`: 3 novos testes (versão no factory, seleção A/B, storage do fake) |
| `tests/unit/test_cli_smoke.py` | Modificado | `TestRunDryRunPromptVersion`: 3 novos testes (exit nonzero, mensagem cita versão, v1_production não causa erro de versão) |
| `docs/dev-log/M3_TAREFA-316_A2_prompt-fidelidade.md` | Criado | Este relatório |

---

## Problemas Encontrados e Soluções

### Bug em `build_fake_container`
`ParquetStorage` era construído sem `prompt_version=config.generation_prompt_version`.
O dry-run gravaria linhas com `prompt_version=""` em vez do valor configurado no YAML.
**Fix**: passa `prompt_version=config.generation_prompt_version` ao `ParquetStorage`.

### `CliRunner(mix_stderr=False)` inválido
Versão do Typer instalada não aceita `mix_stderr`. Removido — `CliRunner()` padrão
captura stdout+stderr juntos em `result.output`, que é suficiente para as asserções.

### Passagem de path como argumento posicional ao CLI
`run` exige `--config PATH` (opção), não argumento posicional.
Corrigido para `["run", "--config", str(p), "--dry-run"]`.

---

## Validação (DoD)

### Gates executados

```
uv run ruff check .          → All checks passed!
uv run ruff format --check . → 174 files already formatted
uv run mypy --strict src     → Success: no issues found in 61 source files
uv run lint-imports          → 4 contracts: 4 kept, 0 broken
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n 4
    → 1342 passed, 16 skipped
    → Total coverage: 89.66% (gate 85% ✅)
```

### Testes novos

| Arquivo | Testes adicionados |
|---------|-------------------|
| `test_wiring.py::TestVLLMGeneratorFactoryVersionPropagation` | `test_factory_uses_configured_prompt_version` — registry chamado com versão da config |
| | `test_two_different_versions_call_registry_with_distinct_version` — v1 e v2 chamam registry com versões distintas |
| | `test_fake_container_storage_prompt_version_matches_config` — `build_fake_container` propaga `prompt_version` ao storage |
| `test_cli_smoke.py::TestRunDryRunPromptVersion` | `test_invalid_generation_prompt_version_exits_nonzero` — exit != 0 |
| | `test_invalid_version_error_message_cites_version` — saída cita `v99_does_not_exist` |
| | `test_valid_generation_prompt_version_passes_dry_run` — v1_production não causa erro de versão |

---

## Observações

O bug em `build_fake_container` não afetava correctude funcional dos runs (o container
fake é usado apenas em `--dry-run` e testes unitários, nunca para persistir dados reais),
mas era uma inconsistência de proveniência documentável.
