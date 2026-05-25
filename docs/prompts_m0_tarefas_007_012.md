# Prompts M0 — TAREFA-007 a 012 (Claude Code ↔ ChatGPT Codex)

**Milestone:** M0 — Bootstrap e contratos (fecha o milestone: scoring executivo, agregação, persistência, config e E2E stub) **Documento de referência:** `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1) **Continuação de:** `prompts_m0_tarefas_001_006.md` (mesmas convenções e "Nota de operacionalização") **Formato:** para cada tarefa, um **Prompt A (implementação — Claude Code)** e um **Prompt B (verificação — ChatGPT Codex)**, conforme seção 16 do documento de arquitetura.

Pressupõe que **001–006 já estão mergeados e verdes** (exceções, VOs, entidades, ports e `FinalScoreCalculator`). A "Nota de operacionalização" do arquivo 001–006 (lista canônica de libs proibidas em `domain`/`application`; `ResultFrame` é wrapper, não DataFrame) **continua valendo integralmente** e é referenciada abaixo.

---

## Nota de operacionalização adicional (decisões que estes prompts fixam)

Três pontos que 007–012 precisam fixar para Code e Codex não divergirem (vetáveis pela equipe):

1. **Onde mora a regra de "qual métrica conta como falha".** `is_failure(threshold)` já existe na entidade (TAREFA-004) e usa `final_score < threshold`. O `AggregationService` (008) **reusa** esse método — não reimplementa o limiar. O `failure_threshold` vem da config (010), default 0.70 (§7.2 doc-base).  
     
2. **`WinRate` precisa de contexto entre configurações.** `WinRate_{b,m}` \= em quantas das 13 perguntas a config `{b,m}` teve o maior `FinalScore` **entre todas as configs** (§7.2 doc-base). Logo é calculado por uma função que recebe **todas** as configs de uma vez (não config-a-config isolada). Operacionalização: `AggregationService.aggregate_all(results) -> tuple[ConfigAggregate, ...]` resolve `WinRate` comparando por `question_id`; empates dividem a vitória igualmente (1/k para k empatados) — documentar essa convenção.  
     
3. **`ParquetStorage` é a primeira fronteira de I/O do projeto.** É `infrastructure/repositories/`, implementa `ResultWriterPort`/`ResultReaderPort` (TAREFA-005), pode importar `pyarrow`/`pandas`/`polars` (proibidos só em domain/application). A conversão `EvaluationResult ↔ linha tidy` (schema §5.3) vive AQUI, num mapeador dedicado e testável, não espalhada. `ResultFrame` (retorno do reader) permanece o wrapper de domínio sobre `tuple[EvaluationResult, ...]`.

---

## TAREFA-007 — `RankScoreCalculator` (`domain/services/rank_score.py`)

**Épico:** E0 · **Skill:** ml-engineer · **Prioridade:** P0 · **Tamanho:** S **Dependências:** TAREFA-003 (RankScore, VOs), TAREFA-002 (exceções) · **ADRs:** ADR-007 (NaN) · **Camadas:** domain/services

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §4.4 "Serviços de

domínio"; doc-base §7.3 fórmula RankScore executivo). Padrão: python-clean-architecture §2

(serviço de domínio PURO, sem I/O, sem logging). Depende de TAREFA-003 (RankScore) e

TAREFA-002 (exceções).

TAREFA: TAREFA-007 — implementar \`RankScoreCalculator\` em

\`src/inteligenciomica\_eval/domain/services/rank\_score.py\`.

ESPECIFICAÇÃO:

\- Fórmula (doc-base §7.3):

    RankScore \= 0.50\*MedianScore \+ 0.20\*(1 \- FailureRate) \+ 0.15\*WinRate

              \- 0.15\*CriticalFailureRate

\- Entrada: um objeto/Mapping com os agregados de UMA configuração já calculados

  (MedianScore, FailureRate, WinRate, CriticalFailureRate — todos em \[0,1\], exceto

  MedianScore que é FinalScore em \[0,1\]). Defina um pequeno DTO de entrada PURO

  (frozen dataclass) \`RankScoreInputs\` OU receba os 4 floats por keyword — escolha a

  forma e documente; prefira o DTO por clareza.

\- Os PESOS vêm da config (não hardcode como única fonte): assinatura recebe

  \`weights: Mapping\[str, float\]\` com chaves

  {median, one\_minus\_failure, win\_rate, critical\_failure\_penalty}. Os defaults

  (0.50/0.20/0.15/0.15) ficam como constante documentada.

\- IMPORTANTE (semântica do doc-base §7.3): o RankScore PODE ser NEGATIVO (penalização

  clínica forte por CriticalFailureRate alta é um sinal desejável). NÃO faça clamp em

  \[0,1\]. O VO RankScore (TAREFA-003) já permite negativo — apenas construa-o.

\- Validação de pesos: diferente do FinalScore, aqui os 4 termos NÃO precisam somar 1.0

  (há um termo subtrativo e um (1-x)). A regra é: cada peso é finito e \>= 0; o termo de

  penalização é aplicado com sinal negativo na fórmula. Se algum peso for negativo/NaN/

  inf, levantar \`WeightsDoNotSumToOneError\` (reuso da exceção existente — ou, se preferir

  semântica mais clara, proponha/observe; mas NÃO crie exceção nova sem necessidade).

  Documente claramente por que NÃO há checagem de soma==1 aqui (contraste com FinalScore).

\- Tratamento de NaN (ADR-007): se QUALQUER insumo for NaN, RankScore(NaN). Não imputar.

\- Interface: \`class RankScoreCalculator:\` com \`\_\_init\_\_(self, weights)\` (valida na

  construção, fail-fast) e \`compute(self, inputs: RankScoreInputs) \-\> RankScore\`.

\- Puro e determinístico.

ENTREGÁVEL:

\- src/inteligenciomica\_eval/domain/services/rank\_score.py

\- tests/unit/domain/services/test\_rank\_score.py

\- tests/golden/rank\_score\_cases.json (\>=5 casos, incluindo um com RankScore NEGATIVO

  por CriticalFailureRate alta, e um caso NaN) \+ teste que lê e valida o golden

RESTRIÇÕES (DoD §14.2):

\- \`from \_\_future\_\_ import annotations\`; docstrings Google; type hints; mypy \--strict.

\- Serviço PURO: sem I/O, sem logging, só stdlib \+ VOs de domínio. import-linter OK.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-007):

\- Caso com CriticalFailureRate alta produz RankScore negativo (SEM clamp) — testado.

\- Golden numérico: \>=5 casos com valor esperado calculado independentemente; bordas

  (config perfeita; config péssima com crítico=1.0 ⇒ negativo); caso NaN ⇒ NaN.

\- Cobertura line+branch \>= 95% do módulo.

\- Property-based (hypothesis): aumentar CriticalFailureRate (demais fixos) NUNCA aumenta

  o RankScore (monotonicidade da penalização); aumentar MedianScore nunca o diminui.

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer (com olhar de revisão numérica). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-007 \+ arquitetura §4.4 \+ doc-base §7.3 \+ ADR-007 \+

skill ml-engineer \+ test-engineer §13 (golden).

VERIFIQUE, item a item, citando arquivo:linha:

1\. Fórmula bate EXATAMENTE com doc-base §7.3 (0.50\*Median \+ 0.20\*(1-Failure) \+

   0.15\*Win \- 0.15\*Critical)? O termo de penalização é SUBTRATIVO?

2\. RankScore PODE ser negativo (SEM clamp em \[0,1\])? Há teste que prova isso?

3\. Pesos vêm da config? A ausência de checagem soma==1 está justificada por escrito

   (contraste com FinalScore)? Pesos inválidos (neg/NaN/inf) falham na construção?

4\. NaN em qualquer insumo ⇒ RankScore(NaN), sem imputação (ADR-007)?

5\. Serviço puro/determinístico (sem I/O/logging/estado)?

6\. Golden: \>=5 casos \+ caso negativo \+ caso NaN; recompute 1-2 casos você mesmo e cite

   o resultado. Monotonicidade testada (Critical↑ ⇒ Rank não sobe)?

7\. Cobertura \>=95%; import-linter OK; DoD §14.2?

SAÍDA: PASS/FAIL \+ tabela de divergências (critério | arquivo:linha | gravidade).

Inclua sua recomputação manual de pelo menos 1 caso (especialmente o negativo).

Confirme pytest (cobertura do módulo) e lint-imports.

---

## TAREFA-008 — `AggregationService` (`domain/services/aggregation.py`)

**Épico:** E0 · **Skill:** data-engineer · **Prioridade:** P0 · **Tamanho:** M **Dependências:** TAREFA-004 (EvaluationResult), TAREFA-007 (RankScore), TAREFA-003 (VOs) · **ADRs:** ADR-007 (NaN) · **Camadas:** domain/services

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §4.4; doc-base §7.2

"Agregação por configuração" e §7.3). Padrão: python-clean-architecture §2 (serviço de

domínio PURO). Depende de TAREFA-004 (EvaluationResult), TAREFA-007 (RankScoreCalculator)

e TAREFA-003 (VOs). VER "Nota de operacionalização adicional" itens 1 e 2\.

TAREFA: TAREFA-008 — implementar \`AggregationService\` em

\`src/inteligenciomica\_eval/domain/services/aggregation.py\`, que recebe EvaluationResult

materializados e produz os agregados por configuração {base, llm}.

ESPECIFICAÇÃO:

\- Defina um VO de saída \`ConfigAggregate\` (frozen dataclass) com os campos do doc-base §7.2:

  base, llm, mean\_score, median\_score, min\_score, iqr, failure\_rate,

  critical\_failure\_rate, win\_rate, rank\_score, n\_observations, n\_excluded\_nan.

\- Métricas (doc-base §7.2), todas sobre os FinalScore das 13 perguntas × seeds da config:

    \* mean/median/min/IQR (IQR \= Q3 \- Q1).

    \* failure\_rate \= proporção com final\_score \< threshold. REUSE

      \`EvaluationResult.is\_failure(threshold)\` (NÃO reimplemente o limiar). threshold é

      parâmetro do método (vem da config, default 0.70).

    \* critical\_failure\_rate \= proporção com critical\_failure\_flag \== 1\. Linhas com flag

      None (não anotadas) NÃO contam no denominador de crítico — documente e teste essa

      decisão (Camada 3 pode estar ausente; ADR-010).

    \* win\_rate: ver Nota item 2 — só calculável comparando TODAS as configs por

      question\_id; empate divide 1/k.

\- Tratamento de NaN (ADR-007): final\_score NaN é EXCLUÍDO dos cálculos de

  mean/median/min/IQR/failure\_rate; conte os excluídos em n\_excluded\_nan e em

  n\_observations (válidos). NÃO imputar. Se TODAS as observações de uma config forem NaN,

  os agregados numéricos são NaN e n\_observations=0 (não quebrar).

\- API:

    \`aggregate\_all(self, results: Sequence\[EvaluationResult\], \*, threshold: float)

        \-\> tuple\[ConfigAggregate, ...\]\`

  Agrupa por (base, llm), calcula tudo, resolve win\_rate cross-config, e usa o

  RankScoreCalculator (injetado no \_\_init\_\_) para preencher rank\_score de cada config.

\- Puro: sem I/O, sem pandas/numpy (use statistics da stdlib; para quantis, implemente ou

  use statistics.quantiles — documente o método de quantil escolhido, pois afeta IQR).

  Sem logging.

ENTREGÁVEL:

\- src/inteligenciomica\_eval/domain/services/aggregation.py

\- tests/unit/domain/services/test\_aggregation.py

\- tests/golden/aggregation\_cases.json (entradas: conjunto de EvaluationResult sintéticos;

  saídas: ConfigAggregate esperados, incluindo caso com NaN excluído e caso com empate

  de win\_rate) \+ teste que valida o golden

RESTRIÇÕES (DoD §14.2):

\- \`from \_\_future\_\_ import annotations\`; frozen dataclass de saída; docstrings; type hints.

\- Serviço PURO: stdlib apenas (math, statistics); sem pandas/polars/numpy; import-linter OK.

\- Determinístico; sem estado mutável.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-008):

\- Exclui NaN dos cálculos e REPORTA a contagem (n\_excluded\_nan) — testado.

\- failure\_rate usa EvaluationResult.is\_failure (não duplica limiar).

\- critical\_failure\_rate ignora flags None no denominador — testado.

\- win\_rate correto entre configs, com empate 1/k — testado com cenário de empate.

\- Método de quantil para IQR documentado; golden numérico confere.

\- Cobertura line+branch \>= 95% do módulo.

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer (revisão numérica \+ estatística). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-008 \+ arquitetura §4.4 \+ doc-base §7.2/§7.3 \+ ADR-007/010 \+

"Nota de operacionalização adicional" itens 1-2 \+ skill data-engineer \+ test-engineer §13.

VERIFIQUE, item a item, citando arquivo:linha:

1\. ConfigAggregate tem TODOS os campos do §7.2 (mean/median/min/iqr/failure\_rate/

   critical\_failure\_rate/win\_rate/rank\_score/n\_observations/n\_excluded\_nan)?

2\. failure\_rate REUSA EvaluationResult.is\_failure(threshold) (não reimplementa \< )?

3\. NaN excluído de TODOS os cálculos numéricos E contado em n\_excluded\_nan (ADR-007)?

   Config 100% NaN não quebra (n\_observations=0)?

4\. critical\_failure\_rate: flags None fora do denominador (ADR-010)? testado?

5\. win\_rate: comparado cross-config por question\_id? empate divide 1/k? testado?

6\. IQR: método de quantil documentado e consistente com o golden?

7\. Serviço PURO (sem pandas/polars/numpy; só stdlib; sem logging; import-linter OK)?

8\. RankScoreCalculator é injetado (não instanciado hardcoded internamente)?

9\. Golden confere (recompute mean/median/failure\_rate de 1 caso você mesmo)?

   Cobertura \>=95%? DoD §14.2?

SAÍDA: PASS/FAIL \+ tabela de divergências (critério | arquivo:linha | gravidade).

Inclua recomputação manual de pelo menos 1 agregado (ex.: failure\_rate de uma config).

Confirme pytest (cobertura do módulo) e lint-imports.

---

## TAREFA-009 — `ParquetStorage` (`infrastructure/repositories/parquet_storage.py`)

**Épico:** E0 · **Skill:** data-engineer · **Prioridade:** P0 · **Tamanho:** M **Dependências:** TAREFA-004 (EvaluationResult), TAREFA-005 (ports \+ ResultFrame), TAREFA-003 (RowId) · **ADRs:** ADR-002 (Parquet), ADR-009 (idempotência por RowId) · **Camadas:** infrastructure/repositories

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §5.3 "Esquema de

dados tidy", §5.4 "Contrato entre passadas", ADR-002, ADR-009). Padrão:

python-clean-architecture §1 (adapter de infraestrutura implementa um Port de domínio).

Depende de TAREFA-004/005/003. VER "Nota de operacionalização adicional" item 3

(ParquetStorage é a primeira fronteira de I/O; mapeador dedicado; pode usar pyarrow).

TAREFA: TAREFA-009 — implementar \`ParquetStorage\` em

\`src/inteligenciomica\_eval/infrastructure/repositories/parquet\_storage.py\`, que implementa

\`ResultWriterPort\` e \`ResultReaderPort\` (TAREFA-005), persistindo o schema do §5.3.

ESPECIFICAÇÃO:

\- Implementa os métodos dos ports:

    ResultWriter: \`append(result)\`, \`update\_metrics(row\_id, metrics)\`, \`exists(row\_id) \-\> bool\`.

    ResultReader: \`load(\*, round\_id, phase=None) \-\> ResultFrame\`.

\- Schema EXATO do §5.3 (todos os campos, tipos pyarrow indicados na tabela). Inclua os

  campos derivados/proveniência: row\_id, run\_id, experiment\_phase, round\_id, base, llm,

  judge\_model, embedding\_model, chunk\_strategy, reranker, top\_k, prompt\_version,

  temperature, seed, batch\_invariant, vllm\_version, ragas\_version, config\_hash,

  question\_id, question, ground\_truth, retrieved\_chunk\_ids (list\<string\>),

  retrieved\_chunks\_text (list\<string\>), retrieval\_scores (list\<float32\>),

  generated\_answer, as 8 métricas de Camada 1+2 (float32, podem ser null),

  rubric\_feedback, critical\_failure\_flag (int8 nullable), critical\_failure\_note,

  final\_score (float32 nullable), metric\_nan\_fields (list\<string\>), retry\_count (int8),

  latency\_ms, tokens\_in, tokens\_out, timestamp (timestamp\[us\], UTC).

\- Mapeador dedicado e testável \`EvaluationResult \<-\> dict/linha\` (uma função/par de

  funções, NÃO espalhado): \`to\_row(result) \-\> dict\` e \`from\_row(row) \-\> EvaluationResult\`.

  Roundtrip deve ser fiel (incluindo NaN e None corretos: NaN em métrica float vs.

  null/None em flag — manter a distinção semântica).

\- Particionamento físico: \`round\_id / experiment\_phase / base / llm\` (§5.3). Use pyarrow

  dataset (ou pandas+pyarrow) com partição por essas colunas.

\- Idempotência (ADR-009): \`exists(row\_id)\` consulta se a linha já existe E está completa

  o suficiente para pular (definir "completa": pelo menos generated\_answer presente para

  a passada de geração). \`append\` de row\_id já existente deve ser seguro (não duplicar):

  estratégia last-write-wins por row\_id na partição (documente). \`update\_metrics\` localiza

  por row\_id e completa as colunas de métrica \+ final\_score sem reescrever o resto.

\- Erros: falhas de I/O viram \`StorageError\` (TAREFA-002) com mensagem acionável (sem

  vazar paths absolutos sensíveis). Diretório-base configurável (não hardcode).

\- Logging estruturado (structlog) nesta camada É permitido (é infra, não domínio):

  logar append/update/skip por row\_id, sem despejar textos longos (ground\_truth/chunks).

ENTREGÁVEL:

\- src/inteligenciomica\_eval/infrastructure/repositories/parquet\_storage.py

\- tests/integration/repositories/test\_parquet\_storage.py (usa tmp\_path; SEM serviços

  externos — Parquet é local)

\- tests/unit/repositories/test\_row\_mapper.py (roundtrip to\_row/from\_row, incl. NaN vs None)

RESTRIÇÕES (DoD §14.2):

\- \`from \_\_future\_\_ import annotations\`; type hints; docstrings Google; mypy \--strict.

\- Importa pyarrow/pandas/polars à vontade (é infra) — mas NADA de domain importando isto.

  import-linter deve continuar verde (a dependência é infra-\>domain, nunca o contrário).

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-009):

\- Schema do §5.3 materializado (todos os campos e tipos); particionamento round/phase/base/llm.

\- Roundtrip append→load reconstrói EvaluationResult equivalente (NaN/None preservados).

\- \`exists(row\_id)\` correto; reexecutar append do mesmo row\_id NÃO duplica.

\- \`update\_metrics\` completa métricas de linha gerada-mas-não-julgada (§5.4) sem tocar o resto.

\- Falha de I/O ⇒ StorageError; cobertura \>= 80% (adapter de I/O).

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-009 \+ arquitetura §5.3/§5.4 \+ ADR-002/009 \+

"Nota de operacionalização adicional" item 3 \+ skill data-engineer \+ python-clean-architecture §1.

VERIFIQUE, item a item, citando arquivo:linha:

1\. Implementa ResultWriterPort e ResultReaderPort com as assinaturas da TAREFA-005?

2\. Schema bate com a TABELA do §5.3 — confira CADA campo e tipo pyarrow (em especial

   list\<string\>/list\<float32\>, int8 nullable do flag, timestamp\[us\] UTC, e os campos

   ⊕ row\_id/metric\_nan\_fields/retry\_count/config\_hash/ragas\_version)?

3\. Mapeador to\_row/from\_row é dedicado e faz roundtrip fiel? NaN (métrica float) e None

   (flag não anotada) são preservados como coisas DISTINTAS?

4\. Particionamento físico \= round\_id/experiment\_phase/base/llm?

5\. Idempotência (ADR-009): exists(row\_id) correto; append duplicado não cria duplicata

   (last-write-wins documentado)? update\_metrics completa sem reescrever o resto (§5.4)?

6\. Falhas de I/O viram StorageError sem vazar info sensível?

7\. import-linter: domain/application NÃO importam este módulo nem pyarrow; a seta é

   infra-\>domain. Confirme que nada de domínio passou a depender de infra.

8\. Logging estruturado sem despejar textos longos? Cobertura \>=80%? DoD §14.2?

SAÍDA: PASS/FAIL \+ tabela de divergências (critério | arquivo:linha | gravidade).

Liste qualquer campo do §5.3 ausente ou com tipo divergente como BLOQUEADOR.

Confirme pytest (test\_parquet\_storage \+ test\_row\_mapper) e lint-imports.

---

## TAREFA-010 — Config YAML \+ schema Pydantic \+ `config_hash` \+ `--dry-run`

**Épico:** E0 · **Skill:** python-engineer · **Prioridade:** P0 · **Tamanho:** M **Dependências:** TAREFA-001 (repo), TAREFA-002 (exceções), TAREFA-003 (VOs para validar) · **ADRs:** ADR-008 (config declarativa), ADR-003 (regimes) · **Camadas:** infrastructure/config \+ cli

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §12.1 "YAML de

rodada", §12.2 "Proveniência", ADR-008). Padrão: python-clean-architecture §3 (config via

pydantic-settings; YAML validado por modelos Pydantic; fail-fast). Depende de TAREFA-001/

002/003.

TAREFA: TAREFA-010 — implementar a carga e validação de configuração de rodada em

\`src/inteligenciomica\_eval/infrastructure/config/\` (schema.py, settings.py, provenance.py)

e o comando \`ielm-eval run \--dry-run\` que valida e imprime o plano SEM tocar GPU.

ESPECIFICAÇÃO:

\- \`schema.py\`: modelos Pydantic v2 que validam o YAML do §12.1 (campos: round\_id, phases,

  bases, llms, seeds, temperature, retrieval{top\_k, reranker, embedding\_model,

  chunk\_strategy}, judge{model, endpoint\_env, batch\_invariant, temperature},

  scoring{weights, failure\_threshold}, experiment\_b{canonical\_context\_source,

  canonical\_top\_k}; e da v1.1 também gpu\_layout no model\_registry — ver TAREFA-301, mas

  aqui só o schema de RODADA). Validações:

    \* bases ⊆ {IDx\_400k, ID\_230K} (use BaseId para validar); llms não-vazios sem espaço.

    \* scoring.weights deve somar 1.0 (tolerância 1e-9) — senão ConfigValidationError

      (não WeightsDoNotSumToOneError aqui; este é erro de CONFIG, falha na carga).

    \* failure\_threshold ∈ \[0,1\]; temperature \>= 0; top\_k \>= 1; seeds não-vazio.

    \* judge.batch\_invariant deve ser True (ADR-003) — avisar/erro se vier False

      (o juiz PRECISA ser determinístico). Documente a decisão (erro vs warning forte).

\- \`settings.py\`: pydantic-settings lê SEGREDOS/endpoints de env (VLLM\_GENERATOR\_URL,

  VLLM\_JUDGE\_URL, QDRANT\_URL). NUNCA do YAML versionado (ADR-008). O YAML referencia só

  nomes de env (ex.: endpoint\_env: VLLM\_JUDGE\_URL); a resolução do valor é em settings.

\- \`provenance.py\`: \`config\_hash(config) \-\> str\` \= SHA-256 do YAML NORMALIZADO

  (serialização canônica/ordenada — documente a normalização para o hash ser estável).

  Também coleta vllm\_version/ragas\_version (de onde? em M0, placeholders lidos de env ou

  de importlib.metadata quando o pacote existir; documente). Retorna um objeto de

  proveniência que será injetado nas linhas (TAREFA-009 schema).

\- CLI \`run \--dry-run\` (em cli.py, comando \`run\`): carrega o YAML, valida (fail-fast com

  ConfigValidationError de mensagem clara apontando o campo), resolve endpoints de env,

  e IMPRIME o plano: nº de células planejadas (produto bases×llms×seeds×perguntas para

  fase A; llms×seeds×perguntas para B), config\_hash, endpoints resolvidos (mascarando

  credenciais), e — placeholder em M0 — o mapa de GPUs/ondas será detalhado na TAREFA-303.

  NÃO chama Qdrant/vLLM em \--dry-run.

\- Forneça \`config/experiment\_round1.yaml\` de exemplo coerente com §12.1 (com placeholders

  \<a-definir\> para embedding/chunk baseline).

ENTREGÁVEL:

\- src/inteligenciomica\_eval/infrastructure/config/{schema.py, settings.py, provenance.py}

\- atualização de cli.py com o comando \`run \--dry-run\` (sem execução real ainda)

\- config/experiment\_round1.yaml (exemplo)

\- tests/unit/config/test\_schema.py (YAML válido carrega; inválidos falham com

  ConfigValidationError no campo certo)

\- tests/unit/config/test\_provenance.py (config\_hash é ESTÁVEL e SENSÍVEL: mesma config →

  mesmo hash; mudar 1 campo → hash diferente)

\- tests/unit/cli/test\_dry\_run.py (dry-run imprime nº de células e hash; não acessa rede)

RESTRIÇÕES (DoD §14.2):

\- \`from \_\_future\_\_ import annotations\`; type hints; docstrings; mypy \--strict.

\- pydantic/pydantic-settings permitidos (transversais — Nota de operacionalização 001-006).

\- Sem segredo no YAML versionado. import-linter: config é infra; cli pode importar

  application/infra, mas NÃO o contrário.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-010):

\- YAML inválido (peso não soma 1, base desconhecida, threshold fora de \[0,1\],

  batch\_invariant=False no juiz) falha FAST com ConfigValidationError apontando o campo.

\- config\_hash estável e sensível (testado).

\- \`ielm-eval run \--dry-run \--config config/experiment\_round1.yaml\` imprime plano e hash,

  sem tocar rede/GPU.

\- Endpoints vêm de env; nenhum segredo no YAML.

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-010 \+ arquitetura §12.1/§12.2 \+ ADR-008/003 \+

skill python-clean-architecture §3.

VERIFIQUE, item a item, citando arquivo:linha:

1\. schema.py valida todos os campos do §12.1? weights somam 1.0 (senão

   ConfigValidationError — e NÃO WeightsDoNotSumToOneError)? bases via BaseId?

   failure\_threshold/temperature/top\_k/seeds validados?

2\. judge.batch\_invariant=False é tratado (erro ou warning forte) conforme ADR-003?

3\. settings.py lê endpoints/segredos de ENV (não do YAML)? YAML referencia só nomes de env?

4\. config\_hash: normalização documentada, ESTÁVEL (mesma config→mesmo hash) e SENSÍVEL

   (campo muda→hash muda)? Testado nos dois sentidos?

5\. \`run \--dry-run\`: calcula nº de células correto (A: bases×llms×seeds×perguntas;

   B: llms×seeds×perguntas), imprime hash, mascara credenciais, NÃO acessa rede/GPU?

6\. Nenhum segredo no YAML versionado? import-linter mantém direção cli/infra-\>... correta?

7\. Cobertura dos ramos de validação; DoD §14.2?

SAÍDA: PASS/FAIL \+ tabela de divergências (critério | arquivo:linha | gravidade).

Confirme pytest (schema/provenance/dry\_run) e lint-imports. Cole a saída do \--dry-run.

---

## TAREFA-011 — Fakes de todos os ports \+ factories (`tests/fakes/`, `tests/factories/`)

**Épico:** E0 · **Skill:** test-engineer · **Prioridade:** P0 · **Tamanho:** M **Dependências:** TAREFA-005 (ports \+ DTOs), TAREFA-004 (entidades), TAREFA-003 (VOs) · **ADRs:** — · **Camadas:** tests

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §11.2 "Fakes das

ports", §11 estratégia de testes). Padrão: test-engineer §6 (fakes tipados preferidos a

mocks) \+ §10 (factories). Depende de TAREFA-005 (Protocols) e das entidades/VOs.

TAREFA: TAREFA-011 — implementar, em \`tests/fakes/\` e \`tests/factories/\`, fakes in-memory

para TODOS os ports da §5.1 e factories de dados de teste, prontos para os use cases

(M1+) e para o E2E stub (TAREFA-012).

ESPECIFICAÇÃO:

\- \`tests/fakes/\` — uma implementação in-memory, determinística e tipada por cada Protocol

  (devem satisfazer isinstance quando runtime\_checkable; mypy \--strict deve aceitá-las

  como o Protocol):

    \* \`StubRetriever(RetrieverPort)\` — devolve chunks plantados configuráveis por pergunta.

    \* \`FakeGenerator(GeneratorPort)\` — devolve resposta canônica determinística (função de

      (llm, question, seed) — ex.: template fixo); registra chamadas para asserção.

    \* \`FakeMetricSuite(MetricSuitePort)\` e \`FakeRubricJudge(RubricJudgePort)\` — devolvem

      Layer1Metrics/RubricResult fixos ou parametrizáveis; suportam injetar NaN p/ testar

      ADR-007.

    \* \`FakeDeterministicMetric(DeterministicMetricPort)\` — AuxMetrics fixos.

    \* \`InMemoryResultWriter\`/\`InMemoryResultReader\` (Result\*Port) — guardam

      EvaluationResult em dict por row\_id; \`exists\` real; \`update\_metrics\` real; \`load\`

      devolve ResultFrame (wrapper). É o fake que o E2E usará no lugar do ParquetStorage.

    \* \`FakeGoldChunkReader\`, \`FakeAnnotationReader\`, \`FakeStats\` (StatsPort),

      \`FakeVLLMServerManager\` (registra start/stop/wait sem subir nada).

\- \`tests/factories/\` — factories (polyfactory ou builders simples) para Question,

  GeneratedAnswer, EvaluationResult, MetricVector, ConfigAggregate, com defaults válidos

  e overrides por kwargs. Determinísticas (seeds fixas).

\- Os fakes NÃO fazem I/O nem rede; são puros e determinísticos. Documentar cada um.

ENTREGÁVEL:

\- tests/fakes/\_\_init\_\_.py \+ um módulo por grupo de fakes (ex.: fakes/generation.py,

  fakes/storage.py, fakes/metrics.py, fakes/servers.py)

\- tests/factories/\_\_init\_\_.py \+ factories.py

\- tests/unit/fakes/test\_fakes\_satisfy\_ports.py — prova, por porta, que o fake é

  estruturalmente compatível com o Protocol (isinstance/runtime\_checkable e/ou

  asserção de mypy via reveal\_type em comentário) e que é determinístico.

RESTRIÇÕES (DoD §14.2):

\- \`from \_\_future\_\_ import annotations\`; type hints; docstrings; mypy \--strict nos fakes.

\- Fakes podem importar domain (entities/VOs/ports) — NÃO importam infra real

  (qdrant/openai/pyarrow). Determinísticos; sem rede/disco.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-011):

\- Existe um fake tipado por CADA port da §5.1; todos passam no teste de compatibilidade

  estrutural com o Protocol correspondente.

\- InMemoryResultWriter/Reader implementam exists/update\_metrics/load corretamente

  (espelham o contrato do ParquetStorage para uso no E2E).

\- Fakes de métricas conseguem injetar NaN (para testar caminho ADR-007 nos use cases).

\- Factories produzem entidades válidas com overrides; determinísticas.

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-011 \+ arquitetura §5.1/§11.2 \+ skill test-engineer §6/§10.

VERIFIQUE, item a item, citando arquivo:linha:

1\. Há um fake para CADA um dos 11 ports da §5.1? Algum faltando?

2\. Cada fake é estruturalmente compatível com seu Protocol (teste isinstance/runtime ou

   prova de tipo)? mypy \--strict aceita os fakes como o Protocol?

3\. InMemoryResultWriter/Reader: exists/update\_metrics/load espelham o contrato do

   ParquetStorage (mesma semântica de idempotência por row\_id)?

4\. Fakes de métrica permitem injetar NaN (suporte ao teste de ADR-007 em M2)?

5\. Fakes são determinísticos e SEM I/O/rede (não importam qdrant/openai/pyarrow)?

6\. Factories geram entidades válidas com overrides e são determinísticas?

7\. DoD §14.2; import-linter (fakes são test-code, mas não devem puxar infra real)?

SAÍDA: PASS/FAIL \+ tabela de divergências (critério | arquivo:linha | gravidade).

Liste qualquer port SEM fake como BLOQUEADOR. Confirme pytest dos fakes e lint-imports.

---

## TAREFA-012 — E2E stub: rodada mínima em CPU

**Épico:** E0 · **Skill:** test-engineer · **Prioridade:** P0 · **Tamanho:** M **Dependências:** TAREFA-006/007/008 (scoring/agregação), TAREFA-009 (storage), TAREFA-011 (fakes) · **ADRs:** ADR-009 (idempotência) · **Camadas:** tests/e2e

### Prompt A — Implementação (Claude Code)

CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §3.4 fluxo principal,

§14.3 critério de go/no-go do M0). Padrão: test-engineer §9 (E2E enxuto, poucos e

valiosos). Depende de scoring (006/007), agregação (008), storage (009) e fakes (011).

ESTE É O TESTE QUE FECHA O M0: prova o esqueleto ponta-a-ponta SEM GPU.

TAREFA: TAREFA-012 — implementar um teste E2E (\`tests/e2e/test\_min\_round\_stub.py\`,

marcado \`@pytest.mark.e2e\`) que roda uma rodada mínima inteiramente com fakes/stubs em

CPU e materializa Parquet REAL \+ scores \+ agregados, validando o resultado esperado.

ESPECIFICAÇÃO:

\- Cenário mínimo determinístico: 2 perguntas, 1 base ("IDx\_400k"), 2 LLMs stub, 1 seed

  (ou 2 se quiser exercitar variância) — produto pequeno, resultado previsível.

\- Fluxo (espelha §3.4, mas com fakes):

    1\. StubRetriever devolve contextos plantados por pergunta.

    2\. FakeGenerator devolve respostas canônicas determinísticas.

    3\. Persistência: use o ParquetStorage REAL (TAREFA-009) em tmp\_path (Parquet é local,

       não é GPU/rede) — isso valida o schema §5.3 de verdade. (Alternativamente, um teste

       gêmeo com InMemoryResultWriter para velocidade; mas pelo menos UM caminho usa

       ParquetStorage real.)

    4\. FakeMetricSuite \+ FakeRubricJudge devolvem métricas determinísticas (inclua UMA

       resposta com métrica NaN para exercitar ADR-007 no caminho de agregação).

    5\. FinalScoreCalculator (006) calcula final\_score; linhas persistidas.

    6\. AggregationService (008) \+ RankScoreCalculator (007) produzem ConfigAggregate por

       {base, llm}.

\- Asserções:

    \* Nº de linhas no Parquet \== nº de células planejadas.

    \* Roundtrip: ler o Parquet de volta reconstrói EvaluationResult equivalentes.

    \* final\_score e rank\_score batem com valores ESPERADOS calculados à mão para o cenário

      (golden inline ou arquivo em tests/golden/).

    \* A linha com métrica NaN é EXCLUÍDA da agregação e contabilizada em n\_excluded\_nan.

    \* Idempotência (ADR-009): rodar o fluxo 2× com o mesmo run\_id NÃO duplica linhas.

    \* Nenhuma chamada de rede/GPU ocorre (garanta por construção — só fakes \+ Parquet local).

\- O teste deve rodar em CI normal (CPU), rápido (\< poucos segundos), marcado \`e2e\`.

ENTREGÁVEL:

\- tests/e2e/test\_min\_round\_stub.py

\- (se necessário) um pequeno orquestrador de teste em tests/e2e/\_harness.py que costura

  fakes \+ storage \+ serviços de domínio (NÃO antecipe os use cases de M1; pode ser uma

  função de teste que chama as peças na ordem do §3.4).

\- tests/golden/e2e\_min\_round\_expected.json (valores esperados do cenário)

RESTRIÇÕES (DoD §14.2):

\- \`from \_\_future\_\_ import annotations\`; type hints; docstrings no harness; mypy \--strict.

\- Determinístico (seeds fixas, freezegun para timestamp se necessário). Sem rede/GPU.

\- import-linter verde (test-code não puxa infra de rede; Parquet local é permitido).

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-012):

\- \`pytest \-m e2e\` gera Parquet válido (schema §5.3) e RankScore esperado, SEM GPU/rede.

\- NaN excluído e contado; idempotência por run\_id comprovada (2ª execução não duplica).

\- Roundtrip Parquet fiel; valores batem com o golden do cenário.

\- Tempo de execução baixo; roda no CI de CPU.

### Prompt B — Verificação (ChatGPT Codex)

PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-012 \+ arquitetura §3.4/§14.3 \+ ADR-009 \+

skill test-engineer §9 (E2E).

VERIFIQUE, item a item, citando arquivo:linha:

1\. O E2E usa o ParquetStorage REAL (em tmp\_path) em pelo menos um caminho — validando o

   schema §5.3 de fato (não só InMemory)?

2\. Fluxo espelha §3.4 (retrieve→generate→persist→metrics→final\_score→aggregate→rank)?

3\. Há UMA resposta com métrica NaN, e o teste prova que ela é EXCLUÍDA da agregação e

   contada em n\_excluded\_nan (ADR-007)?

4\. Idempotência: 2ª execução com mesmo run\_id NÃO duplica linhas (ADR-009) — testado?

5\. final\_score/rank\_score conferem com golden calculado à mão para o cenário?

6\. Roundtrip Parquet (ler de volta) reconstrói os EvaluationResult?

7\. Determinístico, SEM rede/GPU (confirme que nenhum adapter real de rede é instanciado)?

8\. Roda sob \`pytest \-m e2e\` em CPU, rápido? DoD §14.2; import-linter?

SAÍDA: PASS/FAIL \+ tabela de divergências (critério | arquivo:linha | gravidade).

Recompute o final\_score esperado de 1 célula do cenário e confronte com o golden.

Confirme \`pytest \-m e2e\` e lint-imports; cole o resumo da execução.

---

## Apêndice — Fechamento do milestone M0 (001–012)

DAG completo do M0 (§14.3 da arquitetura):

001 ─┬─ 002 ── 003 ── 004 ─┐

     ├─ 005 ───────────────┼─ 006 ─┐

     └─ 010                 │       ├─ 008 ─┐

                            └─ 007 ─┘       ├─ 009 ── 011 ── 012

                                            └───────────────┘

Sequência recomendada de PRs para 007–012 (respeitando dependências):

1. **TAREFA-007** (RankScore) — após 003; pode ir junto com 006\.  
2. **TAREFA-008** (AggregationService) — após 004 \+ 007\.  
3. **TAREFA-009** (ParquetStorage) — após 004 \+ 005; pode paralelizar com 008\.  
4. **TAREFA-010** (Config/YAML/dry-run) — após 001/002/003; independente de 008/009, pode ser feita em paralelo bem cedo.  
5. **TAREFA-011** (Fakes \+ factories) — após 005 (precisa dos Protocols); idealmente antes do E2E.  
6. **TAREFA-012** (E2E stub) — POR ÚLTIMO: consome 006/007/008/009/011.

**Gate de saída do M0 (go/no-go para M1):**

- `mypy --strict`, `ruff`, `ruff format --check`, `lint-imports`, `pytest` (unit \+ integração local \+ e2e) todos VERDES no CI.  
- Cobertura de `domain` ≥ 95% (VOs, FinalScore, RankScore, Aggregation); adapters de I/O (ParquetStorage) ≥ 80%.  
- E2E stub (TAREFA-012) verde: esqueleto ponta-a-ponta prova-se SEM GPU, com Parquet real, idempotência e tratamento de NaN.  
- `ielm-eval run --dry-run` imprime plano \+ config\_hash sem tocar rede/GPU.

Cumprido o gate, o esqueleto está pronto para receber os adapters REAIS de M1 (OpenAICompatibleClient, QdrantRetriever, VLLMGenerator, RunExperimentUseCase): cada um substitui um fake correspondente, com o E2E stub permanecendo como rede de segurança.

**Observação para M1:** os fakes da TAREFA-011 definem o contrato que os adapters reais de M1 devem honrar. Ao implementar `QdrantRetriever`/`VLLMGenerator`, o teste de integração deve mostrar que o adapter real é substituível pelo fake no E2E sem mudar o harness — prova de que a regra de dependência (ADR-001) foi respeitada.  
