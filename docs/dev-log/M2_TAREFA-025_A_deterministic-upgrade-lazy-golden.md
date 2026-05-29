# M2_TAREFA-025_A — Upgrade `DeterministicMetricsAdapter` (lazy init + golden PT-BR + config)

**Data**: 2026-05-29
**Milestone**: M2 — Avaliação automática (Camadas 1+2, juiz determinístico)
**Épico**: E2
**Skill**: ml-engineer
**Prioridade / Tamanho**: P1 / S
**Referência arquitetural**: TAREFA-203 (§14.5) — upgrade de M1/TAREFA-018 · §5.1/§5.2 · Nota M2 itens 1 e 2

## Objetivo

Refinar o `DeterministicMetricsAdapter` de M1 com três melhorias: (a) lazy init via
**atributo de instância** (não `functools.cached_property`, que vaza estado mockado
entre instâncias em testes), (b) `DeterministicAdapterConfig` dedicada com `lang="pt"`
canônico, (c) golden dataset PT-BR (`det_metrics_pt_golden.json`) com 3 pares e
thresholds documentados. A assinatura canônica `.score(*, answer, ground_truth)` e
`lang="pt"` já vinham corretos de TAREFA-018 (Nota M2 itens 1 e 2 — sem mudança de idioma).

## Arquivos Criados / Modificados

### Criados
- `tests/golden/det_metrics_pt_golden.json` — 3 pares PT-BR biomédicos (chave `id`),
  thresholds + `rouge_l_observed` por par.
- `tests/integration/adapters/test_deterministic_integration.py` — golden BERTScore real
  + determinismo, `@pytest.mark.integration`, skipável sem o modelo.

### Modificados
- `src/inteligenciomica_eval/infrastructure/adapters/deterministic_metrics.py` —
  `cached_property` → atributo de instância (`self._scorer`/`self._rouge`) + métodos
  `_get_scorer`/`_get_rouge`; construtor agora aceita `DeterministicAdapterConfig | None`.
- `src/inteligenciomica_eval/infrastructure/config/adapter_configs.py` —
  `DeterministicAdapterConfig` (`model_type`, `lang`, `rescale_with_baseline`, `device`).
- `tests/unit/infrastructure/adapters/test_deterministic_metrics.py` — golden PT-BR (chave
  `id`); novos testes de assinatura keyword-only, config explícita, lazy (`_scorer is None`
  na construção) e **isolamento de instância** (`id()` distintos); golden BERTScore real
  movido para o teste de integração.

### Removidos
- `tests/golden/det_metrics_golden.json` — substituído por `det_metrics_pt_golden.json`
  (nenhum código/teste o referenciava após a migração; apenas dev-logs históricos de M1).

## Decisões Técnicas

1. **Lazy init por atributo de instância, NÃO `cached_property` (Nota M2 item 2 — CRÍTICO).**
   `functools.cached_property` materializa o valor no `__dict__` da instância, mas o
   **descritor** é de classe; em suítes de teste isso facilita vazamento de scorer mockado
   e dificulta o isolamento. `self._scorer: BERTScorer | None = None` + `_get_scorer()`
   (`if self._scorer is None: self._scorer = BERTScorer(...)`) garante que **2 instâncias
   distintas têm `_scorer` distintos** (testado por `id()`), preservando a carga única
   por adapter (1 instância → 1 `BERTScorer`, reutilizado entre chamadas).
2. **Config com defaults; construtor aceita `None`.** `DeterministicMetricsAdapter()` ≡
   `DeterministicMetricsAdapter(DeterministicAdapterConfig())` — todos os campos têm
   default canônico. Mantém a ergonomia dos testes e adiciona o ponto de configuração.
3. **`lang="pt"` canônico (Nota M2 item 2).** A docstring da config documenta que mudar o
   idioma exige **novo golden + aprovação da equipe** — os thresholds são específicos do
   idioma. `model_type="bert-base-multilingual-cased"` passado explicitamente equivale ao
   que o `bert_score` derivaria de `lang="pt"` (mesmo comportamento de M1).
4. **Golden BERTScore real → teste de integração.** O unit roda só o ROUGE-L golden (puro
   Python, sempre); o BERTScore real (modelo) fica em `test_deterministic_integration.py`
   (§5 do Prompt A: "teste de integração com golden real"). Sem duplicação.

## Problemas Encontrados e Soluções

- **Tokenizer ASCII-only do `rouge_score` quebra acentos.** `rouge_score.tokenize` aplica
  `re.sub(r"[^a-z0-9]+", " ", ...)` — "fosforilação" vira `["fosforila", "o"]`. Como o
  golden é PT-BR acentuado, **calibrei os thresholds com os valores reais** computados
  pelo próprio `rouge_score` (não com tokenização ingênua), evitando discrepância na
  recomputação do auditor. Valores observados gravados em `rouge_l_observed`.

## Validação (DoD §14.2)

```
ruff check / format          → OK
mypy --strict src            → Success (32 source files)
lint-imports                 → 4 kept, 0 broken
pytest test_deterministic_metrics            → 17 passed
pytest test_deterministic_integration        → 4 passed (modelo disponível localmente)
pytest (full, -n 4)          → 737 passed, 13 skipped — 96.84% cobertura
deterministic_metrics.py     → 100% | adapter_configs.py → 100%
```

### Valores reais do golden (modelo `bert-base-multilingual-cased`, CPU)

| par | bertscore_f1 | threshold | rouge_l | threshold |
|-----|-------------:|-----------|--------:|-----------|
| identical | 1.0000 | ≥ 0.98 ✓ | 1.0000 | ≥ 0.98 ✓ |
| similar   | 0.8528 | ≥ 0.70 ✓ | 0.7000 | ≥ 0.40 ✓ |
| different | 0.1606 | ≤ 0.60 ✓ | 0.0769 | ≤ 0.30 ✓ |

### Recomputação manual do ROUGE-L (par `similar`, para o auditor)

Tokenização real (`rouge_score`, ASCII-only, sem stemmer):
- **answer** (prediction): 19 tokens
- **ground_truth** (reference): 21 tokens
- **LCS = 14** → `P = 14/19 = 0.7368`, `R = 14/21 = 0.6667`
- `F = 2·P·R/(P+R) = 2·0.7368·0.6667 / (0.7368+0.6667) = 0.7000` ✓

## Critérios de Aceitação (TAREFA-025)

- [x] `.score(*, answer, ground_truth) -> AuxMetrics` keyword-only; `isinstance(DeterministicMetricPort)` True.
- [x] Lazy init por atributo de instância `_scorer: BERTScorer | None` (NÃO `cached_property`); motivo documentado.
- [x] 2 instâncias distintas NÃO compartilham `_scorer` (`id()` check) — `TestInstanceIsolation`.
- [x] `lang="pt"`, `rescale_with_baseline=True` na config; mudar idioma exige golden + aprovação (documentado).
- [x] Golden 3 pares PT-BR: identical ≥ 0.98; similar ≥ 0.70/0.40; different ≤ 0.60/0.30 (validado no modelo real).
- [x] Determinismo: 2 chamadas idênticas → mesmo float (`test_determinism_same_input_same_float`).
- [x] Síncrono (sem async); import-linter OK; mypy --strict; cobertura 100% ≥ 80%.

## Observações para Próximas Tarefas

- **TAREFA-026 (`ComputeMetricsUseCase`)**: injeta o `DeterministicMetricsAdapter` como
  `deterministic_metric` (sem decorator de retry — é determinístico e não faz I/O de rede,
  então não passa pelo `RetryableMetricAdapter` da TAREFA-027). Lê `AuxMetrics.bertscore_f1`
  para o `MetricVector`; `rouge_l` permanece campo de log (Nota M1 item 10).
- O `functools` deixou de ser importado pelo adapter (lazy init manual).
