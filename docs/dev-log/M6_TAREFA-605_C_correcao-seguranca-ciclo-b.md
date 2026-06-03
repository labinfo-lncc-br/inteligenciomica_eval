# M6_TAREFA-605_C — Revisão Final de Segurança (Correções pós-auditoria Codex)

**Data**: 2026-06-03
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: code-reviewer
**Prioridade / Tamanho**: P1 / S

---

## Objetivo

Corrigir os três pontos levantados pela auditoria Codex (Parte B) sobre a TAREFA-605:
1. **Bloqueador S7** — `RAGASLayer1Adapter` logava `judge_url` cru; credenciais embutidas
   na URL poderiam vazar para logs.
2. **Aviso** — Template `biomed_rubric.j2` com fix de delimitação presente, mas sem
   o comentário referenciando ADR-003 pedido na especificação.
3. **Aviso** — Teste de prompt injection usa AsyncMock (padrão do projeto) em vez de
   `respx.mock` (mencionado na spec); ausência de justificativa documentada.

---

## Arquivos Criados / Modificados

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py` | Modificado | Substitui `judge_url=self._judge_url` por `mask_endpoint(self._judge_url)` nos 3 eventos de log; importa `mask_endpoint` de `settings.py` |
| `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric.j2` | Modificado | Adiciona comentário Jinja `{# ADR-003: delimitação dados×instrução #}` antes do loop de chunks |
| `tests/security/test_prompt_injection.py` | Modificado | Adiciona nota no docstring explicando a escolha deliberada de AsyncMock vs respx (CLAUDE.md §11) |
| `docs/security_review.md` | Modificado | Atualiza S7: documenta o fix, o comando de verificação pós-fix e confirma PASS |

---

## Decisões Técnicas

### Fix S7: uso de `mask_endpoint` existente

A função `mask_endpoint` já estava implementada em
`infrastructure/config/settings.py` (linha 47) com exatamente a lógica necessária:
substituição do segmento `user:pass@` por `****@` via regex `_URL_AUTH_RE`.

Não foi criada nova função nem utilitário — reutilização direta da função existente.
Os três eventos de log afetados eram independentes (error, warning, info) e todos foram
corrigidos com o mesmo padrão.

**Verificação pós-fix:**
```bash
grep -rn "judge_url=self\._judge_url" src/
```
Saída: (vazia) — nenhuma ocorrência de URL crua em log.

### Aviso AsyncMock vs respx (não alterado, apenas documentado)

A spec da TAREFA-605 menciona `respx.mock` como opção de simulação. O CLAUDE.md §11
(TAREFA-014-G, decisão final) estabelece AsyncMock como padrão definitivo para adapters
com SDK OpenAI — `httpx.MockTransport` pode não interceptar chamadas quando o SDK usa
`asyncify`/`asyncio.to_thread` em ambientes sandboxed. A abordagem AsyncMock é 100%
determinística e independente de versão de anyio/sniffio/httpx.

A escolha foi mantida; a justificativa foi adicionada ao docstring do módulo de teste
para que o Codex e futuros revisores entendam o raciocínio sem precisar buscar na
documentação externa.

---

## Problemas Encontrados e Soluções

### Bloqueador S7 detectado pelo Codex

**Problema:** `ragas_metrics.py` linhas 253, 262 e 272 passavam `judge_url=self._judge_url`
diretamente para eventos structlog. A URL vem da variável de ambiente `VLLM_JUDGE_URL`;
se o operador configurar uma URL com credenciais embutidas (padrão `http://user:pass@host`),
elas ficariam visíveis nos logs de produção — violando S7 e ADR-008.

**Raiz do problema:** O campo `judge_url` foi adicionado nos logs para rastreabilidade
(identificar qual servidor RAGAS estava sendo usado), mas sem ofuscação das credenciais.
A função `mask_endpoint` existia para exatamente esse caso e não foi usada.

**Solução:** Importar `mask_endpoint` e envolver as três ocorrências. Zero impacto de
performance (operação de regex sobre string curta, executada apenas em eventos de log).

---

## Validação (DoD)

```
ruff check .                         → All checks passed
ruff format --check .                → 155 files already formatted
mypy --strict src/                   → Success: no issues found in 54 source files
lint-imports                         → 4 contracts kept, 0 broken
pytest -m security -v                → 5 passed in 11.46s
pytest -m "not integration" -n 4 \
  --cov-fail-under=85                → 1140 passed, 90.43% coverage
grep -rn "judge_url=self._judge_url" → (vazio) PASS
```

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| Bloqueador S7 resolvido: `judge_url` ofuscado nos 3 eventos de log | ✅ PASS |
| Comentário ADR-003 presente em `biomed_rubric.j2` | ✅ PASS |
| Justificativa AsyncMock vs respx documentada no teste | ✅ PASS |
| `docs/security_review.md` S7 atualizado com evidência pós-fix | ✅ PASS |
| `ruff`, `mypy`, `lint-imports` verdes | ✅ PASS |
| `pytest -m security`: 5 passed | ✅ PASS |
| Cobertura ≥ 85% | ✅ PASS (90.43%) |

---

## Observações para o Codex (Prompt B — 2ª rodada)

1. O único bloqueador (S7) foi resolvido via `mask_endpoint(self._judge_url)` nas linhas
   255, 264 e 276 de `ragas_metrics.py` (após inserção do import).
2. O comentário ADR-003 foi adicionado como comentário Jinja `{# ... #}` em
   `biomed_rubric.j2` — não aparece no output renderizado do template.
3. A escolha AsyncMock está documentada no docstring do módulo; o comportamento do
   teste não mudou — continua 5 passed, offline, sem GPU.
4. Commits desta tarefa: `f9ab9ec` (ciclo A) e `92fa1aa` (ciclo B/C).
