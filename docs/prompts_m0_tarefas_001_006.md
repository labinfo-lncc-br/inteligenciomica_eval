# Prompts M0 — TAREFA-001 a 006 (Claude Code ↔ ChatGPT Codex)

**Milestone:** M0 — Bootstrap e contratos (esqueleto executável com stubs) **Documento de referência:** `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1) **Formato:** para cada tarefa, um **Prompt A (implementação — Claude Code)** e um **Prompt B (verificação — ChatGPT Codex)**, conforme seção 16 do documento de arquitetura. **Uso:** o desenvolvedor sênior cola o Prompt A no Claude Code; ao receber o PR, cola o Prompt B no Codex; arbitra PASS/FAIL; itera até PASS; só então parte para a próxima tarefa **respeitando o DAG do §14.3**.

Os prompts abaixo são autocontidos, mas pressupõem que **o arquivo de arquitetura está disponível no contexto/repo** de ambos os agentes e que as **skills do projeto** (`python-clean-architecture`, `test-engineer`, `python-engineer`, `ml-engineer`) estão ativas no Claude Code.

---

## Nota de operacionalização (decisões que estes prompts fixam)

Duas ambiguidades do documento de arquitetura precisam de uma regra única e estável para M0. Estas decisões valem para todos os prompts a seguir e devem ser confirmadas pela equipe (vetáveis):

1. **O que `import-linter` proíbe no domínio/aplicação.** A frase "domínio não importa third-party" (§8) é operacionalizada como: **`domain` e `application` não importam bibliotecas de I/O/dados** (a lista enumerada na §5.1 \+ as de dados/plot). **`pydantic` e `structlog` são permitidos** em qualquer camada, por serem bibliotecas de *modelagem/observabilidade transversal*, não de I/O. Convenção adicional (revisada, não imposta pelo linter): **serviços de domínio são puros e não logam** — logging fica em `application`/`infrastructure`.  
     
2. **`ResultFrame` é um tipo de domínio, não um `DataFrame`.** Como `pandas`/`polars`/`pyarrow` são proibidos no domínio, `ResultFrame` é um wrapper de domínio sobre `tuple[EvaluationResult, ...]` (sem dependência de dataframes). Os adapters de estatística/armazenamento convertem para `pandas`/`polars` **internamente**. Isso preserva a pureza testável do domínio (RNF5).

Lista canônica de **bibliotecas proibidas em `domain` e `application`** (usada no `.importlinter`): `qdrant_client, openai, litellm, ragas, deepeval, bert_score, rouge_score, pandas, polars, pyarrow, scipy, scikit_posthocs, statsmodels, pymer4, seaborn, matplotlib, plotly, typer`.

---

## TAREFA-001 — Bootstrap do repositório

**Épico:** E0 · **Skill:** python-engineer · **Prioridade:** P0 · **Tamanho:** S **Dependências:** nenhuma (raiz do DAG) · **ADRs:** ADR-001, ADR-008 · **Camadas:** tooling

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica. Arquitetura em

\`arquitetura\_detalhada\_validacao\_inteligenciomica.md\` (v1.1). As skills do projeto

valem como padrão (python-clean-architecture §1, test-engineer §14–15). Esta é a

PRIMEIRA tarefa do milestone M0: criar o esqueleto do repositório.

TAREFA: TAREFA-001 — bootstrap do repositório (pyproject \+ uv \+ ruff \+ mypy strict \+

import-linter \+ pre-commit \+ CI), com layout src e CLI mínima.

ESPECIFICAÇÃO:

\- Layout src conforme §8 do documento: pacote \`src/inteligenciomica\_eval/\` com os

  diretórios vazios (com \_\_init\_\_.py) \`domain/\`, \`domain/services/\`, \`application/\`,

  \`infrastructure/adapters/\`, \`infrastructure/repositories/\`, \`infrastructure/prompts/\`,

  \`infrastructure/config/\`, \`visualization/\`, e \`cli.py\`. Diretório \`tests/\` espelhando

  (\`unit/\`, \`integration/\`, \`e2e/\`, \`fakes/\`, \`factories/\`, \`golden/\`) \+ \`conftest.py\`.

  Diretório \`config/\` e \`docs/adr/\`.

\- \`pyproject.toml\`:

  \- Python 3.11+; build via hatchling ou setuptools; entry point de console

    \`ielm-eval \= "inteligenciomica\_eval.cli:app"\`.

  \- Deps de runtime (pin com placeholders a confirmar): pydantic\>=2, pydantic-settings,

    structlog, typer, rich, pandas, polars, pyarrow.

  \- Deps de dev: pytest, pytest-xdist, pytest-mock, hypothesis, coverage, ruff, mypy,

    import-linter, pre-commit, polyfactory, freezegun, respx.

\- Configuração de ferramentas:

  \- ruff (lint \+ format) com regras sensatas; \`mypy\` em modo STRICT para \`src\`.

  \- coverage com \`branch=true\`, \`source=\["src/inteligenciomica\_eval"\]\`,

    \`fail\_under=85\`, \`show\_missing=true\` (test-engineer §14).

  \- pytest com marcadores registrados: \`unit\`, \`integration\`, \`e2e\`.

\- \`.importlinter\` (ver "Nota de operacionalização" do arquivo de prompts) com TRÊS

  contratos \`forbidden\`:

  (1) \`domain\` NÃO importa \`application\`, \`infrastructure\`, \`cli\` nem as libs de I/O

      da lista canônica;

  (2) \`application\` NÃO importa \`infrastructure\`, \`cli\` nem as libs de I/O da lista;

  (3) \`infrastructure\` NÃO importa \`cli\`.

  root\_package \= inteligenciomica\_eval.

\- \`.pre-commit-config.yaml\`: hooks ruff (lint), ruff-format, mypy.

\- CI \`.github/workflows/ci.yml\` (adaptar test-engineer §15 para uv): passos

  \`uv sync \--frozen\`, \`ruff check .\`, \`ruff format \--check .\`, \`mypy \--strict src\`,

  \`lint-imports\` (import-linter), \`pytest \--cov=src \--cov-report=xml \--cov-fail-under=85 \-n auto\`.

\- \`cli.py\`: app Typer mínimo com \`--help\` funcionando e um comando placeholder

  \`version\` que imprime a versão do pacote. Tratar \`KeyboardInterrupt\` no entrypoint.

\- \`README.md\`: quickstart copy-paste (clone, \`uv sync \--frozen\`, \`uv run ielm-eval \--help\`).

ENTREGÁVEL:

\- pyproject.toml, uv.lock, ruff.toml (ou \[tool.ruff\] no pyproject), mypy.ini (ou \[tool.mypy\]),

  .importlinter, .pre-commit-config.yaml, .github/workflows/ci.yml, README.md

\- src/inteligenciomica\_eval/\*\* (esqueleto com \_\_init\_\_.py) \+ cli.py

\- tests/conftest.py \+ tests/unit/test\_cli\_smoke.py (testa \`ielm-eval version\` e \`--help\`)

RESTRIÇÕES (DoD §14.2):

\- \`from \_\_future\_\_ import annotations\` no topo de todo módulo Python.

\- Type hints em toda API pública; docstrings Google nas funções/classes públicas.

\- \`ruff\`, \`ruff format \--check\`, \`mypy \--strict src\`, \`lint-imports\` e \`pytest\` verdes.

\- Sem segredos no repositório.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-001):

\- \`uv sync \--frozen\` funciona; CI verde em repositório essencialmente vazio;

  pre-commit hooks instaláveis (\`pre-commit install\`) e passando;

  \`uv run ielm-eval \--help\` e \`uv run ielm-eval version\` funcionam.

\- \`lint-imports\` passa com os 3 contratos declarados (mesmo que as camadas estejam vazias).

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer (skill code-reviewer). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-001 \+ \`arquitetura\_detalhada\_validacao\_inteligenciomica.md\`

(§8 estrutura, §14.2 DoD, "Nota de operacionalização" do arquivo de prompts) \+ skill

test-engineer (§14–15).

VERIFIQUE, item a item, citando arquivo:linha:

1\. Layout src bate com §8 (pastas domain/application/infrastructure/cli/visualization \+

   tests espelhando \+ config/ \+ docs/adr/)? \_\_init\_\_.py presentes?

2\. pyproject: Python 3.11+, entry point \`ielm-eval\`, deps de runtime e dev pinadas,

   marcadores pytest registrados?

3\. mypy está em modo STRICT para src? coverage com branch=true e fail\_under=85?

4\. \`.importlinter\` tem EXATAMENTE os 3 contratos forbidden descritos, com a lista

   canônica de libs de I/O proibidas em domain e application? root\_package correto?

5\. CI roda, na ordem: ruff check, ruff format \--check, mypy \--strict, lint-imports,

   pytest com cobertura e \-n auto?

6\. CLI: \`--help\`, comando \`version\`, KeyboardInterrupt tratado? Smoke test cobre isso?

7\. DoD §14.2 integralmente (future annotations, type hints, docstrings, sem segredos)?

SAÍDA: veredito PASS/FAIL \+ tabela de divergências

(critério | arquivo:linha | gravidade {bloqueador|importante|sugestão}).

Sem bloqueadores ⇒ PASS. Liste comandos que rodou (uv sync, lint-imports, pytest) e seus resultados.

---

## TAREFA-002 — Hierarquia de exceções (`domain/errors.py`)

**Épico:** E0 · **Skill:** python-engineer · **Prioridade:** P0 · **Tamanho:** XS **Dependências:** TAREFA-001 · **ADRs:** — (governa ADR-007 a jusante) · **Camadas:** domain

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §9 "Estratégia de

exceções"). Padrão: python-clean-architecture §5 (hierarquia específica de domínio,

nunca \`Exception\` cru). Depende de TAREFA-001 (repo já existe).

TAREFA: TAREFA-002 — criar a hierarquia de exceções de domínio em

\`src/inteligenciomica\_eval/domain/errors.py\`.

ESPECIFICAÇÃO:

\- Classe base \`InteligenciomicaEvalError(Exception)\`.

\- Subclasses EXATAMENTE como na §9 do documento, agrupadas por área (com docstring

  curta cada uma):

  \- Domínio/validação: InvalidBaseIdError, InvalidLLMIdError, ScoreOutOfRangeError,

    WeightsDoNotSumToOneError

  \- Configuração: ConfigValidationError, ModelNotInRegistryError

  \- Adapters/I/O: RetrievalError, GenerationError, JudgeUnavailableError,

    LLMOutputParseError, MetricComputationError, StorageError

  \- Orquestração de servidores: ServerStartTimeoutError, ModelSwitchError

  \- Estatística: InsufficientSampleError

\- Todas herdam (direta ou transitivamente) de \`InteligenciomicaEvalError\`.

\- Mensagens acionáveis; NÃO vazar segredos. Sem dependência externa (stdlib apenas).

ENTREGÁVEL:

\- src/inteligenciomica\_eval/domain/errors.py

\- tests/unit/domain/test\_errors.py

RESTRIÇÕES (DoD §14.2):

\- \`from \_\_future\_\_ import annotations\`; docstrings Google; type hints.

\- Nenhum import de I/O/infra (import-linter deve passar — é módulo de domínio).

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-002):

\- Todas as classes da §9 presentes.

\- Teste de hierarquia: cada subclasse \`issubclass(...)\` de \`InteligenciomicaEvalError\`;

  é possível \`raise\`/\`except\` pela base e capturar qualquer subclasse;

  pelo menos um teste verifica que capturar a base pega uma subclasse de cada grupo.

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-002 \+ arquitetura §9 \+ skill python-clean-architecture §5.

VERIFIQUE, item a item, citando arquivo:linha:

1\. Base \`InteligenciomicaEvalError\` existe e TODAS as subclasses da §9 estão presentes,

   sem faltar nem sobrar?

2\. Toda subclasse herda (direta/transitiva) da base? (cheque a cadeia)

3\. Docstrings presentes; mensagens não vazam segredos; só stdlib?

4\. Teste cobre a hierarquia (issubclass) e captura pela base de pelo menos um membro de

   cada grupo?

5\. import-linter passa (módulo de domínio puro)? DoD §14.2?

SAÍDA: PASS/FAIL \+ tabela de divergências (critério | arquivo:linha | gravidade).

Confirme que rodou \`pytest tests/unit/domain/test\_errors.py\` e \`lint-imports\`.

---

## TAREFA-003 — Value Objects e invariantes (`domain/value_objects.py`)

**Épico:** E0 · **Skill:** python-engineer · **Prioridade:** P0 · **Tamanho:** S **Dependências:** TAREFA-001, TAREFA-002 · **ADRs:** ADR-009 (RowId) · **Camadas:** domain

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §4.1, §5.2, §5.3).

Padrão: python-clean-architecture §2 (VOs imutáveis com invariantes validadas em

\_\_post\_init\_\_; exceptions específicas de domínio). Depende de TAREFA-002 (exceções).

TAREFA: TAREFA-003 — criar os Value Objects de domínio em

\`src/inteligenciomica\_eval/domain/value\_objects.py\`, como \`@dataclass(frozen=True)\`,

validando invariantes no \_\_post\_init\_\_ e levantando as exceções de TAREFA-002.

ESPECIFICAÇÃO (VOs):

\- \`BaseId(value: str)\` — válido apenas em {"IDx\_400k", "ID\_230K", "fixed"} (o "fixed"

  é usado pelo Experimento B, §5.3); senão \`InvalidBaseIdError\`.

\- \`LLMId(value: str)\` — string não-vazia e sem espaços; senão \`InvalidLLMIdError\`.

  (A pertinência ao registry NÃO é validada aqui — isso é ModelNotInRegistryError na

  carga de config; mantenha o VO leve.)

\- \`Seed(value: int)\` — inteiro \>= 0; senão \`ScoreOutOfRangeError\` NÃO — crie validação

  simples levantando \`InvalidLLMIdError\`? NÃO. Use ValueError de domínio adequado:

  levante \`InteligenciomicaEvalError\` específica se quiser, ou aceite que Seed só exige

  value \>= 0 (levante um erro de domínio claro — proponha e documente).

\- \`FinalScore(value: float)\` — \`math.isnan(value)\` OU \`0.0 \<= value \<= 1.0\`; senão

  \`ScoreOutOfRangeError\` (ver exemplo no §5.2).

\- \`RankScore(value: float)\` — float finito OU NaN; PODE ser negativo (penalização

  clínica forte, §7.3 do doc-base é desejada); rejeitar apenas \`inf\`/não-float.

\- \`MetricVector\` — container imutável das métricas de Camada 1+2 de uma resposta:

  campos float (cada um pode ser NaN): answer\_correctness, answer\_similarity,

  faithfulness, context\_precision, context\_recall, answer\_relevancy, bertscore\_f1,

  rubric\_biomed\_score. Método utilitário \`nan\_fields() \-\> tuple\[str, ...\]\` que retorna

  os nomes dos campos NaN (alimenta \`metric\_nan\_fields\` no schema, §5.3 / ADR-007).

\- \`RowId(value: str)\` — VO de IDENTIDADE (string hex SHA-256). Inclui classmethod

  \`from\_cell(\*, run\_id, phase, base, llm, seed, question\_id) \-\> RowId\` que computa o

  hash determinístico de (run\_id, phase, base, llm, seed, question\_id) — ADR-009.

  (NOTA: RowId e DeterminismRegime são adicionados a esta tarefa por serem VOs puros

  referenciados por TAREFA-004/005; é pequena extensão consciente da lista da tabela.)

\- \`DeterminismRegime\` — enum {JUDGE, GENERATOR} (§4.1); usado por EvaluationResult.

ENTREGÁVEL:

\- src/inteligenciomica\_eval/domain/value\_objects.py

\- tests/unit/domain/test\_value\_objects.py

RESTRIÇÕES (DoD §14.2):

\- \`from \_\_future\_\_ import annotations\`; frozen dataclasses; docstrings; type hints.

\- Sem libs de I/O (só stdlib; \`math\`, \`hashlib\`, \`dataclasses\`, \`enum\`).

\- Domínio puro e sem logging.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-003):

\- Invariantes validadas em \_\_post\_init\_\_; cada VO tem teste de caso válido \+ caso que

  levanta a exceção correta.

\- Cobertura line+branch \>= 95% deste módulo.

\- Property-based (hypothesis): FinalScore aceita exatamente \[0,1\]∪{NaN} e rejeita o resto;

  RowId.from\_cell é determinístico (mesmos insumos → mesmo hash; insumo diferente → hash

  diferente) — teste de roundtrip/estabilidade.

\- \`nan\_fields()\` retorna exatamente os campos NaN.

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-003 \+ arquitetura §4.1/§5.2/§5.3 \+ ADR-009 \+

skill python-clean-architecture §2 \+ test-engineer §8 (property-based).

VERIFIQUE, item a item, citando arquivo:linha:

1\. Todos os VOs presentes: BaseId, LLMId, Seed, FinalScore, RankScore, MetricVector,

   RowId, DeterminismRegime?

2\. BaseId aceita {IDx\_400k, ID\_230K, fixed} e rejeita o resto com InvalidBaseIdError?

3\. FinalScore aceita \[0,1\]∪{NaN}, rejeita fora disso com ScoreOutOfRangeError?

4\. RankScore permite NEGATIVO e NaN, rejeita inf/não-float? (este é um ponto sutil —

   confirme que não há clamp indevido em \[0,1\])

5\. MetricVector é frozen, campos corretos, \`nan\_fields()\` correto?

6\. RowId.from\_cell é determinístico (SHA-256 de exatamente os 6 campos do ADR-009)?

   Mudar 1 campo muda o hash?

7\. Cobertura \>= 95% line+branch no módulo? Há property-based test?

8\. Domínio puro (só stdlib, sem logging, import-linter OK)? DoD §14.2?

ATENÇÃO: o VO \`Seed\` ficou com escolha de exceção em aberto no prompt de implementação —

verifique que a escolha feita é coerente (erro de domínio específico, mensagem clara) e

sinalize como "importante" se um \`ValueError\`/\`Exception\` genérico foi usado.

SAÍDA: PASS/FAIL \+ tabela de divergências (critério | arquivo:linha | gravidade).

Confirme execução de pytest (com cobertura do módulo) e lint-imports.

---

## TAREFA-004 — Entidades de domínio (`domain/entities.py`)

**Épico:** E0 · **Skill:** python-engineer · **Prioridade:** P0 · **Tamanho:** S **Dependências:** TAREFA-002, TAREFA-003 · **ADRs:** ADR-003 (coerência `batch_invariant`), ADR-009 · **Camadas:** domain

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §4.3 "Agregado raiz",

§4.1, §5.3). Padrão: python-clean-architecture §2 (entidades com identidade e invariantes).

Depende de TAREFA-003 (Value Objects) e TAREFA-002 (exceções).

TAREFA: TAREFA-004 — criar as entidades de domínio em

\`src/inteligenciomica\_eval/domain/entities.py\`: \`Question\`, \`GeneratedAnswer\` e o

agregado raiz \`EvaluationResult\`.

ESPECIFICAÇÃO:

\- \`Question\` (entidade): \`question\_id: str\`, \`text: str\`, \`ground\_truth: str\`.

  Invariantes: ids/textos não-vazios. Imutável (frozen) — as 13 perguntas são fixas.

\- \`GeneratedAnswer\` (entidade): identidade por \`RowId\`. Campos:

  \`row\_id: RowId\`, \`question: Question\`, \`base: BaseId\`, \`llm: LLMId\`, \`seed: Seed\`,

  \`phase: str\` ("A"|"B"), \`generated\_answer: str\`,

  \`retrieved\_chunk\_ids: tuple\[str, ...\]\`, \`retrieved\_chunks\_text: tuple\[str, ...\]\`,

  \`retrieval\_scores: tuple\[float, ...\]\`.

  Invariantes: \`phase ∈ {"A","B"}\`; as três tuplas de retrieval têm o MESMO comprimento

  (senão erro de domínio claro); Experimento B (\`phase=="B"\`) usa \`base \== BaseId("fixed")\`.

\- \`EvaluationResult\` (AGREGADO RAIZ, §4.3): compõe \`GeneratedAnswer\` \+

  \`metrics: MetricVector\` \+ \`final\_score: FinalScore\` \+

  \`determinism\_regime: DeterminismRegime\` \+

  \`critical\_failure\_flag: int | None\` (None \= ainda não anotado; senão 0|1) \+

  \`critical\_failure\_note: str | None\`.

  Invariantes (§4.3):

    \* \`final\_score\` é FinalScore válido (já garantido pelo VO);

    \* \`critical\_failure\_flag ∈ {0,1}\` quando não-None;

    \* COERÊNCIA de determinismo: se as métricas vieram do juiz, \`determinism\_regime\`

      deve ser JUDGE; este invariante é verificado aqui de forma estrutural — exponha

      um método \`assert\_determinism\_coherent()\` ou valide no \_\_post\_init\_\_ que o

      regime é um DeterminismRegime válido (a ligação semântica métrica→regime é

      responsabilidade do use case, mas a entidade NÃO aceita regime ausente/inválido).

  \- Métodos de conveniência PUROS (sem I/O):

      \`is\_failure(threshold: float) \-\> bool\` (final\_score \< threshold, §7.2 FailureRate);

      \`is\_critical\_failure() \-\> bool\` (flag \== 1);

      \`with\_metrics(metrics, final\_score, regime) \-\> EvaluationResult\` (retorna NOVA

       instância — imutabilidade; usado pela passada de julgamento, §5.4);

      \`with\_human\_annotation(flag, note) \-\> EvaluationResult\` (idem; Camada 3, ADR-010).

\- Todas as entidades imutáveis (frozen). Mutação \= nova instância.

ENTREGÁVEL:

\- src/inteligenciomica\_eval/domain/entities.py

\- tests/unit/domain/test\_entities.py

RESTRIÇÕES (DoD §14.2):

\- \`from \_\_future\_\_ import annotations\`; frozen; docstrings Google; type hints.

\- Só stdlib \+ VOs/erros do próprio domínio. Sem logging. import-linter deve passar.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-004):

\- Invariantes do agregado (§4.3) testadas: tuplas de retrieval de tamanhos diferentes

  falham; phase inválida falha; B exige base "fixed"; flag fora de {0,1,None} falha.

\- \`with\_metrics\`/\`with\_human\_annotation\` retornam nova instância sem mutar a original.

\- \`is\_failure\`/\`is\_critical\_failure\` corretos nas bordas (== threshold, flag None vs 0 vs 1).

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-004 \+ arquitetura §4.3/§4.1/§5.3 \+ ADR-003/009 \+

skill python-clean-architecture §2.

VERIFIQUE, item a item, citando arquivo:linha:

1\. Question/GeneratedAnswer/EvaluationResult presentes, frozen, com os campos da spec?

2\. GeneratedAnswer: as 3 tuplas de retrieval têm checagem de comprimento igual?

   phase ∈ {A,B}? B exige base "fixed"?

3\. EvaluationResult é o agregado raiz: compõe GeneratedAnswer \+ MetricVector \+

   FinalScore \+ DeterminismRegime \+ flag/nota humanas (opcionais)?

4\. Invariantes §4.3 presentes (flag ∈ {0,1} quando não-None; regime válido obrigatório;

   coerência de determinismo exposta)?

5\. with\_metrics / with\_human\_annotation retornam NOVA instância (imutabilidade) —

   confirme que não há mutação in-place?

6\. is\_failure usa \< threshold (não \<=)? is\_critical\_failure trata None corretamente?

7\. Domínio puro (sem I/O/logging, import-linter OK)? Cobertura dos ramos de invariante?

   DoD §14.2?

SAÍDA: PASS/FAIL \+ tabela de divergências (critério | arquivo:linha | gravidade).

Confirme execução de pytest do módulo \+ lint-imports.

---

## TAREFA-005 — Ports como `Protocol` (`domain/ports.py`)

**Épico:** E0 · **Skill:** python-engineer · **Prioridade:** P0 · **Tamanho:** S **Dependências:** TAREFA-003, TAREFA-004 · **ADRs:** ADR-001 (regra de dependência), ADR-011 (StatsPort) · **Camadas:** domain

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §5.1 "Ports").

Padrão: python-clean-architecture §2 (ports \= typing.Protocol, estrutural, sem herança

forçada). Depende de TAREFA-003/004 (VOs e entidades existem).

TAREFA: TAREFA-005 — declarar TODOS os ports como \`typing.Protocol\` em

\`src/inteligenciomica\_eval/domain/ports.py\`, mais os DTOs auxiliares de domínio que as

assinaturas exigem (puros, sem libs externas).

ESPECIFICAÇÃO:

\- Reproduza fielmente as assinaturas da §5.1 (use \`@runtime\_checkable\` onde fizer sentido

  para permitir checagem estrutural nos fakes de TAREFA-011):

    RetrieverPort, GeneratorPort, MetricSuitePort, RubricJudgePort,

    DeterministicMetricPort, GoldChunkReaderPort, ResultWriterPort, ResultReaderPort,

    StatsPort, AnnotationReaderPort, VLLMServerManagerPort.

\- DTOs de DOMÍNIO necessários às assinaturas (defina-os como frozen dataclasses puros,

  NÃO Pydantic — Pydantic é para fronteira de adapter, §5.2). Mínimos:

    \`RetrievalResult\` (chunks \+ ids \+ scores), \`Chunk\` (id \+ text \+ score),

    \`GenerationOutput\` (texto \+ usage tokens\_in/out \+ latency\_ms),

    \`EvaluationSample\` (question, ground\_truth, generated\_answer, contexts),

    \`Layer1Metrics\`, \`RubricResult\` (score \+ feedback), \`AuxMetrics\`,

    \`WilcoxonReport\`, \`FriedmanReport\`, \`MLMReport\`, \`CriticalAnnotation\`,

    \`ModelSpec\`, \`ServerHandle\`, \`ResultFrame\` (ver Nota: wrapper sobre

    tuple\[EvaluationResult, ...\], SEM dataframe), \`RowId\` (reusa o de TAREFA-003).

  Para DTOs cujo conteúdo detalhado ainda não é crítico em M0 (ex.: relatórios

  estatísticos), defina a estrutura mínima coerente e documente com docstring que será

  detalhada no milestone que a consome (M4 para StatsPort). NÃO deixe \`Any\` solto: use

  tipos concretos ou TypedDict/dataclass.

\- Regra de dependência (ADR-001): este módulo importa SOMENTE de \`domain\` (entities,

  value\_objects, errors) e stdlib/typing. NADA de infra/third-party de I/O.

ENTREGÁVEL:

\- src/inteligenciomica\_eval/domain/ports.py

\- tests/unit/domain/test\_ports\_contract.py (testes de TIPO/estrutura: um stub mínimo

  que satisfaz cada Protocol é aceito por isinstance quando runtime\_checkable, e mypy

  não acusa; sem I/O real)

RESTRIÇÕES (DoD §14.2):

\- \`from \_\_future\_\_ import annotations\`; docstrings em cada Protocol e DTO; type hints

  completos (mypy \--strict sem \`Any\` implícito).

\- import-linter: domínio puro. Sem logging.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-005):

\- Todos os ports da §5.1 presentes com assinaturas idênticas (nomes de parâmetros e

  tipos batem).

\- \`mypy \--strict\` passa sobre o módulo e o teste.

\- import-linter confirma que \`domain\` continua sem importar infra/third-party.

\- O teste de contrato mostra que um stub trivial é estruturalmente compatível com cada

  Protocol (prova que os fakes de TAREFA-011 poderão implementá-los).

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-005 \+ arquitetura §5.1/§5.2 \+ ADR-001/011 \+

"Nota de operacionalização" (ResultFrame não é dataframe) \+ skill python-clean-architecture §2.

VERIFIQUE, item a item, citando arquivo:linha:

1\. Os 11 ports da §5.1 estão presentes? Compare CADA assinatura (nome do método,

   nomes de parâmetros, keyword-only \`\*\`, tipos de retorno) com o documento — sinalize

   qualquer divergência como bloqueador.

2\. Ports são typing.Protocol (não ABC com herança forçada)? runtime\_checkable onde útil?

3\. DTOs auxiliares são frozen dataclasses PUROS (não Pydantic)? ResultFrame é wrapper

   sobre tuple\[EvaluationResult,...\] SEM pandas/polars/pyarrow?

4\. Nenhum \`Any\` solto / \`\# type: ignore\` injustificado? mypy \--strict limpo?

5\. import-linter: domain não importa infra nem libs de I/O da lista canônica?

6\. Teste de contrato prova compatibilidade estrutural de um stub com cada Protocol?

7\. DoD §14.2 (future annotations, docstrings em todos os Protocols/DTOs)?

SAÍDA: PASS/FAIL \+ tabela de divergências (critério | arquivo:linha | gravidade).

Liste explicitamente quaisquer assinaturas que NÃO batem com a §5.1.

Confirme \`mypy \--strict src\` e \`lint-imports\`.

---

## TAREFA-006 — `FinalScoreCalculator` (`domain/services/final_score.py`)

**Épico:** E0 · **Skill:** ml-engineer · **Prioridade:** P0 · **Tamanho:** S **Dependências:** TAREFA-003 (MetricVector, FinalScore), TAREFA-002 (exceções) · **ADRs:** ADR-007 (NaN) · **Camadas:** domain/services

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §4.4 "Serviços de

domínio", §7.1 fórmula FinalScore do doc-base). Padrão: python-clean-architecture §2

(serviço de domínio PURO, sem I/O, sem logging). Depende de TAREFA-003 (MetricVector,

FinalScore) e TAREFA-002 (WeightsDoNotSumToOneError).

TAREFA: TAREFA-006 — implementar \`FinalScoreCalculator\` em

\`src/inteligenciomica\_eval/domain/services/final\_score.py\`.

ESPECIFICAÇÃO:

\- Fórmula (§7.1 do documento-base, reproduzida no §4.4 da arquitetura):

    FinalScore \= 0.45\*answer\_correctness \+ 0.20\*faithfulness

               \+ 0.15\*rubric\_biomed\_score \+ 0.10\*context\_recall

               \+ 0.05\*context\_precision \+ 0.05\*answer\_relevancy

  (note: \`answer\_similarity\` e \`bertscore\_f1\` NÃO entram no FinalScore — são auxiliares;

   evitar double-counting, §7.1 nota técnica).

\- Pesos vêm da CONFIG (não hardcode os números como única fonte): a assinatura recebe

  um mapeamento \`weights: Mapping\[str, float\]\`. Os defaults acima ficam como constante

  documentada para teste/golden, mas o cálculo usa os pesos passados.

\- Validação: se \`sum(weights.values())\` não for \~1.0 (tolerância 1e-9), levantar

  \`WeightsDoNotSumToOneError\`. Se \`weights\` referenciar métrica inexistente em

  MetricVector, erro de configuração claro.

\- Tratamento de NaN (ADR-007): se QUALQUER métrica usada (peso \> 0\) for NaN, o resultado

  é \`FinalScore(NaN)\` (a linha será excluída na agregação; NÃO imputar). Documente esse

  comportamento e o porquê. Não logar (é serviço puro) — apenas retornar NaN.

\- Interface: \`class FinalScoreCalculator:\` com \`\_\_init\_\_(self, weights: Mapping\[str,float\])\`

  (valida pesos na construção, fail-fast) e

  \`compute(self, metrics: MetricVector) \-\> FinalScore\`.

\- Determinístico e puro: mesma entrada → mesma saída; sem estado mutável.

ENTREGÁVEL:

\- src/inteligenciomica\_eval/domain/services/final\_score.py

\- tests/unit/domain/services/test\_final\_score.py

\- tests/golden/final\_score\_cases.json (casos golden: vetores de entrada → FinalScore

  esperado, incluindo um caso com NaN → NaN) \+ teste que lê e valida o golden

RESTRIÇÕES (DoD §14.2):

\- \`from \_\_future\_\_ import annotations\`; docstrings Google; type hints; mypy \--strict.

\- Serviço PURO: sem I/O, sem logging, só stdlib \+ VOs de domínio. import-linter OK.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-006):

\- Pesos que não somam 1.0 ⇒ WeightsDoNotSumToOneError na construção.

\- Golden numérico: pelo menos 5 casos com valor esperado calculado à mão/independente,

  batendo até tolerância (ex.: 1e-6); incluir caso de borda (todas métricas \= 1.0 ⇒ 1.0;

  todas \= 0.0 ⇒ 0.0) e caso com métrica NaN de peso \> 0 ⇒ NaN.

\- Cobertura line+branch \>= 95% do módulo.

\- Property-based (hypothesis): para métricas em \[0,1\] e pesos válidos, o resultado cai

  em \[0,1\] (exceto NaN); monotonicidade fraca — aumentar uma métrica (mantendo as outras)

  não diminui o FinalScore.

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer (com olhar de revisão numérica). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-006 \+ arquitetura §4.4 \+ doc-base §7.1 \+ ADR-007 \+

skill ml-engineer \+ test-engineer §13 (golden).

VERIFIQUE, item a item, citando arquivo:linha:

1\. A fórmula bate EXATAMENTE com §7.1 (pesos 0.45/0.20/0.15/0.10/0.05/0.05 nas métricas

   corretas)? answer\_similarity e bertscore\_f1 ficaram FORA (anti double-counting)?

2\. Pesos vêm da config (não só hardcode)? Soma \!= 1.0 ⇒ WeightsDoNotSumToOneError na

   construção (fail-fast)?

3\. NaN propaga para FinalScore(NaN) quando métrica de peso\>0 é NaN — SEM imputação (ADR-007)?

4\. Serviço é puro (sem I/O/logging/estado mutável)? Determinístico?

5\. Golden: \>=5 casos \+ bordas (tudo 1, tudo 0\) \+ caso NaN; valores conferem por cálculo

   INDEPENDENTE (refaça a conta de 1-2 casos você mesmo e cite o resultado)?

6\. Property-based presente (faixa \[0,1\]; monotonicidade fraca)?

7\. Cobertura \>=95% do módulo; import-linter OK; DoD §14.2?

SAÍDA: PASS/FAIL \+ tabela de divergências (critério | arquivo:linha | gravidade).

Inclua a sua recomputação manual de pelo menos 1 caso golden como evidência.

Confirme execução de pytest (com cobertura do módulo) e lint-imports.

---

## Apêndice — Ordem de execução e gates de M0 (001–006)

Sub-DAG das tarefas cobertas aqui (extraído do §14.3):

001 ─┬─ 002 ── 003 ── 004 ─┐

     └─ 005 ───────────────┴─ (005 também depende de 003/004)

                              006 depende de 002/003

Sequência recomendada de PRs (respeitando dependências):

1. **TAREFA-001** (raiz — nada começa sem o repo/CI/import-linter).  
2. **TAREFA-002** (exceções — base para VOs e serviços).  
3. **TAREFA-003** (VOs — base para entidades, ports e scoring).  
4. **TAREFA-004** (entidades) e **TAREFA-006** (FinalScoreCalculator) podem ir em paralelo após 003 (006 só precisa de 002+003; 004 precisa de 002+003).  
5. **TAREFA-005** (ports) após 003+004.

**Gate parcial (ao fim de 001–006):** `mypy --strict`, `ruff`, `lint-imports` e `pytest` verdes; cobertura de `domain` já elevada (VOs e FinalScore ≥95%); contratos (ports) compiláveis e estruturalmente verificados. Isso prepara o terreno para **007–012** (AggregationService, RankScore, ParquetStorage, config/YAML, fakes e E2E stub), que fecham o milestone M0.

**Observação para a continuação (007–012):** a TAREFA-003 já adianta `RowId` e `DeterminismRegime` (necessários a 004/005). Ao escrever 007–012, lembrar que `AggregationService` (TAREFA-008) consome `EvaluationResult`/`MetricVector` e deve EXCLUIR NaN reportando a contagem (ADR-007), e que `ParquetStorage` (TAREFA-009) materializa o schema do §5.3 e implementa a idempotência por `RowId` (ADR-009).  
