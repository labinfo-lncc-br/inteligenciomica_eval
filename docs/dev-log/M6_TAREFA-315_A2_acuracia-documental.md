# M6_TAREFA-315_A2 — Acurácia Documental (ciclo de correção pós-auditoria B)

**Data**: 2026-06-08
**Milestone**: M3/M6 — Saneamento pós-auditoria completa
**Épico**: E9 (docs)
**Skill**: system-architect
**Ciclo**: A2 — correção do achado da auditoria B (ChatGPT Codex)

---

## Achado Corrigido

### ⚠️ B1 — `docs/operations_manual.md:421` — prosa `endpoint_masked` no formato antigo

A prosa da Seção 4-B descrevia o endpoint mascarado como `scheme://host:port/***`
(formato anterior à TAREFA-314), enquanto o exemplo JSON logo abaixo já usava
`scheme://host:port` (formato correto pós-TAREFA-314 com `mask_url()`).

O ciclo A corrigiu apenas o exemplo JSON (linha `"endpoint_masked": "http://localhost:8010"`),
mas manteve a prosa introdutória na forma antiga — criando dois contratos contraditórios
na mesma seção.

**Correção:**

```diff
- com `config_hash`, topologia, endpoint mascarado (`scheme://host:port/***`),
+ com `config_hash`, topologia, endpoint mascarado (`scheme://host:port` — sem path,
+ pós-TAREFA-314),
```

**Arquivo**: `docs/operations_manual.md`, linha 421.

---

## Validação (DoD A2)

### Gates de qualidade

```
ruff check .             → All checks passed!
ruff format --check .    → 174 files already formatted
```

### validate_manual.py PASS

```
uv run python scripts/validate_manual.py

Subcomandos ielm-eval: ... (7 OK)
Flags obrigatórias: --run-id OK, --require-verified-determinism OK
PASS — todos os subcomandos e flags validados existem na CLI.
```

---

## Critérios de Aceitação A2

- [x] Prosa da Seção 4-B alinhada ao exemplo JSON e ao comportamento real de `mask_url()` pós-TAREFA-314
- [x] Sem ocorrência de `/***` em `docs/operations_manual.md`
- [x] `validate_manual.py` PASS
- [x] ruff/format OK
