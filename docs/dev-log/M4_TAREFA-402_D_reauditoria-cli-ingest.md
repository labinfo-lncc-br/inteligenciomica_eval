# M4_TAREFA-402_D — Reauditoria da Correção de CLI `annotate --ingest`

**Data**: 2026-06-01
**Milestone**: M4 — Decisão executiva da Rodada 1 (Camada 3 + Agregação + Estatística + Relatório)
**Épico**: E5
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / S

## Objetivo

Reauditar a TAREFA-402 após a correção da lacuna apontada na auditoria anterior: ausência de testes dedicados para a CLI pública `annotate --ingest`.

## Arquivos Revisados

- `tests/unit/test_cli_annotate_export.py`
- `docs/dev-log/M4_TAREFA-402_C_correcao-cli-ingest-tests.md`

## Decisões Técnicas Observadas

- A correção reutiliza o padrão de patch já usado nos testes de `--export`, mantendo o escopo unitário e controlando o writer via `InMemoryResultWriter`.
- Os três cenários faltantes foram adicionados na CLI:
  - fluxo feliz com saída resumida
  - sobrescrita condicionada por `--force`
  - erro amigável para arquivo inexistente

## Problemas Encontrados e Soluções

Nenhum achado novo. A divergência registrada na auditoria `402_B` foi resolvida.

## Validação (DoD)

- `uv run pytest tests/unit/test_cli_annotate_export.py -v` → **16 passed**
- `uv run lint-imports` → **4 contratos OK / 0 quebrados**
- Evidência fornecida pelo desenvolvedor:
  - `ruff` ✅
  - `mypy --strict src` ✅
  - cobertura global **92.48%** ✅
  - suíte completa **955 passed** ✅

## Critérios de Aceitação

| Critério | Evidência | Status |
|---|---|---|
| CLI `annotate --ingest` coberta por teste dedicado | `tests/unit/test_cli_annotate_export.py:663-714` | PASS |
| `--force` testado no fluxo de ingest | `tests/unit/test_cli_annotate_export.py:715-777` | PASS |
| Arquivo inexistente retorna erro amigável | `tests/unit/test_cli_annotate_export.py:779-804` | PASS |
| `lint-imports` OK | execução local da reauditoria | PASS |
| Gates reportados verdes (`ruff`, `mypy`, cobertura >= 85%) | evidência da rodada C | PASS |

## Parecer Final

**PASS**

A única divergência da auditoria anterior foi corrigida. Neste estado, a TAREFA-402 está aprovada na revisão Codex.

## Observações para Próximas Tarefas

- A documentação de execução agora cobre a sequência completa da tarefa: implementação (`A`), auditoria inicial (`B`), correção (`C`) e reauditoria (`D`).
- O avanço para a próxima tarefa continua condicionado à sua autorização e ao fluxo manual de `git add` / `commit` / `push`.
