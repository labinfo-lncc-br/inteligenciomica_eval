# Prompts M2 — TAREFA-022 a 028 (Claude Code ↔ ChatGPT Codex)

**Milestone:** M2 — Avaliação automática (Camadas 1+2, juiz determinístico)
**Documento de referência:** `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1)
**Versão:** 2.0 — corrigido após auditoria de cobertura  
**Continuação de:** `prompts_m1_tarefas_013_021.md` (M1 encerra em TAREFA-021)
**Formato:** para cada tarefa, um **Prompt A (implementação — Claude Code)** e um
**Prompt B (verificação — ChatGPT Codex)**, conforme seção 16 do documento de arquitetura.

> **Pré-requisito:** gate de M1 verde (TAREFA-013–021 mergeados: `QdrantRetrieverAdapter`,
> `VLLMGeneratorAdapter`, `PromptRegistry`, `PrometheusJudgeAdapter`,
> `RAGASLayer1Adapter`, `DeterministicMetricsAdapter`, `VLLMServerManagerAdapter`,
> `AnnotationReaderAdapter`, E2E M1).
>
> **Rastreabilidade com a arquitetura (§14.5):**
> | Arq. §14.5 | Prompt M2 | Observação |
> |---|---|---|
> | TAREFA-201 | **TAREFA-022** | M1/TAREFA-016 entregou o HTTP client; esta tarefa fecha o contrato de `batch_invariant` no schema §5.3 |
> | TAREFA-202 | **TAREFA-023** | Upgrade de M1/TAREFA-017 — corrige API RAGAS v0.2+, async, embed endpoint |
> | TAREFA-204 | **TAREFA-024** | Nova — rubrica biomédica via DeepEval G-Eval (6 dimensões, §5.2) |
> | TAREFA-203 | **TAREFA-025** | Upgrade de M1/TAREFA-018 — reconcilia spec de idioma e lazy init |
> | TAREFA-206 | **TAREFA-026** | `ComputeMetricsUseCase` — passada de julgamento, §5.4 |
> | TAREFA-205 | **TAREFA-027** | `RetryableMetricAdapter` — decorator, ADR-007 |
> | TAREFA-207 | **TAREFA-028** | Integration + E2E M2 — fecha milestone |

---

## Nota de operacionalização M2 — decisões que estes prompts fixam

Confirmar com a equipe antes de TAREFA-022 (vetáveis sem retrabalho).

### 1. Assinaturas canônicas dos Ports (§5.1 — autoritativo)

A arquitetura §5.1 define método `.score()` em **todos** os ports de métrica.
Os prompts de M1 usaram `.judge()` e `.compute_aux()` em alguns adapters.
**M2 corrige e padroniza:**

```python
MetricSuitePort.score(sample: EvaluationSample) -> Layer1Metrics
RubricJudgePort.score(sample: EvaluationSample) -> RubricResult
DeterministicMetricPort.score(*, answer: str, ground_truth: str) -> AuxMetrics
```

`DeterministicMetricPort` **não** recebe `EvaluationSample` — recebe strings diretamente
(é síncrono, sem LLM, e o domínio não quer acoplar BertScore ao DTO completo).
Qualquer divergência em M1 deve ser corrigida como parte do PR da tarefa que usa o port.

### 2. Idioma do BertScore — português (PT), não inglês

M1/TAREFA-018 usou `lang="pt"` (correto para o corpus biomédico em PT-BR do
InteligenciÔmica). O arquivo de prompts M2 anterior erroneamente especificou `lang="en"`.
**Esta versão canoniza `lang="pt"`, `rescale_with_baseline=True`** — alinhado com
TAREFA-018. TAREFA-025 (upgrade) não muda o idioma; corrige apenas o padrão de
lazy-init e adiciona o golden dataset de idioma correto.

### 3. `batch_invariant` é um campo de `EvaluationResult`, não só de log

§4.3 exige que `batch_invariant == True` ⟺ métrica veio do juiz. Este campo deve ser
propagado do adapter até o `EvaluationResult` e então até o Parquet (§5.3, campo
obrigatório `batch_invariant: bool`). TAREFA-022 fecha esta lacuna: verifica que
TAREFA-016 (M1) seta corretamente o regime e que o `ComputeMetricsUseCase` (TAREFA-026)
o grava via `ResultWriterPort.update_metrics()` com `regime=DeterminismRegime.JUDGE`.

### 4. Retry é um decorator nos Ports — não nos adapters internos

O `RetryableMetricAdapter` (TAREFA-027) envolve qualquer `MetricSuitePort` ou
`RubricJudgePort`. Os adapters internos (TAREFA-023, 024) levantam
`MetricComputationError` em falha total de I/O; retornam NaN em falha de parsing. O
decorator absorve `MetricComputationError`, aplica backoff, e retorna NaN-sentinel após
esgotar tentativas. O `ComputeMetricsUseCase` injeta **sempre** os adapters com o
decorator aplicado — nunca o adapter nu.

### 5. API RAGAS v0.2+ — async, `single_turn_ascore`, não `evaluate()`

M1/TAREFA-017 corretamente usou `single_turn_ascore()` por métrica individual.
TAREFA-023 confirma e complementa: adiciona configuração explícita do embed endpoint
(`VLLM_EMBED_URL` com fallback para `VLLM_JUDGE_URL`), adiciona `max_concurrency=1`
para preservar determinismo, e corrige o async (todos os adapters de métrica são async
— Nota M1 item 1).

---

## TAREFA-022 — Contrato `batch_invariant` + `DeterminismRegime.JUDGE` ponta-a-ponta

**Épico:** E2 · **Skill:** python-engineer, test-engineer · **Prioridade:** P0 · **Tamanho:** S  
**Referência arquitetural:** TAREFA-201 (§14.5)  
**Dependências:** TAREFA-016 (M1, `PrometheusJudgeAdapter`), TAREFA-004 (M0, entidade
`EvaluationResult` + `DeterminismRegime`), TAREFA-009 (M0, `ParquetStorage`)  
**ADRs:** ADR-003 (dois regimes), ADR-009 (idempotência) · **Camadas:** domain + infrastructure

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §4.3, §5.3
schema Parquet, ADR-003). M1/TAREFA-016 entregou `PrometheusJudgeAdapter` com
`batch_invariant=True` registrado em structlog. Esta tarefa confirma que o contrato do
§4.3 está integralmente implementado: o campo `batch_invariant: bool` do schema §5.3
recebe `True` para toda linha julgada pelo Prometheus-2, e que `DeterminismRegime.JUDGE`
flui corretamente da camada de adapter até o `EvaluationResult` persistido no Parquet.
Skills: python-engineer, test-engineer.

TAREFA: TAREFA-022 — auditar, corrigir e testar a propagação de `batch_invariant` e
`DeterminismRegime.JUDGE` do `PrometheusJudgeAdapter` (TAREFA-016) ao Parquet (§5.3).

ESPECIFICAÇÃO:

1. AUDITORIA DE TAREFA-016 — verificar se:
   a. `PrometheusJudgeAdapter` expõe `adapter.determinism_regime` como atributo de
      instância com valor `DeterminismRegime.JUDGE` (ou equivalente que permite ao
      use case descobrir o regime sem depender de herança).
   b. `EvaluationResult.batch_invariant: bool` existe na entidade de TAREFA-004.
      Se não existir, adicionar o campo como parte desta tarefa (ver §4.3 invariante).
   c. `ResultWriterPort.update_metrics` (TAREFA-009) persiste `batch_invariant` no
      Parquet — conferir que o schema `pyarrow` inclui `pa.field("batch_invariant", pa.bool_())`.
   Se (a), (b) ou (c) estiverem ausentes, corrigi-los como parte desta tarefa e
   documentar a mudança como `fix: propagação de batch_invariant (TAREFA-022)`.

2. TESTE DE CONTRATO (obrigatório, é a entrega principal):
   Criar `tests/contract/test_batch_invariant_contract.py` com os seguintes cenários:
   a. `PrometheusJudgeAdapter.determinism_regime == DeterminismRegime.JUDGE` — verificado
      via atributo, sem instanciar o servidor real.
   b. `EvaluationResult` criado via `result.with_metrics(metrics, final_score,
      DeterminismRegime.JUDGE)` tem `batch_invariant == True` — verificado em unit puro.
   c. Round-trip Parquet (usando `InMemoryResultWriter` de TAREFA-011 com schema real):
      escreve `EvaluationResult` com `batch_invariant=True`, lê de volta, confirma
      `batch_invariant == True` no DataFrame resultante.
   d. Invariante do §4.3: criar `EvaluationResult` com métricas de juiz mas
      `batch_invariant=False` deve levantar exceção de domínio (se a invariante estiver
      implementada) OU — se a validação for apenas no writer — o writer deve logar WARNING
      (comportamento escolhido deve ser documentado num comentário inline indicando a decisão).
   e. `DeterminismRegime.GENERATOR` (gerador) persiste `batch_invariant=False` — confirmado
      em round-trip paralelo para garantir que o campo é diferenciado por regime.

3. CHECKLIST DE ALINHAMENTO (para verificação rápida no Codex):
   Gerar `tests/contract/BATCH_INVARIANT_CHECKLIST.md` listando:
   - Arquivo:linha onde `DeterminismRegime.JUDGE` é definido.
   - Arquivo:linha onde `batch_invariant` é setado para `True` no `EvaluationResult`.
   - Arquivo:linha onde `batch_invariant` é incluído no schema pyarrow do Parquet.
   - Status de cada item (✓ OK | ✗ corrigido nesta tarefa | ⚠ ausente/manual).

ENTREGÁVEL:
- Eventuais correções em TAREFA-004/009/016 (documentadas como fix desta tarefa)
- `tests/contract/test_batch_invariant_contract.py` (5 cenários acima)
- `tests/contract/BATCH_INVARIANT_CHECKLIST.md`

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings Google; mypy --strict.
- Testes de contrato NÃO usam rede real nem GPU.
- Nenhuma mudança de comportamento funcional nos adapters de M1 — só correctives.

CRITÉRIO DE ACEITAÇÃO (TAREFA-022):
- 5 cenários de contrato passam em `pytest tests/contract/`.
- `BATCH_INVARIANT_CHECKLIST.md` sem itens marcados como "⚠ ausente".
- `batch_invariant=True` confirmado num round-trip Parquet real (não mockado).
- import-linter OK; mypy --strict; DoD §14.2.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-022 + arquitetura §4.3/§5.3 + ADR-003 +
"Nota de operacionalização M2" itens 3 e 1.

VERIFIQUE, item a item, citando arquivo:linha:
1. `PrometheusJudgeAdapter` (TAREFA-016) tem atributo `determinism_regime` com valor
   `DeterminismRegime.JUDGE`? Se ausente, foi adicionado nesta tarefa?
2. `EvaluationResult.batch_invariant: bool` existe na entidade (TAREFA-004)? Invariante
   §4.3 implementada (JUDGE→True, GENERATOR→False)?
3. Schema pyarrow do Parquet inclui `pa.field("batch_invariant", pa.bool_())`? Obrigatório
   (não null)?
4. Os 5 cenários de teste estão todos presentes e corretos?
   - (a) `determinism_regime == JUDGE` no adapter — sem rede real?
   - (b) `with_metrics(..., JUDGE)` → `batch_invariant=True` em unit puro?
   - (c) Round-trip Parquet com `batch_invariant=True` persistido e relido?
   - (d) Invariante validada (exceção ou WARNING documentado)?
   - (e) GENERATOR → `batch_invariant=False` round-trip?
5. `BATCH_INVARIANT_CHECKLIST.md` gerado e sem itens "⚠ ausente"?
6. Nenhuma mudança de comportamento funcional nos adapters de M1 (apenas correctivas)?
7. import-linter OK? mypy --strict? DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Confirme `pytest tests/contract/` e `lint-imports`.
~~~

---

## TAREFA-023 — Upgrade `RAGASLayer1Adapter` — async + embed endpoint + golden PT

**Épico:** E2 · **Skills:** rag-engineer, ml-engineer · **Prioridade:** P0 · **Tamanho:** M  
**Referência arquitetural:** TAREFA-202 (§14.5) — upgrade de M1/TAREFA-017  
**Dependências:** TAREFA-017 (M1, `RAGASLayer1Adapter` — substituído por este), TAREFA-022
(contrato `batch_invariant`), TAREFA-005 (M0, `MetricSuitePort`)  
**ADRs:** ADR-006 (RAGAS atrás de port, versão pinada), ADR-007 (NaN) · **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §5.1 MetricSuitePort,
§5.2 Camada 1, ADR-006). M1/TAREFA-017 entregou `RAGASLayer1Adapter` usando
`single_turn_ascore()` individualmente — abordagem correta. Esta tarefa (TAREFA-023)
complementa e consolida TAREFA-017 com: (a) endpoint de embedding configurável separado do
juiz, (b) `max_concurrency=1` explícito para determinismo, (c) campo `ragas_version`
lido e exposto, (d) golden dataset em português para smoke test, (e) método renomeado
para `.score()` (canonical §5.1). Skills: rag-engineer, ml-engineer.
VER "Nota de operacionalização M2" itens 1, 4 e 5.

TAREFA: TAREFA-023 — refatorar/completar `RAGASLayer1Adapter` em
`src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py`,
garantindo a conformidade integral com §5.1 e ADR-006.

ESPECIFICAÇÃO (delta sobre TAREFA-017):

1. MÉTODO CANÔNICO (Nota M2 item 1):
   - Renomear para `score(self, sample: EvaluationSample) -> Layer1Metrics`
     (não `.compute()`). O adapter deve satisfazer `isinstance(adapter, MetricSuitePort)`
     com o Protocol `@runtime_checkable`.

2. EMBED ENDPOINT SEPARADO (Nota M2 item 5):
   - Adicionar `vllm_embed_url: str | None = None` à config do adapter.
   - Se `vllm_embed_url` estiver setado: usar `OpenAIEmbeddings(base_url=embed_url, ...)`
     com `LangchainEmbeddingsWrapper` para `SemanticSimilarity`.
   - Se não: usar `HuggingFaceEmbeddings(model_name=config.hf_embed_model)` como
     fallback (padrão: `"sentence-transformers/all-MiniLM-L6-v2"` — leve, CPU).
   - Lógica de fallback documentada em docstring e testada nos dois ramos.

3. `max_concurrency=1` EXPLÍCITO:
   - Toda métrica RAGAS deve ser configurada com `max_concurrency=1` para preservar
     determinismo com o juiz (ADR-003). Documentar como constante com comentário ADR-003.
     ```python
     RAGAS_MAX_CONCURRENCY: Final[int] = 1  # ADR-003: preserva determinismo do juiz
     ```

4. `ragas_version` EXPOSTO:
   - `adapter.ragas_version: str` — ler de `importlib.metadata.version("ragas")` na
     inicialização. Logar na primeira chamada a `score()`. Gravar no `EvaluationResult`
     via o campo `ragas_version` do schema §5.3 (passado para o use case via um campo
     acessório no resultado ou via o config do run — documenta a opção escolhida).

5. GOLDEN DATASET EM PORTUGUÊS:
   - Adicionar `tests/golden/ragas_pt_smoke.json` com 1 amostra PT-BR biomédica:
     `{"question": "...", "generated_answer": "...", "ground_truth": "...",
      "contexts": ["...", "..."], "expected_answer_correctness_min": 0.4}`.
   - Teste de smoke (marcado `@pytest.mark.integration`): `answer_correctness >= 0.4`
     confirmado com o vllm-judge real (skipável via `pytest.mark.skipif` quando
     `VLLM_JUDGE_URL` não estiver setado).

6. TRATAMENTO DE NaN (sem mudança de M1/TAREFA-017):
   - Mantém: cada métrica individualmente em try/except; NaN isolado por campo.
   - Falha total (connection error, timeout): levanta `MetricComputationError`.

7. LOGGING (complementar ao de TAREFA-017):
   - Adicionar `ragas_version` e `embed_source` ("hf_local" | "vllm_endpoint") ao log
     `ragas_layer1_computed`.

ENTREGÁVEL:
- `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py` (refatorado)
- Atualização de `infrastructure/config/adapter_configs.py` com `RagasAdapterConfig`
  incluindo `vllm_embed_url: str | None`, `hf_embed_model: str`, `ragas_max_concurrency: int = 1`
- `tests/unit/infrastructure/adapters/test_ragas_layer1.py` (atualizado):
  - Novos cenários: embed via endpoint vs. HF local; `isinstance` MetricSuitePort; `ragas_version` no log
- `tests/golden/ragas_pt_smoke.json`
- `tests/integration/adapters/test_ragas_smoke.py` (smoke PT, skipável)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; mypy --strict; import-linter OK.
- NÃO usar `ragas.evaluate(dataset)` em batch — individual por métrica.
- `judge_url` e `embed_url` NUNCA hardcoded — sempre do construtor/config.
- Cobertura da lógica de fallback de embed (ambos os ramos testados).

CRITÉRIO DE ACEITAÇÃO (TAREFA-023):
- `isinstance(adapter, MetricSuitePort)` True com `@runtime_checkable`.
- `max_concurrency=1` presente como constante e documentado ADR-003.
- Ramo HF-embed e ramo vllm-embed ambos cobertos no unit.
- `ragas_version` no log da primeira chamada.
- Golden PT: `answer_correctness >= 0.4` no smoke (quando juiz disponível).
- import-linter OK; mypy --strict; DoD §14.2.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-023 + arquitetura §5.1/§5.2 + ADR-003/006/007 +
"Nota de operacionalização M2" itens 1, 4 e 5 + skill rag-engineer §10.

VERIFIQUE, item a item, citando arquivo:linha:
1. Método renomeado para `.score(sample: EvaluationSample) -> Layer1Metrics`?
   `isinstance(adapter, MetricSuitePort)` verdadeiro (Protocol `@runtime_checkable`)?
2. `max_concurrency=1` presente como constante `Final[int]` com comentário ADR-003?
   NÃO usa `ragas.evaluate(dataset)` em batch?
3. Dois ramos de embed: (a) `vllm_embed_url` setado → `OpenAIEmbeddings` +
   `LangchainEmbeddingsWrapper`; (b) não setado → `HuggingFaceEmbeddings` fallback?
   Ambos testados no unit?
4. `ragas_version` lido de `importlib.metadata`, logado na primeira chamada?
   Campo `embed_source` ("hf_local" | "vllm_endpoint") no log?
5. NaN por métrica individual (não NaN total em try/except de topo)? Testado?
   Falha total → `MetricComputationError` (não NaN)?
6. Golden PT presente em `tests/golden/ragas_pt_smoke.json`? Amostra em português?
   Smoke test skipável quando `VLLM_JUDGE_URL` ausente?
7. `judge_url` e `embed_url` nunca hardcoded? import-linter OK? mypy --strict? DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Confirme `pytest tests/unit/infrastructure/adapters/test_ragas_layer1.py` e `lint-imports`.
~~~

---

## TAREFA-024 — `PrometheusRubricJudgeAdapter` (nova — Camada 2, DeepEval G-Eval)

**Épico:** E2 · **Skills:** ml-engineer, rag-engineer · **Prioridade:** P0 · **Tamanho:** M  
**Referência arquitetural:** TAREFA-204 (§14.5) — nova, não coberta em M1  
**Dependências:** TAREFA-016 (M1, `PrometheusJudgeAdapter` como referência de config do juiz),
TAREFA-022 (`DeterminismRegime.JUDGE` propagado), TAREFA-005 (M0, `RubricJudgePort`)  
**ADRs:** ADR-003 (determinismo), ADR-006 (DeepEval atrás de port), ADR-008 (config) ·
**Camadas:** infrastructure/adapters + infrastructure/prompts

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §5.1 RubricJudgePort,
§5.2 Camada 2 — rubrica biomédica 6 dimensões, §9 Prometheus-2, ADR-006). M1/TAREFA-016
entregou `PrometheusJudgeAdapter` que usa a rubrica via `PromptRegistry.render_biomed_rubric`.
Esta tarefa (`TAREFA-024`) cria um adapter de **Camada 2 formal** usando DeepEval G-Eval com a
rubrica versionada das 6 dimensões biomédicas (§5.2 doc-base), com score normalizado [0,1]
e feedback estruturado para auditoria. Skills: ml-engineer, rag-engineer.
VER "Nota de operacionalização M2" itens 1, 4.

TAREFA: TAREFA-024 — implementar `PrometheusRubricJudgeAdapter` em
`src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py`.
Este adapter é a implementação **canônica** de Camada 2; o `PrometheusJudgeAdapter` de
M1/TAREFA-016 pode ser mantido para compatibilidade ou depreciado — documentar a decisão.

ESPECIFICAÇÃO:

1. INTERFACE CANÔNICA (Nota M2 item 1):
   - Implementa `RubricJudgePort.score(sample: EvaluationSample) -> RubricResult`
   - `RubricResult(score: float, feedback: str)` onde `score ∈ [0,1]` ou `math.nan`.
   - `isinstance(adapter, RubricJudgePort)` True com `@runtime_checkable`.

2. RUBRICA BIOMÉDICA — 6 DIMENSÕES (§5.2 doc-base):
   As dimensões obrigatórias são exatamente estas (não adicionar, não remover):
   1. **Correção factual** — afirmações batem com a ground truth?
   2. **Completude** — cobre todos os pontos essenciais?
   3. **Contradições internas** — afirma algo oposto à referência?
   4. **Alucinação** — afirmações sem sustentação no contexto recuperado?
   5. **Ressalvas omitidas** — incertezas biológicas/clínicas descartadas?
   6. **Pertinência biomédica** — terminologia técnica usada corretamente?

   O prompt da rubrica é um artefato **versionado e externo ao código** (rag-engineer §16):
   `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric_v1.txt` (ou `.jinja2`).
   Variáveis de template: `{question}`, `{reference}`, `{generated_answer}`,
   `{retrieved_context}`. O prompt deve instruir o modelo a:
   (a) avaliar cada dimensão individualmente com justificativa curta,
   (b) dar um score global de 1 a 5 (normalizado pelo adapter para [0,1]),
   (c) retornar JSON estruturado: `{"score": <int 1-5>, "feedback": {"dim1": "...", ..., "global": "..."}}`.
   Expor `adapter.prompt_version: str` para gravação no schema §5.3.

3. IMPLEMENTAÇÃO VIA DEEPEVAL:
   - Opção A (preferida): subclassear `DeepEvalBaseLLM` do DeepEval para apontar para
     `VLLM_JUDGE_URL` (OpenAI-compatible, temperatura 0.0). Usar `GEval(...)` com os
     critérios das 6 dimensões.
   - Opção B (fallback): se a versão instalada do DeepEval não suportar endpoint
     customizado, chamar o endpoint do juiz diretamente via `openai.AsyncOpenAI` (mesmo
     padrão de TAREFA-016), passar o prompt da rubrica como `user` message, parsear
     manualmente com Pydantic. Documentar o motivo como ADR inline.
   - Em ambas as opções: `temperature=0.0`, modelo = `config.judge_model_name`,
     endpoint = `VLLM_JUDGE_URL`.

4. PARSER DE SAÍDA (rag-engineer §16 — "json.loads cego"):
   - Usar Pydantic para validar o JSON retornado pelo juiz.
   - Schema de saída esperado:
     ```python
     class RubricOutput(BaseModel):
         score: int = Field(..., ge=1, le=5)
         feedback: dict[str, str]
     ```
   - Normalização: `score_normalizado = (score_bruto - 1) / 4.0` → [0.0, 1.0].
   - Em falha de parsing (JSON malformado, score fora de [1,5], campos ausentes):
     retornar `RubricResult(score=math.nan, feedback="[parse_error]")` SEM exceção.
   - Falha total de I/O (HTTP 5xx, timeout): levantar `MetricComputationError`.

5. CONFIG — `RubricJudgeAdapterConfig` (em `adapter_configs.py`):
   `vllm_judge_url: str`, `vllm_judge_api_key: str = "EMPTY"`,
   `judge_model_name: str`, `timeout_s: int = 180`,
   `prompt_version: str` (lido do arquivo de prompt — hash da primeira linha ou
   constante declarada no topo do arquivo .txt).

6. LOGGING ESTRUTURADO (sem vazar conteúdo longo):
   `rubric_judge_completed` com: `question_id` (se disponível), `score`,
   `prompt_version`, `latency_ms`, `parse_error: bool`. NÃO logar feedback completo
   (pode ter conteúdo biomédico sensível — somente o comprimento: `feedback_len`).

ENTREGÁVEL:
- `src/inteligenciomica_eval/infrastructure/adapters/prometheus_rubric_judge.py`
- `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric_v1.txt` (ou `.jinja2`)
- Atualização de `infrastructure/config/adapter_configs.py` com `RubricJudgeAdapterConfig`
- `tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py`
  (respx; cenários: score 3/5 → normaliza para 0.5; parse falho → NaN sem exceção;
  HTTP 500 → MetricComputationError; `isinstance` RubricJudgePort; `prompt_version` acessível)
- `tests/integration/adapters/test_rubric_judge_integration.py`
  (marcado `@pytest.mark.integration`; skipável; confirma determinismo: mesma entrada
  2× → mesmo score quando `VLLM_JUDGE_URL` disponível)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings; mypy --strict.
- Prompt em arquivo separado (NUNCA string inline). `prompt_version` testado.
- Sem segredo hardcoded. import-linter OK. Cobertura ≥ 80%.

CRITÉRIO DE ACEITAÇÃO (TAREFA-024):
- Exatamente 6 dimensões no arquivo de prompt (não mais, não menos).
- Normalização: score 1 → 0.0; score 3 → 0.5; score 5 → 1.0 — 3 pontos testados.
- Parse falho → `RubricResult(NaN, "[parse_error]")` SEM exceção — testado.
- HTTP 500 → `MetricComputationError` — testado.
- `adapter.prompt_version` acessível — testado.
- `isinstance(adapter, RubricJudgePort)` True.
- import-linter OK; mypy --strict; DoD §14.2.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-024 + arquitetura §5.1/§5.2 + ADR-003/006/008 +
"Nota de operacionalização M2" itens 1 e 4 + skill rag-engineer §16 ("prompt inline",
"json.loads cego") + skill ml-engineer.

VERIFIQUE, item a item, citando arquivo:linha:
1. Implementa `RubricJudgePort.score(sample) -> RubricResult` (não `.judge()`, não
   `.compute()`)? `isinstance(adapter, RubricJudgePort)` True? Testado?
2. Arquivo de prompt existe em `infrastructure/prompts/biomed_rubric_v1.txt` (ou .jinja2)
   e contém EXATAMENTE as 6 dimensões do §5.2? Conte as dimensões no arquivo e reporte.
3. Parser usa Pydantic com `RubricOutput` (score: int ∈ [1,5], feedback: dict)?
   NÃO usa `json.loads` cego?
4. Normalização score 1-5 → [0,1]: recompute você mesmo 1→0.0, 3→0.5, 5→1.0 e confira
   a fórmula no código. Cite a linha.
5. Parse falho → `RubricResult(NaN, "[parse_error]")` SEM exceção — confirmado no
   código (não só nos testes)?
6. HTTP 5xx / timeout → `MetricComputationError` — confirmado no código?
7. `adapter.prompt_version` exposto (para o schema §5.3)?
8. Logging sem conteúdo completo de resposta/contexto? Só `feedback_len`?
9. Se Opção B (chamada direta) foi usada, ADR inline justificando presente?
10. Determinismo (ADR-003): `temperature=0.0` no body da request (verificado via respx)?
11. mypy --strict; import-linter OK; cobertura ≥ 80%? DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Recompute a normalização e indique o resultado esperado. Confirme
`pytest tests/unit/infrastructure/adapters/test_prometheus_rubric_judge.py` e `lint-imports`.
~~~

---

## TAREFA-025 — Upgrade `DeterministicMetricsAdapter` — lazy init + golden + assinatura canônica

**Épico:** E2 · **Skill:** ml-engineer · **Prioridade:** P1 · **Tamanho:** S  
**Referência arquitetural:** TAREFA-203 (§14.5) — upgrade de M1/TAREFA-018  
**Dependências:** TAREFA-018 (M1, `DeterministicMetricsAdapter` — refinado por este),
TAREFA-005 (M0, `DeterministicMetricPort`)  
**ADRs:** — · **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §5.1
DeterministicMetricPort, §5.2 Camada 1 auxiliares). M1/TAREFA-018 entregou
`DeterministicMetricsAdapter` com BERTScore-F1 e ROUGE-L em português (correto).
Esta tarefa (TAREFA-025) realiza três melhorias: (a) assinatura canônica §5.1,
(b) lazy init via atributo de instância (não `cached_property` — vaza em testes),
(c) golden dataset com 3 pares PT-BR biomédicos incluindo threshold documentado.
Skill: ml-engineer. VER "Nota de operacionalização M2" itens 1 e 2.

TAREFA: TAREFA-025 — refatorar `DeterministicMetricsAdapter` em
`src/inteligenciomica_eval/infrastructure/adapters/deterministic_metrics.py`.

ESPECIFICAÇÃO (delta sobre TAREFA-018):

1. ASSINATURA CANÔNICA (Nota M2 item 1 — CRÍTICO):
   - Port §5.1: `DeterministicMetricPort.score(*, answer: str, ground_truth: str) -> AuxMetrics`
   - O adapter NÃO recebe `EvaluationSample` — recebe strings diretamente.
   - Renomear de `.compute_aux(sample)` (se assim estava em M1) para
     `.score(*, answer: str, ground_truth: str) -> AuxMetrics`.
   - `isinstance(adapter, DeterministicMetricPort)` True com `@runtime_checkable`.

2. LAZY INIT VIA ATRIBUTO DE INSTÂNCIA (Nota M2 item 2):
   - Substituir `functools.cached_property` por atributo privado:
     ```python
     class DeterministicMetricsAdapter:
         def __init__(self, config: DeterministicAdapterConfig) -> None:
             self._config = config
             self._scorer: BERTScorer | None = None  # lazy, NOT cached_property

         def _get_scorer(self) -> BERTScorer:
             if self._scorer is None:
                 self._scorer = BERTScorer(
                     model_type=self._config.model_type,
                     lang=self._config.lang,          # "pt" (Nota M2 item 2)
                     rescale_with_baseline=True,
                     device=self._config.device,
                 )
             return self._scorer
     ```
   - Motivo documentado em docstring: `cached_property` é um singleton por classe em
     Python, vaza entre instâncias de teste diferentes; atributo de instância não.
   - Teste: 2 instâncias distintas do adapter NÃO compartilham o mesmo `_scorer`
     (verificado por comparação de `id()`).

3. CONFIG — `DeterministicAdapterConfig` (em `adapter_configs.py`):
   - Campos: `model_type: str = "bert-base-multilingual-cased"`, `lang: str = "pt"`,
     `rescale_with_baseline: bool = True`, `device: str = "cpu"`.
   - Documentar: `lang="pt"` é o idioma canônico do corpus InteligenciÔmica.
     Mudar para "en" exigiria um novo golden dataset e aprovação explícita da equipe.

4. GOLDEN DATASET (3 pares PT-BR biomédicos):
   - Criar `tests/golden/det_metrics_pt_golden.json` com:
     ```json
     [
       {"id": "identical", "answer": "...", "ground_truth": "...",
        "bertscore_f1_min": 0.98, "rouge_l_min": 0.98},
       {"id": "similar",   "answer": "...", "ground_truth": "...",
        "bertscore_f1_min": 0.70, "rouge_l_min": 0.40},
       {"id": "different", "answer": "...", "ground_truth": "...",
        "bertscore_f1_max": 0.60, "rouge_l_max": 0.30}
     ]
     ```
   - Os textos devem ser frases biomédicas reais em PT-BR (ex.: sobre receptores de
     adenosina, inibidores de quinase etc. — qualquer conteúdo do domínio InteligenciÔmica).
   - Teste de golden: `bertscore_f1 >= min` e `rouge_l >= min` para identical/similar;
     `bertscore_f1 <= max` para different. Roda em CPU sem rede.

5. DETERMINISMO (sem mudança de M1):
   - Confirmado: 2 chamadas com input idêntico → mesmo float bit-a-bit.
   - Teste de integração mantido (`@pytest.mark.integration`), agora com golden real.

ENTREGÁVEL:
- `src/inteligenciomica_eval/infrastructure/adapters/deterministic_metrics.py` (refatorado)
- Atualização de `infrastructure/config/adapter_configs.py`
- `tests/unit/infrastructure/adapters/test_deterministic_metrics.py` (atualizado):
  - Novos: `isinstance(adapter, DeterministicMetricPort)`; assinatura `.score(*, answer, ground_truth)`;
    2 instâncias distintas têm `_scorer` distintos (id check)
- `tests/golden/det_metrics_pt_golden.json` (3 pares PT-BR biomédicos)
- `tests/integration/adapters/test_deterministic_integration.py` (golden + determinismo)

RESTRIÇÕES (DoD §14.2):
- Síncrono (NÃO async — Nota M1 item 1); lazy init por instância; `lang="pt"`.
- `from __future__ import annotations`; type hints; docstrings; mypy --strict.
- Cobertura ≥ 80%.

CRITÉRIO DE ACEITAÇÃO (TAREFA-025):
- `isinstance(adapter, DeterministicMetricPort)` True; assinatura `.score(*, answer, ground_truth)`.
- 2 instâncias distintas NÃO compartilham `_scorer` (id check).
- Golden 3 pares PT-BR passa em CPU: identical ≥ 0.98; similar ≥ 0.70; different ≤ 0.60.
- Determinismo: 2 chamadas idênticas → mesmo float.
- import-linter OK; mypy --strict; DoD §14.2.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-025 + arquitetura §5.1/§5.2 + "Nota de operacionalização
M2" itens 1 e 2 + skill ml-engineer.

VERIFIQUE, item a item, citando arquivo:linha:
1. Assinatura `.score(*, answer: str, ground_truth: str) -> AuxMetrics` (NÃO
   `.compute_aux(sample)`, NÃO `.score(sample)`)? `isinstance(DeterministicMetricPort)` True?
2. Lazy init por atributo de instância `_scorer: BERTScorer | None` (NÃO `cached_property`)?
   Motivo documentado? Teste de isolamento (id check entre 2 instâncias) presente?
3. `lang="pt"`, `rescale_with_baseline=True` na config? Documentado que mudar idioma
   exige golden + aprovação?
4. Golden `tests/golden/det_metrics_pt_golden.json` com 3 pares PT-BR biomédicos?
   - Textos realmente em PT? (Não em EN ou lorem ipsum?)
   - Thresholds: identical ≥ 0.98, similar ≥ 0.70, different ≤ 0.60?
5. Determinismo testado (2 chamadas idênticas → mesmo float)?
6. Síncrono (sem async)? Cobertura ≥ 80%? import-linter OK? mypy --strict? DoD §14.2?

ATENÇÃO: verifique se `lang="en"` ou `lang="pt-br"` foi usado acidentalmente
(bloqueador — só "pt" é aceito conforme Nota M2 item 2). Verifique também se
`cached_property` ainda aparece no código (bloqueador — causa vazamento entre testes).

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Recompute manualmente ROUGE-L de 1 par do golden (fórmula F = 2PR/(P+R) sobre LCS de
tokens) e indique o valor esperado. Confirme
`pytest tests/unit/infrastructure/adapters/test_deterministic_metrics.py
tests/integration/adapters/test_deterministic_integration.py` e `lint-imports`.
~~~

---

## TAREFA-026 — `ComputeMetricsUseCase` (passada de julgamento, §5.4)

**Épico:** E2 · **Skills:** python-engineer, data-engineer · **Prioridade:** P0 · **Tamanho:** M  
**Referência arquitetural:** TAREFA-206 (§14.5)  
**Dependências:** TAREFA-022 (`DeterminismRegime.JUDGE`), TAREFA-023 (`MetricSuitePort.score`),
TAREFA-024 (`RubricJudgePort.score`), TAREFA-025 (`DeterministicMetricPort.score`),
TAREFA-027 (`RetryableMetricAdapter` — injetado; pode ser implementado em paralelo se a
interface do Port já existir), TAREFA-006 (M0, `FinalScoreCalculator`), TAREFA-009
(M0, `ResultWriterPort`), TAREFA-002 (M0, `MetricComputationError`)  
**ADRs:** ADR-007 (NaN), ADR-009 (idempotência) · **Camadas:** application

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §5.4 "Contrato
entre passadas", §3.4 fluxo principal). Padrão: python-clean-architecture §2 (use case
de application: orquestra ports, NÃO duplica lógica de domínio, NÃO importa infra).
Skills: python-engineer, data-engineer.

IMPORTANTE — assinaturas canônicas dos ports injetados (Nota M2 item 1):
  metric_suite.score(sample: EvaluationSample) -> Layer1Metrics
  rubric_judge.score(sample: EvaluationSample) -> RubricResult
  aux_metrics.score(*, answer: str, ground_truth: str) -> AuxMetrics

Os adapters de `metric_suite` e `rubric_judge` chegam JÁ ENVOLVIDOS pelo
`RetryableMetricAdapter` (TAREFA-027) — nunca o adapter nu. O `aux_metrics`
NÃO precisa de retry (é determinístico, sem LLM).

TAREFA: TAREFA-026 — implementar `ComputeMetricsUseCase` em
`src/inteligenciomica_eval/application/compute_metrics_use_case.py`.

ESPECIFICAÇÃO:

1. DTOs de I/O (frozen dataclasses, sem Pydantic — Pydantic é fronteira de adapter):
   ```python
   @dataclass(frozen=True)
   class ComputeMetricsInput:
       run_id: str
       round_id: str
       phase: str | None = None    # None = todas as fases
       force: bool = False         # reprocessar linhas com final_score já preenchido

   @dataclass(frozen=True)
   class ComputeMetricsReport:
       run_id: str
       n_processed: int            # linhas processadas com sucesso
       n_skipped: int              # linhas com final_score preenchido (puladas)
       n_nan_excluded: int         # linhas persistidas com final_score NaN
       n_failed_terminal: int      # erros inesperados após retry esgotado
       failed_row_ids: tuple[str, ...]
   ```

2. INTERFACE DO USE CASE:
   ```python
   class ComputeMetricsUseCase:
       def __init__(
           self, *,
           reader: ResultReaderPort,
           writer: ResultWriterPort,
           metric_suite: MetricSuitePort,       # JÁ com RetryableMetricAdapter
           rubric_judge: RubricJudgePort,        # JÁ com RetryableMetricAdapter
           aux_metrics: DeterministicMetricPort, # sem retry
           score_calculator: FinalScoreCalculator,
           config: ComputeMetricsConfig,
       ) -> None: ...

       async def execute(self, inp: ComputeMetricsInput) -> ComputeMetricsReport: ...
   ```
   O método `execute` é **async** (Nota M1 item 1 — adapters de métrica são async).

3. `ComputeMetricsConfig` (frozen dataclass em application — sem Pydantic):
   `log_progress_every: int = 10`, `failure_threshold: float = 0.70`.

4. FLUXO DE `execute` (§5.4):
   a. `rows = await reader.load(round_id=inp.round_id, phase=inp.phase)`
      → `ResultFrame` (wrapper sobre `tuple[EvaluationResult, ...]`).
   b. Separar `to_process` (`final_score is None` ou `force=True`) de `to_skip`.
      Incrementar `n_skipped` para as puladas.
   c. Para cada `result` em `to_process`, em ordem DETERMINÍSTICA (sort por `row_id`):
      i.   Montar `EvaluationSample` de `result`: `question=result.answer.question.text`,
           `generated_answer=result.answer.text`, `ground_truth=result.answer.question.ground_truth`,
           `contexts=result.answer.retrieved_chunks_text`.
      ii.  `layer1: Layer1Metrics = await metric_suite.score(sample)`.
      iii. `rubric: RubricResult = await rubric_judge.score(sample)`.
      iv.  `aux: AuxMetrics = aux_metrics.score(answer=result.answer.text,
                                                  ground_truth=result.answer.question.ground_truth)`.
      v.   Montar `MetricVector` (TAREFA-003) com todos os campos; detectar `nan_fields`.
      vi.  `final_score = score_calculator.compute(metrics)`.
      vii. Novo `EvaluationResult` via `result.with_metrics(metrics, final_score,
            DeterminismRegime.JUDGE)` — seta `batch_invariant=True` (TAREFA-022).
      viii.`await writer.update_metrics(row_id=result.answer.row_id,
            metrics=metrics, final_score=final_score, regime=DeterminismRegime.JUDGE)`.
      ix.  Incrementar `n_nan_excluded` se `math.isnan(final_score.value)`, senão `n_processed`.
      x.   Logar progresso a cada `config.log_progress_every` linhas.
   d. Exceção inesperada por linha (bug de adapter escapa do decorator):
      capturar, logar `ERROR` com `row_id`, `n_failed_terminal++`, adicionar a
      `failed_row_ids`, **CONTINUAR** o loop (não abortar).
   e. Logar summary final.
   f. Retornar `ComputeMetricsReport`.

5. CONCORRÊNCIA — M2 é SERIAL:
   Processar uma linha por vez (await sequencial). Documentar explicitamente em docstring
   que paralelismo via `asyncio.gather` será adicionado em M3. NÃO antecipar.

6. CAMADA APPLICATION:
   PODE importar `domain`; NÃO importa `infrastructure`. Ports chegam por DI.
   `structlog` permitido em application.

ENTREGÁVEL:
- `src/inteligenciomica_eval/application/compute_metrics_use_case.py`
- `tests/unit/application/test_compute_metrics_use_case.py`
  (usa fakes de TAREFA-011; cenários obrigatórios:
    - fluxo normal: `n_processed == N`
    - skip por `final_score` existente: `n_skipped == N`, writer não chamado
    - `force=True`: reprocessa linha já processada
    - NaN propagado de `metric_suite`: `n_nan_excluded++`, `update_metrics` chamado
    - Exceção inesperada por linha: `n_failed_terminal++`, demais continuam
    - Ordem determinística por `row_id`: sort verificado via spy no fake reader
    - `DeterminismRegime.JUDGE` passado ao `update_metrics`: verificado via spy)
- `tests/golden/compute_metrics_expected.json`
  (4 linhas: normal, NaN parcial, NaN-sentinel completo, force=True; `ComputeMetricsReport` esperado)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; frozen dataclasses; docstrings; type hints; mypy --strict.
- Camada application: import-linter proíbe importar infrastructure. Sem I/O direto.
- Determinístico: sort por `row_id` documentado e testado.
- Cobertura line+branch ≥ 90%.

CRITÉRIO DE ACEITAÇÃO (TAREFA-026):
- `execute` é `async def`; todos os adapters awaited corretamente.
- Idempotência: skip por `final_score` não-nulo por default; `force=True` reprocessa.
- `DeterminismRegime.JUDGE` passado ao `update_metrics` — testado via spy.
- Exceção inesperada por linha → continua loop — testado.
- Ordem determinística (sort por `row_id`) — testado.
- Golden com 4 linhas confere `ComputeMetricsReport` esperado.
- import-linter OK; mypy --strict; cobertura ≥ 90%.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-026 + arquitetura §5.4/§3.4 + ADR-007/009 +
"Nota de operacionalização M2" itens 1, 3, 4 + skill python-engineer + data-engineer.

VERIFIQUE, item a item, citando arquivo:linha:
1. `execute` é `async def`? Adapters de `metric_suite` e `rubric_judge` são awaited
   com `await metric_suite.score(sample)` (não sync)? `aux_metrics.score(...)` é sync?
2. Use case em `application`: NÃO importa `infrastructure`? Ports chegam por DI?
3. Assinaturas dos ports no construtor: `metric_suite: MetricSuitePort`,
   `rubric_judge: RubricJudgePort`, `aux_metrics: DeterministicMetricPort` — corretos?
4. `DeterminismRegime.JUDGE` passado ao `update_metrics`? Verificado em teste via spy?
5. Idempotência (ADR-009): linhas com `final_score` não-nulo PULADAS por default?
   `force=True` as reprocessa? Ambos testados?
6. Exceção inesperada por linha → `n_failed_terminal++` + continua loop? Testado?
7. NaN propagado: `n_nan_excluded++` + `update_metrics` chamado (NaN persiste)? Testado?
8. Sort por `row_id` presente e documentado? Testado via spy?
9. `ComputeMetricsReport` com 5 campos corretos? Golden com 4 linhas confere?
10. Concorrência serial documentada em docstring? `asyncio.gather` ausente?
11. Cobertura ≥ 90%? import-linter OK? mypy --strict? DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Confirme `pytest tests/unit/application/test_compute_metrics_use_case.py` e `lint-imports`.
~~~

---

## TAREFA-027 — `RetryableMetricAdapter` (decorator, ADR-007)

**Épico:** E2 · **Skill:** python-engineer · **Prioridade:** P0 · **Tamanho:** S  
**Referência arquitetural:** TAREFA-205 (§14.5)  
**Dependências:** TAREFA-023/024 (ports a decorar), TAREFA-002 (M0, `MetricComputationError`) ·
**ADRs:** ADR-007 (NaN com retry e degradação explícita) · **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, ADR-007: "retry
máx 3 → NaN explícito", §12 risco "NaN frequente"). Padrão: python-clean-architecture §1
(decorator de adapter). Depende de TAREFA-023/024 (Protocols) e TAREFA-002
(`MetricComputationError`). Skill: python-engineer.
VER "Nota de operacionalização M2" item 4 (retry é no decorator, não nos adapters).

TAREFA: TAREFA-027 — implementar `RetryableMetricSuiteAdapter` e
`RetryableRubricJudgeAdapter` em
`src/inteligenciomica_eval/infrastructure/adapters/retryable_metric_adapter.py`.

ESPECIFICAÇÃO:

1. DOIS DECORATORS CONCRETOS (async — Nota M1 item 1):
   ```python
   class RetryableMetricSuiteAdapter:
       """Decora MetricSuitePort com retry async + NaN-sentinel."""
       def __init__(self, wrapped: MetricSuitePort, config: RetryConfig) -> None: ...
       async def score(self, sample: EvaluationSample) -> Layer1Metrics: ...

   class RetryableRubricJudgeAdapter:
       """Decora RubricJudgePort com retry async + NaN-sentinel."""
       def __init__(self, wrapped: RubricJudgePort, config: RetryConfig) -> None: ...
       async def score(self, sample: EvaluationSample) -> RubricResult: ...
   ```
   Ambos devem satisfazer `isinstance(adapter, MetricSuitePort/RubricJudgePort)` quando
   o Protocol for `@runtime_checkable`.

2. `RetryConfig` (frozen dataclass):
   `max_retries: int = 3`, `initial_wait_s: float = 1.0`, `jitter: bool = False`.
   Jitter off por default para determinismo em testes.

3. LÓGICA DE RETRY (idêntica nos dois decorators, async):
   ```
   tentativa 0: await wrapped.score(sample)
   → sucesso: retornar resultado
   → MetricComputationError:
       se tentativa < max_retries: await asyncio.sleep(initial_wait_s * 2^tentativa); retry
       se tentativa == max_retries: retornar NaN-sentinel (SEM levantar exceção)
   → NaN parcial no resultado (não MetricComputationError):
       NÃO retryar — é decisão do adapter interno (parsing falhou, não I/O).
       Retornar o resultado com NaN parcial como está.
   → Qualquer outra exceção inesperada: propagar imediatamente (não retryar).
   ```

4. NaN-SENTINELS:
   - `MetricSuitePort`: `Layer1Metrics` com TODOS os campos `= math.nan`.
   - `RubricJudgePort`: `RubricResult(score=math.nan, feedback=f"[retry_exhausted:{n}]")`
     onde `n` = número de tentativas realizadas.

5. ESPERA ASYNC:
   Usar `await asyncio.sleep(wait_s)`. Em testes, mockear `asyncio.sleep` via
   `unittest.mock.patch("asyncio.sleep", new_callable=AsyncMock)` ou equivalente
   para testes rápidos e determinísticos.

6. LOGGING ESTRUTURADO:
   Cada tentativa fallida: `WARNING` com `attempt`, `wait_s`, `error_type`.
   NaN-sentinel retornado: `WARNING` com `retry_exhausted=True`, `n_attempts`.

7. FACTORY FUNCTIONS (opcionais mas recomendadas):
   ```python
   def make_retryable_metric_suite(
       adapter: MetricSuitePort, config: RetryConfig | None = None
   ) -> RetryableMetricSuiteAdapter: ...

   def make_retryable_rubric_judge(
       adapter: RubricJudgePort, config: RetryConfig | None = None
   ) -> RetryableRubricJudgeAdapter: ...
   ```

ENTREGÁVEL:
- `src/inteligenciomica_eval/infrastructure/adapters/retryable_metric_adapter.py`
- `tests/unit/adapters/test_retryable_metric_adapter.py`
  (cenários obrigatórios com `AsyncMock` e `patch("asyncio.sleep")`:
   * 1ª falha + 2ª sucesso → resultado correto, 1 retry
   * 3 falhas → NaN-sentinel, SEM exceção ao caller
   * NaN parcial na 1ª → retornado diretamente, SEM retry
   * Exceção inesperada → propagada imediatamente
   * Backoff: sleep chamado com [1.0, 2.0, 4.0] para `max_retries=3, initial_wait_s=1.0`
   * `isinstance(RetryableMetricSuiteAdapter, MetricSuitePort)` True
   * `isinstance(RetryableRubricJudgeAdapter, RubricJudgePort)` True
   * `feedback="[retry_exhausted:3]"` no NaN-sentinel do rubric judge)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings; mypy --strict.
- Puro Python + stdlib (`asyncio`, `math`). Sem rede real.
- import-linter OK. Cobertura line+branch ≥ 95%.

CRITÉRIO DE ACEITAÇÃO (TAREFA-027):
- Todos os 8 cenários de teste passam.
- Backoff correto: `asyncio.sleep` chamado com `[1.0, 2.0, 4.0]` — verificado via spy.
- NaN-sentinel correto para cada Port.
- `isinstance` check positivo para ambos os Protocols.
- Cobertura ≥ 95%. import-linter OK; mypy --strict.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-027 + ADR-007 + "Nota de operacionalização M2" item 4 +
skill python-engineer.

VERIFIQUE, item a item, citando arquivo:linha:
1. Dois decorators async (`async def score`)? Ambos implementam os Protocols?
   `isinstance` positivo para `MetricSuitePort` e `RubricJudgePort`? Testado?
2. `RetryConfig` tem os 3 campos corretos? Frozen? `jitter=False` por default?
3. Lógica de retry: apenas `MetricComputationError` é retryada?
   NaN parcial → retornado SEM retry (confirmado no código, não só nos testes)?
   Exceção inesperada → propagada imediatamente?
4. Após `max_retries` esgotados: NaN-sentinel retornado SEM exceção ao caller?
   `feedback="[retry_exhausted:N]"` com N correto para o rubric judge?
5. Espera via `await asyncio.sleep` (não `time.sleep`)? Backoff `initial_wait_s * 2^i`?
   Sequência `[1.0, 2.0, 4.0]` para `max=3`? Verificada via spy de `asyncio.sleep`?
6. Logging: cada tentativa fallida como WARNING; NaN-sentinel como WARNING?
7. Todos os 8 cenários de teste presentes? Cobertura ≥ 95%?
8. Puro Python/stdlib? import-linter OK? mypy --strict? DoD §14.2?

ATENÇÃO: verificar se o developer usou `time.sleep` em vez de `await asyncio.sleep`
(bloqueador — congela o event loop). Verificar também se NaN parcial aciona retry
indevidamente (bloqueador — violação de ADR-007).

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Confirme `pytest tests/unit/adapters/test_retryable_metric_adapter.py` e `lint-imports`.
~~~

---

## TAREFA-028 — Integration + E2E M2 (fecha milestone)

**Épico:** E2 · **Skill:** test-engineer · **Prioridade:** P0 · **Tamanho:** M  
**Referência arquitetural:** TAREFA-207 (§14.5) — gate do milestone  
**Dependências:** TAREFA-022–027 (todo M2) + TAREFA-021 (E2E M1) ·
**ADRs:** ADR-007 (NaN), ADR-009 (idempotência), ADR-003 (determinismo) · **Camadas:** tests/integration + tests/e2e

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §11 estratégia de
testes, §14.5 gate de go/no-go do M2). FECHA O M2. Depende de todos os artefatos de M2
(022–027) e do E2E de M1 (TAREFA-021). Skills: test-engineer.

TAREFA: TAREFA-028 — implementar:
(a) `tests/integration/test_metrics_pipeline_m2.py` — pipeline de métricas com HTTP
    mockado via `respx` (async);
(b) `tests/e2e/test_full_pipeline_m2.py` — E2E M2 com adapters reais, respx mock para
    HTTP do juiz, BertScore real em CPU, ParquetStorage em `tmp_path`.

ESPECIFICAÇÃO DA PARTE (a) — Integration (async, `pytest-asyncio`):
Marcados `@pytest.mark.integration`. Testam `ComputeMetricsUseCase` + adapters M2 com
`InMemoryResultWriter/Reader` (fakes de TAREFA-011) e `respx.MockRouter` para o
`vllm-judge`. Todos os testes async (`asyncio_mode = "auto"` de M0).

Cenário base — 4 `EvaluationResult` sem `final_score`:
  - Sample 1: `metric_suite.score()` e `rubric_judge.score()` retornam valores normais
    → `FinalScore` calculável.
  - Sample 2: `metric_suite.score()` retorna `answer_correctness = NaN` (parse falhou)
    → `FinalScore` NaN.
  - Sample 3: `metric_suite.score()` levanta `MetricComputationError` na 1ª chamada,
    sucesso na 2ª (retry) → `FinalScore` calculável.
  - Sample 4: `metric_suite.score()` levanta `MetricComputationError` 3× consecutivas
    → NaN-sentinel → `FinalScore` NaN.

Asserções obrigatórias:
  1. `n_processed == 2` (Samples 1 e 3); `n_nan_excluded == 2` (Samples 2 e 4).
  2. `final_score` de Sample 1 bate com valor calculado à mão (golden inline).
  3. Sample 3: exatamente 2 chamadas HTTP para Camada 1 (1 falha + 1 sucesso) —
     `len(respx_router.calls) == 2` (ou equivalente na sessão do Sample 3).
  4. Sample 4: exatamente 3 chamadas HTTP para Camada 1 — todas 500.
  5. Idempotência (ADR-009): 2ª execução com mesma entrada → `n_skipped == 4`;
     `writer.update_metrics` NÃO chamado na 2ª rodada.
  6. `batch_invariant=True` em todos os `EvaluationResult` resultantes — verificado no
     `InMemoryResultWriter` (TAREFA-022 fluindo até aqui).
  7. BertScore real em CPU (Sample 1): `aux_metrics.bertscore_f1 > 0.0` assertado.

ESPECIFICAÇÃO DA PARTE (b) — E2E M2 (async):
Marcado `@pytest.mark.e2e`. Estende o harness do E2E de M1 (TAREFA-021).

Cenário: 2 perguntas PT-BR × 2 LLMs × 1 seed = 4 respostas + 1 resposta extra com
NaN forçado (respx retorna HTTP 500 três vezes para uma resposta).

Fluxo completo:
  1. Reusar fixture de geração de M1 (4+1 respostas em Parquet em `tmp_path`).
  2. `ComputeMetricsUseCase.execute()` com adapters reais de M2 (respx mock para HTTP
     do juiz; BertScore real em CPU; `DeterministicMetricsAdapter` real).
  3. `AggregationService` (TAREFA-008) + `RankScoreCalculator` (TAREFA-007) → `ConfigAggregate`.

Asserções obrigatórias do E2E M2:
  1. Schema §5.3: TODOS os campos de métrica presentes no Parquet (`answer_correctness`,
     `faithfulness`, `context_precision`, `context_recall`, `answer_relevancy`,
     `bertscore_f1`, `rubric_biomed_score`, `rubric_feedback`). Nenhum null por bug de
     campo ausente (null legítimo por NaN é permitido).
  2. `batch_invariant=True` em TODAS as linhas do Parquet — lido de volta via `pd.read_parquet`.
  3. `final_score` das 4 respostas "normais" bate com `tests/golden/e2e_m2_expected.json`.
  4. `n_nan_excluded >= 1` no `ComputeMetricsReport` e `ConfigAggregate.n_excluded_nan >= 1`.
  5. Idempotência: 2ª execução → `n_skipped == 5` (todas as linhas).
  6. Tempo total do E2E M2 < 60s em CPU de CI.

ENTREGÁVEL:
- `tests/integration/test_metrics_pipeline_m2.py`
- `tests/e2e/test_full_pipeline_m2.py`
- Atualização de `tests/e2e/_harness.py` para suportar adapters reais de M2 com respx async.
- `tests/golden/metrics_pipeline_m2_expected.json`
  (FinalScore esperado para Sample 1 da integration, calculado à mão com os pesos do YAML)
- `tests/golden/e2e_m2_expected.json`
  (FinalScore e RankScore esperados para as 4 respostas normais do E2E M2)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings no harness; mypy --strict.
- `asyncio_mode = "auto"` (pytest-asyncio); todos os testes async.
- Determinístico: seeds fixas, respx determinístico, `freezegun` para timestamp.
- Sem GPU/vLLM real; respx mocka todo HTTP para o juiz.
- `pytest -m integration` < 30s; `pytest -m e2e` < 60s em CI de CPU.

CRITÉRIO DE ACEITAÇÃO (TAREFA-028):
- `pytest -m integration` verde: 7 asserções obrigatórias passando.
- `pytest -m e2e` verde: schema §5.3 completo, `batch_invariant=True` em todas as
  linhas, golden correto, idempotência, `n_nan_excluded` propagado.
- Nenhuma chamada de rede real (`respx.NetworkNotMocked` ausente).
- Tempo dentro dos limites (integration < 30s; e2e < 60s).
- Nenhuma violação de `lint-imports`.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-028 + arquitetura §11/§14.5 + ADR-003/007/009 +
skill test-engineer §9 (E2E enxuto) + skill rag-engineer §10 (avaliação).

VERIFIQUE, item a item, citando arquivo:linha:

PARTE (a) — Integration:
1. Testes async com `pytest-asyncio`? `asyncio_mode = "auto"`?
2. Os 4 cenários (normal, NaN parcial, retry 1×, retry esgotado) presentes e corretos?
3. Contagem exata de chamadas HTTP: Sample 3 → 2 calls; Sample 4 → 3 calls?
   Verificado via `respx.calls` ou equivalente?
4. Idempotência: 2ª execução → `n_skipped == 4`; `update_metrics` NÃO chamado? Testado?
5. `batch_invariant=True` em todos os resultantes — verificado no InMemoryResultWriter?
6. BertScore real (Sample 1): `bertscore_f1 > 0.0` assertado? Sem mock?
7. `n_processed == 2` e `n_nan_excluded == 2` assertados?
8. Golden inline para FinalScore de Sample 1 — recompute você mesmo o valor
   (use os pesos do YAML de config ou os defaults) e confirme (cite a recomputação)?

PARTE (b) — E2E M2:
9. Adapters reais M2 (023/024/025) com respx async? BertScore real? Parquet em `tmp_path`?
10. Schema §5.3: TODOS os 8 campos de métrica presentes? Liste qualquer ausente como BLOQUEADOR.
11. `batch_invariant=True` em TODAS as linhas lidas do Parquet?
12. `n_nan_excluded` propagado até `ConfigAggregate.n_excluded_nan`? Testado?
13. Idempotência 2ª execução: `n_skipped == 5`?
14. Tempo assertado (< 60s)? Nenhuma `respx.NetworkNotMocked`?
15. Recompute FinalScore de 1 resposta e RankScore de 1 config do golden e2e. Confira.
16. DoD §14.2; import-linter; mypy --strict?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Inclua a recomputação manual de FinalScore (integration) e RankScore (E2E M2).
Confirme `pytest -m integration && pytest -m e2e`, tempos e `lint-imports`.
Cole o resumo de execução.
~~~

---

## Apêndice — DAG de M2 e gate de saída

### DAG de M2 (baseado em §14.5)

```
M1 gate (013–021) — pré-requisito
    │
    ├── 022 (ContratoBatchInvariant — P0, auditoria M1) ────────────────────────┐
    │                                                                             │
    ├── 025 (DeterministicMetricsAdapter upgrade — P1, independente, CPU) ──────┤
    │                                                                             │
    ├── 027 (RetryableMetricAdapter — P0, deps apenas nos Protocols) ────────────┤
    │                                                                             │
    ├── 023 (RAGASLayer1Adapter upgrade — P0, requer 022 + M1/016) ─────────────┤
    │                                                                             │
    ├── 024 (PrometheusRubricJudgeAdapter — P0, nova, requer M1/016 + 022) ─────┤
    │                                                                             │
    └── 026 (ComputeMetricsUseCase — P0, requer 022+023+024+025+027) ───────────┘
                                                                                  │
                                                               028 (Integration + E2E) ← ÚLTIMO
                                                                                  │
                                                                          GATE M2 ✓
```

### Sequência recomendada de PRs

1. **TAREFA-022** — contrato `batch_invariant`; sem rede; base para todo M2.
2. **TAREFA-025** — BertScore upgrade; CPU puro; pode ir em paralelo com 022.
3. **TAREFA-027** — RetryableMetricAdapter; stdlib puro; pode ir em paralelo.
4. **TAREFA-023** + **TAREFA-024** em paralelo (dependem ambos de 022 + M1/016).
5. **TAREFA-026** — ComputeMetricsUseCase; após 022+023+024+025+027 mergeados.
6. **TAREFA-028** — fecha o milestone; por último.

### Gate de saída M2 (go/no-go para M3)

- `mypy --strict`, `ruff check`, `ruff format --check`, `lint-imports` verdes.
- `pytest -m unit` verde; cobertura `domain` ≥ 95% (mantida de M0/M1).
- `pytest -m integration` verde em < 30s (CPU, sem GPU/vLLM real).
- `pytest -m e2e` verde em < 60s; schema §5.3 completo no Parquet.
- `batch_invariant=True` confirmado em todas as linhas julgadas — evidência no E2E M2.
- Idempotência por `row_id` demonstrada no E2E M2 (2ª execução: `n_skipped == n_total`).
- `ComputeMetricsReport.n_nan_excluded` propagado até `ConfigAggregate` — evidência no E2E.
- Cobertura dos adapters de M2 (022–027) ≥ 85%.
- Cobertura do `ComputeMetricsUseCase` ≥ 90%.
- `BATCH_INVARIANT_CHECKLIST.md` (TAREFA-022) sem itens "⚠ ausente".
- `ielm-eval run --dry-run` ainda funciona (regressão de M0/M1).

### Nota sobre M3 (Rodada 1 completa + orquestração GH200)

M3 implementará a orquestração das 4 GPUs (ADR-012): juiz residente em GPU dedicada,
5 geradores em rotação por ondas nas 3 GPUs restantes. Tarefas principais:
- `TAREFA-029` — `model_registry.yaml` + resolver (nome lógico → pesos + TP + GPU)
- `TAREFA-030` — `VLLMServerManagerAdapter` upgrade para 4 GPUs concorrentes
  (`CUDA_VISIBLE_DEVICES`, `ServerStartTimeoutError`, healthcheck por GPU)
- `TAREFA-031` — Escalonador de ondas (juiz residente + 2 ondas de geradores)
- `TAREFA-032` — Experimento B no `RunExperimentUseCase` (`base="fixed"`)
- `TAREFA-033` — Run report com mapa GPU→modelo por onda
- `TAREFA-034` — E2E orquestração com stubs simulando 4 GPUs

> **Pré-requisito crítico de M3:** a passada de métricas de M2 deve estar completa para
> todas as respostas da Rodada 1 antes de M3 calcular estatísticas. Se
> `n_nan_excluded > 20%` das linhas, investigar parsing do juiz antes de prosseguir —
> resultados estatísticos sobre N insuficiente são não-interpretáveis (ADR-007).
