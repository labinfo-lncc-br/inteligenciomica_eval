# M6_TAREFA-605_B — Auditoria de Segurança Final

**Data**: 2026-06-03  
**Tarefa**: TAREFA-605 — Revisão final de segurança (segredos + prompt injection)  
**Papel**: ChatGPT Codex — Prompt B (auditoria)  
**Veredito**: **FAIL / Request changes**

## Resultado da verificação

Comando confirmado nesta auditoria:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m security
```

Resultado:

```text
5 passed, 1175 deselected in 8.05s
```

Verificações adicionais confirmadas:

- `grep -rn "shell=True" src/` → sem saída
- `grep -rn "password\|token\|secret\|api_key\|Authorization" config/ --include="*.yaml"` → sem saída

## Divergências

| Critério | Arquivo:linha | Gravidade | Observação |
|---|---|---|---|
| S7 — Logs sem PII / segredos | `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py:253-257`, `262-266`, `272-275`; `docs/security_review.md:21`, `169-177` | **BLOQUEADOR** | O relatório marca S7 como PASS e afirma que nenhum adapter loga URL com credencial embutida, mas `RAGASLayer1Adapter` loga `judge_url=self._judge_url` em `error`, `warning` e `info`. Como `judge_url` é resolvida de env (ADR-008), qualquer credencial embutida no endpoint vaza para logs. O projeto já possui `mask_endpoint()` em `infrastructure/config/settings.py`, mas ele não é aplicado aqui. Pelo próprio prompt B, log de URL com credencial é FAIL automático. |
| S6 — Mock de rede no teste de prompt injection | `tests/security/test_prompt_injection.py:7-8`, `14`, `59-69`, `131-152`; `docs/security_review.md:154-156` | **IMPORTANTE** | O prompt exigia `respx.mock` para interceptar a chamada sem GPU/rede. O teste implementado intercepta no nível do SDK com `AsyncMock`, o que mantém o teste offline, mas não cumpre literalmente o requisito pedido na tarefa. Se a equipe quer aderência estrita ao prompt, o teste precisa ser ajustado ou a exceção precisa ser explicitamente aceita. |
| Fix mínimo com referência ao ADR no template | `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric.j2:69-74` | **IMPORTANTE** | O fix funcional existe, mas o comentário solicitado no prompt (`ADR-003: delimitação dados×instrução`) não foi adicionado ao template. O item 10 da auditoria pedia validar essa rastreabilidade no próprio código de produção alterado. |

## Sumário

O hardening principal foi implementado: o template agora delimita chunks com `<contexto ...>`, os 5 testes `security` passam, `.secrets.baseline` está preenchido e `docs/security_review.md` traz evidências suficientes para S1, S2, S4, S5, S6, S8 e S9.

O merge ainda não deve ocorrer porque S7 está incorreto no código e no relatório: há logging de `judge_url` bruto em produção. Depois disso, recomendo alinhar a suite ao requisito formal de `respx.mock` e adicionar a referência explícita ao ADR no template.
