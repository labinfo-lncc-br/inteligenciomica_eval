# M1_TAREFA-018_B — Auditoria DeterministicMetricsAdapter

**Data**: 2026-05-28
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E2 — Adapters de Avaliação
**Skill**: code-reviewer, test-engineer, ml-engineer
**Prioridade / Tamanho**: P1 / S
**Resultado**: FAIL / Request changes

## Objetivo

Auditar a implementação da TAREFA-018A contra o Prompt B da TAREFA-018
(`docs/prompts_m1_tarefas_013_021_corrigido.md`, linhas 786-806), verificando:

- uso correto de BERTScore-F1 (`lang="pt"`, `rescale_with_baseline=True`, parâmetro
  `answer`);
- lazy-load real do BERTScore via `cached_property` e método síncrono;
- ROUGE-L (`rougeL`, `fmeasure`) calculado/logado, mas não persistido no Parquet;
- assinatura `.score(*, answer, ground_truth)` e conformidade com
  `DeterministicMetricPort`;
- dataset golden com 3 casos e thresholds;
- logging estruturado;
- gates (`ruff`, `mypy --strict src`, `lint-imports`, cobertura);
- recálculo manual de ROUGE-L para 1 par golden.

## Arquivos Criados / Modificados

| Arquivo | Ação | Observação |
|---------|------|------------|
| `docs/dev-log/M1_TAREFA-018_B_auditoria-deterministic-metrics-adapter.md` | Criado | Este relatório de auditoria |

Arquivos auditados:

- `src/inteligenciomica_eval/infrastructure/adapters/deterministic_metrics.py`
- `src/inteligenciomica_eval/domain/ports.py`
- `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py`
- `tests/unit/infrastructure/adapters/test_deterministic_metrics.py`
- `tests/golden/det_metrics_golden.json`
- `tests/fakes/metrics.py`
- `tests/unit/domain/test_ports_contract.py`
- `tests/unit/fakes/test_fakes_satisfy_ports.py`
- `pyproject.toml`
- `.importlinter`

## Achados

### Bloqueador 1 — `cached_property` não cacheia o modelo BERTScore

**Arquivo:linha**:

- `src/inteligenciomica_eval/infrastructure/adapters/deterministic_metrics.py:64-80`
- `src/inteligenciomica_eval/infrastructure/adapters/deterministic_metrics.py:126-130`

O adapter declara `_bert_scorer` como `cached_property`, mas o valor cacheado é apenas
`functools.partial(bert_score.score, lang=..., rescale_with_baseline=...)`. Isso não
mantém o modelo BERT carregado em memória. A API funcional `bert_score.score` instalada
executa `get_tokenizer(...)` e `get_model(...)` a cada chamada; `get_model(...)` instancia
`AutoModel.from_pretrained(...)` novamente.

Probe executado com duas chamadas consecutivas no mesmo processo:

```text
first
Loading weights: 100% ...
deterministic_metrics_computed bertscore_f1=1.0000003576278687 latency_ms=450 rouge_l=1.0
second
Loading weights: 100% ...
deterministic_metrics_computed bertscore_f1=1.0000003576278687 latency_ms=323 rouge_l=1.0
```

Impacto:

- viola o Prompt A, linhas 756-757: "Lazy-load do modelo BERTScore (somente na primeira
  chamada) ... `functools.cached_property` no cliente interno";
- viola o Prompt B, linha 794: "BERTScore é lazy-load via `cached_property`?";
- torna o adapter muito mais caro em chamadas repetidas e invalida a justificativa de
  startup rápido + carga única.

Sugestão:

- cachear um cliente que realmente retenha o modelo em memória, por exemplo
  `bert_score.BERTScorer(..., lang="pt", rescale_with_baseline=True, device="cpu")` em
  `cached_property`, e chamar `.score([answer], [ground_truth])`; ou
- se a exigência literal de chamar `bert_score.score` for mantida, adicionar uma solução
  equivalente com teste/probe que comprove carga única do modelo no mesmo processo.

### Importante 1 — Uso de GPU não está bloqueado explicitamente

**Arquivo:linha**:

- `src/inteligenciomica_eval/infrastructure/adapters/deterministic_metrics.py:76-80`
- `src/inteligenciomica_eval/infrastructure/adapters/deterministic_metrics.py:126-130`

O código não passa `device="cpu"` para o BERTScore. Na API instalada, quando `device` é
`None`, `bert_score.score` usa `"cuda"` se `torch.cuda.is_available()`. Isso conflita com
a documentação da própria tarefa e do módulo, que tratam o adapter como "sem GPU" e
CPU-bound. Em uma máquina GH200/CUDA, o adapter pode consumir GPU sem intenção e competir
com os servidores vLLM.

Sugestão: fixar `device="cpu"` no cliente BERTScore cacheado.

### Observação não bloqueadora — `mypy --strict` no teste novo falha fora do gate oficial

**Arquivo:linha**:

- `tests/unit/infrastructure/adapters/test_deterministic_metrics.py:60`
- `tests/unit/infrastructure/adapters/test_deterministic_metrics.py:183`
- `tests/unit/infrastructure/adapters/test_deterministic_metrics.py:204`
- `tests/unit/infrastructure/adapters/test_deterministic_metrics.py:218`
- `tests/unit/infrastructure/adapters/test_deterministic_metrics.py:225`
- `tests/unit/infrastructure/adapters/test_deterministic_metrics.py:265`

O gate oficial do projeto é `mypy --strict src`, e ele passou. Porém, ao rodar
`mypy --strict tests/unit/infrastructure/adapters/test_deterministic_metrics.py`, o mypy
aponta que `deterministic_metrics.bert_score` e `deterministic_metrics.rouge_scorer` não
são atributos exportados explicitamente do módulo.

Resultado:

```text
Found 6 errors in 1 file (checked 1 source file)
```

Não bloqueia a TAREFA-018 pelo padrão do `CLAUDE.md`, mas vale corrigir se o projeto
passar a tipar testes novos de adapter.

## Critérios de Aceitação

| Critério Prompt B | Evidência arquivo:linha | Gravidade / Resultado |
|-------------------|-------------------------|-----------------------|
| 1. `bert_score.score` com `lang="pt"` e `rescale_with_baseline=True`; parâmetro `answer` | `deterministic_metrics.py:76-80`, `deterministic_metrics.py:96-110`, `deterministic_metrics.py:126-130`; probe registrou `call(['resposta'], ['referência'], lang='pt', rescale_with_baseline=True)` | PASS |
| 2. BERTScore lazy-load via `cached_property`; síncrono | `deterministic_metrics.py:64-80` usa `cached_property`, mas cacheia só `partial`; `deterministic_metrics.py:96` é `def`, não `async`; probe `inspect.iscoroutinefunction=False` | FAIL / Bloqueador |
| 3. ROUGE-L usa `rougeL`, retorna `fmeasure`; logado mas não persistido no Parquet | `deterministic_metrics.py:82-90`, `deterministic_metrics.py:145-147`, `deterministic_metrics.py:113-118`; `parquet_storage.py:42-87` tem `bertscore_f1` mas não `rouge_l`; probe `rouge_l_in_schema=False` | PASS |
| 4. Método `.score(*, answer, ground_truth)`; `AuxMetrics` satisfaz port | `deterministic_metrics.py:96`, `ports.py:129-143`, `ports.py:373-391`; probe `score_signature=(*, answer: 'str', ground_truth: 'str') -> 'AuxMetrics'` e `runtime_port=True` | PASS |
| 5. 3 casos golden com `answer`/`ground_truth`; idêntico > 0.99; diferente < 0.6 | `det_metrics_golden.json:1-25`, `test_deterministic_metrics.py:99-122`, `test_deterministic_metrics.py:130-171`; testes focados rodaram BERTScore real sem skip | PASS |
| 6. Logging `deterministic_metrics_computed` com `bertscore_f1`, `rouge_l`, `latency_ms` | `deterministic_metrics.py:113-118`, `test_deterministic_metrics.py:243-258` | PASS |
| 7. `mypy --strict`; `lint-imports`; cobertura ≥ 80% | `mypy --strict src` PASS; `lint-imports` PASS; cobertura total 96.40%, `deterministic_metrics.py` 100% | PASS |

## Recálculo Manual de ROUGE-L

Caso recalculado: `similar` em `tests/golden/det_metrics_golden.json:10-17`.

Tokenização: `rouge_score.tokenizers.DefaultTokenizer(use_stemmer=False)`.

```text
ref_tokens  = ['a', 'resist', 'ncia', 'a', 'antibi', 'ticos', 'ocorre',
               'por', 'betalactamases', 'altera', 'o', 'de', 'pbps',
               'e', 'redu', 'o', 'de', 'porinas']
pred_tokens = ['bact', 'rias', 'resistem', 'por', 'betalactamases', 'por',
               'altera', 'o', 'das', 'pbps', 'e', 'pela', 'redu', 'o',
               'de', 'porinas']
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

O cálculo de ROUGE-L está correto.

## Validação (DoD)

| Comando / Probe | Resultado |
|-----------------|-----------|
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .` | PASS — `All checks passed!` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .` | PASS — `78 files already formatted` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src` | PASS — `Success: no issues found in 28 source files` |
| `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` | PASS — 64 files, 158 dependencies, 4 contracts kept, 0 broken |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest -v tests/unit/infrastructure/adapters/test_deterministic_metrics.py tests/unit/domain/test_ports_contract.py tests/unit/fakes/test_fakes_satisfy_ports.py` | PASS — 111 passed, 1 warning; BERTScore golden real executado sem skip |
| `UV_CACHE_DIR=/tmp/uv-cache uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n 4` | PASS — 654 passed, 7 skipped, 96.40%; `deterministic_metrics.py` 100% |
| Probe de schema Parquet | PASS — `rouge_l_in_schema=False`, `bertscore_f1_in_schema=True`, `rouge_l_in_metric_fields=False` |
| Probe de assinatura/cache | Parcial — síncrono e `cached_property=True`, mas cache real do modelo falhou |
| Probe de chamadas repetidas BERTScore | FAIL funcional de lazy-load — pesos carregados nas duas chamadas |
| `UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict tests/unit/infrastructure/adapters/test_deterministic_metrics.py` | FAIL fora do gate oficial — 6 erros `attr-defined` em mocks de dependências internas |

Warnings observados:

- `pytest-benchmark` avisa que benchmarks são desabilitados com `xdist`.
- `ragas_metrics.py` emite `DeprecationWarning` de `langchain-community`.
- `bert_score` emite `UserWarning` de NumPy array não gravável ao carregar baseline.

Nenhum warning acima altera o veredito; o bloqueio é a falha de lazy-load/cache do modelo.

## Observações para Próximas Tarefas

- Depois da correção, adicionar um teste/probe que falhe se duas chamadas consecutivas em
  um mesmo adapter carregarem o modelo duas vezes. Um teste viável é injetar/patchar o
  cliente cacheado ou espiar a factory usada pelo `cached_property`.
- Se a correção migrar para `bert_score.BERTScorer`, revisar os testes de mock para não
  dependerem de `deterministic_metrics.bert_score` como atributo exportado.
- Fixar `device="cpu"` evita consumo acidental de GPU em ambientes de produção com CUDA.
