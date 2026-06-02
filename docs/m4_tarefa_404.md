# Prompts M4 — TAREFA-401 a 409 (Claude Code ↔ ChatGPT Codex)

**Milestone:** M4 — Decisão executiva da Rodada 1 (Camada 3 + Agregação + Estatística + Relatório)
**Documentos de referência:**
- `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1, §§ 5.1, 6, 7.2–7.3, 8, 11.4–11.5, 14.7)
- `visao_alto_nivel_validacao_inteligenciomica.md` (v1.0, §§ 5, 7, 8, 11, 13)
**Continuação de:** M3 (TAREFA-301–310 — orquestração das 4 GPUs, Rodada 1 completa)
**Formato:** para cada tarefa, um **Prompt A (implementação — Claude Code)** e um
**Prompt B (verificação — ChatGPT Codex)**, conforme seção 16 do documento de arquitetura.
**Uso:** o desenvolvedor sênior cola o Prompt A no Claude Code; ao receber o PR, cola o
Prompt B no Codex; arbitra PASS/FAIL; itera até PASS; só então parte para a próxima
tarefa **respeitando o DAG do Apêndice**.

> Pressupõe que **M0 (001–012), M1 (013–021), M2 (022–028) e M3 (301–310) já estão
> mergeados e verdes**: domínio completo, adapters de infraestrutura, pipeline de
> métricas (Camadas 1 e 2), Rodada 1 executada, Parquet com `generated_answer` +
> métricas + `rubric_biomed_score` + `final_score` disponível para leitura.
>
> **Skills esperadas no Claude Code:** `python-clean-architecture`, `test-engineer`,
> `python-engineer`, `ml-engineer`, `data-engineer`, `backend-engineer`.
>
> **Nota de rastreabilidade:** TAREFA-4xx mapeia diretamente para a tabela do §14.7.
>
> | §14.7 (arquitetura) | Prompt M4 | Descrição |
> |---|---|---|
> | TAREFA-401 | **TAREFA-401** | CLI `annotate` (export estratificado) |
> | TAREFA-402 | **TAREFA-402** | `IngestHumanAnnotationUseCase` |
> | TAREFA-403 | **TAREFA-403** | `AggregateResultsUseCase` |
> | TAREFA-404 | **TAREFA-404** | `StatsPort` adapters (Wilcoxon + Friedman+Nemenyi + MLM) |
> | TAREFA-405 | **TAREFA-405** | `StatisticalAnalysisUseCase` + correção múltipla |
> | TAREFA-406 | **TAREFA-406** | Extensões de domínio M4 (ports, VOs) |
> | TAREFA-407 | **TAREFA-407** | `MatplotlibVisualizationAdapter` (7 plots canônicos) |
> | TAREFA-408 | **TAREFA-408** | `HTMLReportAdapter` + CLI `analyze`/`report`/`status` |
> | TAREFA-409 | **TAREFA-409** | Gate M4: E2E decisão executiva completa |

---

## Nota de operacionalização M4 — decisões que estes prompts fixam

As decisões abaixo são complementares às de M0–M3 e valem para todos os prompts de M4.
Devem ser confirmadas pela equipe (vetáveis antes da TAREFA-401).

### 1. `GoldChunkReaderPort` — delta de contrato declarado

A arquitetura §5.1 declara `gold_for(question_id: str) -> list[str]`. M1 (TAREFA-013)
implementou o adapter com `read_gold_chunks(question_id: str) -> tuple[str, ...]`.
**Resolução:** manter `read_gold_chunks` como nome canônico (delta em relação ao §5.1,
declarado e aprovado implicitamente pela conclusão do M1 sem auditoria contrária).
Qualquer uso novo do port em M4 usa `read_gold_chunks`. Uma correção futura de §5.1
para `gold_for` seria tratada como PR de renomeação isolado. **Este delta está
registrado aqui como decisão explícita.**

### 2. `RetrieverPort` — uso assíncrono

A arquitetura §5.1 declara `search(...)` como método síncrono. M1 (TAREFA-013)
implementou `QdrantRetrieverAdapter` como async. **Resolução para M4:** qualquer
chamada ao `RetrieverPort` em M4 usa `await retriever.search(...)`. Esta é uma extensão
do contrato, não uma quebra. Documentar na **Nota de operacionalização M5** (quando M5
for escrito) para rastrear o delta formalmente.

### 3. Visualização — `visualization/matplotlib_adapter.py` (ADR inline)

A arquitetura §8 prevê arquivos separados por tipo de plot. **Decisão M4:** implementar
todos os 7 plots em um único `visualization/matplotlib_adapter.py`. **Justificativa:**
cada método tem ~20–40 linhas de código; criar 7 arquivos com 1 função cada aumenta
overhead de importação e fragmentação. **Reversibilidade:** se algum plot crescer (>100
linhas), extrai-se o método para `visualization/<tipo>.py` sem alterar a interface do
adapter. Esta decisão não altera os contratos de domínio.

### 4. Matplotlib — `Agg` backend antes de qualquer import gráfico (bloqueador se violado)

`import matplotlib; matplotlib.use("Agg")` **ANTES** de qualquer
`import matplotlib.pyplot` ou `import seaborn` — linha 1 ou 2 do módulo. CI sem display
falha silenciosamente sem isso. É critério de aceitação verificado pelo Codex.

### 5. Relatório HTML — autocontido, sem dependências externas (bloqueador se violado)

O HTML gerado por `HTMLReportAdapter` deve ser um arquivo único, sem URLs http/https
externas (fontes, scripts, CDN). Plots embutidos como `data:image/svg+xml;base64,...`.
Verificado por `assert "http" not in html_content.lower()` no teste.

### 6. Análise estatística — `StatsPort` implementado via adapters, `StatsReport` como VO agregado

Os três adapters de TAREFA-404 (`WilcoxonAdapter`, `FriedmanNemenyiAdapter`,
`MixedLinearModelAdapter`) implementam `StatsPort` (§5.1) individualmente.
`StatisticalAnalysisUseCase` (TAREFA-405) os orquestra e produz um `StatsReport` (novo
VO de M4, declarado em TAREFA-406) com todos os resultados consolidados + p-values
corrigidos. O `StatsReport` é o input do `HTMLReportAdapter` (TAREFA-408).

### 7. Anotação humana — workflow export→edit→ingest (ADR-010)

O subcomando `annotate` **exporta** respostas priorizando scores baixos para um arquivo
JSONL editável pelo especialista. Após a edição offline, `annotate --ingest` faz o
merge por `row_id` via `IngestHumanAnnotationUseCase`. Esta separação é mandatória
(ADR-010). **Não há prompt interativo em sessão** — o especialista biomédico edita
o arquivo externamente, no seu tempo.

### 8. `AggregationService` (M0/TAREFA-008) vs `AggregateResultsUseCase` (M4/TAREFA-403)

`AggregationService` (domínio puro, TAREFA-008) já existe e produz `ConfigAggregate`
dado um conjunto de `EvaluationResult` em memória. `AggregateResultsUseCase`
(application, TAREFA-403) é o orquestrador que: lê o Parquet via `ResultReaderPort`,
converte para `EvaluationResult`, injeta no `AggregationService` existente, e persiste
o sumário. Não reimplementar lógica de agregação — **delegar 100% ao `AggregationService`**.

---

## TAREFA-404 — Adapters `StatsPort`: Wilcoxon, Friedman+Nemenyi e Modelo Linear Misto

**Épico:** E7 — Estatística · **Skill:** ml-engineer
**Prioridade:** P0 · **Tamanho:** L
**Dependências:** TAREFA-005 (`StatsPort`, `ResultFrame`, VOs de output) — M0
**ADRs:** ADR-011 (statsmodels+scikit-posthocs, pymer4 opcional) · **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §5.1 StatsPort,
ADR-011, doc-base §8 análise estatística). Skills: ml-engineer, python-clean-architecture.
M0: `StatsPort` declarado com `WilcoxonReport`, `FriedmanReport`, `MLMReport` como VOs
de retorno (a serem definidos nesta tarefa se ainda não declarados em M0).

TAREFA: TAREFA-404 — três entregáveis:
(a) VOs de saída estatística em `domain/value_objects.py` (se não declarados em M0).
(b) Três adapters implementando `StatsPort` em `infrastructure/adapters/stats_adapters.py`.
(c) Testes unitários e de integração.

ESPECIFICAÇÃO — (a) VOs de saída (frozen dataclasses, sem Pydantic):

```python
@dataclass(frozen=True)
class WilcoxonReport:
    metric: str
    base_a: str
    base_b: str
    statistic: float
    p_value: float
    p_value_corrected: float | None       # após correção múltipla
    significant: bool                     # p_value_corrected < alpha (0.05)
    n_pairs: int
    effect_size_r: float | None           # r = Z / sqrt(N)

@dataclass(frozen=True)
class NemenyiPair:
    llm_a: str
    llm_b: str
    p_value: float
    significant: bool

@dataclass(frozen=True)
class FriedmanReport:
    metric: str
    chi2_statistic: float
    p_value: float
    p_value_corrected: float | None
    significant: bool
    n_groups: int
    n_blocks: int
    nemenyi_pairs: tuple[NemenyiPair, ...]    # post-hoc (só se significant=True)

@dataclass(frozen=True)
class MLMReport:
    formula: str
    base_effect_coef: float
    base_effect_p_value: float
    llm_effect_p_values: dict[str, float]     # por LLM (vs. referência)
    interaction_p_value: float
    interaction_significant: bool
    aic: float
    n_observations: int
    convergence_warning: bool
```

ESPECIFICAÇÃO — (b) Três adapters em `infrastructure/adapters/stats_adapters.py`:

**Adapter 1: `WilcoxonAdapter`** (implementa `StatsPort.wilcoxon_paired`):
- `scipy.stats.wilcoxon(x, y, alternative="two-sided", zero_method="wilcox")`
- `x` = `FinalScore` (ou `metric`) da base A por pergunta × seed.
- `y` = `FinalScore` da base B nas mesmas observações (pareamento por `question_id` + `seed`).
- Calcular `effect_size_r = Z / sqrt(N)` onde `Z = norm.ppf(1 - p/2)` e `N = n_pairs`.
- Logging: `metric`, `statistic`, `p_value`, `n_pairs`, `latency_ms`.
- Se `n_pairs < 5`: logar WARNING e retornar `WilcoxonReport` com `significant=False` e
  `p_value=1.0` (amostra insuficiente). NÃO levantar exceção.

**Adapter 2: `FriedmanNemenyiAdapter`** (implementa `StatsPort.friedman_nemenyi`):
- `scipy.stats.friedmanchisquare(*grupos)` onde cada grupo = array de FinalScore
  para um LLM, pareado por `(question_id, seed, base)`.
- Post-hoc (só se `p_value < 0.05`):
  `scikit_posthocs.posthoc_nemenyi_friedman(data_matrix)`.
- Montar `NemenyiPair` para cada par `(llm_a, llm_b)`.
- Logging: `metric`, `chi2_statistic`, `p_value`, `n_groups`, `n_blocks`, `latency_ms`.
- Se menos de 3 grupos: `significant=False`, `p_value=1.0`, `nemenyi_pairs=()`, WARNING.

**Adapter 3: `MixedLinearModelAdapter`** (implementa `StatsPort.mixed_linear_model`):
- Fórmula padrão: `"final_score ~ base * llm + (1 | question_id)"` mas recebe
  `formula: str` como parâmetro (§5.1).
- Usar `statsmodels.formula.api.mixedlm`:
  ```python
  import statsmodels.formula.api as smf
  model = smf.mixedlm(formula, data=df, groups=df["question_id"])
  result = model.fit(reml=True, method="lbfgs")
  ```
- `df` é construído do `ResultFrame` — converter para `pandas.DataFrame` **dentro do
  adapter** (pandas é permitido em infra).
- Extrair: `base_effect_coef` e `base_effect_p_value` (coeficiente de `base`);
  `llm_effect_p_values` (p-values das variáveis LLM); `interaction_p_value` (variável
  com `*` na fórmula, ex.: `base:llm`); `aic`; `n_observations = result.nobs`.
- `convergence_warning = not result.converged` (structlog WARNING se True).
- Se `statsmodels.mixedlm` não convergir OU lançar exceção numérica: retornar
  `MLMReport` com todos os p-values = `float("nan")` e `convergence_warning=True`.
  NÃO levantar exceção — degradação graceful.

**Config Pydantic** `StatsAdapterConfig` (em `adapter_configs.py`):
```python
alpha: float = 0.05
correction_method: str = "benjamini-hochberg"   # ou "holm"
min_pairs_wilcoxon: int = 5
reml: bool = True
```

ENTREGÁVEL:
- Extensão de `domain/value_objects.py` (VOs de stats)
- `src/inteligenciomica_eval/infrastructure/adapters/stats_adapters.py`
- Extensão de `infrastructure/config/adapter_configs.py`
- `tests/unit/adapters/test_stats_adapters.py`
  Para CADA adapter:
  a) Dataset sintético conhecido → valores p calculados manualmente conferem.
  b) Amostra insuficiente (n<5 para Wilcoxon; <3 grupos para Friedman) → `significant=False`,
     sem exceção, WARNING logado.
  c) Falha numérica no MLM → `convergence_warning=True`, `p_values=NaN`, sem exceção.
- `tests/integration/adapters/test_stats_integration.py`
  (marcado `@pytest.mark.integration`; dataset de 13 pares reais; valores verificados
  contra cálculo direto de scipy)
- `tests/golden/stats_wilcoxon_expected.json` + `stats_friedman_expected.json`
  (valores calculados independentemente via scipy notebook ou R)

RESTRIÇÕES (DoD §14.2):
- Adapters NUNCA levantam exceção em caso de amostra pequena ou falha numérica —
  degradação graceful para p=1.0/NaN com WARNING.
- `pandas` e `scipy`/`statsmodels`/`scikit-posthocs` usados **somente** em `infrastructure/`.
- `from __future__ import annotations`; type hints; docstrings; mypy --strict.
- import-linter: `domain/application` NÃO importam `scipy`/`statsmodels`/`pandas`.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-404):
- 3 VOs de output (`WilcoxonReport`, `FriedmanReport`, `MLMReport`) são frozen dataclasses.
- 3 adapters implementam `StatsPort` estruturalmente (`isinstance` com Protocol passa).
- Amostra insuficiente: `significant=False`, sem exceção — testado para cada adapter.
- MLM não convergente: `convergence_warning=True`, p-values NaN, sem exceção — testado.
- Golden de Wilcoxon e Friedman conferem valores calculados independentemente.
- import-linter OK; mypy --strict; cobertura ≥ 85%.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer (skill ml-engineer). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-404 + arquitetura §5.1 (StatsPort assinaturas) +
doc-base §8.1–8.5 + ADR-011 + "Nota de operacionalização M4" item 6.

VERIFIQUE, item a item, citando arquivo:linha:
1. VOs `WilcoxonReport`, `FriedmanReport` (com `NemenyiPair`), `MLMReport` são
   frozen dataclasses em `domain/value_objects.py`? Sem Pydantic?
2. Assinaturas dos 3 adapters batem com `StatsPort` de §5.1?
   `isinstance(adapter, StatsPort)` passa para cada um?
3. Wilcoxon: pareamento por `(question_id, seed)` correto?
   `effect_size_r = Z / sqrt(N)` calculado e testado?
   n<5 → `significant=False`, sem exceção, WARNING — testado?
4. Friedman: post-hoc Nemenyi só quando `p_value < 0.05`?
   < 3 grupos → degradação graceful — testado?
5. MLM: `statsmodels.formula.api.mixedlm` com `groups=question_id`?
   `convergence_warning=True` e p-values=NaN em falha numérica — testado?
6. `pandas` e `scipy`/`statsmodels`/`scikit-posthocs` usados SOMENTE em `infrastructure/`?
   Execute: `grep -rn "import scipy\|import statsmodels\|import pandas"
   src/inteligenciomica_eval/domain/ src/inteligenciomica_eval/application/`
   e reporte (deve ser vazio).
7. Golden de Wilcoxon: recalcule um p-value manualmente com os pares do arquivo JSON
   e confira — cite o resultado.
8. import-linter OK; cobertura ≥ 85%; DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Cole o output do grep do item 6. Inclua recomputação do p-value do item 7.
Confirme `pytest tests/unit/adapters/test_stats_adapters.py -v` e `lint-imports`.
~~~

---

