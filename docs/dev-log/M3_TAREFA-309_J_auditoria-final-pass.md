# M3_TAREFA-309_J — Auditoria final pós-correções (PASS)

**Data**: 2026-06-03
**Milestone**: M3 — Orquestração end-to-end
**Épico**: E3
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / XS

## Objetivo

Validar a correção do último achado remanescente da TAREFA-309:
- `--dry-run --phase B` mostrava wave map e `Total cells per pass` calculados com A+B

## Arquivos Criados / Modificados

- `docs/dev-log/M3_TAREFA-309_J_auditoria-final-pass.md`

## Decisões Técnicas

- A auditoria final foi restrita ao delta do ciclo I, porque os ciclos anteriores já
  haviam sido reavaliados e o único ponto aberto estava no planejamento do dry-run.

## Problemas Encontrados e Soluções

### 1. Corrigido — `scheduler.plan()` passou a receber config filtrado por fase

**Arquivo**: `src/inteligenciomica_eval/cli.py`

O dry-run agora cria uma cópia filtrada da config:

```python
cfg_for_plan = cfg.model_copy(update={"phases": phases})
plan = scheduler.plan(specs, cfg_for_plan)
```

Com isso, a tabela do wave map e o rodapé passam a refletir a mesma fase exibida no
cabeçalho do dry-run.

## Validação (DoD)

### Comandos executados

```bash
PYTHONPATH=tests UV_CACHE_DIR=/tmp/uv-cache uv run ielm-eval run --config config/experiment_round1.yaml --run-id test --dry-run --phase B
```

### Evidência observada

```text
phases       : ['B']
Phase B  : 5 LLM(s) x 3 seed(s) x 2 questions = 30 cells
Total cells per pass: 30 · across 3 passes (generation + metrics + judge): 90
```

Os números do wave map ficaram consistentes com o filtro `--phase B`.

## Critérios de Aceitação

| Critério | Evidência | Status |
|---|---|---|
| Dry-run respeita `--phase` no cabeçalho | smoke `--phase B` | ✅ |
| Dry-run respeita `--phase` na contagem textual | smoke `--phase B` | ✅ |
| Dry-run respeita `--phase` no wave map e total por passada | smoke `--phase B` | ✅ |

## Observações para Próximas Tarefas

- Nenhum achado adicional foi aberto nesta auditoria final.

## Resultado

**PASS**

Resumo:
- o último desvio funcional remanescente foi corrigido
- a TAREFA-309 pode ser considerada aprovada nesta rodada de auditoria
