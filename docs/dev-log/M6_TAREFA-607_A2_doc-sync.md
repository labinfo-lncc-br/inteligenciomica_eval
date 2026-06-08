# M6_TAREFA-607_A2 — Doc-sync (ciclo de correção pós-auditoria B)

**Data**: 2026-06-08
**Milestone**: M6 — Hardening, validação e documentação final
**Épico**: E9 (docs)
**Skill**: system-architect
**Ciclo**: A2 — correção do achado da auditoria B (ChatGPT Codex)

---

## Achado Corrigido

### ⚠️ B1 — `docs/arquitetura_detalhada_validacao_inteligenciomica.md` — referências residuais a `serve`

O subcomando `serve` **não existe** na CLI real (confirmado por `ielm-eval --help`; 8 subcomandos
reais: `version`, `run`, `annotate`, `analyze`, `report`, `status`, `show-config`, `validate-judge`).

Embora a §15 já tivesse sido corrigida na Parte A, três ocorrências residuais permaneceram em outras
seções do documento:

1. **Diagrama C4 (linha ~138)**: `│  │  serve/    │` no bloco `cli/` → corrigido para `│  │  status/   │`
2. **Tabela de stack (§7.1)**: `CLI (run/analyze/report/annotate/serve)` → corrigido para
   `CLI (run/annotate/analyze/report/status/show-config/validate-judge)`
3. **Texto da topologia (§7.2)**: `O \`serve\`/\`run\` da CLI orquestra esse ciclo de vida.` →
   corrigido para `O \`run\` da CLI orquestra esse ciclo de vida.`

**Ocorrência preservada (não alterada)**: linha ~1253 usa `serve` como verbo comum ("Cada servidor
vLLM serve **um** modelo") — sem relação com subcomando CLI.

---

## Validação (DoD A2)

### git diff --name-only

```
docs/arquitetura_detalhada_validacao_inteligenciomica.md
docs/visao_alto_nivel_validacao_inteligenciomica.md
```

DOCS-ONLY confirmado — nenhum `.py`, `.yaml`, teste ou config tocado.

### Grep de validação

```bash
grep -n "\bserve\b" docs/arquitetura_*.md | grep -v "server\|service\|Server\|served\|#"
```

Única ocorrência restante: linha ~1253 (`serve **um** modelo`) — verbo, não subcomando.

---

## Critérios de Aceitação A2

- [x] `serve/` removido do diagrama C4
- [x] `serve` removido da tabela de stack (§7.1)
- [x] `serve/run` corrigido para `run` na descrição da topologia (§7.2)
- [x] Nenhuma outra ocorrência de `serve` como subcomando CLI no documento
- [x] DOCS-ONLY mantido
