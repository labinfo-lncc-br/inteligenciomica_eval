# M6_TAREFA-605_A — Revisão Final de Segurança (Segredos + Prompt Injection)

**Data**: 2026-06-03
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: code-reviewer
**Prioridade / Tamanho**: P1 / S

---

## Objetivo

Executar revisão de segurança final do subsistema InteligenciÔmica Eval, verificando as
duas superfícies de risco identificadas no §13 da arquitetura:
1. Segredos no histórico Git
2. Prompt injection indireta via chunk malicioso no template do juiz

Produzir `docs/security_review.md` com checklist S1–S9 completo e evidências de execução.

---

## Arquivos Criados / Modificados

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric.j2` | Modificado | Fix ADR-003: adição de `<contexto id="N">...</contexto>` por chunk |
| `tests/security/__init__.py` | Criado | Módulo Python para o pacote de testes de segurança |
| `tests/security/test_prompt_injection.py` | Criado | 5 testes `@pytest.mark.security` de delimitação de prompt |
| `tests/security/reports/detect_secrets_baseline.json` | Criado | Resultado da varredura detect-secrets (9 FPs) |
| `tests/security/reports/.gitignore` | Criado | Exclui relatórios completos de scan do VCS |
| `.secrets.baseline` | Criado | Baseline detect-secrets com 9 FPs marcados `is_secret: false` |
| `docs/security_review.md` | Criado | Checklist S1–S9 completo com evidências de execução |

---

## Decisões Técnicas

### Fix do template biomed_rubric.j2 (ADR-003)

O template original formatava contextos como `[N] <texto>` sem encapsulamento explícito.
A mitigação de ADR-003 (delimitação dados×instrução) exige marcadores estruturais que
o LLM não confunda com instrução de rubrica.

**Solução:** adicionar `<contexto id="{{ loop.index }}">...</contexto>` por chunk, dentro
do bloco `<AVALIAÇÃO>` já existente. O template já tinha separação estrutural (`<INSTRUÇÕES>`,
`<EXEMPLOS>`, `<AVALIAÇÃO>`); os novos marcadores por chunk tornam a delimitação granular.

Não foi alterado o template `biomed_rubric_v1.jinja2` (versão legada, não usada em produção).

### Padrão de testes de segurança

Seguindo o padrão CLAUDE.md §11 (mockar no nível do SDK), o teste
`test_prompt_sent_to_judge_contains_context_delimiters` usa `AsyncMock` em
`adapter._client.chat.completions.create` e inspeciona `call_args.kwargs["messages"]`
para capturar o prompt real enviado ao juiz — sem chamar GPU nem rede.

Os demais 4 testes verificam a renderização direta via `PromptRegistry`, testando
invariantes estruturais do template (presença de tags, ordenação de seções).

### Falsos positivos detect-secrets

9 itens detectados, todos falsos positivos:
- `api_key="EMPTY"` em 6 arquivos: placeholder obrigatório pelo SDK OpenAI; vLLM não
  impõe autenticação real (ADR-008)
- Docstring de ofuscação de URL em `settings.py`: documenta padrão `user:pass@host`
  sem conter credencial real
- URL fictícia em teste `test_dry_run.py`: `monkeypatch.setenv` com valor de teste
- Hex SHA-256 em fixture de `test_annotation_reader.py`: `RowId` de teste, não credencial

### CVEs encontrados (pip-audit)

**CVE-2025-69872 (diskcache 5.6.3):** dependência transitiva de ragas; vetor exige
escrita no diretório de cache (ambiente controlado). Severidade baixa para este projeto.

**CVE-2026-6587 (ragas 0.3.1):** SSRF no módulo `multi_modal_faithfulness` (nunca
instanciado neste projeto). Confirmado por `grep -rn "multi_modal" src/` → sem saída.
Severidade baixa; atualizar ragas quando nova versão compatível for lançada.

---

## Problemas Encontrados e Soluções

### Template sem delimitadores de contexto (S5 FAIL → PASS)

**Problema:** O template `biomed_rubric.j2` formatava chunks como `[N] texto` sem
encapsulamento explícito. Um chunk malicioso poderia fazer o LLM confundir o conteúdo
do contexto com instrução de rubrica (prompt injection indireta).

**Solução:** Adição de `<contexto id="...">...</contexto>` por chunk. Custo de tokens
mínimo (2 linhas por chunk); ganho de clareza estrutural para o LLM e verificabilidade
programática nos testes.

---

## Validação (DoD)

```
ruff check .                    → All checks passed
ruff format --check .           → 155 files already formatted (1 reformatado antes do commit)
mypy --strict src/              → Success: no issues found in 54 source files
lint-imports                    → 4 contracts kept, 0 broken
pytest -m security -v           → 5 passed in 11.34s
pytest -m "not integration" -n 4 --cov-fail-under=85 → 1140 passed, 90.43% coverage
grep -rn "shell=True" src/      → (vazio) PASS
grep -rn "password|..." config/ → (vazio) PASS
```

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| Nenhum segredo real no Git | ✅ PASS (9 FPs documentados) |
| `grep -rn "shell=True" src/` vazio | ✅ PASS |
| Teste de chunk malicioso PASS | ✅ PASS (5 testes `@pytest.mark.security`) |
| `docs/security_review.md` S1–S9 preenchidos com evidências | ✅ PASS |
| `ruff`, `mypy`, `lint-imports` verdes | ✅ PASS |
| Cobertura ≥ 85% | ✅ PASS (90.43%) |

---

## Gate de Saída M6

Com a TAREFA-605 concluída, todos os itens do gate de M6 estão satisfeitos:
- ✅ TAREFA-601: `tests/mutation/mutation_report.txt` — mutation score >80% em `domain/services/`
- ✅ TAREFA-602: `docs/judge_validation_report.md` — Cohen's κ calculado sobre dados reais
- ✅ TAREFA-603: `pytest -m property` verde em CPU
- ✅ TAREFA-604: `python scripts/validate_manual.py` PASS; manual completo
- ✅ TAREFA-605: `docs/security_review.md` S1–S9 PASS; `pytest -m security` verde

O subsistema InteligenciÔmica Eval (Rodada 1) está **reprodutível, auditável, robusto
e documentado**.

---

## Observações para o Codex (Prompt B)

1. O fix de `biomed_rubric.j2` adiciona `<contexto id="{{ loop.index }}">...</contexto>`
   — verificar que todos os 5 testes de segurança passam e que o template delimita
   corretamente dados×instrução.
2. Os 9 FPs do detect-secrets estão em `.secrets.baseline` com `is_secret: false`;
   verificar que nenhum envolve credencial real.
3. Os 2 CVEs (diskcache, ragas) têm severidade baixa no vetor de ataque deste projeto;
   nenhum é crítico nem bloqueador do M6.
4. `pytest -m security` executado com resultado `5 passed`.
5. `grep -rn "shell=True" src/` → vazio (S4 PASS).
