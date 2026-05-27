# Prompts M1 — TAREFA-013 a 021 (Claude Code ↔ ChatGPT Codex)

**Versão:** 1.1 — corrigido após auditoria `auditoria_m1.md` (26 mai 2026)
**Correções aplicadas (B=Bloqueadoras, I=Importantes, m=Menores):**
B1 (`MetricSuitePort.score`), B2 (`RubricJudgePort.score`), B3 (`DeterministicMetricPort.score`),
B4 (`GoldChunkReaderPort.gold_for`), B5 (`AnnotationReaderPort.read` contrato correto),
B6 (`VLLMServerManagerPort.wait_healthy`), B7 (`GeneratorPort` contexts+temperature+keyword-only),
B8 (`RetrieverPort` top_k obrigatório+keyword-only); I1 (Nota item 5 RAGAS), I2 (rouge_l),
I3 (close() extensão), I4 (sync/async decisão), I5 (8 adapters), I6 (question_id);
m1 (épico), m2 (spec→model), m3 (referência seção), m4 (fixtures path).

**Milestone:** M1 — Adapters de Infraestrutura (implementações reais substituindo os fakes de M0)
**Documento de referência:** `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1) +
`visao_alto_nivel_validacao_inteligenciomica.md` (v1.0, §§ 5, 9, 10, 11)
**Formato:** para cada tarefa, um **Prompt A (implementação — Claude Code)** e um
**Prompt B (verificação — ChatGPT Codex)**, conforme seção 16 do documento de arquitetura.
**Uso:** o desenvolvedor sênior cola o Prompt A no Claude Code; ao receber o PR, cola o Prompt B
no Codex; arbitra PASS/FAIL; itera até PASS; só então parte para a próxima tarefa
**respeitando o DAG do Apêndice**.

> Os prompts abaixo são autocontidos, mas pressupõem que **o arquivo de arquitetura está
> disponível no contexto/repo** de ambos os agentes e que as **skills do projeto**
> (`python-clean-architecture`, `test-engineer`, `python-engineer`, `ml-engineer`,
> `rag-engineer`, `backend-engineer`) estão ativas no Claude Code.
>
> **Pré-requisito:** gate parcial de M0 verde (TAREFA-001 a 012: domínio completo,
> fakes tipados, config/YAML, ParquetStorage, CI verde com `mypy --strict` + `lint-imports`).

---

## Nota de operacionalização — Decisões que M1 fixa

As decisões abaixo são complementares às de M0 e valem para todos os prompts de M1.
Devem ser confirmadas pela equipe (vetáveis antes da TAREFA-013).

### 1. Async-first em todos os adapters I/O-bound + decisão de ports async (I4, B7, B8)

Todos os adapters que realizam chamadas de rede (`QdrantRetrieverAdapter`,
`VLLMGeneratorAdapter`, `PrometheusJudgeAdapter`, `RAGASLayer1Adapter`,
`VLLMServerManagerAdapter`) usam `async/await` + `httpx.AsyncClient` ou o cliente
assíncrono nativo da biblioteca (ex.: `qdrant_client.AsyncQdrantClient`).
Os testes de integração usam `pytest-asyncio` com `asyncio_mode = "auto"` (configurado
no M0) e `respx` para mockar chamadas HTTP ao vLLM.
Adapters síncronos por natureza (BERTScore, ROUGE-L, `AnnotationReaderAdapter`) permanecem
síncronos — não envolva em `asyncio.to_thread` sem necessidade mensurável.

**Decisão de contrato — ports async (vetável pela equipe, PR retroativo obrigatório em M0):**
`RetrieverPort.search()` e `GeneratorPort.generate()` em §5.1 são síncronos. Para manter
compatibilidade com adapters async sem violar o Protocol, **M1 promove ambos a `async def`**
como delta de contrato explícito. PR retroativo em `domain/ports.py` (TAREFA-005/M0) deve
ser mergeado **antes** de TAREFA-013 e TAREFA-014. Os fakes em `tests/fakes/` devem ser
atualizados correspondentemente.

**Extensão `close()` do `QdrantRetrieverAdapter`:** o método `async close()` é de ciclo
de vida do adapter — NÃO faz parte de `RetrieverPort` em §5.1. Use cases não chamam
`close()` diretamente; o gerenciamento de contexto fica no DI container (M3). O
`FakeRetriever` não precisa implementar `close()`. Documentar no docstring do adapter.

### 2. Pydantic exclusivamente na fronteira de infraestrutura

Respostas HTTP de vLLM (OpenAI-compatible) e de Qdrant são deserializadas em Pydantic
models **internas ao adapter** (nunca expostas ao domínio). O adapter converte essas
models para DTOs de domínio (definidos em `domain/ports.py`, frozen dataclasses puras)
antes de retornar. Isso mantém a regra de dependência (ADR-001): `domain/` nunca importa
Pydantic, `infrastructure/` pode.

### 3. Política NaN-or-retry (ADR-007) — implementação canônica

Para todos os adapters que chamam o juiz (PrometheusJudge, RAGAS):

```
tentativa 1 → falha de parsing → loga (structlog, nível WARNING) → retry
tentativa 2 → falha de parsing → loga → retry
tentativa 3 → falha de parsing → loga (nível ERROR, campo nan_reason) →
              retorna float("nan") para a métrica afetada (NÃO levanta exceção)
```

Exceção: se o servidor estiver indisponível (connection refused, timeout de healthcheck),
**sim** levanta `JudgeUnavailableError` — esse erro é irrecuperável pelo caller.
Retry usa `tenacity.AsyncRetrying(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4))`.

### 4. Cliente vLLM via OpenAI SDK (sem litellm em M1)

Ambos os adapters HTTP para vLLM usam:
```python
import openai
client = openai.AsyncOpenAI(base_url=url, api_key="EMPTY")
```
O vLLM expõe API compatível com OpenAI REST. Usar o SDK oficial evita dependência extra
e é mais tipado. `litellm` permanece como opção futura (multi-provider).

### 5. RAGAS aponta para o `vllm-judge` determinístico — via `single_turn_ascore` (I1)

O `RAGASLayer1Adapter` configura RAGAS com `LangchainLLMWrapper` apontando para o
`vllm-judge`. As métricas são calculadas **individualmente** via `single_turn_ascore` —
**NÃO** via `ragas.evaluate(dataset)` batch (que perde o controle de NaN por métrica):
```python
from langchain_openai import ChatOpenAI
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import AnswerCorrectness  # exemplo de uma métrica

llm = LangchainLLMWrapper(
    ChatOpenAI(base_url=judge_url, model=judge_model, temperature=0.0, api_key="EMPTY")
)
# Chamada individual — NÃO usar ragas.evaluate()
metric = AnswerCorrectness(llm=llm, embeddings=embeddings)
score = await metric.single_turn_ascore(ragas_sample)
```
Isso garante que as métricas RAGAS que usam LLM internamente (answer_correctness,
faithfulness, context_precision, context_recall, answer_relevancy) chamam o
`vllm-judge` determinístico — e **não** o vllm-generator. Sem essa configuração explícita,
RAGAS usa a variável de ambiente `OPENAI_API_KEY`, o que é silenciosamente errado.

### 6. PromptRegistry: templates Jinja2, versionados como código

Os templates de prompt da rubrica biomédica ficam em
`src/inteligenciomica_eval/infrastructure/prompts/*.j2`. O `PromptRegistry` carrega
esses templates via `jinja2.Environment(loader=PackageLoader(...))`. O campo
`prompt_version` no schema (§11.2) é preenchido com `git describe --tags --dirty`
capturado na inicialização do registry. **NÃO** usar strings inline de prompt
— mudança de prompt = mudança de arquivo + commit rastreável.

### 7. Testes de integração — estratégia por adapter

| Adapter | Estratégia de teste de integração |
|---|---|
| `QdrantRetrieverAdapter` | `testcontainers.qdrant` (Docker `qdrant/qdrant:v1.9`) com scope="session"; dados de fixture carregados uma vez |
| `GoldChunkReaderAdapter` | lê arquivo JSONL de fixture em `tests/fixtures/` (não `tests/golden/` — reservado para golden datasets de ML); sem container |
| `VLLMGeneratorAdapter` | `respx.mock` sobre `httpx`; fixture de resposta OpenAI-compatible |
| `PrometheusJudgeAdapter` | `respx.mock`; fixture de resposta com score + feedback JSON |
| `RAGASLayer1Adapter` | `respx.mock` para chamadas LLM do RAGAS + Qdrant real (container) |
| `DeterministicMetricsAdapter` | direto (sem I/O externo); usa corpus golden de 3 pares |
| `VLLMServerManagerAdapter` | mock de `asyncio.create_subprocess_exec` + `respx` para `/health` |
| `AnnotationReaderAdapter` | lê arquivo JSONL de fixture em `tests/fixtures/`; sem container |

### 8. Import-linter em M1 — regras existentes mantidas, sem novos contratos

Os três contratos de M0 permanecem inalterados. `infrastructure/adapters/` pode importar
third-party (qdrant_client, openai, ragas, deepeval, bert_score, etc.) — isso é
intencional e correto para a camada de infraestrutura.

### 9. VLLMServerManagerAdapter — escopo limitado em M1

Em M1, o `VLLMServerManagerAdapter` gerencia processos locais via
`asyncio.create_subprocess_exec`. Não usa Docker SDK (reservado para M3/produção).
O método `start()` lança o processo; `wait_healthy()` faz polling no `/health` com timeout
configurável (`startup_timeout_s`, default 120 s). O `ServerHandle` retornado permite
`stop()` e `wait_healthy()`. O adapter é exercitado em testes via mock de subprocess —
**não** inicia vLLM real em CI.

### 10. `rouge_l` — calculado mas não persistido no Parquet §5.3 (I2)

`ROUGE-L` é calculado pelo `DeterministicMetricsAdapter` como sanity check, mas o schema
§5.3 **não possui coluna `rouge_l`**. Decisão de M1: `AuxMetrics(bertscore_f1, rouge_l)`
mantém ambos os campos para uso interno e logging, mas o `ParquetStorage` persiste
apenas `bertscore_f1` (coluna do schema). O campo `rouge_l` é registrado via structlog
(`deterministic_metrics_computed`) com o valor numérico. Nenhum PR retroativo em M0 é
necessário; o Code Agent deve tratar `rouge_l` como campo de log, não de schema.

### 11. `EvaluationSample.question_id` — extensão obrigatória de DTO (I6)

O DTO `EvaluationSample` (definido em M0/TAREFA-005 com campos `question`, `ground_truth`,
`generated_answer`, `contexts`) é estendido com `question_id: str` obrigatório. PR
retroativo em `domain/ports.py` antes de TAREFA-016 (que usa `sample.question_id` no
logging). O `question_id` é obrigatório no schema §5.3, portanto sua ausência em
`EvaluationSample` seria uma lacuna de proveniência.

---

## TAREFA-013 — QdrantRetrieverAdapter + GoldChunkReaderAdapter

**Épico:** E1 — Adapters de Recuperação · **Skills:** rag-engineer, python-engineer
**Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-005 (ports), TAREFA-010 (config/YAML) — ambas de M0
**ADRs:** ADR-001 (regra de dependência) · **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica. Arquitetura v1.1, §5.1
(RetrieverPort, GoldChunkReaderPort). Skills ativas: rag-engineer, python-engineer,
python-clean-architecture, test-engineer. M0 concluído: ports e VOs de domínio existem.

TAREFA: TAREFA-013 — implementar dois adapters em
`src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py`:
(a) `QdrantRetrieverAdapter` — implementa `RetrieverPort`
(b) `GoldChunkReaderAdapter` — implementa `GoldChunkReaderPort`

ESPECIFICAÇÃO:

(a) QdrantRetrieverAdapter:
- Usa `qdrant_client.AsyncQdrantClient` (async obrigatório — ver Nota de M1, item 1).
- Construtor recebe `url: str`, `collection_map: Mapping[str, str]` (mapeia
  `BaseId.value` → nome da coleção no Qdrant, configurado via YAML da Rodada 1),
  e `top_k: int = 8`.
- Implementa `RetrieverPort.search(self, *, base: BaseId, question: str, top_k: int)
  -> RetrievalResult` (assinatura exata do §5.1 — todos keyword-only via `*`; `top_k`
  obrigatório no port):
  - O adapter aceita `top_k` do parâmetro (sempre obrigatório). O DEFAULT de `top_k=8`
    fica no construtor e é passado pelo use case — não é default da assinatura do port.
  - Faz `await async_client.search(collection_name=..., query_vector=..., limit=top_k)`.
  - A query é embedada PELO PRÓPRIO Qdrant (assume que a coleção foi indexada com
    um named vector; o adapter passa o texto da query via `query_text` se o cliente
    suportar, ou usa `payload`). **IMPORTANTE:** o adapter NÃO chama um modelo de
    embedding separado — usa a interface de busca por texto do Qdrant, que delega ao
    embedding model configurado na coleção. Documente essa decisão de design.
  - Converte `ScoredPoint[]` do Qdrant para `RetrievalResult` (DTO de domínio):
    `retrieved_chunk_ids: tuple[str, ...]`, `retrieved_chunks_text: tuple[str, ...]`,
    `retrieval_scores: tuple[float, ...]`. O texto do chunk vem de `point.payload["text"]`.
  - Levanta `RetrievalError` se coleção não existe ou conexão falha.
  - Logging estruturado (structlog): ao final de cada busca, loga
    `qdrant_search_completed` com base, top_k, num_results, latency_ms.
- Implementa também `RetrieverPort.close()` — fecha `async_client`.

(b) GoldChunkReaderAdapter:
- Arquivo JSONL: uma linha por pergunta, formato:
  `{"question_id": "q01", "gold_chunk_ids": ["chunk_abc", "chunk_def", ...]}`.
- Construtor recebe `gold_file: pathlib.Path`.
- Implementa `GoldChunkReaderPort.gold_for(question_id: str) -> list[str]`
  (assinatura exata do §5.1 — método `gold_for`, retorno `list[str]`):
  - Carrega o arquivo na construção (lazy OK, mas deve ser idempotente).
  - Levanta `StorageError` se arquivo não existe.
  - Levanta `StorageError` se question_id não encontrado.
- É síncrono (sem I/O de rede). Sem async.

ENTREGÁVEL:
- `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py`
- `tests/unit/infrastructure/adapters/test_qdrant_retriever_unit.py`
  (unit: mocka AsyncQdrantClient via pytest-mock; testa mapeamento BaseId→coleção,
   conversão de ScoredPoint→RetrievalResult, propagação de RetrievalError)
- `tests/integration/adapters/test_qdrant_retriever_integration.py`
  (integração: Qdrant real via `testcontainers.qdrant`; cria coleção de teste,
   insere 5 chunks, busca e verifica que top_k é respeitado e scores são float em [0,1])
- `tests/unit/infrastructure/adapters/test_gold_chunk_reader.py`
  (unit: lê JSONL de fixture em `tests/fixtures/gold_chunks.jsonl`; testa happy path,
   question_id ausente — levanta `StorageError`, arquivo inexistente — levanta `StorageError`;
   verifica retorno é `list[str]`, não tuple)

RESTRIÇÕES (DoD §14.2 + Nota de M1):
- `from __future__ import annotations`; type hints; docstrings Google.
- Adapter NÃO importa de `domain/application` — apenas de `infrastructure` e third-party.
  Usa DTOs de `domain/ports.py` (RetrieverPort, RetrievalResult, etc.) — isso é permitido.
- `mypy --strict` sem erros; import-linter OK.
- Logging structurado em cada operação de I/O. Sem `print`.
- testcontainers: scope="session" para o container Qdrant; scope="function" para dados.

CRITÉRIO DE ACEITAÇÃO (TAREFA-013):
- `QdrantRetrieverAdapter` satisfaz `RetrieverPort` estruturalmente (isinstance com
  runtime_checkable passa).
- Teste de integração: busca de texto retorna top-k documentos com scores não-nulos,
  ordenados por score descrescente.
- `GoldChunkReaderAdapter.gold_for(question_id)` retorna `list[str]` com os chunk IDs
  do arquivo JSONL para a question_id correta; `StorageError` nos dois casos de falha.
- `mypy --strict`, `ruff`, `lint-imports`, cobertura dos adapters ≥ 80%.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer (skill code-reviewer + rag-engineer). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-013 + arquitetura §5.1 (RetrieverPort, GoldChunkReaderPort)
+ Nota de operacionalização M1 (itens 1, 2, 7, 8) + skill test-engineer §9 (containers).

VERIFIQUE, item a item, citando arquivo:linha:
1. `QdrantRetrieverAdapter` usa `AsyncQdrantClient` (não o síncrono)? Construtor recebe
   `url`, `collection_map`, `top_k`?
2. Assinatura de `search` bate com `RetrieverPort.search` (§5.1): todos os parâmetros
   são keyword-only (`*`), `top_k: int` é obrigatório (sem `Optional` nem default na
   assinatura do port)? Retorna `RetrievalResult` (DTO de domínio, não dict/lista nua)?
3. O adapter NÃO chama modelo de embedding separado — usa busca por texto do Qdrant?
   Está documentado no docstring?
4. `RetrievalError` é levantada em falha de conexão/coleção inexistente?
   `close()` existe e fecha o cliente?
5. Logging estruturado presente (structlog, não print) com campos latency_ms, base,
   num_results?
6. `GoldChunkReaderAdapter` lê JSONL, é síncrono, método é `gold_for()` (§5.1 —
   não `read_gold_chunks`), retorno é `list[str]` (não tuple), levanta `StorageError`
   nos dois casos de falha?
7. Testes de integração usam `testcontainers.qdrant` com scope="session" para o
   container e scope="function" para dados? Verifica top_k e ordenação por score?
8. Cobertura ≥ 80%? `mypy --strict` + `lint-imports` passam?
   Pydantic NUNCA aparece em `domain/`?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Confirme execução: `pytest -m integration tests/integration/adapters/test_qdrant_retriever_integration.py -v`
e `lint-imports`.
~~~

---

## TAREFA-014 — VLLMGeneratorAdapter

**Épico:** E1 — Adapters de Geração · **Skills:** python-engineer, ml-engineer
**Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-005 (ports), TAREFA-010 (config) — M0
**ADRs:** ADR-003 (regime de determinismo), §9.2.4 (sem BATCH_INVARIANT nos geradores)
**Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica. Arquitetura v1.1, §5.1
(GeneratorPort), §9.3 (servidor vllm-generator). Skills: python-engineer, ml-engineer,
python-clean-architecture. M0 completo.

TAREFA: TAREFA-014 — implementar `VLLMGeneratorAdapter` em
`src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py`.

ESPECIFICAÇÃO:
- Implementa `GeneratorPort` (§5.1), com assinatura exata (todos keyword-only via `*`):
    `generate(self, *, llm: LLMId, question: str, contexts: Sequence[Chunk], seed: int,
    temperature: float) -> GenerationOutput`
  Internamente, o adapter converte `Sequence[Chunk]` → `[chunk.text for chunk in contexts]`
  para construir o prompt. Documentar essa conversão no docstring.
- Usa `openai.AsyncOpenAI(base_url=url, api_key="EMPTY")` (Nota M1, item 4).
  URL e modelo são passados pelo construtor (configurados via YAML).
  NÃO usar `OPENAI_API_KEY` do ambiente — deixar api_key="EMPTY" explicitamente.
- Constrói o prompt de geração a partir de (question, contexts):
  prompt_template: um template simples mas parametrizável, carregado do `PromptRegistry`
  (TAREFA-015, ainda não existe). Em M1, aceitar um `prompt_fn: Callable[[str, list[str]], str]`
  no construtor como injeção de dependência. O default pode ser uma lambda inline mínima
  para permitir testes antes de TAREFA-015.
- `temperature` é injetado pelo use case (§5.1 — não hardcoded no adapter); o vLLM recebe
  `temperature=temperature` na chamada. `seed` passado via `extra_body={"seed": seed}`.
  **NÃO** ativar `VLLM_BATCH_INVARIANT` nos geradores — seção §9.2.4.
  Campo `batch_invariant=False` no `GenerationOutput`.
- Registrar em `GenerationOutput`: `text`, `tokens_in`, `tokens_out`, `latency_ms`,
  `batch_invariant=False` (constante para este adapter).
- Retry: `tenacity.AsyncRetrying(stop=stop_after_attempt(3),
  wait=wait_exponential(multiplier=1, min=1, max=8))` para `openai.APIConnectionError`
  e `openai.RateLimitError`. Outros erros: propagar como `GenerationError`.
- Logging estruturado: `vllm_generation_completed` com llm, seed, tokens_in, tokens_out,
  latency_ms, batch_invariant.
- Fechar o `httpx` client interno do `AsyncOpenAI`: implementar `async close()`.

ENTREGÁVEL:
- `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py`
- `tests/unit/infrastructure/adapters/test_vllm_generator.py`
  (unit: usa `respx.mock` sobre httpx para interceptar chamadas ao endpoint OpenAI-compatible;
   testa: prompt construído corretamente, seed no extra_body, batch_invariant=False,
   GenerationError em erro não-retryable, retry em APIConnectionError com máx 3 tentativas)
- `tests/fixtures/vllm_generator_response.json`
  (fixture de resposta OpenAI chat completion compatível com vLLM)

RESTRIÇÕES (DoD §14.2 + Nota M1, itens 1, 4):
- Async; `from __future__ import annotations`; type hints; docstrings.
- `batch_invariant=False` SEMPRE — nunca `True` neste adapter.
- Retry com tenacity documentado (max attempts, quais erros são retryable).
- `mypy --strict`; import-linter OK; cobertura ≥ 80%.

CRITÉRIO DE ACEITAÇÃO (TAREFA-014):
- `VLLMGeneratorAdapter` satisfaz `GeneratorPort` (isinstance + mypy).
- Teste com respx: seed aparece em `extra_body` da requisição; latência medida e
  incluída em `GenerationOutput`.
- `GenerationError` em falha não-retryable; 3 retries em `APIConnectionError`
  (verificado com contador de chamadas interceptadas pelo respx).
- `batch_invariant=False` em todas as instâncias de `GenerationOutput`.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-014 + §5.1 (GeneratorPort) + §9.2.4 + ADR-003 +
Nota M1 (itens 1, 3, 4).

VERIFIQUE, item a item, citando arquivo:linha:
1. Assinatura de `generate` bate com `GeneratorPort` (§5.1): todos keyword-only (`*`),
   `contexts: Sequence[Chunk]` (não `tuple[str,...]`), `temperature: float` presente?
   Retorna `GenerationOutput`?
2. Usa `openai.AsyncOpenAI(..., api_key="EMPTY")` — sem litellm, sem env var de key?
3. Seed aparece em `extra_body={"seed": seed}`; `temperature` é passado diretamente
   ao SDK (não hardcoded como `0.1` no adapter)?
4. `batch_invariant=False` é constante e nunca parametrizável neste adapter
   (ADR-003 — configuração realista de produção)?
5. Retry cobre APENAS erros transitórios (`APIConnectionError`, `RateLimitError`)?
   Outros erros propagam como `GenerationError` diretamente?
6. Logging structurado com campos corretos (llm, seed, tokens_in, tokens_out,
   latency_ms, batch_invariant=False)?
7. Testes usam `respx.mock` (não `pytest.mock.patch`)? Verifica seed no body da request?
   Conta retries?
8. `mypy --strict` + `lint-imports`; cobertura ≥ 80%; sem `print`.

SAÍDA: PASS/FAIL + tabela (critério | arquivo:linha | gravidade).
Confirme `pytest tests/unit/infrastructure/adapters/test_vllm_generator.py -v` e
`lint-imports`.
~~~

---

## TAREFA-015 — PromptRegistry

**Épico:** E2 — Adapters de Avaliação · **Skills:** python-engineer, rag-engineer
**Prioridade:** P0 · **Tamanho:** S
**Dependências:** TAREFA-001 (repo bootstrap) — M0
**ADRs:** §11.2 (campo `prompt_version`) · **Camadas:** infrastructure/prompts

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica. §9.5 (auditabilidade do juiz),
§11.2 (campo prompt_version no schema). Skills: python-engineer, rag-engineer.
Esta tarefa é pré-requisito de TAREFA-016 (PrometheusJudgeAdapter).

TAREFA: TAREFA-015 — implementar o `PromptRegistry` e os templates da rubrica
biomédica em `src/inteligenciomica_eval/infrastructure/prompts/`.

ESPECIFICAÇÃO:
- Diretório `src/inteligenciomica_eval/infrastructure/prompts/` com:
  - `registry.py` — classe `PromptRegistry`
  - `biomed_rubric.j2` — template Jinja2 da rubrica biomédica (Camada 2)
  - `ragas_system.j2` — template opcional de system prompt para as chamadas RAGAS
    (pode ser vazio em M1, mas o arquivo deve existir para registro de versão)
- `PromptRegistry`:
  - Usa `jinja2.Environment(loader=jinja2.PackageLoader("inteligenciomica_eval",
    "infrastructure/prompts"), autoescape=False)`.
  - Método `render_biomed_rubric(*, question: str, ground_truth: str,
    generated_answer: str, contexts: tuple[str, ...]) -> str`:
    renderiza `biomed_rubric.j2` com os argumentos fornecidos.
  - Propriedade `prompt_version: str`: retorna string de versão capturada uma única vez
    na instanciação via `subprocess.run(["git", "describe", "--tags", "--dirty"],
    capture_output=True, text=True)`. Se git não disponível (CI sem histórico):
    usa variável de ambiente `PROMPT_VERSION` como fallback; se também ausente,
    usa `"unversioned"`. Loga aviso via structlog se `"unversioned"`.
  - O registry é imutável após construção (não recarregar templates em produção).
  - Singleton opcional: expor `get_default_registry() -> PromptRegistry` como
    função de conveniência (sem escopo de módulo global — usa `functools.cache`).
- Template `biomed_rubric.j2` deve implementar a rubrica da §5 do visão_alto_nivel
  (Camada 2 — rubrica biomédica customizada via Prometheus-2/G-Eval): cobrindo os 6
  critérios: correção factual, completude, contradições, alucinação, ressalvas omitidas,
  pertinência biomédica. O template deve:
  - Ter uma seção `<INSTRUÇÕES>` descrevendo o papel do juiz (Prometheus-2).
  - Ter placeholders `{{ question }}`, `{{ ground_truth }}`, `{{ generated_answer }}`,
    `{% for ctx in contexts %}...{% endfor %}` para os contextos recuperados.
  - Solicitar saída **estritamente JSON**: `{"score": <float 0-1>, "feedback": "<str>"}`.
    Isso é crítico para o parsing do PrometheusJudgeAdapter (TAREFA-016).
  - Incluir few-shot com 1 exemplo de score 1.0 e 1 de score 0.2 (construídos sobre
    biomedicina genérica, sem PII ou dados reais de paciente).
- IMPORTANTE: o template é propriedade intelectual crítica; cada alteração deve ser
  commitada com mensagem explícita. O campo `prompt_version` rastreia exatamente qual
  versão foi usada em cada linha do Parquet.

ENTREGÁVEL:
- `src/inteligenciomica_eval/infrastructure/prompts/registry.py`
- `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric.j2`
- `src/inteligenciomica_eval/infrastructure/prompts/ragas_system.j2` (pode ser vazio)
- `tests/unit/infrastructure/prompts/test_prompt_registry.py`
  (testa: renderização inclui question/ground_truth/generated_answer; saída do template
   contém os 6 critérios; `prompt_version` é string não-vazia; fallback "unversioned"
   quando git ausente — mockar subprocess via pytest-mock; output JSON é solicitado)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings Google.
- NÃO usar f-strings para o prompt — usar Jinja2 (versionamento e separação).
- `mypy --strict`; import-linter OK (infrastructure pode importar jinja2, subprocess).
- Template não deve conter PII ou dados clínicos reais.

CRITÉRIO DE ACEITAÇÃO (TAREFA-015):
- `render_biomed_rubric` retorna string contendo `{{ question }}` substituído e
  os 6 critérios da §5.2 (verificado por substring matching no teste).
- `prompt_version` retorna string não-vazia em qualquer ambiente.
- Fallback correto quando git ausente (subprocess mock retorna erro).
- Output JSON solicitado pelo template (teste verifica presença de `"score"` e
  `"feedback"` na instrução de saída do template renderizado).
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-015 + §5 do visão (Camada 2 — rubrica biomédica) +
§9.5 (mitigação de viés do juiz) + §11.2 (campo prompt_version) +
Nota M1 item 6 + skill rag-engineer §16 (anti-pattern: prompt inline no código).

VERIFIQUE, item a item, citando arquivo:linha:
1. Templates são `.j2` em `infrastructure/prompts/` — sem prompt inline em `.py`?
2. `biomed_rubric.j2` cobre TODOS os 6 critérios da Camada 2 (§5 visão)? Tem placeholders corretos
   (`question`, `ground_truth`, `generated_answer`, loop de contextos)?
3. O template solicita saída JSON com campos `score` e `feedback` — obrigatório para
   parsing em TAREFA-016?
4. Few-shot: 1 exemplo bom (score ~1.0) e 1 fraco (~0.2), sem PII?
5. `prompt_version` usa `git describe --tags --dirty` com fallback para env var
   e depois "unversioned"? Loga aviso se unversioned?
6. `get_default_registry()` usa `functools.cache` (não variável global de módulo)?
7. Teste mocka subprocess; verifica 6 critérios; verifica JSON na saída?
8. `mypy --strict`; `lint-imports`; `ruff` OK?

SAÍDA: PASS/FAIL + tabela (critério | arquivo:linha | gravidade).
ATENÇÃO: liste explicitamente quais dos 6 critérios biomédicos estão no template
e quais (se houver) estão faltando — bloqueia se faltar algum.
~~~

---

## TAREFA-016 — PrometheusJudgeAdapter

**Épico:** E2 — Adapters de Avaliação · **Skills:** ml-engineer, python-engineer
**Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-015 (PromptRegistry), TAREFA-005 (ports), TAREFA-010 (config)
**ADRs:** ADR-003 (DeterminismRegime.JUDGE), §9.2 (VLLM_BATCH_INVARIANT), §9.3 (vllm-judge)
**Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica. §9.1–9.5 (Prometheus-2 8x7B como
juiz determinístico), §5.1 (RubricJudgePort). Skills: ml-engineer, python-engineer.
Depende de TAREFA-015 (PromptRegistry existe). TAREFA-014 serve de referência de
padrão para clientes vLLM.

TAREFA: TAREFA-016 — implementar `PrometheusJudgeAdapter` em
`src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py`.

ESPECIFICAÇÃO:
- Implementa `RubricJudgePort` (§5.1):
    `score(self, sample: EvaluationSample) -> RubricResult`
  onde `RubricResult(score: float, feedback: str)`.
  **Atenção:** o método é `.score()` — não `.judge()` (§5.1 é autoritativo;
  M2 Nota item 1 confirma a padronização).
- Usa `openai.AsyncOpenAI(base_url=judge_url, api_key="EMPTY")` apontando para
  `http://vllm-judge:8001/v1` (configurado via pydantic-settings, não hardcoded).
- Constrói o prompt via `PromptRegistry.render_biomed_rubric(...)` (injetado no
  construtor — não instanciado internamente).
- Parâmetros de chamada ao juiz: `temperature=0.0`, `seed=42` (ou qualquer constante
  fixa — o juiz é determinístico por `VLLM_BATCH_INVARIANT=1` no servidor, mas
  setamos seed para extra garantia). `model="prometheus-eval/prometheus-8x7b-v2.0"`.
- Campo `batch_invariant=True` — SEMPRE. Documentar que este adapter representa
  chamadas ao vllm-judge determinístico (ADR-003, DeterminismRegime.JUDGE).
- Parsing da resposta (crítico — §12, risco "NaN frequente"):
  - O juiz deve retornar JSON: `{"score": <float>, "feedback": "<str>"}`.
  - Parsear `json.loads(response.choices[0].message.content)` dentro de try/except.
  - Em falha de parsing: implementar política NaN-or-retry (Nota M1, item 3):
    até 3 tentativas com tenacity, backoff exponencial (1s, 2s, 4s).
    Se todas falharem: `RubricResult(score=float("nan"), feedback="parse_failure")`
    e loga structlog ERROR com o conteúdo bruto (truncado a 500 chars).
  - Em servidor indisponível (connection error, timeout): levanta `JudgeUnavailableError`.
  - Validar `0.0 <= score <= 1.0`; se score for ≠ número em [0,1], tratar como
    parse failure.
- Logging estruturado: `prometheus_judge_completed` com `sample.question_id` (campo
  obrigatório de `EvaluationSample` — ver Nota M1 item 11), score, nan=(score is NaN),
  feedback_len, latency_ms, batch_invariant=True.
- Método `async close()`.

ENTREGÁVEL:
- `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py`
- `tests/unit/infrastructure/adapters/test_prometheus_judge.py`
  (unit: respx.mock; testa: prompt contém question/ground_truth; score parseado;
   NaN retornado em JSON mal-formado após 3 tentativas; JudgeUnavailableError em
   connection error; batch_invariant=True sempre presente no log)
- `tests/fixtures/prometheus_judge_response_valid.json`
  (resposta OpenAI-compatible com content=`{"score": 0.85, "feedback": "..."}`)
- `tests/fixtures/prometheus_judge_response_malformed.json`
  (resposta com content inválido para testar NaN path)

RESTRIÇÕES (DoD §14.2 + Nota M1, itens 1, 2, 3, 4):
- `batch_invariant=True` é constante e não configurável — documente o motivo (ADR-003).
- `temperature=0.0` e seed constante são obrigatórios (§9.3 tabela servidor de juiz).
- Nenhum `print`; logging structurado com campos explícitos.
- `mypy --strict`; `lint-imports`; cobertura ≥ 80%.

CRITÉRIO DE ACEITAÇÃO (TAREFA-016):
- Happy path: `adapter.score(sample)` retorna `RubricResult.score == 0.85` (fixture válida).
- NaN path: 3 tentativas (verificadas via respx call count) + `RubricResult.score == float("nan")`.
- `JudgeUnavailableError` em falha de conexão.
- `temperature=0.0` presente no body da request (verificado via respx).
- `batch_invariant=True` registrado no log (captado via caplog ou structlog captura).
- `isinstance(adapter, RubricJudgePort)` passa (método `.score()` satisfaz o Protocol).
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-016 + §9.1–9.5 + §5.1 (RubricJudgePort) + ADR-003 +
Nota M1 (itens 1, 3, 4) + skill ml-engineer.

VERIFIQUE, item a item, citando arquivo:linha:
1. Assinatura `score(self, sample: EvaluationSample) -> RubricResult` bate com §5.1?
   Método é `.score()` — não `.judge()` (verificar o nome exato no arquivo)?
2. `temperature=0.0` e `seed` constante estão no body da chamada — não variáveis?
3. `batch_invariant=True` é constante (nunca parametrizável) com justificativa ADR-003?
4. Política NaN-or-retry (Nota M1 item 3): 3 tentativas com tenacity ANTES de retornar
   NaN? JSON mal-formado retorna `RubricResult(score=nan, feedback="parse_failure")`
   — NÃO levanta exceção?
5. `JudgeUnavailableError` APENAS em falha de servidor — não em parse failure?
   (este é o ponto mais sutil — confirme)
6. Score validado em [0.0, 1.0]: fora do intervalo é tratado como parse failure?
7. `PromptRegistry` é injetado no construtor (não instanciado internamente)?
8. Logging com `batch_invariant=True` e campos corretos; respx verifica o body da
   request (temperature, seed, model)?
9. `mypy --strict`; cobertura ≥ 80% com ambos os paths (happy + NaN)?

SAÍDA: PASS/FAIL + tabela (critério | arquivo:linha | gravidade).
ATENÇÃO ESPECIAL: item 4 (NaN vs exceção) e item 5 (qual erro levanta) são
bloqueadores diretos se errados — verifique na linha do código, não só nos testes.
~~~

---

## TAREFA-017 — RAGASLayer1Adapter

**Épico:** E2 — Adapters de Avaliação · **Skills:** rag-engineer, ml-engineer, python-engineer
**Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-016 (PrometheusJudgeAdapter — fornece LLM para o RAGAS),
TAREFA-005 (MetricSuitePort), TAREFA-010 (config)
**ADRs:** ADR-007 (NaN), §5.1 (MetricSuitePort), §5.2 Camada 1
**Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica. §5.2 Camada 1 (RAGAS metrics),
§5.1 MetricSuitePort, Nota de M1 item 5 (RAGAS aponta para vllm-judge). Skills:
rag-engineer, ml-engineer, python-engineer. TAREFA-016 concluída.

TAREFA: TAREFA-017 — implementar `RAGASLayer1Adapter` em
`src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py`.

ESPECIFICAÇÃO:
- Implementa `MetricSuitePort` (§5.1):
    `score(self, sample: EvaluationSample) -> Layer1Metrics`
  onde `Layer1Metrics` tem: answer_correctness, answer_similarity, faithfulness,
  context_precision, context_recall, answer_relevancy (todos float, podem ser NaN).
  **Atenção:** o método é `.score()` — não `.compute()` (§5.1 é autoritativo;
  M2 Nota item 1 confirma a padronização).
- RAGAS LLM wrapper (Nota M1, item 5 — CRÍTICO):
  ```python
  from langchain_openai import ChatOpenAI
  from ragas.llms import LangchainLLMWrapper
  llm = LangchainLLMWrapper(
      ChatOpenAI(base_url=judge_url, model=judge_model,
                 temperature=0.0, api_key="EMPTY")
  )
  ```
  Injetar `judge_url` e `judge_model` no construtor (via config). NÃO usar
  `OPENAI_API_KEY` do ambiente — definir `api_key="EMPTY"` explicitamente.
  RAGAS também precisa de um embedding model para `answer_similarity` — usar
  `HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")`
  (leve, disponível em CPU, sem chamada de rede para cada embedding).
- Construção do `SingleTurnSample` RAGAS:
  ```python
  from ragas.dataset_schema import SingleTurnSample
  ragas_sample = SingleTurnSample(
      user_input=sample.question,
      response=sample.generated_answer,
      reference=sample.ground_truth,
      retrieved_contexts=list(sample.contexts),
  )
  ```
- Calcular cada métrica **individualmente** via `await metric.single_turn_ascore(sample)`.
  NÃO usar `ragas.evaluate(dataset)` em batch — usamos uma pergunta de cada vez para
  controlar NaN por métrica.
- Tratamento de NaN (ADR-007): envolver cada `single_turn_ascore` em try/except;
  em qualquer exceção (parse failure, timeout de LLM): logar WARNING e retornar
  `float("nan")` para aquela métrica específica. As outras métricas continuam.
- `batch_invariant` das chamadas internas: True (RAGAS usa o vllm-judge). Logar via
  structlog o campo `judge_url` para rastreabilidade.
- Logging: `ragas_layer1_computed` com todos os 6 valores de métrica (incluindo NaN
  explicitamente como `null` no JSON de log), `nan_fields: list[str]`, `latency_ms`.

ENTREGÁVEL:
- `src/inteligenciomica_eval/infrastructure/adapters/ragas_metrics.py`
- `tests/unit/infrastructure/adapters/test_ragas_layer1.py`
  (unit: respx.mock intercepta chamadas LLM do RAGAS; fixture simula resposta para
   cada métrica; testa: values dentro de [0,1]; NaN retornado quando LLM falha para
   uma métrica; outras métricas não afetadas pelo NaN de uma delas)
- `tests/fixtures/ragas_llm_response_answer_correctness.json` (e outros por métrica)

RESTRIÇÕES (DoD §14.2 + Nota M1, itens 1, 2, 3, 5):
- `from __future__ import annotations`; type hints; docstrings.
- `judge_url` e `judge_model` NUNCA hardcoded — sempre do construtor/config.
- NaN por métrica individual — nunca NaN total se apenas uma métrica falhar.
- `mypy --strict`; import-linter OK; cobertura ≥ 80%.

CRITÉRIO DE ACEITAÇÃO (TAREFA-017):
- Happy path: 6 métricas retornadas, todas em [0,1] (tolância 1e-6).
- Isolamento de NaN: se mock de `faithfulness` falhar, as outras 5 métricas ainda
  chegam com valores numéricos.
- `judge_url` visível no log structurado (`ragas_layer1_computed`).
- `isinstance(adapter, MetricSuitePort)` passa (método `.score()` satisfaz o Protocol).
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-017 + §5.2 Camada 1 + §5.1 (MetricSuitePort) + ADR-007
+ Nota M1 (itens 1, 3, 5) + skill rag-engineer §10 (RAGAS metrics).

VERIFIQUE, item a item, citando arquivo:linha:
1. RAGAS usa `LangchainLLMWrapper(ChatOpenAI(base_url=judge_url, ..., api_key="EMPTY"))`
   — NÃO `OPENAI_API_KEY` do ambiente? judge_url/judge_model vêm do construtor?
2. Métricas calculadas INDIVIDUALMENTE via `single_turn_ascore` — NÃO `ragas.evaluate(dataset)` batch?
   Método do adapter é `.score()` (não `.compute()`) conforme §5.1?
3. `SingleTurnSample` construído com campos corretos (`user_input`, `response`,
   `reference`, `retrieved_contexts`)?
4. NaN por métrica individual: exceção em uma métrica → `float("nan")` só nessa métrica;
   outras continuam? Verificar que não há `return NaN_vector` total em catch de topo.
5. `Layer1Metrics` tem os 6 campos corretos da §5.2? `answer_similarity` E
   `bertscore_f1` NOT incluídos no cálculo de `FinalScore` (double-counting — verificar
   que o adapter os calcula separadamente se incluídos, mas não os retorna misturados)?
6. Logging com todos os 6 valores e `nan_fields`?
7. `mypy --strict`; import-linter OK; cobertura dos dois paths (happy + NaN isolado)?

SAÍDA: PASS/FAIL + tabela (critério | arquivo:linha | gravidade).
ATENÇÃO: item 4 (isolamento de NaN) e item 2 (individual vs batch) são
bloqueadores — confirme na implementação, não só nos testes.
~~~

---

## TAREFA-018 — DeterministicMetricsAdapter

**Épico:** E2 — Adapters de Avaliação · **Skills:** ml-engineer, python-engineer
**Prioridade:** P1 · **Tamanho:** S
**Dependências:** TAREFA-005 (DeterministicMetricPort)
**ADRs:** §5.2 (Camada 1 auxiliares: BERTScore-F1, ROUGE-L) · **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica. §5.2 Camada 1, métricas auxiliares
(`BERTScore-F1` e `ROUGE-L` — determinísticas, sem LLM, *sanity check*). §13.3
(glossário auxiliares). Skills: ml-engineer, python-engineer.

TAREFA: TAREFA-018 — implementar `DeterministicMetricsAdapter` em
`src/inteligenciomica_eval/infrastructure/adapters/deterministic_metrics.py`.

ESPECIFICAÇÃO:
- Implementa `DeterministicMetricPort` (§5.1), com assinatura exata (keyword-only via `*`):
    `score(self, *, answer: str, ground_truth: str) -> AuxMetrics`
  onde `AuxMetrics(bertscore_f1: float, rouge_l: float)`.
  **Atenção:** método é `.score()` (não `.compute_aux()`); parâmetro é `answer` (não
  `generated`) — ambos keyword-only via `*`. M2 Nota item 1 confirma a padronização.
- BERTScore-F1:
  - Usa `bert_score.score([answer], [ground_truth], lang="pt", rescale_with_baseline=True)`.
    (textos são em português biomédico; `lang="pt"` usa modelo `bert-base-multilingual-cased`).
  - Retorna o escalar F1: `float(f1.mean().item())`.
  - É síncrono (BERTScore não tem async nativo; pesa CPU, não GPU, em escala de M1).
  - Em erro: retorna `float("nan")` + loga WARNING. Nunca levanta exceção para o caller.
- ROUGE-L:
  - Usa `rouge_score.rouge_scorer.RougeScorer(["rougeL"], use_stemmer=False)`.
  - Retorna `scores["rougeL"].fmeasure` como float.
  - É síncrono e determinístico — sem LLM.
  - **Nota (Nota M1 item 10):** `rouge_l` é calculado e logado mas NÃO persistido
    no Parquet §5.3 (sem coluna `rouge_l`). O `ParquetStorage` persiste apenas
    `bertscore_f1`. Logar ambos via structlog (`deterministic_metrics_computed`).
- Determinismo garantido: documentar explicitamente que `batch_invariant` é irrelevante
  aqui (não usa LLM nem GPU). Logar `deterministic_metrics_computed` com bertscore_f1,
  rouge_l, latency_ms.
- Lazy-load do modelo BERTScore (somente na primeira chamada) para não atrasar startup.
  Usar `functools.cached_property` no cliente interno.
- NÃO usar async (§ Nota M1 item 1 — adapters síncronos por natureza).

ENTREGÁVEL:
- `src/inteligenciomica_eval/infrastructure/adapters/deterministic_metrics.py`
- `tests/unit/infrastructure/adapters/test_deterministic_metrics.py`
  (unit sem mock: testa com 3 pares golden de texto PT-biomédico em
   `tests/golden/det_metrics_golden.json`:
   `[{"answer": "...", "ground_truth": "...", "bertscore_f1_min": 0.8, "rouge_l_min": 0.5}]`
   (campos `answer`/`ground_truth` conforme §5.1 — não `generated`/`reference`)
   — verifica que os valores estão ACIMA do mínimo esperado, não igualdade exata)
- `tests/golden/det_metrics_golden.json` — 3 casos: par idêntico (F1~1.0), par
  semanticamente similar (F1~0.75), par semanticamente diferente (F1<0.5).

RESTRIÇÕES (DoD §14.2):
- Síncrono; lazy-load; `from __future__ import annotations`; type hints; docstrings.
- Sem NaN propagado para cima — adapter absorve e loga.
- `mypy --strict`; import-linter OK; cobertura ≥ 80%.

CRITÉRIO DE ACEITAÇÃO (TAREFA-018):
- 3 casos golden passam com os thresholds documentados no JSON.
- Par idêntico: `bertscore_f1 > 0.99` e `rouge_l > 0.99`.
- Par diferente: `bertscore_f1 < 0.6`.
- NaN retornado (não exceção) ao chamar `.score(answer=..., ground_truth=...)` com
  `bert_score.score` mockado via pytest-mock para levantar exceção.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-018 + §5.2 (Camada 1 auxiliares) + §13.3 + skill ml-engineer.

VERIFIQUE, item a item, citando arquivo:linha:
1. Usa `bert_score.score` com `lang="pt"` e `rescale_with_baseline=True`?
   Parâmetro é `answer` (não `generated`) — conforme §5.1?
2. BERTScore é lazy-load via `cached_property`? Síncrono (sem async)?
3. ROUGE-L usa `rougeL`, retorna `fmeasure`? Logado via structlog mas NÃO persistido
   no Parquet (§5.3 não tem coluna `rouge_l` — Nota M1 item 10)?
4. Método do adapter é `.score(*, answer, ground_truth)` — não `.compute_aux()`?
   `AuxMetrics` satisfaz `DeterministicMetricPort`?
5. 3 casos golden no JSON com campos `answer`/`ground_truth` (não `generated`/`reference`)?
   Par idêntico > 0.99 em ambas as métricas? Par diferente < 0.6?
6. Logging `deterministic_metrics_computed` com bertscore_f1, rouge_l, latency_ms?
7. `mypy --strict`; `lint-imports`; cobertura ≥ 80%?

SAÍDA: PASS/FAIL + tabela (critério | arquivo:linha | gravidade).
Recompute manualmente ROUGE-L de 1 par do golden (LCS sobre tokens, fórmula
F = 2PR/(P+R)) e cite o resultado esperado vs. obtido.
~~~

---

## TAREFA-019 — VLLMServerManagerAdapter

**Épico:** E1 — Adapters de Recuperação · **Skills:** python-engineer
**Prioridade:** P1 · **Tamanho:** M
**Dependências:** TAREFA-005 (VLLMServerManagerPort), TAREFA-010 (config)
**ADRs:** §9.3 (comandos de inicialização dos dois vLLMs), Nota M1 item 9
**Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica. §9.3 (dois servidores vLLM com
configurações distintas). Nota M1 item 9 (usa asyncio subprocess, não Docker SDK).
Skills: python-engineer, backend-engineer.

TAREFA: TAREFA-019 — implementar `VLLMServerManagerAdapter` em
`src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py`.

ESPECIFICAÇÃO:
- Implementa `VLLMServerManagerPort` (§5.1) — assinaturas exatas:
    `start(self, model: ModelSpec) -> ServerHandle`
    `wait_healthy(self, handle: ServerHandle, timeout_s: int) -> None`
    `stop(self, handle: ServerHandle) -> None`
  **Atenção:** o port define `wait_healthy()` — não `is_healthy()`. O polling de
  healthcheck é a implementação de `wait_healthy`. Não há `is_healthy()` no port.
- `ServerHandle` (DTO de domínio, frozen dataclass de ports.py): `pid: int`, `url: str`,
  `model: str`, `batch_invariant: bool` (True se juiz, False se gerador).
- `ModelSpec` (DTO de domínio): `model: str`, `port: int`, `quantization: str | None`,
  `tensor_parallel_size: int`, `max_model_len: int`, `extra_env: dict[str, str]`.
  Para o juiz: `extra_env = {"VLLM_BATCH_INVARIANT": "1", "VLLM_ENABLE_V1_MULTIPROCESSING": "0"}`.
  Para os geradores: `extra_env = {}` (sem BATCH_INVARIANT — §9.2.4).
- `start(model: ModelSpec)` — implementação (parâmetro `model`, conforme §5.1 — não `spec`):
  1. Constrói o comando `python -m vllm.entrypoints.openai.api_server ...`
     a partir de `model` (via lista de args, não shell=True).
  2. Lança via `await asyncio.create_subprocess_exec(...)` com `env={**os.environ, **model.extra_env}`.
  3. Retorna `ServerHandle(pid=process.pid, url=f"http://localhost:{model.port}/v1",
     model=model.model, batch_invariant="VLLM_BATCH_INVARIANT" in model.extra_env)`.
  4. Loga `vllm_server_started` com model, port, batch_invariant, pid.
- `wait_healthy(handle: ServerHandle, timeout_s: int) -> None` — implementação do port:
  Polling `GET http://{handle.url.replace("/v1","")}/health` via `httpx.AsyncClient`,
  a cada 2s, até `timeout_s`. Se timeout: mata o processo, levanta `ServerStartTimeoutError`.
- `stop(handle)` — `os.kill(handle.pid, signal.SIGTERM)` + aguarda finalização com
  timeout de 30s; em timeout: `SIGKILL`. Loga `vllm_server_stopped`.
- `async close()` — para todos os handles ainda vivos (rastrear internamente via set).

ENTREGÁVEL:
- `src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py`
- `tests/unit/infrastructure/adapters/test_vllm_server_manager.py`
  (unit: mocka `asyncio.create_subprocess_exec` via pytest-mock; respx.mock para
   `/health` (chamado por `wait_healthy`, não por `start`);
   testa: BATCH_INVARIANT só no juiz (ModelSpec com extra_env correto);
   `ServerStartTimeoutError` em `wait_healthy()` quando /health nunca responde 200;
   stop envia SIGTERM + SIGKILL após timeout;
   `batch_invariant=True` no ServerHandle do juiz, False do gerador;
   `isinstance(adapter, VLLMServerManagerPort)` passa)

RESTRIÇÕES (DoD §14.2 + Nota M1 item 9):
- `shell=False` em subprocess — nunca shell injection.
- `from __future__ import annotations`; type hints; docstrings.
- `mypy --strict`; import-linter OK; cobertura ≥ 80%.

CRITÉRIO DE ACEITAÇÃO (TAREFA-019):
- `ModelSpec` com `extra_env={"VLLM_BATCH_INVARIANT": "1"}` → `handle.batch_invariant=True`.
- `ModelSpec` sem BATCH_INVARIANT → `handle.batch_invariant=False`.
- `wait_healthy(handle, timeout_s=10)` levanta `ServerStartTimeoutError` quando /health
  nunca responde 200 (mockado via respx).
- SIGTERM enviado em `stop(handle)`; SIGKILL após timeout de 30s.
- `isinstance(adapter, VLLMServerManagerPort)` passa (`.start`, `.wait_healthy`, `.stop` presentes).
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-019 + §9.3 (comandos dos dois servidores) + ADR-003 +
Nota M1 item 9 + skill backend-engineer (healthcheck pattern).

VERIFIQUE, item a item, citando arquivo:linha:
1. `create_subprocess_exec` com `shell=False`? `env={**os.environ, **model.extra_env}`
   (parâmetro é `model`, não `spec` — §5.1; não substitui todo env)?
2. `VLLM_BATCH_INVARIANT=1` e `VLLM_ENABLE_V1_MULTIPROCESSING=0` aparecem APENAS
   quando `model.extra_env` os contém — NÃO hardcoded no método `start()`?
3. `ServerHandle.batch_invariant` derivado de `"VLLM_BATCH_INVARIANT" in model.extra_env`?
4. Polling de /health em `wait_healthy()` (não em `start()`) — a cada 2s; levanta
   `ServerStartTimeoutError` (não `TimeoutError` genérico)?
   Não há `is_healthy()` no port — verificar que não foi adicionado como método público?
5. `stop()` usa SIGTERM + espera + SIGKILL em timeout — não SIGKILL direto?
6. Testes mockam subprocess e respx para /health? Verificam `batch_invariant` no handle?
7. `mypy --strict`; `lint-imports`; cobertura ≥ 80%?

SAÍDA: PASS/FAIL + tabela (critério | arquivo:linha | gravidade).
ATENÇÃO: itens 2 e 3 são bloqueadores — a distinção juiz/gerador é a decisão
arquitetural central de §9.2 e deve estar visível no código, não só nos testes.
~~~

---

## TAREFA-020 — AnnotationReaderAdapter

**Épico:** E2 — Adapters de Avaliação · **Skills:** python-engineer
**Prioridade:** P1 · **Tamanho:** S
**Dependências:** TAREFA-005 (AnnotationReaderPort) — M0
**ADRs:** §5.3 (campos `critical_failure_flag`, `critical_failure_note`) · **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica. Camada 3 de avaliação (§5.3
"Anotação humana de falhas críticas"). §5.1 AnnotationReaderPort. Skills: python-engineer.

TAREFA: TAREFA-020 — implementar `AnnotationReaderAdapter` em
`src/inteligenciomica_eval/infrastructure/adapters/annotation_reader.py`.

ESPECIFICAÇÃO:
- Implementa `AnnotationReaderPort` (§5.1) — assinatura exata:
    `read(self, run_id: str) -> list[CriticalAnnotation]`
  onde `CriticalAnnotation(row_id: RowId, flag: int, note: str | None)`.
  Retorna **lista vazia** `[]` se o `run_id` não tiver anotações (Camada 3 é offline e
  parcial). NÃO retorna `None` — contrato é `list[CriticalAnnotation]`.
- Formato do arquivo de anotação: JSONL, uma linha por anotação:
  `{"run_id": "<run_id>", "row_id": "<hex_sha256>", "flag": 0, "note": "opcional"}`.
  O arquivo é criado pelo especialista biomédico fora do sistema (ex.: via
  `ielm-eval annotate`). O adapter apenas lê.
- Construtor: `annotation_file: pathlib.Path`. Carrega o arquivo na construção em
  `dict[str, list[CriticalAnnotation]]` (run_id → lista de anotações). Lança `StorageError`
  se o arquivo existir mas estiver malformado (JSON inválido, campos `run_id`/`row_id`/`flag`
  ausentes).
  Se o arquivo NÃO existir: loga INFO ("annotation file not found, Camada 3 disabled")
  e inicia com dicionário vazio — `read(run_id)` sempre retornará `[]`.
- Validação: `flag ∈ {0, 1}` — `StorageError` na construção se outro valor.
- `RowId` do domínio: o adapter converte `row_id` do JSON para `RowId(value=str)`.
- Método `reload(annotation_file: pathlib.Path | None = None) -> int`:
  recarrega o arquivo em memória; retorna o número total de anotações carregadas.
- É síncrono. Sem async.

ENTREGÁVEL:
- `src/inteligenciomica_eval/infrastructure/adapters/annotation_reader.py`
- `tests/unit/infrastructure/adapters/test_annotation_reader.py`
  (unit: lê JSONL de `tests/fixtures/annotations.jsonl`; testa:
   happy path — `read(run_id)` retorna lista com as anotações do run;
   run_id ausente → lista vazia `[]` (não None, não exceção);
   arquivo ausente → `[]` sem exceção (loga INFO);
   arquivo malformado → `StorageError` na construção;
   flag fora de {0,1} → `StorageError` na construção;
   reload() retorna contagem total de anotações)
- `tests/fixtures/annotations.jsonl` — 3 linhas de exemplo com campos
  `run_id`, `row_id`, `flag`, `note`

RESTRIÇÕES (DoD §14.2):
- Síncrono; `from __future__ import annotations`; type hints; docstrings Google.
- Arquivo ausente = Camada 3 desabilitada (não é erro — é o estado normal em M1).
- `mypy --strict`; import-linter OK; cobertura ≥ 90% (lógica simples).

CRITÉRIO DE ACEITAÇÃO (TAREFA-020):
- `isinstance(adapter, AnnotationReaderPort)` passa (método `.read(run_id)` satisfaz §5.1).
- `read(run_id)` retorna `list[CriticalAnnotation]` (não `None`, não `Optional`) com as
  anotações do run_id fornecido; lista vazia `[]` para run_id inexistente.
- Arquivo ausente: `read(any_run_id)` retorna `[]` sem exceção (loga INFO).
- Arquivo com `flag=2`: `StorageError` na construção (não em `read()`).
- `reload()` retorna contagem total correta após recarregar.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-020 + §5.1 (AnnotationReaderPort) + §5.3 +
skill python-engineer.

VERIFIQUE, item a item, citando arquivo:linha:
1. Assinatura `read(self, run_id: str) -> list[CriticalAnnotation]` — parâmetro é
   `run_id: str` (não `row_id: RowId`), retorno é `list[...]` (não `Optional`)?
   BLOQUEADOR se diferente — §5.1 é autoritativo.
2. `read(run_id)` retorna `[]` (lista vazia — não `None`) quando run_id ausente?
   Arquivo ausente: loga INFO + dicionário vazio — NÃO levanta `StorageError`?
3. Arquivo malformado OU `flag ∉ {0,1}`: levanta `StorageError` NA CONSTRUÇÃO
   (não em `read()`)?
4. `reload()` existe, retorna `int` (contagem total), recarrega o arquivo?
5. É síncrono (sem async, sem threading)?
6. Cobertura ≥ 90%; `mypy --strict`; `lint-imports`?

SAÍDA: PASS/FAIL + tabela (critério | arquivo:linha | gravidade).
~~~

---

## TAREFA-021 — Gate de Integração M1 (pipeline adapter end-to-end)

**Épico:** E1+E2 · **Skills:** test-engineer, python-engineer
**Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-013 a 020 (todos os adapters) + TAREFA-009 (ParquetStorage — M0)
**ADRs:** todos os ADRs anteriores · **Camadas:** tests/integration, tests/e2e

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica. Esta é a tarefa de fechamento de
M1: um teste de integração ponta-a-ponta que exercita TODOS os adapters reais
em sequência, substituindo os fakes de M0. Skills: test-engineer, python-engineer.
Depende de TAREFA-013 a 020.

TAREFA: TAREFA-021 — implementar o Gate de Integração M1 em
`tests/integration/test_m1_pipeline_integration.py` e
`tests/e2e/test_m1_smoke_e2e.py`.

ESPECIFICAÇÃO:

(a) `tests/integration/test_m1_pipeline_integration.py`:

Teste de integração que simula uma execução completa de UMA pergunta pelo pipeline
(retrieval → geração → avaliação L1 + L2 → score final → persistência), usando:
- Qdrant REAL (testcontainers) — `QdrantRetrieverAdapter`
- vLLM MOCKADO via respx — `VLLMGeneratorAdapter` e `PrometheusJudgeAdapter`
- RAGAS com LLM MOCKADO (respx) + Qdrant REAL — `RAGASLayer1Adapter`
- BERTScore e ROUGE reais (CPU) — `DeterministicMetricsAdapter`
- Anotação de fixture (arquivo JSONL) — `AnnotationReaderAdapter`
- `FinalScoreCalculator` do domínio (M0)
- `ParquetStorage` (M0)

Fluxo do teste:
1. Criar fixture Qdrant com 5 chunks para a pergunta de teste.
2. Buscar top-3 via `QdrantRetrieverAdapter`.
3. Gerar resposta via `VLLMGeneratorAdapter` (respx retorna texto fixo).
4. Computar métricas L1 via `RAGASLayer1Adapter` (respx para LLM; Qdrant real).
5. Computar métricas L2 via `PrometheusJudgeAdapter` (respx retorna JSON `{"score": 0.78, "feedback": "..."}`).
6. Computar métricas aux via `DeterministicMetricsAdapter`.
7. Calcular `FinalScore` via `FinalScoreCalculator`.
8. Construir `EvaluationResult` com `DeterminismRegime.GENERATOR` para a resposta
   e `DeterminismRegime.JUDGE` para as métricas de juiz.
9. Persistir via `ParquetStorage`.
10. Ler de volta via `ParquetStorage.read_by_run_id(run_id)` e verificar que a linha
    foi gravada com os campos corretos (não NaN no score final, question_id correto,
    `batch_invariant` dos geradores = False).

Critérios de asserção:
- `final_score` não é NaN (pelo menos a resposta mockada deve produzir scores parseáveis).
- `generated_answer` bate com o texto fixo retornado pelo respx.
- Arquivo Parquet contém exatamente 1 linha com o `row_id` correto.
- `batch_invariant` = False na linha do Parquet (é chamada de gerador).

(b) `tests/e2e/test_m1_smoke_e2e.py`:

Smoke test mínimo que verifica que todos os adapters são instanciáveis com config
real (mesmo sem servidores rodando), que os imports não quebram, e que as factories
de cada adapter produzem objetos que satisfazem o Protocol correspondente
(`isinstance` com runtime_checkable).

Marcador `@pytest.mark.e2e` e `@pytest.mark.skipif(not os.getenv("E2E_ENABLED"), ...)`.

(c) Atualizar `.github/workflows/ci.yml`:
- Adicionar job `integration` que roda `pytest -m integration` com serviço Qdrant
  via `services.qdrant` (image `qdrant/qdrant:v1.9`).
- Job `unit` permanece separado e mais rápido (sem Qdrant).
- Separar coverage: unit + integration reportam para codecov separadamente.

ENTREGÁVEL:
- `tests/integration/test_m1_pipeline_integration.py`
- `tests/e2e/test_m1_smoke_e2e.py`
- `.github/workflows/ci.yml` (atualizado com job integration + serviço Qdrant)
- `tests/fixtures/integration_question.json` — 1 pergunta com ground_truth e 5 chunks

RESTRIÇÕES (DoD §14.2 + test-engineer §9):
- Container Qdrant com scope="session"; dados com scope="function".
- Testes não dependem de ordem de execução (`pytest --randomly` deve passar).
- Cobertura end-to-end: este teste deve fazer a cobertura de infrastructure/adapters
  subir (não é substituto dos unit tests de cada adapter).

CRITÉRIO DE ACEITAÇÃO (TAREFA-021 = Gate M1):
- `pytest -m integration` verde localmente (com Docker disponível).
- CI verde no job `integration` (Qdrant como service, respx para vLLM).
- Smoke E2E: todos os adapters instanciáveis; isinstance passa para cada Protocol.
- `final_score` não NaN no Parquet lido de volta.
- Cobertura global não regride abaixo de 85%.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer (skill test-engineer). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-021 + skills test-engineer (§9 containers, §16 checklist) +
todos os ADRs anteriores + Nota M1 (itens 1, 7).

VERIFIQUE, item a item, citando arquivo:linha:
1. Fluxo do teste de integração cobre TODOS os 8 adapters de M1 em sequência?
   (QdrantRetriever → GoldChunkReader → VLLMGenerator → PrometheusJudge →
   RAGASLayer1 → DeterministicMetrics → AnnotationReader → ParquetStorage)
   Nota: `VLLMServerManager` é testado no smoke E2E (não no pipeline de pergunta única).
   `ParquetStorage` é de M0; sua inclusão aqui é como verificação de roundtrip.
2. Qdrant usa `testcontainers` com scope="session" para o container e
   scope="function" para dados? Nenhum dado persiste entre testes?
3. `respx.mock` intercepta TODAS as chamadas HTTP ao vLLM (generator + judge +
   chamadas internas do RAGAS ao LLM)?
4. `final_score` assertado como NÃO NaN; `batch_invariant=False` assertado no Parquet?
5. Linha do Parquet lida de volta (roundtrip) com `row_id` correto?
6. Smoke E2E verifica `isinstance` de cada adapter contra seu Protocol?
   Marcado com `@pytest.mark.e2e` e skipif sem env var?
7. CI atualizado: job `integration` com `services.qdrant` image `qdrant/qdrant:v1.9`?
   Cobertura não regride abaixo de 85%?
8. Testes paralelizáveis (`pytest --randomly` não quebra — sem estado global compartilhado)?

SAÍDA: PASS/FAIL + tabela (critério | arquivo:linha | gravidade).
Confirme execução local de
`pytest -m "integration" --cov=src --cov-report=term-missing -v tests/integration/`
e liste output de cobertura de `infrastructure/adapters/`.

GATE M1: PASS nesta tarefa + PASS nas TAREFA-013 a 020 = milestone M1 concluído.
Verificação final: todos os 8 adapters satisfazem seus Protocol (isinstance + mypy).
Pré-requisito validado: PR retroativo de ports async (Nota M1 item 1) mergeado em M0.
~~~

---

## Apêndice — Ordem de execução e gate de M1 (013–021)

### Sub-DAG de M1

```
Pré-requisito: M0 gate verde (001–012)
                │
    ┌───────────┼────────────────────────────────────────────────┐
    ▼           ▼                                                 ▼
013            014              015 ──→ 016 ──→ 017              018
(Qdrant        (VLLM            (Prompt  (Judge  (RAGAS           (Determ.
Retriever)     Generator)       Registry) Adapter) Layer1)        Metrics)
    │           │                │        │        │                │
    └───────────┴────────────────┴────────┴────────┴────────────────┤
                                                                    │
                                          019                        │
                                    (VLLMServer                     │
                                     Manager)                       │
                                          │                         │
                                          │     020                 │
                                          │  (Annotation            │
                                          │   Reader)               │
                                          │     │                   │
                                          └─────┴───────────────────▼
                                                                  021
                                                           (Gate M1 —
                                                        Integration E2E)
```

**Caminho crítico:** 015 → 016 → 017 → 021
(PromptRegistry → PrometheusJudge → RAGASLayer1 → Gate)

### Sequência recomendada de PRs

1. **TAREFA-013** e **TAREFA-014** em paralelo (independentes entre si, ambas dependem só de M0).
2. **TAREFA-015** (PromptRegistry) — desbloqueador do caminho crítico.
3. **TAREFA-016** (PrometheusJudge) após 015 + 014 (padrão de cliente vLLM).
4. **TAREFA-017** (RAGASLayer1) após 016.
5. **TAREFA-018** e **TAREFA-019** e **TAREFA-020** em paralelo (podem ir junto com 015–017).
6. **TAREFA-021** (Gate) após todas as anteriores.

### Tarefas paralelizáveis (com time ≥ 2 engenheiros)

- Desenvolvedor A: 013 → 014 → (aguarda 015) → auxilia 017
- Desenvolvedor B: 015 → 016 → 017
- Desenvolvedor C: 018 → 019 → 020 → (aguarda todos) → 021

### Gate de M1

Ao fim de 013–021, o milestone M1 está concluído quando:

- [ ] `mypy --strict src` verde (sem nenhum `# type: ignore` novo não-justificado)
- [ ] `ruff check .` e `ruff format --check .` verdes
- [ ] `lint-imports` verde (contratos de M0 inalterados; infrastructure pode importar third-party)
- [ ] Todos os adapters: `.score()` (não `.compute()` nem `.judge()`) em MetricSuitePort e RubricJudgePort
- [ ] `DeterministicMetricPort`: `.score(*, answer, ground_truth)` (não `.compute_aux(generated, ...)`)
- [ ] `GoldChunkReaderPort`: `.gold_for()` retornando `list[str]` (não `read_gold_chunks` / `tuple`)
- [ ] `AnnotationReaderPort`: `.read(run_id: str) -> list[CriticalAnnotation]` (não `Optional`)
- [ ] `VLLMServerManagerPort`: `.wait_healthy()` presente, `.is_healthy()` ausente do port
- [ ] `GeneratorPort`: `Sequence[Chunk]` + `temperature: float` + todos keyword-only
- [ ] `pytest -m unit` verde com cobertura ≥ 85% global, ≥ 80% em cada adapter
- [ ] `pytest -m integration` verde (Qdrant container, respx mocks)
- [ ] Smoke E2E: todos os `isinstance(adapter, Port)` passam
- [ ] Parquet roundtrip do teste de integração: `final_score` não NaN, `batch_invariant` correto
- [ ] `prompt_version` não é "unversioned" em nenhum cenário de teste com git disponível
- [ ] NaN-or-retry documentado no CHANGELOG do PR da TAREFA-016 (referenciando ADR-007)

> **Observação para M2 (Use Cases de Aplicação):**
> Com M1 concluído, os adapters reais estão disponíveis. M2 implementa os use cases
> de aplicação (`RunExperimentUseCase`, `ComputeMetricsUseCase`, `AggregateResultsUseCase`)
> que orquestram os adapters de M1 + os serviços de domínio de M0, completando o
> pipeline ponta-a-ponta da Rodada 1 (`ielm-eval run --config round1.yaml`).
> A `VLLMServerManagerAdapter` (TAREFA-019) será integrada ao use case de orquestração
> em M2 para start/stop automático dos servidores antes e após a rodada experimental.
