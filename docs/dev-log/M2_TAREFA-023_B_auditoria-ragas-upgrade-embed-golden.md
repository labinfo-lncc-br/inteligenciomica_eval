# M2_TAREFA-023_B — Auditoria `RAGASLayer1Adapter`

**Data**: 2026-05-29  
**Milestone**: M2 — Avaliação automática (Camadas 1+2, juiz determinístico)  
**Épico**: E2  
**Skill**: code-reviewer  
**Prioridade / Tamanho**: P0 / M  
**Referência arquitetural**: §5.1/§5.2 · ADR-003/006/007 · Nota de operacionalização M2 (itens 1, 4, 5)

## Objetivo

Auditar o diff da TAREFA-023A e verificar a conformidade do `RAGASLayer1Adapter`
com o contrato M2: método canônico `score`, endpoint de embedding separado,
`max_concurrency=1`, `ragas_version`, tratamento de NaN/I/O e golden PT-BR.

## Arquivos Auditados

- `src/inteligenciomica_eval/domain/ports.py`
- `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py`
- `src/inteligenciomica_eval/infrastructure/config/adapter_configs.py`
- `tests/unit/infrastructure/adapters/test_ragas_layer1.py`
- `tests/integration/adapters/test_ragas_smoke.py`
- `tests/golden/ragas_pt_smoke.json`
- `docs/dev-log/M2_TAREFA-023_A_ragas-upgrade-embed-golden.md`

## Veredito

**PASS / Approve**

Nenhuma divergência material foi encontrada. O adapter e os testes cobrem os
itens exigidos pelo Prompt B.

## Critérios Auditados

| Critério | Evidência | Veredito |
|---|---|---|
| 1. Método canônico `.score(...)` e conformidade com `MetricSuitePort` | `MetricSuitePort` é `@runtime_checkable` e define `async def score(...)` em `src/inteligenciomica_eval/domain/ports.py:346-355`; `RAGASLayer1Adapter.score(...)` em `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py:207-295`; `isinstance(adapter, MetricSuitePort)` testado em `tests/unit/infrastructure/adapters/test_ragas_layer1.py:118-131` | PASS |
| 2. `max_concurrency=1` como `Final[int]`, ADR-003, sem batch `ragas.evaluate()` | `RAGAS_MAX_CONCURRENCY: Final[int] = 1` em `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py:60-63`; uso sequencial por loop/`await` individual em `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py:246-268`; teste de chamada individual em `tests/unit/infrastructure/adapters/test_ragas_layer1.py:168-177`; sem `ragas.evaluate()` na implementação | PASS |
| 3. Dois ramos de embed (`vllm_embed_url` vs HF local) e cobertura unitária | Config em `src/inteligenciomica_eval/infrastructure/config/adapter_configs.py:24-54`; construção dos embeddings em `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py:105-130`; unit cobrindo os dois ramos em `tests/unit/infrastructure/adapters/test_ragas_layer1.py:324-361` | PASS |
| 4. `ragas_version` de `importlib.metadata`, log da 1ª chamada, `embed_source` no log | `self.ragas_version = importlib.metadata.version("ragas")` em `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py:167-173`; log `ragas_adapter_first_call` em `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py:226-233`; log `ragas_layer1_computed` com `ragas_version` e `embed_source` em `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py:272-286`; testes em `tests/unit/infrastructure/adapters/test_ragas_layer1.py:369-391` e `:467-478` | PASS |
| 5. NaN isolado por métrica; falha total de I/O → `MetricComputationError` | Classificação de I/O em `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py:82-102`; NaN por campo e propagação de `MetricComputationError` em `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py:246-268`; testes em `tests/unit/infrastructure/adapters/test_ragas_layer1.py:185-262` e `:281-316` | PASS |
| 6. Golden PT presente e smoke skipável sem `VLLM_JUDGE_URL` | Golden PT-BR em `tests/golden/ragas_pt_smoke.json:1-10`; smoke de integração com `skipif` em `tests/integration/adapters/test_ragas_smoke.py:27-40`; threshold `answer_correctness >= 0.4` verificado em `tests/integration/adapters/test_ragas_smoke.py:55-60` | PASS |
| 7. `judge_url`/`embed_url` não hardcoded na implementação; `lint-imports` e `mypy --strict` | URLs vêm do `RagasAdapterConfig` e são consumidas em `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py:158-185`; não há URL hardcoded no adapter; `lint-imports` e `mypy --strict src` executados com sucesso | PASS |

## Divergências

Nenhuma.

## Probes Executados

| Comando | Resultado |
|---|---|
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/adapters/test_ragas_layer1.py -q` | `26 passed` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` | `4 kept, 0 broken` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src` | `Success: no issues found in 31 source files` |

## Observações

- A interpretação do fallback de embeddings documentada no Prompt A (`vllm_embed_url` ausente → `HuggingFaceEmbeddings`) está correta e implementada no adapter; eventual fallback de env (`VLLM_EMBED_URL` → `VLLM_JUDGE_URL`) permanece como responsabilidade de settings/orquestração, não desta camada.
- O smoke PT-BR existe e está corretamente protegido por `skipif`, mas não foi executado nesta auditoria porque depende de `VLLM_JUDGE_URL` ativo.
- Há apenas um warning de depreciação transitivo de `langchain_community` no unit test; não é regressão funcional nem quebra o critério do prompt.

## Conclusão

**PASS / Approve.** A TAREFA-023A está pronta para seguir. O próximo acoplamento
relevante é a TAREFA-026, que precisará consumir `adapter.ragas_version` na
proveniência do resultado.
