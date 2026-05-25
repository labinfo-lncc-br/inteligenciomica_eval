# Prompts M1 — TAREFA-013 a 021 (Claude Code ↔ ChatGPT Codex)

**Milestone:** M1 — Adapters de Infraestrutura (implementações reais substituindo os fakes de M0) **Documento de referência:** `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1) \+ `visao_alto_nivel_validacao_inteligenciomica.md` (v1.0, §§ 5, 9, 10, 11\) **Formato:** para cada tarefa, um **Prompt A (implementação — Claude Code)** e um **Prompt B (verificação — ChatGPT Codex)**, conforme seção 16 do documento de arquitetura. **Uso:** o desenvolvedor sênior cola o Prompt A no Claude Code; ao receber o PR, cola o Prompt B no Codex; arbitra PASS/FAIL; itera até PASS; só então parte para a próxima tarefa **respeitando o DAG do Apêndice**.

Os prompts abaixo são autocontidos, mas pressupõem que **o arquivo de arquitetura está disponível no contexto/repo** de ambos os agentes e que as **skills do projeto** (`python-clean-architecture`, `test-engineer`, `python-engineer`, `ml-engineer`, `rag-engineer`, `backend-engineer`) estão ativas no Claude Code.

**Pré-requisito:** gate parcial de M0 verde (TAREFA-001 a 012: domínio completo, fakes tipados, config/YAML, ParquetStorage, CI verde com `mypy --strict` \+ `lint-imports`).

---

## Nota de operacionalização — Decisões que M1 fixa

As decisões abaixo são complementares às de M0 e valem para todos os prompts de M1. Devem ser confirmadas pela equipe (vetáveis antes da TAREFA-013).

### 1\. Async-first em todos os adapters I/O-bound

Todos os adapters que realizam chamadas de rede (`QdrantRetrieverAdapter`, `VLLMGeneratorAdapter`, `PrometheusJudgeAdapter`, `RAGASLayer1Adapter`, `VLLMServerManagerAdapter`) usam `async/await` \+ `httpx.AsyncClient` ou o cliente assíncrono nativo da biblioteca (ex.: `qdrant_client.AsyncQdrantClient`). Os testes de integração usam `pytest-asyncio` com `asyncio_mode = "auto"` (configurado no M0) e `respx` para mockar chamadas HTTP ao vLLM. Adapters síncronos por natureza (BERTScore, ROUGE-L, `AnnotationReaderAdapter`) permanecem síncronos — não envolva em `asyncio.to_thread` sem necessidade mensurável.

### 2\. Pydantic exclusivamente na fronteira de infraestrutura

Respostas HTTP de vLLM (OpenAI-compatible) e de Qdrant são deserializadas em Pydantic models **internas ao adapter** (nunca expostas ao domínio). O adapter converte essas models para DTOs de domínio (definidos em `domain/ports.py`, frozen dataclasses puras) antes de retornar. Isso mantém a regra de dependência (ADR-001): `domain/` nunca importa Pydantic, `infrastructure/` pode.

### 3\. Política NaN-or-retry (ADR-007) — implementação canônica

Para todos os adapters que chamam o juiz (PrometheusJudge, RAGAS):

tentativa 1 → falha de parsing → loga (structlog, nível WARNING) → retry

tentativa 2 → falha de parsing → loga → retry

tentativa 3 → falha de parsing → loga (nível ERROR, campo nan\_reason) →

              retorna float("nan") para a métrica afetada (NÃO levanta exceção)

Exceção: se o servidor estiver indisponível (connection refused, timeout de healthcheck), **sim** levanta `JudgeUnavailableError` — esse erro é irrecuperável pelo caller. Retry usa `tenacity.AsyncRetrying(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=4))`.

### 4\. Cliente vLLM via OpenAI SDK (sem litellm em M1)

Ambos os adapters HTTP para vLLM usam:

import openai

client \= openai.AsyncOpenAI(base\_url=url, api\_key="EMPTY")

O vLLM expõe API compatível com OpenAI REST. Usar o SDK oficial evita dependência extra e é mais tipado. `litellm` permanece como opção futura (multi-provider).

### 5\. RAGAS aponta para o `vllm-judge` determinístico

O `RAGASLayer1Adapter` configura RAGAS com:

from langchain\_openai import ChatOpenAI

from ragas.llms import LangchainLLMWrapper

llm \= LangchainLLMWrapper(

    ChatOpenAI(base\_url=judge\_url, model=judge\_model, temperature=0.0, api\_key="EMPTY")

)

ragas.evaluate(..., llm=llm)

Isso garante que as métricas RAGAS que usam LLM internamente (answer\_correctness, faithfulness, context\_precision, context\_recall, answer\_relevancy) chamam o `vllm-judge` determinístico — e **não** o vllm-generator. Sem essa configuração explícita, RAGAS usa a variável de ambiente `OPENAI_API_KEY`, o que é silenciosamente errado.

### 6\. PromptRegistry: templates Jinja2, versionados como código

Os templates de prompt da rubrica biomédica ficam em `src/inteligenciomica_eval/infrastructure/prompts/*.j2`. O `PromptRegistry` carrega esses templates via `jinja2.Environment(loader=PackageLoader(...))`. O campo `prompt_version` no schema (§11.2) é preenchido com `git describe --tags --dirty` capturado na inicialização do registry. **NÃO** usar strings inline de prompt — mudança de prompt \= mudança de arquivo \+ commit rastreável.

### 7\. Testes de integração — estratégia por adapter

| Adapter | Estratégia de teste de integração |
| :---- | :---- |
| `QdrantRetrieverAdapter` | `testcontainers.qdrant` (Docker `qdrant/qdrant:v1.9`) com scope="session"; dados de fixture carregados uma vez |
| `GoldChunkReaderAdapter` | lê arquivo JSONL de fixture em `tests/golden/`; sem container |
| `VLLMGeneratorAdapter` | `respx.mock` sobre `httpx`; fixture de resposta OpenAI-compatible |
| `PrometheusJudgeAdapter` | `respx.mock`; fixture de resposta com score \+ feedback JSON |
| `RAGASLayer1Adapter` | `respx.mock` para chamadas LLM do RAGAS \+ Qdrant real (container) |
| `DeterministicMetricsAdapter` | direto (sem I/O externo); usa corpus golden de 3 pares |
| `VLLMServerManagerAdapter` | mock de `asyncio.create_subprocess_exec` \+ `respx` para `/health` |
| `AnnotationReaderAdapter` | lê arquivo JSONL de fixture em `tests/fixtures/`; sem container |

### 8\. Import-linter em M1 — regras existentes mantidas, sem novos contratos

Os três contratos de M0 permanecem inalterados. `infrastructure/adapters/` pode importar third-party (qdrant\_client, openai, ragas, deepeval, bert\_score, etc.) — isso é intencional e correto para a camada de infraestrutura.

### 9\. VLLMServerManagerAdapter — escopo limitado em M1

Em M1, o `VLLMServerManagerAdapter` gerencia processos locais via `asyncio.create_subprocess_exec`. Não usa Docker SDK (reservado para M3/produção). O método `start()` lança o processo e faz polling no `/health` com timeout configurável (`startup_timeout_s`, default 120 s). O `ServerHandle` retornado permite `stop()` e `is_healthy()`. O adapter é exercitado em testes via mock de subprocess — **não** inicia vLLM real em CI.

---

## TAREFA-013 — QdrantRetrieverAdapter \+ GoldChunkReaderAdapter

**Épico:** E1 — Adapters de Recuperação · **Skills:** rag-engineer, python-engineer **Prioridade:** P0 · **Tamanho:** M **Dependências:** TAREFA-005 (ports), TAREFA-010 (config/YAML) — ambas de M0 **ADRs:** ADR-001 (regra de dependência) · **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica. Arquitetura v1.1, §5.1

(RetrieverPort, GoldChunkReaderPort). Skills ativas: rag-engineer, python-engineer,

python-clean-architecture, test-engineer. M0 concluído: ports e VOs de domínio existem.

TAREFA: TAREFA-013 — implementar dois adapters em

\`src/inteligenciomica\_eval/infrastructure/adapters/qdrant\_retriever.py\`:

(a) \`QdrantRetrieverAdapter\` — implementa \`RetrieverPort\`

(b) \`GoldChunkReaderAdapter\` — implementa \`GoldChunkReaderPort\`

ESPECIFICAÇÃO:

(a) QdrantRetrieverAdapter:

\- Usa \`qdrant\_client.AsyncQdrantClient\` (async obrigatório — ver Nota de M1, item 1).

\- Construtor recebe \`url: str\`, \`collection\_map: Mapping\[str, str\]\` (mapeia

  \`BaseId.value\` → nome da coleção no Qdrant, configurado via YAML da Rodada 1),

  e \`top\_k: int \= 8\`.

\- Implementa \`RetrieverPort.search(base: BaseId, question: str, top\_k: int | None \= None)

  \-\> RetrievalResult\` (assinatura exata do §5.1):

  \- Usa \`top\_k\` do parâmetro se fornecido, senão o default do construtor.

  \- Faz \`async\_client.search(collection\_name=..., query\_vector=..., limit=top\_k)\`.

  \- A query é embedada PELO PRÓPRIO Qdrant (assume que a coleção foi indexada com

    um named vector; o adapter passa o texto da query via \`query\_text\` se o cliente

    suportar, ou usa \`payload\`). \*\*IMPORTANTE:\*\* o adapter NÃO chama um modelo de

    embedding separado — usa a interface de busca por texto do Qdrant, que delega ao

    embedding model configurado na coleção. Documente essa decisão de design.

  \- Converte \`ScoredPoint\[\]\` do Qdrant para \`RetrievalResult\` (DTO de domínio):

    \`retrieved\_chunk\_ids: tuple\[str, ...\]\`, \`retrieved\_chunks\_text: tuple\[str, ...\]\`,

    \`retrieval\_scores: tuple\[float, ...\]\`. O texto do chunk vem de \`point.payload\["text"\]\`.

  \- Levanta \`RetrievalError\` se coleção não existe ou conexão falha.

  \- Logging estruturado (structlog): ao final de cada busca, loga

    \`qdrant\_search\_completed\` com base, top\_k, num\_results, latency\_ms.

\- Implementa também \`RetrieverPort.close()\` — fecha \`async\_client\`.

(b) GoldChunkReaderAdapter:

\- Arquivo JSONL: uma linha por pergunta, formato:

  \`{"question\_id": "q01", "gold\_chunk\_ids": \["chunk\_abc", "chunk\_def", ...\]}\`.

\- Construtor recebe \`gold\_file: pathlib.Path\`.

\- Implementa \`GoldChunkReaderPort.read\_gold\_chunks(question\_id: str) \-\> tuple\[str, ...\]\`:

  \- Carrega o arquivo na construção (lazy OK, mas deve ser idempotente).

  \- Levanta \`StorageError\` se arquivo não existe.

  \- Levanta \`StorageError\` se question\_id não encontrado.

\- É síncrono (sem I/O de rede). Sem async.

ENTREGÁVEL:

\- \`src/inteligenciomica\_eval/infrastructure/adapters/qdrant\_retriever.py\`

\- \`tests/unit/infrastructure/adapters/test\_qdrant\_retriever\_unit.py\`

  (unit: mocka AsyncQdrantClient via pytest-mock; testa mapeamento BaseId→coleção,

   conversão de ScoredPoint→RetrievalResult, propagação de RetrievalError)

\- \`tests/integration/adapters/test\_qdrant\_retriever\_integration.py\`

  (integração: Qdrant real via \`testcontainers.qdrant\`; cria coleção de teste,

   insere 5 chunks, busca e verifica que top\_k é respeitado e scores são float em \[0,1\])

\- \`tests/unit/infrastructure/adapters/test\_gold\_chunk\_reader.py\`

  (unit: lê JSONL de fixture em \`tests/fixtures/gold\_chunks.jsonl\`; testa happy path,

   question\_id ausente, arquivo inexistente)

RESTRIÇÕES (DoD §14.2 \+ Nota de M1):

\- \`from \_\_future\_\_ import annotations\`; type hints; docstrings Google.

\- Adapter NÃO importa de \`domain/application\` — apenas de \`infrastructure\` e third-party.

  Usa DTOs de \`domain/ports.py\` (RetrieverPort, RetrievalResult, etc.) — isso é permitido.

\- \`mypy \--strict\` sem erros; import-linter OK.

\- Logging structurado em cada operação de I/O. Sem \`print\`.

\- testcontainers: scope="session" para o container Qdrant; scope="function" para dados.

CRITÉRIO DE ACEITAÇÃO (TAREFA-013):

\- \`QdrantRetrieverAdapter\` satisfaz \`RetrieverPort\` estruturalmente (isinstance com

  runtime\_checkable passa).

\- Teste de integração: busca de texto retorna top-k documentos com scores não-nulos,

  ordenados por score descrescente.

\- \`GoldChunkReaderAdapter\` retorna exatamente os chunk IDs do arquivo JSONL para a

  question\_id correta; \`StorageError\` nos dois casos de falha.

\- \`mypy \--strict\`, \`ruff\`, \`lint-imports\`, cobertura dos adapters ≥ 80%.

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer (skill code-reviewer \+ rag-engineer). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-013 \+ arquitetura §5.1 (RetrieverPort, GoldChunkReaderPort)

\+ Nota de operacionalização M1 (itens 1, 2, 7, 8\) \+ skill test-engineer §9 (containers).

VERIFIQUE, item a item, citando arquivo:linha:

1\. \`QdrantRetrieverAdapter\` usa \`AsyncQdrantClient\` (não o síncrono)? Construtor recebe

   \`url\`, \`collection\_map\`, \`top\_k\`?

2\. Assinatura de \`search\` bate exatamente com \`RetrieverPort.search\` (§5.1)?

   Retorna \`RetrievalResult\` (DTO de domínio, não dict/lista nua)?

3\. O adapter NÃO chama modelo de embedding separado — usa busca por texto do Qdrant?

   Está documentado no docstring?

4\. \`RetrievalError\` é levantada em falha de conexão/coleção inexistente?

   \`close()\` existe e fecha o cliente?

5\. Logging estruturado presente (structlog, não print) com campos latency\_ms, base,

   num\_results?

6\. \`GoldChunkReaderAdapter\` lê JSONL, é síncrono, levanta \`StorageError\` nos dois

   casos de falha?

7\. Testes de integração usam \`testcontainers.qdrant\` com scope="session" para o

   container e scope="function" para dados? Verifica top\_k e ordenação por score?

8\. Cobertura ≥ 80%? \`mypy \--strict\` \+ \`lint-imports\` passam?

   Pydantic NUNCA aparece em \`domain/\`?

SAÍDA: PASS/FAIL \+ tabela de divergências (critério | arquivo:linha | gravidade).

Confirme execução: \`pytest \-m integration tests/integration/adapters/test\_qdrant\_retriever\_integration.py \-v\`

e \`lint-imports\`.

---

## TAREFA-014 — VLLMGeneratorAdapter

**Épico:** E1 — Adapters de Recuperação · **Skills:** python-engineer, ml-engineer **Prioridade:** P0 · **Tamanho:** M **Dependências:** TAREFA-005 (ports), TAREFA-010 (config) — M0 **ADRs:** ADR-003 (regime de determinismo), §9.2.4 (sem BATCH\_INVARIANT nos geradores) **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica. Arquitetura v1.1, §5.1

(GeneratorPort), §9.3 (servidor vllm-generator). Skills: python-engineer, ml-engineer,

python-clean-architecture. M0 completo.

TAREFA: TAREFA-014 — implementar \`VLLMGeneratorAdapter\` em

\`src/inteligenciomica\_eval/infrastructure/adapters/vllm\_generator.py\`.

ESPECIFICAÇÃO:

\- Implementa \`GeneratorPort\` (§5.1), que tem a assinatura:

    \`generate(llm: LLMId, question: str, contexts: tuple\[str, ...\], \*, seed: int)

    \-\> GenerationOutput\`

\- Usa \`openai.AsyncOpenAI(base\_url=url, api\_key="EMPTY")\` (Nota M1, item 4).

  URL e modelo são passados pelo construtor (configuredos via YAML).

  NÃO usar \`OPENAI\_API\_KEY\` do ambiente — deixar api\_key="EMPTY" explicitamente.

\- Constrói o prompt de geração a partir de (question, contexts):

  prompt\_template: um template simples mas parametrizável, carregado do \`PromptRegistry\`

  (TAREFA-015, ainda não existe). Em M1, aceitar um \`prompt\_fn: Callable\[\[str, tuple\[str,...\]\], str\]\`

  no construtor como injeção de dependência. O default pode ser uma lambda inline mínima

  para permitir testes antes de TAREFA-015.

\- \`temperature=0.1\`, \`seed\` passado diretamente para \`SamplingParams\` do vLLM via o

  campo \`extra\_body={"seed": seed}\` da chamada OpenAI SDK (o vLLM aceita isso).

  \*\*NÃO\*\* ativar \`VLLM\_BATCH\_INVARIANT\` nos geradores — seção §9.2.4.

  Campo \`batch\_invariant=False\` no \`GenerationOutput\`.

\- Registrar em \`GenerationOutput\`: \`text\`, \`tokens\_in\`, \`tokens\_out\`, \`latency\_ms\`,

  \`batch\_invariant=False\` (constante para este adapter).

\- Retry: \`tenacity.AsyncRetrying(stop=stop\_after\_attempt(3),

  wait=wait\_exponential(multiplier=1, min=1, max=8))\` para \`openai.APIConnectionError\`

  e \`openai.RateLimitError\`. Outros erros: propagar como \`GenerationError\`.

\- Logging estruturado: \`vllm\_generation\_completed\` com llm, seed, tokens\_in, tokens\_out,

  latency\_ms, batch\_invariant.

\- Fechar o \`httpx\` client interno do \`AsyncOpenAI\`: implementar \`async close()\`.

ENTREGÁVEL:

\- \`src/inteligenciomica\_eval/infrastructure/adapters/vllm\_generator.py\`

\- \`tests/unit/infrastructure/adapters/test\_vllm\_generator.py\`

  (unit: usa \`respx.mock\` sobre httpx para interceptar chamadas ao endpoint OpenAI-compatible;

   testa: prompt construído corretamente, seed no extra\_body, batch\_invariant=False,

   GenerationError em erro não-retryable, retry em APIConnectionError com máx 3 tentativas)

\- \`tests/fixtures/vllm\_generator\_response.json\`

  (fixture de resposta OpenAI chat completion compatível com vLLM)

RESTRIÇÕES (DoD §14.2 \+ Nota M1, itens 1, 4):

\- Async; \`from \_\_future\_\_ import annotations\`; type hints; docstrings.

\- \`batch\_invariant=False\` SEMPRE — nunca \`True\` neste adapter.

\- Retry com tenacity documentado (max attempts, quais erros são retryable).

\- \`mypy \--strict\`; import-linter OK; cobertura ≥ 80%.

CRITÉRIO DE ACEITAÇÃO (TAREFA-014):

\- \`VLLMGeneratorAdapter\` satisfaz \`GeneratorPort\` (isinstance \+ mypy).

\- Teste com respx: seed aparece em \`extra\_body\` da requisição; latência medida e

  incluída em \`GenerationOutput\`.

\- \`GenerationError\` em falha não-retryable; 3 retries em \`APIConnectionError\`

  (verificado com contador de chamadas interceptadas pelo respx).

\- \`batch\_invariant=False\` em todas as instâncias de \`GenerationOutput\`.

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-014 \+ §5.1 (GeneratorPort) \+ §9.2.4 \+ ADR-003 \+

Nota M1 (itens 1, 3, 4).

VERIFIQUE, item a item, citando arquivo:linha:

1\. Assinatura de \`generate\` bate com \`GeneratorPort\` (§5.1)? Retorna \`GenerationOutput\`?

2\. Usa \`openai.AsyncOpenAI(..., api\_key="EMPTY")\` — sem litellm, sem env var de key?

3\. Seed aparece em \`extra\_body={"seed": seed}\` — NÃO em \`SamplingParams\` separado?

4\. \`batch\_invariant=False\` é constante e nunca parametrizável neste adapter

   (ADR-003 — configuração realista de produção)?

5\. Retry cobre APENAS erros transitórios (\`APIConnectionError\`, \`RateLimitError\`)?

   Outros erros propagam como \`GenerationError\` diretamente?

6\. Logging structurado com campos corretos (llm, seed, tokens\_in, tokens\_out,

   latency\_ms, batch\_invariant=False)?

7\. Testes usam \`respx.mock\` (não \`pytest.mock.patch\`)? Verifica seed no body da request?

   Conta retries?

8\. \`mypy \--strict\` \+ \`lint-imports\`; cobertura ≥ 80%; sem \`print\`.

SAÍDA: PASS/FAIL \+ tabela (critério | arquivo:linha | gravidade).

Confirme \`pytest tests/unit/infrastructure/adapters/test\_vllm\_generator.py \-v\` e

\`lint-imports\`.

---

## TAREFA-015 — PromptRegistry

**Épico:** E2 — Adapters de Avaliação · **Skills:** python-engineer, rag-engineer **Prioridade:** P0 · **Tamanho:** S **Dependências:** TAREFA-001 (repo bootstrap) — M0 **ADRs:** §11.2 (campo `prompt_version`) · **Camadas:** infrastructure/prompts

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica. §9.5 (auditabilidade do juiz),

§11.2 (campo prompt\_version no schema). Skills: python-engineer, rag-engineer.

Esta tarefa é pré-requisito de TAREFA-016 (PrometheusJudgeAdapter).

TAREFA: TAREFA-015 — implementar o \`PromptRegistry\` e os templates da rubrica

biomédica em \`src/inteligenciomica\_eval/infrastructure/prompts/\`.

ESPECIFICAÇÃO:

\- Diretório \`src/inteligenciomica\_eval/infrastructure/prompts/\` com:

  \- \`registry.py\` — classe \`PromptRegistry\`

  \- \`biomed\_rubric.j2\` — template Jinja2 da rubrica biomédica (Camada 2\)

  \- \`ragas\_system.j2\` — template opcional de system prompt para as chamadas RAGAS

    (pode ser vazio em M1, mas o arquivo deve existir para registro de versão)

\- \`PromptRegistry\`:

  \- Usa \`jinja2.Environment(loader=jinja2.PackageLoader("inteligenciomica\_eval",

    "infrastructure/prompts"), autoescape=False)\`.

  \- Método \`render\_biomed\_rubric(\*, question: str, ground\_truth: str,

    generated\_answer: str, contexts: tuple\[str, ...\]) \-\> str\`:

    renderiza \`biomed\_rubric.j2\` com os argumentos fornecidos.

  \- Propriedade \`prompt\_version: str\`: retorna string de versão capturada uma única vez

    na instanciação via \`subprocess.run(\["git", "describe", "--tags", "--dirty"\],

    capture\_output=True, text=True)\`. Se git não disponível (CI sem histórico):

    usa variável de ambiente \`PROMPT\_VERSION\` como fallback; se também ausente,

    usa \`"unversioned"\`. Loga aviso via structlog se \`"unversioned"\`.

  \- O registry é imutável após construção (não recarregar templates em produção).

  \- Singleton opcional: expor \`get\_default\_registry() \-\> PromptRegistry\` como

    função de conveniência (sem escopo de módulo global — usa \`functools.cache\`).

\- Template \`biomed\_rubric.j2\` deve implementar a rubrica da §5.2 do visão\_alto\_nivel:

  cobrindo os 6 critérios: correção factual, completude, contradições, alucinação,

  ressalvas omitidas, pertinência biomédica. O template deve:

  \- Ter uma seção \`\<INSTRUÇÕES\>\` descrevendo o papel do juiz (Prometheus-2).

  \- Ter placeholders \`{{ question }}\`, \`{{ ground\_truth }}\`, \`{{ generated\_answer }}\`,

    \`{% for ctx in contexts %}...{% endfor %}\` para os contextos recuperados.

  \- Solicitar saída \*\*estritamente JSON\*\*: \`{"score": \<float 0-1\>, "feedback": "\<str\>"}\`.

    Isso é crítico para o parsing do PrometheusJudgeAdapter (TAREFA-016).

  \- Incluir few-shot com 1 exemplo de score 1.0 e 1 de score 0.2 (construídos sobre

    biomedicina genérica, sem PII ou dados reais de paciente).

\- IMPORTANTE: o template é propriedade intelectual crítica; cada alteração deve ser

  commitada com mensagem explícita. O campo \`prompt\_version\` rastreia exatamente qual

  versão foi usada em cada linha do Parquet.

ENTREGÁVEL:

\- \`src/inteligenciomica\_eval/infrastructure/prompts/registry.py\`

\- \`src/inteligenciomica\_eval/infrastructure/prompts/biomed\_rubric.j2\`

\- \`src/inteligenciomica\_eval/infrastructure/prompts/ragas\_system.j2\` (pode ser vazio)

\- \`tests/unit/infrastructure/prompts/test\_prompt\_registry.py\`

  (testa: renderização inclui question/ground\_truth/generated\_answer; saída do template

   contém os 6 critérios; \`prompt\_version\` é string não-vazia; fallback "unversioned"

   quando git ausente — mockar subprocess via pytest-mock; output JSON é solicitado)

RESTRIÇÕES (DoD §14.2):

\- \`from \_\_future\_\_ import annotations\`; type hints; docstrings Google.

\- NÃO usar f-strings para o prompt — usar Jinja2 (versionamento e separação).

\- \`mypy \--strict\`; import-linter OK (infrastructure pode importar jinja2, subprocess).

\- Template não deve conter PII ou dados clínicos reais.

CRITÉRIO DE ACEITAÇÃO (TAREFA-015):

\- \`render\_biomed\_rubric\` retorna string contendo \`{{ question }}\` substituído e

  os 6 critérios da §5.2 (verificado por substring matching no teste).

\- \`prompt\_version\` retorna string não-vazia em qualquer ambiente.

\- Fallback correto quando git ausente (subprocess mock retorna erro).

\- Output JSON solicitado pelo template (teste verifica presença de \`"score"\` e

  \`"feedback"\` na instrução de saída do template renderizado).

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-015 \+ §5.2 (Camada 2 rubrica) \+ §9.5 \+ §11.2 \+

Nota M1 item 6 \+ skill rag-engineer §16 (anti-pattern: prompt inline no código).

VERIFIQUE, item a item, citando arquivo:linha:

1\. Templates são \`.j2\` em \`infrastructure/prompts/\` — sem prompt inline em \`.py\`?

2\. \`biomed\_rubric.j2\` cobre TODOS os 6 critérios da §5.2? Tem placeholders corretos

   (\`question\`, \`ground\_truth\`, \`generated\_answer\`, loop de contextos)?

3\. O template solicita saída JSON com campos \`score\` e \`feedback\` — obrigatório para

   parsing em TAREFA-016?

4\. Few-shot: 1 exemplo bom (score \~1.0) e 1 fraco (\~0.2), sem PII?

5\. \`prompt\_version\` usa \`git describe \--tags \--dirty\` com fallback para env var

   e depois "unversioned"? Loga aviso se unversioned?

6\. \`get\_default\_registry()\` usa \`functools.cache\` (não variável global de módulo)?

7\. Teste mocka subprocess; verifica 6 critérios; verifica JSON na saída?

8\. \`mypy \--strict\`; \`lint-imports\`; \`ruff\` OK?

SAÍDA: PASS/FAIL \+ tabela (critério | arquivo:linha | gravidade).

ATENÇÃO: liste explicitamente quais dos 6 critérios biomédicos estão no template

e quais (se houver) estão faltando — bloqueia se faltar algum.

---

## TAREFA-016 — PrometheusJudgeAdapter

**Épico:** E2 — Adapters de Avaliação · **Skills:** ml-engineer, python-engineer **Prioridade:** P0 · **Tamanho:** M **Dependências:** TAREFA-015 (PromptRegistry), TAREFA-005 (ports), TAREFA-010 (config) **ADRs:** ADR-003 (DeterminismRegime.JUDGE), §9.2 (VLLM\_BATCH\_INVARIANT), §9.3 (vllm-judge) **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica. §9.1–9.5 (Prometheus-2 8x7B como

juiz determinístico), §5.1 (RubricJudgePort). Skills: ml-engineer, python-engineer.

Depende de TAREFA-015 (PromptRegistry existe). TAREFA-014 serve de referência de

padrão para clientes vLLM.

TAREFA: TAREFA-016 — implementar \`PrometheusJudgeAdapter\` em

\`src/inteligenciomica\_eval/infrastructure/adapters/prometheus\_judge.py\`.

ESPECIFICAÇÃO:

\- Implementa \`RubricJudgePort\` (§5.1):

    \`judge(sample: EvaluationSample) \-\> RubricResult\`

  onde \`RubricResult(score: float, feedback: str)\`.

\- Usa \`openai.AsyncOpenAI(base\_url=judge\_url, api\_key="EMPTY")\` apontando para

  \`http://vllm-judge:8001/v1\` (configurado via pydantic-settings, não hardcoded).

\- Constrói o prompt via \`PromptRegistry.render\_biomed\_rubric(...)\` (injetado no

  construtor — não instanciado internamente).

\- Parâmetros de chamada ao juiz: \`temperature=0.0\`, \`seed=42\` (ou qualquer constante

  fixa — o juiz é determinístico por \`VLLM\_BATCH\_INVARIANT=1\` no servidor, mas

  setamos seed para extra garantia). \`model="prometheus-eval/prometheus-8x7b-v2.0"\`.

\- Campo \`batch\_invariant=True\` — SEMPRE. Documentar que este adapter representa

  chamadas ao vllm-judge determinístico (ADR-003, DeterminismRegime.JUDGE).

\- Parsing da resposta (crítico — §12, risco "NaN frequente"):

  \- O juiz deve retornar JSON: \`{"score": \<float\>, "feedback": "\<str\>"}\`.

  \- Parsear \`json.loads(response.choices\[0\].message.content)\` dentro de try/except.

  \- Em falha de parsing: implementar política NaN-or-retry (Nota M1, item 3):

    até 3 tentativas com tenacity, backoff exponencial (1s, 2s, 4s).

    Se todas falharem: \`RubricResult(score=float("nan"), feedback="parse\_failure")\`

    e loga structlog ERROR com o conteúdo bruto (truncado a 500 chars).

  \- Em servidor indisponível (connection error, timeout): levanta \`JudgeUnavailableError\`.

  \- Validar \`0.0 \<= score \<= 1.0\`; se score for ≠ número em \[0,1\], tratar como

    parse failure.

\- Logging estruturado: \`prometheus\_judge\_completed\` com question\_id (se disponível

  em EvaluationSample), score, nan=(score is NaN), feedback\_len, latency\_ms,

  batch\_invariant=True.

\- Método \`async close()\`.

ENTREGÁVEL:

\- \`src/inteligenciomica\_eval/infrastructure/adapters/prometheus\_judge.py\`

\- \`tests/unit/infrastructure/adapters/test\_prometheus\_judge.py\`

  (unit: respx.mock; testa: prompt contém question/ground\_truth; score parseado;

   NaN retornado em JSON mal-formado após 3 tentativas; JudgeUnavailableError em

   connection error; batch\_invariant=True sempre presente no log)

\- \`tests/fixtures/prometheus\_judge\_response\_valid.json\`

  (resposta OpenAI-compatible com content=\`{"score": 0.85, "feedback": "..."}\`)

\- \`tests/fixtures/prometheus\_judge\_response\_malformed.json\`

  (resposta com content inválido para testar NaN path)

RESTRIÇÕES (DoD §14.2 \+ Nota M1, itens 1, 2, 3, 4):

\- \`batch\_invariant=True\` é constante e não configurável — documente o motivo (ADR-003).

\- \`temperature=0.0\` e seed constante são obrigatórios (§9.3 tabela servidor de juiz).

\- Nenhum \`print\`; logging structurado com campos explícitos.

\- \`mypy \--strict\`; \`lint-imports\`; cobertura ≥ 80%.

CRITÉRIO DE ACEITAÇÃO (TAREFA-016):

\- Happy path: score \`0.85\` parseado de fixture válida; \`RubricResult.score \== 0.85\`.

\- NaN path: 3 tentativas (verificadas via respx call count) \+ \`RubricResult.score \== float("nan")\`.

\- \`JudgeUnavailableError\` em falha de conexão.

\- \`temperature=0.0\` presente no body da request (verificado via respx).

\- \`batch\_invariant=True\` registrado no log (captado via caplog ou structlog captura).

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-016 \+ §9.1–9.5 \+ §5.1 (RubricJudgePort) \+ ADR-003 \+

Nota M1 (itens 1, 3, 4\) \+ skill ml-engineer.

VERIFIQUE, item a item, citando arquivo:linha:

1\. Assinatura \`judge(sample: EvaluationSample) \-\> RubricResult\` bate com §5.1?

2\. \`temperature=0.0\` e \`seed\` constante estão no body da chamada — não variáveis?

3\. \`batch\_invariant=True\` é constante (nunca parametrizável) com justificativa ADR-003?

4\. Política NaN-or-retry (Nota M1 item 3): 3 tentativas com tenacity ANTES de retornar

   NaN? JSON mal-formado retorna \`RubricResult(score=nan, feedback="parse\_failure")\`

   — NÃO levanta exceção?

5\. \`JudgeUnavailableError\` APENAS em falha de servidor — não em parse failure?

   (este é o ponto mais sutil — confirme)

6\. Score validado em \[0.0, 1.0\]: fora do intervalo é tratado como parse failure?

7\. \`PromptRegistry\` é injetado no construtor (não instanciado internamente)?

8\. Logging com \`batch\_invariant=True\` e campos corretos; respx verifica o body da

   request (temperature, seed, model)?

9\. \`mypy \--strict\`; cobertura ≥ 80% com ambos os paths (happy \+ NaN)?

SAÍDA: PASS/FAIL \+ tabela (critério | arquivo:linha | gravidade).

ATENÇÃO ESPECIAL: item 4 (NaN vs exceção) e item 5 (qual erro levanta) são

bloqueadores diretos se errados — verifique na linha do código, não só nos testes.

---

## TAREFA-017 — RAGASLayer1Adapter

**Épico:** E2 — Adapters de Avaliação · **Skills:** rag-engineer, ml-engineer, python-engineer **Prioridade:** P0 · **Tamanho:** M **Dependências:** TAREFA-016 (PrometheusJudgeAdapter — fornece LLM para o RAGAS), TAREFA-005 (MetricSuitePort), TAREFA-010 (config) **ADRs:** ADR-007 (NaN), §5.1 (MetricSuitePort), §5.2 Camada 1 **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica. §5.2 Camada 1 (RAGAS metrics),

§5.1 MetricSuitePort, Nota de M1 item 5 (RAGAS aponta para vllm-judge). Skills:

rag-engineer, ml-engineer, python-engineer. TAREFA-016 concluída.

TAREFA: TAREFA-017 — implementar \`RAGASLayer1Adapter\` em

\`src/inteligenciomica\_eval/infrastructure/adapters/ragas\_metrics.py\`.

ESPECIFICAÇÃO:

\- Implementa \`MetricSuitePort\` (§5.1):

    \`compute(sample: EvaluationSample) \-\> Layer1Metrics\`

  onde \`Layer1Metrics\` tem: answer\_correctness, answer\_similarity, faithfulness,

  context\_precision, context\_recall, answer\_relevancy (todos float, podem ser NaN).

\- RAGAS LLM wrapper (Nota M1, item 5 — CRÍTICO):

  \`\`\`python

  from langchain\_openai import ChatOpenAI

  from ragas.llms import LangchainLLMWrapper

  llm \= LangchainLLMWrapper(

      ChatOpenAI(base\_url=judge\_url, model=judge\_model,

                 temperature=0.0, api\_key="EMPTY")

  )

  \`\`\`

  Injetar \`judge\_url\` e \`judge\_model\` no construtor (via config). NÃO usar

  \`OPENAI\_API\_KEY\` do ambiente — definir \`api\_key="EMPTY"\` explicitamente.

  RAGAS também precisa de um embedding model para \`answer\_similarity\` — usar

  \`HuggingFaceEmbeddings(model\_name="sentence-transformers/all-MiniLM-L6-v2")\`

  (leve, disponível em CPU, sem chamada de rede para cada embedding).

\- Construção do \`SingleTurnSample\` RAGAS:

  \`\`\`python

  from ragas.dataset\_schema import SingleTurnSample

  ragas\_sample \= SingleTurnSample(

      user\_input=sample.question,

      response=sample.generated\_answer,

      reference=sample.ground\_truth,

      retrieved\_contexts=list(sample.contexts),

  )

  \`\`\`

\- Calcular cada métrica \*\*individualmente\*\* via \`await metric.single\_turn\_ascore(sample)\`.

  NÃO usar \`ragas.evaluate(dataset)\` em batch — usamos uma pergunta de cada vez para

  controlar NaN por métrica.

\- Tratamento de NaN (ADR-007): envolver cada \`single\_turn\_ascore\` em try/except;

  em qualquer exceção (parse failure, timeout de LLM): logar WARNING e retornar

  \`float("nan")\` para aquela métrica específica. As outras métricas continuam.

\- \`batch\_invariant\` das chamadas internas: True (RAGAS usa o vllm-judge). Logar via

  structlog o campo \`judge\_url\` para rastreabilidade.

\- Logging: \`ragas\_layer1\_computed\` com todos os 6 valores de métrica (incluindo NaN

  explicitamente como \`null\` no JSON de log), \`nan\_fields: list\[str\]\`, \`latency\_ms\`.

ENTREGÁVEL:

\- \`src/inteligenciomica\_eval/infrastructure/adapters/ragas\_metrics.py\`

\- \`tests/unit/infrastructure/adapters/test\_ragas\_layer1.py\`

  (unit: respx.mock intercepta chamadas LLM do RAGAS; fixture simula resposta para

   cada métrica; testa: values dentro de \[0,1\]; NaN retornado quando LLM falha para

   uma métrica; outras métricas não afetadas pelo NaN de uma delas)

\- \`tests/fixtures/ragas\_llm\_response\_answer\_correctness.json\` (e outros por métrica)

RESTRIÇÕES (DoD §14.2 \+ Nota M1, itens 1, 2, 3, 5):

\- \`from \_\_future\_\_ import annotations\`; type hints; docstrings.

\- \`judge\_url\` e \`judge\_model\` NUNCA hardcoded — sempre do construtor/config.

\- NaN por métrica individual — nunca NaN total se apenas uma métrica falhar.

\- \`mypy \--strict\`; import-linter OK; cobertura ≥ 80%.

CRITÉRIO DE ACEITAÇÃO (TAREFA-017):

\- Happy path: 6 métricas retornadas, todas em \[0,1\] (tolância 1e-6).

\- Isolamento de NaN: se mock de \`faithfulness\` falhar, as outras 5 métricas ainda

  chegam com valores numéricos.

\- \`judge\_url\` visível no log structurado (\`ragas\_layer1\_computed\`).

\- \`MetricSuitePort\` satisfeito estruturalmente (isinstance passa).

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-017 \+ §5.2 Camada 1 \+ §5.1 (MetricSuitePort) \+ ADR-007

\+ Nota M1 (itens 1, 3, 5\) \+ skill rag-engineer §10 (RAGAS metrics).

VERIFIQUE, item a item, citando arquivo:linha:

1\. RAGAS usa \`LangchainLLMWrapper(ChatOpenAI(base\_url=judge\_url, ..., api\_key="EMPTY"))\`

   — NÃO \`OPENAI\_API\_KEY\` do ambiente? judge\_url/judge\_model vêm do construtor?

2\. Métricas calculadas INDIVIDUALMENTE via \`single\_turn\_ascore\` — NÃO \`ragas.evaluate(dataset)\` batch?

3\. \`SingleTurnSample\` construído com campos corretos (\`user\_input\`, \`response\`,

   \`reference\`, \`retrieved\_contexts\`)?

4\. NaN por métrica individual: exceção em uma métrica → \`float("nan")\` só nessa métrica;

   outras continuam? Verificar que não há \`return NaN\_vector\` total em catch de topo.

5\. \`Layer1Metrics\` tem os 6 campos corretos da §5.2? \`answer\_similarity\` E

   \`bertscore\_f1\` NOT incluídos no cálculo de \`FinalScore\` (double-counting — verificar

   que o adapter os calcula separadamente se incluídos, mas não os retorna misturados)?

6\. Logging com todos os 6 valores e \`nan\_fields\`?

7\. \`mypy \--strict\`; import-linter OK; cobertura dos dois paths (happy \+ NaN isolado)?

SAÍDA: PASS/FAIL \+ tabela (critério | arquivo:linha | gravidade).

ATENÇÃO: item 4 (isolamento de NaN) e item 2 (individual vs batch) são

bloqueadores — confirme na implementação, não só nos testes.

---

## TAREFA-018 — DeterministicMetricsAdapter

**Épico:** E2 — Adapters de Avaliação · **Skills:** ml-engineer, python-engineer **Prioridade:** P1 · **Tamanho:** S **Dependências:** TAREFA-005 (DeterministicMetricPort) **ADRs:** §5.2 (Camada 1 auxiliares: BERTScore-F1, ROUGE-L) · **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica. §5.2 Camada 1, métricas auxiliares

(\`BERTScore-F1\` e \`ROUGE-L\` — determinísticas, sem LLM, \*sanity check\*). §13.3

(glossário auxiliares). Skills: ml-engineer, python-engineer.

TAREFA: TAREFA-018 — implementar \`DeterministicMetricsAdapter\` em

\`src/inteligenciomica\_eval/infrastructure/adapters/deterministic\_metrics.py\`.

ESPECIFICAÇÃO:

\- Implementa \`DeterministicMetricPort\` (§5.1):

    \`compute\_aux(generated: str, ground\_truth: str) \-\> AuxMetrics\`

  onde \`AuxMetrics(bertscore\_f1: float, rouge\_l: float)\`.

\- BERTScore-F1:

  \- Usa \`bert\_score.score(\[generated\], \[ground\_truth\], lang="pt", rescale\_with\_baseline=True)\`.

    (textos são em português biomédico; \`lang="pt"\` usa modelo \`bert-base-multilingual-cased\`).

  \- Retorna o escalar F1: \`float(f1.mean().item())\`.

  \- É síncrono (BERTScore não tem async nativo; pesa CPU, não GPU, em escala de M1).

  \- Em erro: retorna \`float("nan")\` \+ loga WARNING. Nunca levanta exceção para o caller.

\- ROUGE-L:

  \- Usa \`rouge\_score.rouge\_scorer.RougeScorer(\["rougeL"\], use\_stemmer=False)\`.

  \- Retorna \`scores\["rougeL"\].fmeasure\` como float.

  \- É síncrono e deterministico — sem LLM.

\- Determinismo garantido: documentar explicitamente que \`batch\_invariant\` é irrelevante

  aqui (não usa LLM nem GPU). Logar \`deterministic\_metrics\_computed\` com bertscore\_f1,

  rouge\_l, latency\_ms.

\- Lazy-load do modelo BERTScore (somente na primeira chamada) para não atrasar startup.

  Usar \`functools.cached\_property\` no cliente interno.

\- NÃO usar async (§ Nota M1 item 1 — adapters síncronos por natureza).

ENTREGÁVEL:

\- \`src/inteligenciomica\_eval/infrastructure/adapters/deterministic\_metrics.py\`

\- \`tests/unit/infrastructure/adapters/test\_deterministic\_metrics.py\`

  (unit sem mock: testa com 3 pares golden de texto PT-biomédico em

   \`tests/golden/det\_metrics\_golden.json\`:

   \`\[{"generated": "...", "reference": "...", "bertscore\_f1\_min": 0.8, "rouge\_l\_min": 0.5}\]\`

   — verifica que os valores estão ACIMA do mínimo esperado, não igualdade exata)

\- \`tests/golden/det\_metrics\_golden.json\` — 3 casos: par idêntico (F1\~1.0), par

  semanticamente similar (F1\~0.75), par semanticamente diferente (F1\<0.5).

RESTRIÇÕES (DoD §14.2):

\- Síncrono; lazy-load; \`from \_\_future\_\_ import annotations\`; type hints; docstrings.

\- Sem NaN propagado para cima — adapter absorve e loga.

\- \`mypy \--strict\`; import-linter OK; cobertura ≥ 80%.

CRITÉRIO DE ACEITAÇÃO (TAREFA-018):

\- 3 casos golden passam com os thresholds documentados no JSON.

\- Par idêntico: \`bertscore\_f1 \> 0.99\` e \`rouge\_l \> 0.99\`.

\- Par diferente: \`bertscore\_f1 \< 0.6\`.

\- NaN retornado (não exceção) em cenário de falha mockado via \`pytest-mock\` em

  \`bert\_score.score\`.

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-018 \+ §5.2 (Camada 1 auxiliares) \+ §13.3 \+ skill ml-engineer.

VERIFIQUE, item a item, citando arquivo:linha:

1\. Usa \`bert\_score.score\` com \`lang="pt"\` e \`rescale\_with\_baseline=True\`?

2\. BERTScore é lazy-load via \`cached\_property\`? Síncrono (sem async)?

3\. ROUGE-L usa \`rougeL\`, retorna \`fmeasure\`?

4\. NaN retornado (não exceção) em falha; \`AuxMetrics\` satisfaz \`DeterministicMetricPort\`?

5\. 3 casos golden no JSON; par idêntico \> 0.99 em ambas as métricas? Par diferente \< 0.6?

6\. Logging \`deterministic\_metrics\_computed\` com bertscore\_f1, rouge\_l, latency\_ms?

7\. \`mypy \--strict\`; \`lint-imports\`; cobertura ≥ 80%?

SAÍDA: PASS/FAIL \+ tabela (critério | arquivo:linha | gravidade).

Recompute manualmente ROUGE-L de 1 par do golden (LCS sobre tokens, fórmula

F \= 2PR/(P+R)) e cite o resultado esperado vs. obtido.

---

## TAREFA-019 — VLLMServerManagerAdapter

**Épico:** E1 — Adapters de Recuperação · **Skills:** python-engineer **Prioridade:** P1 · **Tamanho:** M **Dependências:** TAREFA-005 (VLLMServerManagerPort), TAREFA-010 (config) **ADRs:** §9.3 (comandos de inicialização dos dois vLLMs), Nota M1 item 9 **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica. §9.3 (dois servidores vLLM com

configurações distintas). Nota M1 item 9 (usa asyncio subprocess, não Docker SDK).

Skills: python-engineer, backend-engineer.

TAREFA: TAREFA-019 — implementar \`VLLMServerManagerAdapter\` em

\`src/inteligenciomica\_eval/infrastructure/adapters/vllm\_server\_manager.py\`.

ESPECIFICAÇÃO:

\- Implementa \`VLLMServerManagerPort\` (§5.1):

    \`start(spec: ModelSpec) \-\> ServerHandle\`

    \`stop(handle: ServerHandle) \-\> None\`

    \`is\_healthy(handle: ServerHandle) \-\> bool\`

\- \`ServerHandle\` (DTO de domínio, frozen dataclass de ports.py): \`pid: int\`, \`url: str\`,

  \`model: str\`, \`batch\_invariant: bool\` (True se juiz, False se gerador).

\- \`ModelSpec\` (DTO de domínio): \`model: str\`, \`port: int\`, \`quantization: str | None\`,

  \`tensor\_parallel\_size: int\`, \`max\_model\_len: int\`, \`extra\_env: dict\[str, str\]\`.

  Para o juiz: \`extra\_env \= {"VLLM\_BATCH\_INVARIANT": "1", "VLLM\_ENABLE\_V1\_MULTIPROCESSING": "0"}\`.

  Para os geradores: \`extra\_env \= {}\` (sem BATCH\_INVARIANT — §9.2.4).

\- \`start(spec)\` — implementação:

  1\. Constrói o comando \`python \-m vllm.entrypoints.openai.api\_server ...\`

     a partir de \`spec\` (via lista de args, não shell=True).

  2\. Lança via \`await asyncio.create\_subprocess\_exec(...)\` com \`env={\*\*os.environ, \*\*spec.extra\_env}\`.

  3\. Polling de healthcheck: \`GET http://localhost:{spec.port}/health\` via \`httpx.AsyncClient\`,

     a cada 2s, até \`startup\_timeout\_s\` (default 120s, configurável).

  4\. Se timeout: mata o processo, levanta \`ServerStartTimeoutError\`.

  5\. Retorna \`ServerHandle(pid=process.pid, url=f"http://localhost:{spec.port}/v1",

     model=spec.model, batch\_invariant="VLLM\_BATCH\_INVARIANT" in spec.extra\_env)\`.

  6\. Loga \`vllm\_server\_started\` com model, port, batch\_invariant, pid, startup\_latency\_s.

\- \`stop(handle)\` — \`os.kill(handle.pid, signal.SIGTERM)\` \+ aguarda finalização com

  timeout de 30s; em timeout: \`SIGKILL\`. Loga \`vllm\_server\_stopped\`.

\- \`is\_healthy(handle)\` — faz GET síncrono (ou async) em \`/health\`; retorna bool.

\- \`async close()\` — para todos os handles ainda vivos (rastrear internamente via set).

ENTREGÁVEL:

\- \`src/inteligenciomica\_eval/infrastructure/adapters/vllm\_server\_manager.py\`

\- \`tests/unit/infrastructure/adapters/test\_vllm\_server\_manager.py\`

  (unit: mocka \`asyncio.create\_subprocess\_exec\` via pytest-mock; respx.mock para

   \`/health\`; testa: BATCH\_INVARIANT só no juiz (ModelSpec com extra\_env correto);

   \`ServerStartTimeoutError\` quando /health nunca responde; stop envia SIGTERM;

   \`batch\_invariant=True\` no ServerHandle do juiz, False do gerador)

RESTRIÇÕES (DoD §14.2 \+ Nota M1 item 9):

\- \`shell=False\` em subprocess — nunca shell injection.

\- \`from \_\_future\_\_ import annotations\`; type hints; docstrings.

\- \`mypy \--strict\`; import-linter OK; cobertura ≥ 80%.

CRITÉRIO DE ACEITAÇÃO (TAREFA-019):

\- \`ModelSpec\` com \`extra\_env={"VLLM\_BATCH\_INVARIANT": "1"}\` → \`handle.batch\_invariant=True\`.

\- \`ModelSpec\` sem BATCH\_INVARIANT → \`handle.batch\_invariant=False\`.

\- \`ServerStartTimeoutError\` após polling expirar (mockado com /health nunca 200).

\- SIGTERM enviado em \`stop(handle)\`.

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-019 \+ §9.3 (comandos dos dois servidores) \+ ADR-003 \+

Nota M1 item 9 \+ skill backend-engineer (healthcheck pattern).

VERIFIQUE, item a item, citando arquivo:linha:

1\. \`create\_subprocess\_exec\` com \`shell=False\`? \`env={\*\*os.environ, \*\*spec.extra\_env}\`

   (não substitui todo env)?

2\. \`VLLM\_BATCH\_INVARIANT=1\` e \`VLLM\_ENABLE\_V1\_MULTIPROCESSING=0\` aparecem APENAS

   quando \`spec.extra\_env\` os contém — NÃO hardcoded no método \`start()\`?

3\. \`ServerHandle.batch\_invariant\` derivado de \`"VLLM\_BATCH\_INVARIANT" in spec.extra\_env\`?

4\. Polling de /health a cada 2s com timeout de \`startup\_timeout\_s\`; levanta

   \`ServerStartTimeoutError\` (não \`TimeoutError\` genérico)?

5\. \`stop()\` usa SIGTERM \+ espera \+ SIGKILL em timeout — não SIGKILL direto?

6\. Testes mockam subprocess e respx para /health? Verificam \`batch\_invariant\` no handle?

7\. \`mypy \--strict\`; \`lint-imports\`; cobertura ≥ 80%?

SAÍDA: PASS/FAIL \+ tabela (critério | arquivo:linha | gravidade).

ATENÇÃO: itens 2 e 3 são bloqueadores — a distinção juiz/gerador é a decisão

arquitetural central de §9.2 e deve estar visível no código, não só nos testes.

---

## TAREFA-020 — AnnotationReaderAdapter

**Épico:** E2 — Adapters de Avaliação · **Skills:** python-engineer **Prioridade:** P1 · **Tamanho:** S **Dependências:** TAREFA-005 (AnnotationReaderPort) — M0 **ADRs:** §5.3 (campos `critical_failure_flag`, `critical_failure_note`) · **Camadas:** infrastructure/adapters

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica. Camada 3 de avaliação (§5.3

"Anotação humana de falhas críticas"). §5.1 AnnotationReaderPort. Skills: python-engineer.

TAREFA: TAREFA-020 — implementar \`AnnotationReaderAdapter\` em

\`src/inteligenciomica\_eval/infrastructure/adapters/annotation\_reader.py\`.

ESPECIFICAÇÃO:

\- Implementa \`AnnotationReaderPort\` (§5.1):

    \`read(row\_id: RowId) \-\> CriticalAnnotation | None\`

  onde \`CriticalAnnotation(row\_id: RowId, flag: int, note: str | None)\`.

  Retorna \`None\` se o \`row\_id\` ainda não foi anotado (Camada 3 é offline e parcial).

\- Formato do arquivo de anotação: JSONL, uma linha por anotação:

  \`{"row\_id": "\<hex\_sha256\>", "flag": 0, "note": "opcional"}\`.

  O arquivo é criado pelo especialista biomédico fora do sistema (ex.: via

  \`ielm-eval annotate\`). O adapter apenas lê.

\- Construtor: \`annotation\_file: pathlib.Path\`. Carrega o arquivo na construção em

  \`dict\[str, CriticalAnnotation\]\` (row\_id → anotação). Lança \`StorageError\` se

  o arquivo existir mas estiver malformado (JSON inválido ou campos ausentes).

  Se o arquivo NÃO existir: loga INFO ("annotation file not found, Camada 3 disabled")

  e inicia com dicionário vazio — \`read()\` sempre retornará \`None\`.

\- Validação: \`flag ∈ {0, 1}\` — \`StorageError\` se outro valor.

\- \`RowId\` do domínio (§TAREFA-003): o adapter converte \`str\` do JSON para \`RowId(value=str)\`.

\- Método \`reload(annotation\_file: pathlib.Path | None \= None) \-\> int\`:

  recarrega o arquivo em memória; retorna o número de anotações carregadas.

  Útil quando o especialista adiciona mais anotações durante uma sessão.

\- É síncrono. Sem async.

ENTREGÁVEL:

\- \`src/inteligenciomica\_eval/infrastructure/adapters/annotation\_reader.py\`

\- \`tests/unit/infrastructure/adapters/test\_annotation\_reader.py\`

  (unit: lê JSONL de \`tests/fixtures/annotations.jsonl\`; testa: happy path (flag 0 e 1),

   row\_id ausente → None, arquivo ausente → None sem exceção,

   arquivo malformado → StorageError, flag fora de {0,1} → StorageError,

   reload() atualiza contagem)

\- \`tests/fixtures/annotations.jsonl\` — 3 linhas de exemplo

RESTRIÇÕES (DoD §14.2):

\- Síncrono; \`from \_\_future\_\_ import annotations\`; type hints; docstrings Google.

\- Arquivo ausente \= Camada 3 desabilitada (não é erro — é o estado normal em M1).

\- \`mypy \--strict\`; import-linter OK; cobertura ≥ 90% (lógica simples).

CRITÉRIO DE ACEITAÇÃO (TAREFA-020):

\- \`AnnotationReaderPort\` satisfeito estruturalmente.

\- \`read()\` retorna \`CriticalAnnotation\` para row\_id existente, \`None\` para ausente.

\- Arquivo ausente: \`None\` sem exceção (loga INFO).

\- Arquivo com \`flag=2\`: \`StorageError\` na construção.

\- \`reload()\` retorna contagem correta após recarregar.

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-020 \+ §5.1 (AnnotationReaderPort) \+ §5.3 \+

skill python-engineer.

VERIFIQUE, item a item, citando arquivo:linha:

1\. \`read(row\_id) \-\> CriticalAnnotation | None\` — retorna None (não exceção) quando

   row\_id ausente?

2\. Arquivo ausente: loga INFO \+ dicionário vazio (não levanta StorageError)?

3\. Arquivo malformado OU \`flag ∉ {0,1}\`: levanta \`StorageError\` na construção?

4\. \`reload()\` existe, retorna \`int\` (contagem), recarrega o arquivo?

5\. É síncrono (sem async, sem threading)?

6\. Cobertura ≥ 90%; \`mypy \--strict\`; \`lint-imports\`?

SAÍDA: PASS/FAIL \+ tabela (critério | arquivo:linha | gravidade).

---

## TAREFA-021 — Gate de Integração M1 (pipeline adapter end-to-end)

**Épico:** E1+E2 · **Skills:** test-engineer, python-engineer **Prioridade:** P0 · **Tamanho:** M **Dependências:** TAREFA-013 a 020 (todos os adapters) \+ TAREFA-009 (ParquetStorage — M0) **ADRs:** todos os ADRs anteriores · **Camadas:** tests/integration, tests/e2e

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica. Esta é a tarefa de fechamento de

M1: um teste de integração ponta-a-ponta que exercita TODOS os adapters reais

em sequência, substituindo os fakes de M0. Skills: test-engineer, python-engineer.

Depende de TAREFA-013 a 020\.

TAREFA: TAREFA-021 — implementar o Gate de Integração M1 em

\`tests/integration/test\_m1\_pipeline\_integration.py\` e

\`tests/e2e/test\_m1\_smoke\_e2e.py\`.

ESPECIFICAÇÃO:

(a) \`tests/integration/test\_m1\_pipeline\_integration.py\`:

Teste de integração que simula uma execução completa de UMA pergunta pelo pipeline

(retrieval → geração → avaliação L1 \+ L2 → score final → persistência), usando:

\- Qdrant REAL (testcontainers) — \`QdrantRetrieverAdapter\`

\- vLLM MOCKADO via respx — \`VLLMGeneratorAdapter\` e \`PrometheusJudgeAdapter\`

\- RAGAS com LLM MOCKADO (respx) \+ Qdrant REAL — \`RAGASLayer1Adapter\`

\- BERTScore e ROUGE reais (CPU) — \`DeterministicMetricsAdapter\`

\- Anotação de fixture (arquivo JSONL) — \`AnnotationReaderAdapter\`

\- \`FinalScoreCalculator\` do domínio (M0)

\- \`ParquetStorage\` (M0)

Fluxo do teste:

1\. Criar fixture Qdrant com 5 chunks para a pergunta de teste.

2\. Buscar top-3 via \`QdrantRetrieverAdapter\`.

3\. Gerar resposta via \`VLLMGeneratorAdapter\` (respx retorna texto fixo).

4\. Computar métricas L1 via \`RAGASLayer1Adapter\` (respx para LLM; Qdrant real).

5\. Computar métricas L2 via \`PrometheusJudgeAdapter\` (respx retorna JSON \`{"score": 0.78, "feedback": "..."}\`).

6\. Computar métricas aux via \`DeterministicMetricsAdapter\`.

7\. Calcular \`FinalScore\` via \`FinalScoreCalculator\`.

8\. Construir \`EvaluationResult\` com \`DeterminismRegime.GENERATOR\` para a resposta

   e \`DeterminismRegime.JUDGE\` para as métricas de juiz.

9\. Persistir via \`ParquetStorage\`.

10\. Ler de volta via \`ParquetStorage.read\_by\_run\_id(run\_id)\` e verificar que a linha

    foi gravada com os campos corretos (não NaN no score final, question\_id correto,

    \`batch\_invariant\` dos geradores \= False).

Critérios de asserção:

\- \`final\_score\` não é NaN (pelo menos a resposta mockada deve produzir scores parseáveis).

\- \`generated\_answer\` bate com o texto fixo retornado pelo respx.

\- Arquivo Parquet contém exatamente 1 linha com o \`row\_id\` correto.

\- \`batch\_invariant\` \= False na linha do Parquet (é chamada de gerador).

(b) \`tests/e2e/test\_m1\_smoke\_e2e.py\`:

Smoke test mínimo que verifica que todos os adapters são instanciáveis com config

real (mesmo sem servidores rodando), que os imports não quebram, e que as factories

de cada adapter produzem objetos que satisfazem o Protocol correspondente

(\`isinstance\` com runtime\_checkable).

Marcador \`@pytest.mark.e2e\` e \`@pytest.mark.skipif(not os.getenv("E2E\_ENABLED"), ...)\`.

(c) Atualizar \`.github/workflows/ci.yml\`:

\- Adicionar job \`integration\` que roda \`pytest \-m integration\` com serviço Qdrant

  via \`services.qdrant\` (image \`qdrant/qdrant:v1.9\`).

\- Job \`unit\` permanece separado e mais rápido (sem Qdrant).

\- Separar coverage: unit \+ integration reportam para codecov separadamente.

ENTREGÁVEL:

\- \`tests/integration/test\_m1\_pipeline\_integration.py\`

\- \`tests/e2e/test\_m1\_smoke\_e2e.py\`

\- \`.github/workflows/ci.yml\` (atualizado com job integration \+ serviço Qdrant)

\- \`tests/fixtures/integration\_question.json\` — 1 pergunta com ground\_truth e 5 chunks

RESTRIÇÕES (DoD §14.2 \+ test-engineer §9):

\- Container Qdrant com scope="session"; dados com scope="function".

\- Testes não dependem de ordem de execução (\`pytest \--randomly\` deve passar).

\- Cobertura end-to-end: este teste deve fazer a cobertura de infrastructure/adapters

  subir (não é substituto dos unit tests de cada adapter).

CRITÉRIO DE ACEITAÇÃO (TAREFA-021 \= Gate M1):

\- \`pytest \-m integration\` verde localmente (com Docker disponível).

\- CI verde no job \`integration\` (Qdrant como service, respx para vLLM).

\- Smoke E2E: todos os adapters instanciáveis; isinstance passa para cada Protocol.

\- \`final\_score\` não NaN no Parquet lido de volta.

\- Cobertura global não regride abaixo de 85%.

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer (skill test-engineer). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-021 \+ skills test-engineer (§9 containers, §16 checklist) \+

todos os ADRs anteriores \+ Nota M1 (itens 1, 7).

VERIFIQUE, item a item, citando arquivo:linha:

1\. Fluxo do teste de integração cobre TODOS os 7 adapters de M1 em sequência?

   (QdrantRetriever → VLLMGenerator → RAGASLayer1 → PrometheusJudge →

   DeterministicMetrics → AnnotationReader → ParquetStorage)

2\. Qdrant usa \`testcontainers\` com scope="session" para o container e

   scope="function" para dados? Nenhum dado persiste entre testes?

3\. \`respx.mock\` intercepta TODAS as chamadas HTTP ao vLLM (generator \+ judge \+

   chamadas internas do RAGAS ao LLM)?

4\. \`final\_score\` assertado como NÃO NaN; \`batch\_invariant=False\` assertado no Parquet?

5\. Linha do Parquet lida de volta (roundtrip) com \`row\_id\` correto?

6\. Smoke E2E verifica \`isinstance\` de cada adapter contra seu Protocol?

   Marcado com \`@pytest.mark.e2e\` e skipif sem env var?

7\. CI atualizado: job \`integration\` com \`services.qdrant\` image \`qdrant/qdrant:v1.9\`?

   Cobertura não regride abaixo de 85%?

8\. Testes paralelizáveis (\`pytest \--randomly\` não quebra — sem estado global compartilhado)?

SAÍDA: PASS/FAIL \+ tabela (critério | arquivo:linha | gravidade).

Confirme execução local de

\`pytest \-m "integration" \--cov=src \--cov-report=term-missing \-v tests/integration/\`

e liste output de cobertura de \`infrastructure/adapters/\`.

GATE M1: PASS nesta tarefa \+ PASS nas TAREFA-013 a 020 \= milestone M1 concluído.

---

## Apêndice — Ordem de execução e gate de M1 (013–021)

### Sub-DAG de M1

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

**Caminho crítico:** 015 → 016 → 017 → 021 (PromptRegistry → PrometheusJudge → RAGASLayer1 → Gate)

### Sequência recomendada de PRs

1. **TAREFA-013** e **TAREFA-014** em paralelo (independentes entre si, ambas dependem só de M0).  
2. **TAREFA-015** (PromptRegistry) — desbloqueador do caminho crítico.  
3. **TAREFA-016** (PrometheusJudge) após 015 \+ 014 (padrão de cliente vLLM).  
4. **TAREFA-017** (RAGASLayer1) após 016\.  
5. **TAREFA-018** e **TAREFA-019** e **TAREFA-020** em paralelo (podem ir junto com 015–017).  
6. **TAREFA-021** (Gate) após todas as anteriores.

### Tarefas paralelizáveis (com time ≥ 2 engenheiros)

- Desenvolvedor A: 013 → 014 → (aguarda 015\) → auxilia 017  
- Desenvolvedor B: 015 → 016 → 017  
- Desenvolvedor C: 018 → 019 → 020 → (aguarda todos) → 021

### Gate de M1

Ao fim de 013–021, o milestone M1 está concluído quando:

- [ ] `mypy --strict src` verde (sem nenhum `# type: ignore` novo não-justificado)  
- [ ] `ruff check .` e `ruff format --check .` verdes  
- [ ] `lint-imports` verde (contratos de M0 inalterados; infrastructure pode importar third-party)  
- [ ] `pytest -m unit` verde com cobertura ≥ 85% global, ≥ 80% em cada adapter  
- [ ] `pytest -m integration` verde (Qdrant container, respx mocks)  
- [ ] Smoke E2E: todos os `isinstance(adapter, Port)` passam  
- [ ] Parquet roundtrip do teste de integração: `final_score` não NaN, `batch_invariant` correto  
- [ ] `prompt_version` não é "unversioned" em nenhum cenário de teste com git disponível  
- [ ] NaN-or-retry documentado no CHANGELOG do PR da TAREFA-016 (referenciando ADR-007)

**Observação para M2 (Use Cases de Aplicação):** Com M1 concluído, os adapters reais estão disponíveis. M2 implementa os use cases de aplicação (`RunExperimentUseCase`, `ComputeMetricsUseCase`, `AggregateResultsUseCase`) que orquestram os adapters de M1 \+ os serviços de domínio de M0, completando o pipeline ponta-a-ponta da Rodada 1 (`ielm-eval run --config round1.yaml`). A `VLLMServerManagerAdapter` (TAREFA-019) será integrada ao use case de orquestração em M2 para start/stop automático dos servidores antes e após a rodada experimental.  
