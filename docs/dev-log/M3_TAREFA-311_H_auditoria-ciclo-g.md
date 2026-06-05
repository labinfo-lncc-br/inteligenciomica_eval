# M3_TAREFA-311_H — Auditoria ciclo G (modo external + proveniencia)

**Data**: 2026-06-05
**Escopo**: reauditoria do ciclo G da TAREFA-311 contra o prompt `docs/prompts_m3_tarefa_311.md` (Prompt B)
**Veredito**: `PASS`

## Findings

Nenhum bloqueador ou importante novo foi encontrado nesta reauditoria.

Os dois pontos que mantinham o ciclo anterior em `FAIL` foram corrigidos no estado atual:

- `src/inteligenciomica_eval/infrastructure/wiring.py:605-609`
  - em `server_mode="external"`, `PrometheusJudgeAdapter` e `RAGASLayer1Adapter` passam a usar o mesmo endpoint validado/probeado (`_judge_url_probe`) em vez de depender de `settings.VLLM_JUDGE_URL`.
- `src/inteligenciomica_eval/infrastructure/wiring.py:342-396`
  - `determinism_verified` agora e false-safe: inicia `False` e o fallback por excecao tambem retorna `False`, alinhando o comportamento com a exigencia "sem prova, sem True".

Tambem confirmei a limpeza declarada de referencias residuais em `src/`:

- `grep -rn "ADR-013" src/` -> sem ocorrencias (exit code 1 por ausencia de matches)

## Gates executados

- `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` -> `PASS`
- `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src` -> `PASS`
- `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` -> `PASS`
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m 'not integration' --cov-fail-under=85 -n 4 -q` -> `1252 passed, 6 skipped, 17 warnings in 156.92s`
- `grep -rn "ADR-013" src/` -> sem ocorrencias

## Conclusao

O ciclo G fecha os bloqueadores funcionais do modo `external` identificados na auditoria F e reproduz os gates declarados pelo desenvolvedor. No criterio estrito do prompt `311B`, a entrega auditada nesta rodada esta apta a seguir.

## Risco residual

- A suite ainda emite warnings de dependencias/visualizacao/Qdrant ja observados anteriormente, mas eles nao representam regressao especifica da TAREFA-311 nem bloqueiam este aceite.
