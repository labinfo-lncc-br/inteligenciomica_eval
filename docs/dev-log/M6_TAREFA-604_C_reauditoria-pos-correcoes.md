# M6_TAREFA-604_C — Reauditoria Codex após correções

**Data**: 2026-06-03  
**Prompt**: `M6-604B`  
**Papel**: `code-reviewer`  
**Resultado**: **PASS**

## Escopo revalidado

Foram reavaliados os três findings da auditoria anterior:

1. Documentação incorreta do `ielm-eval run --config ...` como fluxo operacional já disponível.
2. Layout de Parquet divergente da implementação real.
3. Ausência de validação sintática para blocos `curl http://localhost:...` no smoke-test.

## Evidências

### 1. Seção 5 corrigida

- `docs/operations_manual.md:276-286` agora marca explicitamente o full run como
  `[PENDENTE: integração CLI full run — TAREFA-310]`.
- O comando futuro foi movido para dentro de blockquote/fence não executável pelo parser,
  evitando que o smoke-test trate esse fluxo ainda inexistente como comando operacional atual.

### 2. Layout de Parquet alinhado ao storage real

- `docs/operations_manual.md:308-329` agora documenta o layout Hive real:
  `round_id=.../experiment_phase=.../base=.../llm=.../<row_id_hex>.parquet`.
- Isso está consistente com `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:419-427`.

### 3. Validação `curl` implementada

- `scripts/validate_manual.py:116-135` adiciona `_curl_errors_in_block`.
- `scripts/validate_manual.py:199-220` incorpora os erros `curl` ao resultado final.
- `scripts/validate_manual.py:43-101` também passou a rastrear corretamente fences de qualquer linguagem, capturando apenas blocos shell relevantes.

## Execução verificada

```text
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/validate_manual.py

Subcomandos ielm-eval:
  ielm-eval version              OK
  ielm-eval run                  OK
  ielm-eval status               OK
  ielm-eval annotate             OK
  ielm-eval analyze              OK
  ielm-eval report               OK
  ielm-eval validate-judge       OK

PASS — todos os subcomandos validados existem na CLI.
```

## Veredito

Não encontrei divergências remanescentes em relação ao Prompt B.

**Recomendação:** `Approve / PASS`.
