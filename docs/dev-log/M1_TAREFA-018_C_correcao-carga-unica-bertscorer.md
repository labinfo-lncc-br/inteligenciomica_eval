# M1_TAREFA-018_C — Correção pós-auditoria: carga única do BERTScorer + device CPU

**Data**: 2026-05-28
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E2 — Adapters de Avaliação
**Skill**: ml-engineer, python-engineer
**Prioridade / Tamanho**: P1 / S
**Em resposta a**: `M1_TAREFA-018_B_auditoria-deterministic-metrics-adapter.md` (FAIL / Request changes)

## Objetivo

Resolver os achados da auditoria 018-B do `DeterministicMetricsAdapter`:

1. **Bloqueador 1** — `cached_property` cacheava apenas um `functools.partial(bert_score.score)`,
   não o modelo: a API funcional `bert_score.score` recarregava os pesos a cada chamada
   (probe do auditor confirmou "Loading weights" duas vezes em chamadas consecutivas).
2. **Importante 1** — `device` não fixado: em ambiente CUDA o BERTScore usaria GPU
   automaticamente, conflitando com o design CPU-bound do adapter (competiria com os vLLMs).
3. **Observação não-bloqueadora** — `mypy --strict` no arquivo de teste acusava 6 erros
   `attr-defined` por acessar `deterministic_metrics.bert_score`/`.rouge_scorer`.

## Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/.../adapters/deterministic_metrics.py` | `_bert_scorer` passa a cachear uma instância de `bert_score.BERTScorer` (modelo retido em memória, carga única) em vez de um `partial`; novo parâmetro `device: str = "cpu"`; docstrings atualizadas |
| `tests/unit/.../test_deterministic_metrics.py` | Mocks migrados de `bert_score.score` para `bert_score.BERTScorer` via **alvos string**; novo `TestModelLoadedOnce` (regressão de carga única); probe `bertscore_available` usa `BERTScorer(..., device="cpu")` |

## Decisões Técnicas

1. **`BERTScorer` (classe) em vez de `bert_score.score` (funcional)** — Bloqueador 1.
   A classe `BERTScorer` carrega os pesos no `__init__` e os mantém em memória; a API
   funcional reinstancia `AutoModel.from_pretrained(...)` a cada chamada. Cachear a
   **instância** via `cached_property` é o que de fato garante carga única — exatamente
   a sugestão do auditor (relatório 018-B, linhas 81-83). A API semântica é equivalente:
   `scorer.score([answer], [ground_truth])` retorna `(P, R, F1)` com os mesmos `lang` e
   `rescale_with_baseline`. **Reconciliação com a spec**: a spec (linha 741) ilustra com
   `bert_score.score`, mas o requisito *vinculante* (linhas 756-757 / Prompt B item 2) é
   "lazy-load via `cached_property`" com carga única — que só a classe satisfaz.

2. **`device="cpu"` fixo (configurável)** — Importante 1. Novo parâmetro
   `device: str = "cpu"` (default), passado ao `BERTScorer`. Impede uso acidental de GPU
   em máquinas CUDA (ex.: GH200), preservando o design CPU-bound (§5.2) e a reprodutibilidade
   determinística (CPU + `batch_invariant` irrelevante → resultado idêntico).

3. **Mocks via alvo string** — Observação. `mocker.patch("bert_score.BERTScorer", ...)` e
   `mocker.patch("rouge_score.rouge_scorer.RougeScorer", ...)` em vez de
   `mocker.patch.object(deterministic_metrics.bert_score, ...)`. Elimina o acesso a
   atributos não re-exportados → `mypy --strict` no arquivo de teste agora passa
   (`Success: no issues found in 1 source file`), embora o gate oficial seja só `src`.

4. **Teste de regressão de carga única** (`TestModelLoadedOnce`) — atende ao pedido do
   auditor (018-B, "Observações para Próximas Tarefas"): duas chamadas consecutivas a
   `score()` devem instanciar `BERTScorer` **uma única vez** (`factory.call_count == 1`),
   mas pontuar duas vezes (`factory.return_value.score.call_count == 2`). Falharia com a
   implementação antiga baseada em `partial`.

## Validação (DoD)

```
uv run ruff check .            → All checks passed!
uv run ruff format --check .   → 78 files already formatted
uv run mypy --strict src       → Success: no issues found in 28 source files
uv run mypy --strict tests/.../test_deterministic_metrics.py → Success (observação 018-B resolvida)
uv run lint-imports            → 4 kept, 0 broken
uv run pytest tests/.../test_deterministic_metrics.py → 18 passed (BERTScore golden real incluído)
uv run pytest --cov ... -n 4   → 655 passed, 7 skipped — 96.41% total; deterministic_metrics.py 100% (43/43)
```

Cobertura do adapter mantida em **100%** (caminho de sucesso do BERTScore exercido por
`_patch_bert`, que agora mocka `BERTScorer.score`).

## Resposta item a item à auditoria 018-B

| Achado | Gravidade | Resolução |
|--------|-----------|-----------|
| `cached_property` não cacheia o modelo | Bloqueador | ✅ Cacheia instância de `BERTScorer`; `TestModelLoadedOnce` comprova carga única |
| GPU não bloqueada | Importante | ✅ `device="cpu"` fixo (parâmetro configurável) |
| `mypy --strict` no teste falha | Observação | ✅ Mocks via alvo string; mypy no teste passa |

## Observações para Próximas Tarefas

- Pronto para reauditoria (Prompt B novamente) — foco no recálculo de carga única e no
  device CPU.
- O padrão "cachear instância de cliente pesado via `cached_property`" (não um `partial`
  da API funcional) vale para qualquer futuro adapter que carregue modelo local.
