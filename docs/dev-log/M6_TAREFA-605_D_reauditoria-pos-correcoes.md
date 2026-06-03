# M6_TAREFA-605_D — Reauditoria Pós-Correções

**Data**: 2026-06-03  
**Tarefa**: TAREFA-605 — Revisão final de segurança (segredos + prompt injection)  
**Papel**: ChatGPT Codex — reauditoria após ciclo B  
**Veredito**: **PASS**

## Verificações confirmadas

1. **S7 corrigido no código de produção**

- `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py` agora usa
  `mask_endpoint(self._judge_url)` nos eventos `ragas_io_failure`,
  `ragas_metric_failed` e `ragas_layer1_computed`.
- `grep -rn "judge_url=self\._judge_url" src/` → sem saída.

2. **Rastreabilidade do fix ADR-003**

- `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric.j2` contém o comentário:
  `{# ADR-003: delimitação dados×instrução — cada chunk encapsulado entre <contexto> #}`.

3. **Justificativa formal do AsyncMock**

- `tests/security/test_prompt_injection.py` agora documenta explicitamente por que
  o projeto adota `AsyncMock` no nível do SDK em vez de `respx.mock`.
- Mantive isso como aceitável porque o teste continua offline, determinístico e valida
  a estrutura do prompt enviado ao adapter real.

4. **Gate rápido reexecutado**

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m security
```

Resultado:

```text
5 passed, 1175 deselected in 7.74s
```

## Conclusão

Não encontrei achados remanescentes. O bloqueador de S7 foi resolvido e os dois avisos
anteriores ficaram adequadamente endereçados para os critérios desta tarefa.
