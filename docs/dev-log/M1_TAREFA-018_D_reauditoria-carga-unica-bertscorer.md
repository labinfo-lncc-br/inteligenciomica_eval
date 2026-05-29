# M1_TAREFA-018_D — Reauditoria carga única BERTScorer

**Data**: 2026-05-28
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E2 — Adapters de Avaliação
**Skill**: code-reviewer, test-engineer, ml-engineer
**Prioridade / Tamanho**: P1 / S
**Resultado**: PASS / Approve

## Objetivo

Reauditar a correção da TAREFA-018C em resposta ao relatório
`M1_TAREFA-018_B_auditoria-deterministic-metrics-adapter.md`, com foco em:

- carga única real do modelo BERTScore via `cached_property`;
- `device="cpu"` para evitar uso acidental de GPU;
- manutenção da assinatura síncrona `.score(*, answer, ground_truth)`;
- ROUGE-L correto e não persistido no schema Parquet;
- testes/gates oficiais e recálculo manual de ROUGE-L.

## Arquivos Criados / Modificados

| Arquivo | Ação | Observação |
|---------|------|------------|
| `docs/dev-log/M1_TAREFA-018_D_reauditoria-carga-unica-bertscorer.md` | Criado | Este relatório de reauditoria |

Arquivos auditados:

- `docs/dev-log/M1_TAREFA-018_C_correcao-carga-unica-bertscorer.md`
- `src/inteligenciomica_eval/infrastructure/adapters/deterministic_metrics.py`
- `tests/unit/infrastructure/adapters/test_deterministic_metrics.py`
- `tests/golden/det_metrics_golden.json`
- `src/inteligenciomica_eval/domain/ports.py`
- `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py`

## Decisões de Auditoria

### Uso de `BERTScorer` aceito

O Prompt A ilustra `bert_score.score([answer], [ground_truth], lang="pt",
rescale_with_baseline=True)` nas linhas 740-743, mas também exige lazy-load com carga única
do modelo nas linhas 756-757. A auditoria 018-B demonstrou que a API funcional recarrega o
modelo a cada chamada.

A correção usa `bert_score.BERTScorer` em `cached_property` e chama
`self._bert_scorer.score([answer], [ground_truth])`. Isso preserva a semântica da métrica
e satisfaz o requisito operacional que a API funcional não satisfazia. A divergência literal
foi documentada e é aceitável para esta tarefa.

## Critérios de Aceitação

| Critério Prompt B | Evidência arquivo:linha | Gravidade / Resultado |
|-------------------|-------------------------|-----------------------|
| 1. BERTScore com `lang="pt"` e `rescale_with_baseline=True`; parâmetro `answer` | `deterministic_metrics.py:90-94` instancia `BERTScorer(lang=self._lang, rescale_with_baseline=self._rescale_with_baseline, device=self._device)`; `deterministic_metrics.py:140-148` chama `.score([answer], [ground_truth])`; probe registrou `factory_call_args=call(lang='pt', rescale_with_baseline=True, device='cpu')` e `score_call_args=call(['resposta'], ['referência'])` | PASS |
| 2. BERTScore lazy-load via `cached_property`; síncrono | `deterministic_metrics.py:74-94`; `deterministic_metrics.py:110-134`; probe real de duas chamadas mostrou `Loading weights` apenas na primeira chamada; `inspect.iscoroutinefunction=False` | PASS |
| 3. ROUGE-L usa `rougeL`, retorna `fmeasure`; logado mas não persistido no Parquet | `deterministic_metrics.py:96-104`, `deterministic_metrics.py:157-165`, `deterministic_metrics.py:127-132`; `parquet_storage.py:42-87`, `parquet_storage.py:90-99`, `parquet_storage.py:214-222`, `parquet_storage.py:465-474`; probe `rouge_l_in_schema=False`, `rouge_l_in_metric_fields=False` | PASS |
| 4. Método `.score(*, answer, ground_truth)`; `AuxMetrics` satisfaz `DeterministicMetricPort` | `deterministic_metrics.py:110`; `ports.py:129-143`; `ports.py:373-391`; probe `score_signature=(*, answer: 'str', ground_truth: 'str') -> 'AuxMetrics'`, `runtime_port=True`, `has_compute_aux=False` | PASS |
| 5. 3 casos golden com `answer`/`ground_truth`; idêntico > 0.99; diferente < 0.6 | `det_metrics_golden.json:1-26`; `test_deterministic_metrics.py:112-185`; testes focados executaram os golden reais sem skip | PASS |
| 6. Logging `deterministic_metrics_computed` com `bertscore_f1`, `rouge_l`, `latency_ms` | `deterministic_metrics.py:127-132`; `test_deterministic_metrics.py:268-283` | PASS |
| 7. `mypy --strict`; `lint-imports`; cobertura ≥ 80% | Gates oficiais passaram; cobertura total 96.41%, `deterministic_metrics.py` 100% | PASS |

## Verificações dos Achados 018-B

| Achado 018-B | Verificação | Resultado |
|--------------|-------------|-----------|
| `cached_property` cacheava só `partial`, não o modelo | `_bert_scorer` agora cacheia `bert_score.BERTScorer`; teste `TestModelLoadedOnce` em `test_deterministic_metrics.py:245-260`; probe real mostrou carga de pesos só na primeira chamada | Resolvido |
| GPU não bloqueada | `device: str = "cpu"` em `deterministic_metrics.py:59-68`; repassado ao `BERTScorer` em `deterministic_metrics.py:90-94`; probe confirmou `device='cpu'` | Resolvido |
| `mypy --strict` no teste falhava | mocks usam alvos string em `test_deterministic_metrics.py`; `mypy --strict tests/unit/infrastructure/adapters/test_deterministic_metrics.py` passou | Resolvido |

## Probe de Carga Única

Comando executado em processo novo com duas chamadas consecutivas:

```text
first
Loading weights: 100% ...
deterministic_metrics_computed bertscore_f1=1.0000003576278687 latency_ms=350 rouge_l=1.0
r1= 1.0000003576278687 1.0
second
deterministic_metrics_computed bertscore_f1=1.0000003576278687 latency_ms=33 rouge_l=1.0
r2= 1.0000003576278687 1.0
```

Resultado: `Loading weights` apareceu apenas antes da primeira chamada. A segunda chamada
reutilizou o `BERTScorer` cacheado.

## Recálculo Manual de ROUGE-L

Caso recalculado: `similar` em `tests/golden/det_metrics_golden.json:10-17`.

Tokenização: `rouge_score.tokenizers.DefaultTokenizer(use_stemmer=False)`.

```text
LCS = 10
Precision = 10 / 16 = 0.625000
Recall    = 10 / 18 = 0.555556
F         = 2PR/(P+R) = 0.588235
```

Resultado esperado vs. obtido:

| Fonte | ROUGE-L F |
|-------|-----------|
| Recalculo manual por LCS | 0.588235 |
| `DeterministicMetricsAdapter.score(...).rouge_l` | 0.588235 |
| Threshold do golden | `rouge_l_min = 0.5` |

O cálculo de ROUGE-L permanece correto.

## Validação (DoD)

| Comando / Probe | Resultado |
|-----------------|-----------|
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` | PASS — `All checks passed!` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .` | PASS — `78 files already formatted` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src` | PASS — `Success: no issues found in 28 source files` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict tests/unit/infrastructure/adapters/test_deterministic_metrics.py` | PASS — `Success: no issues found in 1 source file` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` | PASS — 64 files, 158 dependencies, 4 contracts kept, 0 broken |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -v tests/unit/infrastructure/adapters/test_deterministic_metrics.py tests/unit/domain/test_ports_contract.py tests/unit/fakes/test_fakes_satisfy_ports.py` | PASS — 112 passed, 1 warning |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n 4` | PASS — 655 passed, 7 skipped, 96.41%; `deterministic_metrics.py` 100% |
| Probe de `BERTScorer` com mock | PASS — `lang='pt'`, `rescale_with_baseline=True`, `device='cpu'`; `.score([answer], [ground_truth])` |
| Probe de assinatura/cache | PASS — síncrono, `cached_property=True`, `runtime_port=True`, sem `.compute_aux()` |
| Probe de schema Parquet | PASS — `rouge_l` ausente do schema e de `_METRIC_FIELDS`; `bertscore_f1` presente |
| Probe real de duas chamadas | PASS — modelo carregado apenas na primeira chamada |
| Recálculo manual de ROUGE-L | PASS — manual `0.588235` igual ao adapter |

Warnings observados:

- `pytest-benchmark` avisa que benchmarks são desabilitados com `xdist`.
- `ragas_metrics.py` emite `DeprecationWarning` de `langchain-community`.
- `bert_score` emite `UserWarning` de NumPy array não gravável ao carregar baseline.

Nenhum warning acima é bloqueador para a TAREFA-018.

## Observações para Próximas Tarefas

- A correção estabelece um padrão útil para adapters com modelos locais pesados:
  cachear a instância do cliente/modelo em `cached_property`, não apenas um wrapper ou
  `partial` de API funcional.
- O uso de `device="cpu"` está adequado para M1. Caso tarefas futuras queiram GPU para
  BERTScore, isso deve ser uma decisão explícita de configuração, não fallback automático.
