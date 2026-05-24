# Visão de Alto Nível — Subsistema de Validação do InteligenciÔmica

**Versão:** 1.0 **Data:** 21 de maio de 2026 **Status:** Documento base para discussão com a equipe de desenvolvimento

---

## Sumário

1. [Resumo executivo](#1-resumo-executivo)  
2. [Escopo e objetivos do subsistema de validação](#2-escopo-e-objetivos-do-subsistema-de-validação)  
3. [Rodada 1 — Desenho experimental inicial](#3-rodada-1--desenho-experimental-inicial)  
4. [Rodada 2 — Variação controlada de chunking e embedding](#4-rodada-2--variação-controlada-de-chunking-e-embedding)  
5. [Arquitetura de avaliação em três camadas](#5-arquitetura-de-avaliação-em-três-camadas)  
6. [Os dois experimentos: A (pipeline completo) e B (geração controlada)](#6-os-dois-experimentos-a-pipeline-completo-e-b-geração-controlada)  
7. [Métricas: por pergunta, agregadas e ranking executivo](#7-métricas-por-pergunta-agregadas-e-ranking-executivo)  
8. [Análise estatística](#8-análise-estatística)  
9. [LLM juiz: Prometheus-2 8x7B](#9-llm-juiz-prometheus-2-8x7b)  
10. [Stack tecnológica](#10-stack-tecnológica)  
11. [Proposta de implementação e codificação](#11-proposta-de-implementação-e-codificação)  
12. [Riscos, limitações e mitigações](#12-riscos-limitações-e-mitigações)  
13. [Glossário](#13-glossário)  
14. [Referências e links úteis](#14-referências-e-links-úteis)

---

## 1\. Resumo executivo

O subsistema de validação do InteligenciÔmica tem como objetivo avaliar de forma **automática, reprodutível e estatisticamente fundamentada** a qualidade das respostas geradas pelo sistema, considerando dois fatores principais: a **base vetorial** utilizada (artigos científicos indexados no Qdrant) e o **modelo de linguagem (LLM)** responsável pela geração.

A avaliação será conduzida em **rodadas sucessivas**, variando um fator de cada vez para isolar efeitos:

- **Rodada 1** — 2 bases vetoriais (`IDx_400k` e `ID_230K`) × 5 LLMs (`gpt-oss-120b`, `gemma4:31b`, `qwen3.6:35b`, `glm-4.7-flash`, `llama4:16x17b`), totalizando **10 configurações**. Chunking e embedding ficam fixos. Cada configuração responde às mesmas **13 perguntas** com **3 seeds**, gerando 390 respostas avaliadas.  
- **Rodada 2** — variação separada de **chunking** (fase 2a) e de **embedding** (fase 2b), aplicando o princípio *One-Factor-At-a-Time* (OFAT). Métricas de retrieval puro (precision@k, recall@k, MRR, nDCG@k) serão usadas como **funil** antes da fase cara de geração.

A avaliação ocorre em **três camadas**:

1. **Métricas automáticas** (RAGAS \+ auxiliares determinísticas)  
2. **Rubrica biomédica customizada** (G-Eval ou Prometheus-2 com prompt estruturado)  
3. **Anotação humana de falhas críticas** (revisão direcionada por especialista)

Cada rodada compreende **dois experimentos complementares**:

- **Experimento A** — pipeline completo (retrieval \+ geração)  
- **Experimento B** — geração controlada com contextos fixos (isola o LLM)

O **LLM juiz** padrão será o **Prometheus-2 8x7B em AWQ 4-bit**, servido via vLLM, escolhido por ser open-source, especializado em avaliação e por caber confortavelmente no GH200 já em produção.

A análise estatística usará testes pareados — **Wilcoxon signed-rank** (base × base), **Friedman \+ Nemenyi post-hoc** (entre LLMs) e **modelo linear misto** (interação base × LLM) — apropriados ao tamanho amostral (n=13).

A implementação será um **pacote Python modular** seguindo Clean Architecture, com persistência em **Parquet tidy**, executando sobre o stack `RAGAS + vLLM + Qdrant + DeepEval + statsmodels/pymer4`.

---

## 2\. Escopo e objetivos do subsistema de validação

### 2.1. O que o subsistema deve responder

Cinco perguntas operacionais e científicas:

1. **Qual combinação `{base, LLM}` produz as melhores respostas?**  
2. **Indexar mais artigos (`IDx_400k`) ajuda ou apenas adiciona ruído em relação à base menor (`ID_230K`)?**  
3. **A diferença entre LLMs domina, ou a base vetorial é mais determinante?**  
4. **Existe interação base × LLM? Alguns LLMs aproveitam mais contexto que outros?**  
5. **Quando os erros ocorrem, são erros de recuperação (retrieval), de fundamentação (faithfulness) ou de geração (síntese)?**

### 2.2. O que o subsistema **não** se propõe a fazer agora

- Avaliar latência, custo ou throughput como métricas primárias (serão apenas registrados).  
- Substituir totalmente avaliação humana — a anotação manual permanece como **camada 3 obrigatória** para falhas críticas biomédicas.  
- Gerar dados de treinamento ou fine-tuning a partir dos resultados (escopo futuro).  
- Medir aspectos não-textuais (formatação, multimodalidade).

### 2.3. Princípios metodológicos adotados

- **Pareamento de amostras** — todas as configurações respondem exatamente às mesmas 13 perguntas, permitindo testes estatísticos pareados (alto poder com n pequeno).  
- **One-Factor-At-a-Time (OFAT)** — em cada rodada, varia-se um fator de cada vez. Evita explosão combinatória e ambiguidade na atribuição de efeitos.  
- **Multiplas camadas de evidência** — métricas automáticas, rubrica de LLM-juiz e anotação humana se complementam; nenhuma sozinha é confiável.  
- **Versionamento rigoroso** — cada execução grava `prompt_version`, `embedding_model`, `chunk_strategy`, `judge_model`, `seed`, `temperature` para reprodutibilidade total.  
- **Separação retrieval × geração** — métricas independentes para cada estágio do pipeline, permitindo diagnóstico de origem dos erros.

---

## 3\. Rodada 1 — Desenho experimental inicial

### 3.1. Configurações

| Fator | Valores | Quantidade |
| :---- | :---- | :---- |
| Base vetorial (Qdrant) | `IDx_400k`, `ID_230K` | 2 |
| LLM gerador | `gpt-oss-120b`, `gemma4:31b`, `qwen3.6:35b`, `glm-4.7-flash`, `llama4:16x17b` | 5 |
| Chunking | Fixo (a definir como *baseline*) | 1 |
| Embedding | Fixo (a definir como *baseline*) | 1 |
| Top-k recuperação | Fixo (proposto: k=8) | 1 |
| Reranker | Fixo (none ou um único reranker, definir) | 1 |
| Temperatura | 0.1 | 1 |
| Seeds | 3 valores fixos | 3 |
| Perguntas | 13 fixas | 13 |

**Total de respostas geradas:** 2 × 5 × 3 × 13 \= **390 respostas** (Experimento A). Acrescido do Experimento B (geração controlada): \+ 5 × 3 × 13 \= **195 respostas adicionais**. **Total geral da Rodada 1: 585 respostas a avaliar.**

### 3.2. Hipóteses primárias a serem testadas

- **H1** — Existe diferença estatisticamente significativa entre `IDx_400k` e `ID_230K` no score agregado.  
- **H2** — Existe diferença significativa entre pelo menos um par de LLMs.  
- **H3** — Existe interação `base × LLM` (alguns LLMs se beneficiam mais de uma base do que outros).  
- **H4** — A configuração com maior média também é a mais robusta (menor `FailureRate`).

### 3.3. Critérios de sucesso da Rodada 1

- Identificação clara da melhor configuração `{base, LLM}` por `RankScore`.  
- Diagnóstico do tipo de erro dominante em configurações ruins (retrieval vs. faithfulness vs. síntese).  
- Estimativas de variabilidade entre seeds para calibrar o tamanho de rodadas futuras.  
- Conjunto de "perguntas difíceis" identificadas (aquelas em que todas as configurações falham), úteis como sinal de problemas estruturais (base incompleta, perguntas mal formuladas, ou domínio fora da cobertura).

---

## 4\. Rodada 2 — Variação controlada de chunking e embedding

### 4.1. Princípio: OFAT

Variar simultaneamente chunking **e** embedding cria ambiguidade na atribuição de efeitos. A Rodada 2 será dividida em **duas fases sequenciais**:

- **Fase 2a — Variação de chunking** (embedding fixo do *baseline* da Rodada 1\)  
- **Fase 2b — Variação de embedding** (chunking fixo do *baseline* ou do melhor identificado em 2a)

A base vetorial e os LLMs também ficam fixos (escolhe-se a melhor `{base, LLM}` da Rodada 1\) para reduzir o número de execuções.

### 4.2. Funil de avaliação para reduzir custo

A fase de geração (chamada de LLM) é a parte cara do pipeline. Para variar chunking/embedding eficientemente, usa-se um funil em 2 estágios:

Estágio 1 — Métricas de retrieval puro (barato, sem LLM)  
    │  
    │ precision@k, recall@k, MRR, nDCG@k  
    │ avaliadas contra lista de chunks-ouro (curada manualmente)  
    │  
    ▼  
Top-3 configurações de retrieval  
    │  
    ▼  
Estágio 2 — Geração \+ avaliação completa (caro, com LLM e juiz)  
    │  
    │ pipeline completo (Camadas 1, 2 e 3\) sobre as 13 perguntas

### 4.3. Pré-requisito da Rodada 2: chunks-ouro

Para usar métricas de retrieval puro, cada uma das 13 perguntas precisa ter uma **lista de chunks/documentos esperados** (chunks-ouro), curada por especialista em biomedicina. Esta curadoria deve ser feita **uma única vez** e reaproveitada em todas as rodadas futuras.

Estimativa: \~2–4 horas de especialista para as 13 perguntas, considerando consulta direta às bases já indexadas.

### 4.4. Critérios de variação

**Para chunking (Fase 2a):**

- Tamanho do chunk (ex.: 256, 512, 1024 tokens)  
- Sobreposição (overlap) entre chunks (ex.: 0%, 10%, 20%)  
- Estratégia de divisão (sentence-aware, fixed-size, semantic, por seção/abstract)

**Para embedding (Fase 2b):**

- Modelo (ex.: `BGE-M3`, `multilingual-e5-large`, `nomic-embed-text-v1.5`, modelos biomédicos como `BioBERT` ou `PubMedBERT` se disponíveis em multilíngue)  
- Dimensionalidade (quando o modelo permite redução, ex.: Matryoshka embeddings)  
- Pooling/normalização

Cada fator candidato deve ser justificado e documentado. Recomenda-se limitar a 3–5 variantes por fase para manter o experimento tratável.

---

## 5\. Arquitetura de avaliação em três camadas

A avaliação de cada par `(resposta_gerada, resposta_humana)` passa por três camadas complementares, cada uma capturando aspectos distintos da qualidade.

### 5.1. Camada 1 — Métricas automáticas (RAGAS \+ auxiliares determinísticas)

**Objetivo:** Sinal automático, escalável e reproduzível em todas as configurações.

**Métricas calculadas (por pergunta):**

- `answer_correctness` — combina F1 factual (claim-based) \+ similaridade semântica  
- `faithfulness` — resposta está ancorada nos contextos recuperados?  
- `context_precision` — sinal/ruído dos chunks recuperados  
- `context_recall` — cobertura dos chunks necessários  
- `answer_relevancy` — pertinência da resposta à pergunta  
- `BERTScore-F1` (auxiliar) — similaridade semântica via embeddings BERT (determinística, sem LLM, *sanity check*)

**Insumos:** pergunta, resposta gerada, resposta humana (ground truth), contextos recuperados.

**Custo:** \~3 chamadas de LLM por linha (juiz Prometheus-2) para `answer_correctness`; demais métricas têm custo menor. Para 390 respostas, estima-se \~1.500 chamadas ao juiz na Camada 1\.

### 5.2. Camada 2 — Rubrica biomédica customizada (LLM-juiz com rubrica explícita)

**Objetivo:** Capturar aspectos que métricas estatísticas não capturam — particularmente erros biomédicos sutis e omissão de ressalvas clínicas.

**Implementação:** uma chamada por par de respostas ao Prometheus-2, com rubrica estruturada cobrindo:

- Correção factual contra a resposta humana  
- Completude — cobre os pontos essenciais?  
- Contradições — afirma algo oposto à referência?  
- Alucinação — afirmações não sustentadas pelo contexto recuperado?  
- Ressalvas omitidas — incertezas biológicas/clínicas descartadas?  
- Pertinência biomédica — uso correto de terminologia técnica?

**Saída:** score normalizado \[0, 1\] \+ feedback textual estruturado (para auditoria).

**Custo:** 1 chamada por par. Para 390 respostas: 390 chamadas.

### 5.3. Camada 3 — Anotação humana de falhas críticas

**Objetivo:** Identificar **erros biomédicos graves** que tanto métricas quanto LLM-juiz podem deixar passar.

**Implementação:** revisão dirigida por especialista. Para cada resposta gerada, marcar um **flag binário** `critical_failure_flag ∈ {0, 1}`:

- 1 \= contém afirmação biomédica grave incorreta, contraindicação omitida, erro de mecanismo molecular, atribuição errada de função gênica, ou outro erro clinicamente relevante.  
- 0 \= mesmo que parcialmente incorreta, não há erro grave.

**Estratégia para reduzir esforço humano:** priorizar revisão das respostas com scores baixos nas Camadas 1 e 2 (revisão amostral estratificada). Para a Rodada 1 (390 respostas), estima-se 4–8 horas de especialista revisando todas; metade disso se houver revisão amostral estratificada.

**Importante:** este sinal alimenta a métrica `CriticalFailureRate`, que tem peso elevado no `RankScore` final.

---

## 6\. Os dois experimentos: A (pipeline completo) e B (geração controlada)

### 6.1. Experimento A — Pipeline completo

pergunta → retrieval no Qdrant → LLM → resposta

Mede o desempenho **ponta-a-ponta** da combinação `{base, LLM}`. É o experimento principal e diretamente alinhado ao uso real do InteligenciÔmica.

**Configurações na Rodada 1:** 10 (2 × 5).

### 6.2. Experimento B — Geração controlada com contextos fixos

pergunta → contextos fixos (pré-determinados) → LLM → resposta

Os contextos recuperados são **congelados** para todos os 5 LLMs (proposta: usar os top-8 chunks da base `IDx_400k` como contexto canônico, ou alternativamente os top-8 escolhidos manualmente por especialista a partir da curadoria dos chunks-ouro).

**Objetivo:** isolar a habilidade de **síntese e fundamentação** do LLM, removendo o ruído do retrieval. Responde à pergunta: "dado o mesmo contexto, qual LLM responde melhor?"

**Configurações na Rodada 1:** 5 (apenas os LLMs variam).

### 6.3. Interpretação cruzada A vs. B

Comparar resultados dos dois experimentos é diagnóstico:

| Caso | Interpretação |
| :---- | :---- |
| LLM bom em A **e** em B | Modelo robusto, aproveita bem qualquer contexto |
| LLM bom em B, ruim em A | Bom sintetizador, mas falhou por retrieval ruim na sua base |
| LLM ruim em B, bom em A | Improvável; pode indicar dependência de chunks específicos ou ruído |
| LLM ruim em A **e** em B | Modelo fraco para o domínio |

---

## 7\. Métricas: por pergunta, agregadas e ranking executivo

### 7.1. Score final por pergunta (`FinalScore`)

Combinação das três camadas, evitando *double-counting*:

FinalScore\_{i, b, m} \=  
    0.45 · answer\_correctness        \# Camada 1 — já combina factual \+ semantic  
  \+ 0.20 · faithfulness              \# Camada 1 — ancoragem nos chunks  
  \+ 0.15 · rubric\_biomed\_score       \# Camada 2 — rubrica biomédica  
  \+ 0.10 · context\_recall            \# Camada 1 — cobertura do retrieval  
  \+ 0.05 · context\_precision         \# Camada 1 — sinal/ruído do retrieval  
  \+ 0.05 · answer\_relevancy          \# Camada 1 — pertinência

Pesos somam 1\. A justificativa dos pesos:

- `answer_correctness` (0.45) é o sinal central: combina precisão factual via claims e similaridade semântica em uma única métrica validada.  
- `faithfulness` (0.20) garante que a resposta esteja ancorada no contexto, evitando alucinação.  
- `rubric_biomed_score` (0.15) traz o sinal de domínio (biomedicina), não capturado pelas métricas genéricas.  
- `context_recall`/`context_precision` (0.10 \+ 0.05) avaliam a qualidade do retrieval.  
- `answer_relevancy` (0.05) penaliza respostas evasivas ou tangenciais.

**Nota técnica:** `answer_correctness` no RAGAS já incorpora internamente claim\_precision e claim\_recall. Listá-los separadamente na fórmula seria *double-counting* e foi explicitamente evitado.

### 7.2. Agregação por configuração `{base, LLM}`

Para cada `{b, m}`, são reportadas **todas** as estatísticas abaixo:

| Métrica | Definição |
| :---- | :---- |
| `MeanScore_{b,m}` | Média dos 13 `FinalScore` (×3 seeds \= 39 valores) |
| `MedianScore_{b,m}` | Mediana — mais robusta a outliers com n pequeno |
| `MinScore_{b,m}` | Pior caso da configuração |
| `IQR_{b,m}` | Intervalo interquartil — robustez central |
| `FailureRate_{b,m}` | % de respostas com `FinalScore < 0.70` |
| `CriticalFailureRate_{b,m}` | % de respostas com `critical_failure_flag = 1` (Camada 3\) |
| `WinRate_{b,m}` | Em quantas das 13 perguntas esta config teve o maior `FinalScore` |

### 7.3. RankScore executivo (ranking final único)

RankScore\_{b,m} \=  
      0.50 · MedianScore\_{b,m}  
    \+ 0.20 · (1 \- FailureRate\_{b,m})  
    \+ 0.15 · WinRate\_{b,m}  
    \- 0.15 · CriticalFailureRate\_{b,m}

Características:

- **Mediana em vez de média** — robusta a outliers com n=13.  
- **Termo de penalização por falhas** matematicamente bem-definido (`FailureRate ∈ [0,1]`).  
- **Termo de superioridade direta** via `WinRate`.  
- **Penalização explícita** por erro biomédico crítico — pode levar `RankScore` a valor negativo se o subsistema for inaceitável clinicamente, sinal forte no ranking.

---

## 8\. Análise estatística

Com n=13 perguntas e amostras pareadas (mesmas perguntas em todas as configurações), o desenho permite testes pareados com poder estatístico razoável.

### 8.1. Pergunta "qual base é melhor?"

**Teste:** Wilcoxon signed-rank pareado.  
**Pareamento:** cada pergunta `i` × LLM `m` produz um par `(score_IDx_400k, score_ID_230K)`.  
**N efetivo:** 13 perguntas × 5 LLMs × 3 seeds \= **195 pares** (após agregar seeds: 65 pares; sem agregar: 195).  
Conduzir o teste em cada métrica relevante (`answer_correctness`, `faithfulness`, `FinalScore`) separadamente.

### 8.2. Pergunta "qual LLM é melhor?"

**Teste:** Friedman para múltiplas amostras pareadas.  
**Pareamento:** cada pergunta × base produz uma linha com 5 colunas (uma por LLM).  
**N efetivo:** 13 × 2 × 3 \= 78 (sem agregar seeds) ou 26 (agregando seeds).  
**Post-hoc:** Nemenyi para identificar quais pares de LLMs diferem entre si.

### 8.3. Pergunta "existe interação base × LLM?"

**Teste:** Modelo Linear Misto (MLM) com pergunta como efeito aleatório.  
score \~ base \* llm \+ (1 | question)  
Permite estimar:

- Efeito principal de `base`  
- Efeito principal de `llm`  
- **Efeito de interação `base × llm`** (alguns modelos se beneficiam mais de uma base que outros)

**Ferramentas:** `statsmodels.formula.api.mixedlm` em Python ou `pymer4` (binding para `lme4` do R).

### 8.4. Controle de variabilidade não-determinística (seeds)

Mesmo com `temperature = 0.1`, há ruído de amostragem no LLM. **Três seeds fixos por configuração** permitem:

- Estimar desvio-padrão intra-configuração  
- Distinguir variabilidade do LLM da variabilidade entre configurações  
- Aumentar o N efetivo para os testes pareados

### 8.5. Correções para múltiplos testes

Quando rodando vários testes simultaneamente (uma por métrica), aplicar correção (Benjamini-Hochberg ou Holm) para controlar a taxa de falsas descobertas.

---

## 9\. LLM juiz: Prometheus-2 8x7B

### 9.1. Escolha justificada

**Prometheus-2 8x7B** foi escolhido como juiz padrão por:

- **Open-source** — sem custo por chamada e sem dependência externa.  
- **Especializado em avaliação** — modelo treinado explicitamente para *direct assessment* e *pairwise ranking*, com forte alinhamento a julgamentos humanos.  
- **Tamanho viável** — \~93 GB em FP16, \~26 GB em AWQ 4-bit. Cabe confortavelmente no GH200 (96 GB HBM3 ou 141 GB HBM3e) já em produção.  
- **Independente dos modelos avaliados** — não está entre os 5 LLMs sendo avaliados, evitando viés sistemático (modelo favorecer respostas geradas por si mesmo).

### 9.2. Configuração recomendada

| Parâmetro | Valor |
| :---- | :---- |
| Modelo | `prometheus-eval/prometheus-8x7b-v2.0` |
| Quantização | AWQ 4-bit |
| Servidor | vLLM (já em produção) |
| Temperatura | 0.0 (determinismo no juiz) |
| `max_model_len` | 8192 |
| Endpoint | OpenAI-compatible (`http://vllm-judge:8001/v1`) |

### 9.3. Mitigação de viés do juiz

- **Versionamento** — o `judge_model` é gravado em cada linha do dataset.  
- **Validação amostral humana** — para \~10% das respostas, comparar o score do juiz com avaliação humana especialista; calcular concordância (Cohen's κ).  
- **Múltiplos juízes opcionais** — em rodadas futuras, considerar comparar Prometheus-2 com outro juiz (ex.: Claude ou GPT-4o via API) em uma amostra reduzida, para checar consistência.

---

## 10\. Stack tecnológica

### 10.1. Componentes principais

| Componente | Função | Justificativa |
| :---- | :---- | :---- |
| **vLLM** | Servir todos os LLMs avaliados \+ juiz | Já em produção; alto throughput; suporte a quantização |
| **Qdrant** | Bases vetoriais `IDx_400k` e `ID_230K` | Já em produção |
| **RAGAS** | Camada 1 — métricas automáticas | Métricas RAG-específicas, integração nativa com ground truth |
| **DeepEval (G-Eval)** | Camada 2 — rubrica biomédica | Suporte a rubricas customizadas via LLM-juiz |
| **Prometheus-2 8x7B** | LLM juiz para Camadas 1 e 2 | Open-source, especializado em avaliação |
| **statsmodels / pymer4** | Análise estatística | Wilcoxon, Friedman, modelos lineares mistos |
| **pandas \+ polars** | Manipulação de dados | Padrão da indústria; polars para volumes maiores |
| **Parquet** | Armazenamento dos resultados | Compacto, colunar, tipado, particionável |
| **seaborn \+ matplotlib \+ plotly** | Visualização | Heatmaps, boxplots, plots de interação |

### 10.2. Ferramentas opcionais para fases futuras

- **TruLens ou Arize Phoenix** — observabilidade e tracing em produção  
- **LangSmith** — caso a stack migre para LangChain/LangGraph  
- **MLflow** — tracking de experimentos se houver necessidade de versionamento mais sofisticado

---

## 11\. Proposta de implementação e codificação

### 11.1. Estrutura modular (Clean Architecture)

inteligenciomica\_eval/  
├── domain/  
│   ├── entities.py              \# Question, Answer, Score, Config, Result  
│   ├── value\_objects.py         \# Métricas, pesos, thresholds  
│   └── ports.py                 \# Interfaces: Retriever, Generator, Judge, Storage  
├── application/  
│   ├── run\_experiment.py        \# Orquestrador de Experimento A ou B  
│   ├── compute\_metrics.py       \# Lógica de Camada 1 \+ Camada 2  
│   ├── aggregate\_results.py     \# Agregação por {base, LLM}  
│   └── statistical\_analysis.py  \# Wilcoxon, Friedman, MLM  
├── adapters/  
│   ├── qdrant\_retriever.py      \# Implementa Retriever  
│   ├── vllm\_generator.py        \# Implementa Generator (clientes vLLM)  
│   ├── prometheus\_judge.py      \# Implementa Judge via vLLM/RAGAS  
│   ├── ragas\_metrics.py         \# Wrappers das métricas RAGAS  
│   ├── deepeval\_geval.py        \# Wrapper da rubrica G-Eval  
│   └── parquet\_storage.py       \# Persistência em Parquet  
├── config/  
│   ├── experiment\_round1.yaml   \# Definição da Rodada 1  
│   ├── experiment\_round2a.yaml  \# Variação de chunking  
│   └── experiment\_round2b.yaml  \# Variação de embedding  
├── cli.py                       \# Typer CLI  
└── visualization/  
    ├── heatmaps.py  
    ├── boxplots.py  
    └── interaction\_plots.py

### 11.2. Schema de dados (formato tidy, salvo em Parquet)

run\_id              : str    \# identificador único da execução completa  
experiment\_phase    : str    \# "A" ou "B"  
round\_id            : str    \# "round\_1", "round\_2a", "round\_2b"  
base                : str    \# IDx\_400k | ID\_230K  
llm                 : str    \# nome do modelo gerador  
judge\_model         : str    \# Prometheus-2 8x7B  
embedding\_model     : str  
chunk\_strategy      : str    \# ex.: "fixed\_512\_overlap\_50"  
reranker            : str    \# ou "none"  
top\_k               : int  
prompt\_version      : str    \# versionamento explícito do prompt RAG  
temperature         : float  
seed                : int  
question\_id         : str  
question            : str  
ground\_truth        : str    \# resposta humana padronizada  
retrieved\_chunk\_ids : list\[str\]  
retrieved\_chunks\_text : list\[str\]  
retrieval\_scores    : list\[float\]  \# scores do Qdrant  
generated\_answer    : str

\# Métricas Camada 1  
answer\_correctness  : float  
answer\_similarity   : float  
faithfulness        : float  
context\_precision   : float  
context\_recall      : float  
answer\_relevancy    : float  
bertscore\_f1        : float

\# Métrica Camada 2  
rubric\_biomed\_score : float  
rubric\_feedback     : str    \# feedback textual estruturado do juiz

\# Métrica Camada 3  
critical\_failure\_flag : int  \# 0 ou 1 (anotação humana)  
critical\_failure\_note : str  \# observação opcional do anotador

\# Score consolidado  
final\_score         : float

\# Metadados de execução  
latency\_ms          : int  
tokens\_in           : int  
tokens\_out          : int  
timestamp           : datetime

**Particionamento sugerido:** `round_id / experiment_phase / base / llm`.

### 11.3. Pipeline de execução (alto nível)

\# Pseudocódigo de alto nível  
def run\_round\_1():  
    for base, llm in itertools.product(BASES, LLMS):  
        for seed in SEEDS:  
            for question in QUESTIONS:  
                \# Experimento A  
                contexts \= retriever.search(base, question, top\_k=TOP\_K)  
                answer \= generator.generate(llm, question, contexts, seed=seed)  
                metrics\_c1 \= compute\_layer1\_metrics(question, answer,  
                                                   contexts, ground\_truth)  
                metrics\_c2 \= compute\_layer2\_rubric(question, answer,  
                                                  contexts, ground\_truth)  
                save\_row(run\_id, "A", base, llm, ..., metrics\_c1, metrics\_c2)

    \# Experimento B \- contextos fixos  
    canonical\_contexts \= build\_canonical\_contexts()  \# top-8 de IDx\_400k  
    for llm in LLMS:  
        for seed in SEEDS:  
            for question in QUESTIONS:  
                answer \= generator.generate(llm, question,  
                                            canonical\_contexts\[question\], seed=seed)  
                metrics\_c1 \= compute\_layer1\_metrics(...)  
                metrics\_c2 \= compute\_layer2\_rubric(...)  
                save\_row(run\_id, "B", "fixed", llm, ..., metrics\_c1, metrics\_c2)

    \# Camada 3 \- anotação humana (offline, em interface separada)

    \# Após anotação, dados são merged ao Parquet

    \# Análise estatística e relatórios  
    df \= load\_parquet()  
    aggregates \= aggregate\_by\_config(df)  
    rank\_scores \= compute\_rank\_scores(aggregates)  
    stats \= run\_statistical\_tests(df)  
    generate\_report(df, aggregates, rank\_scores, stats)

### 11.4. Visualizações canônicas

1. **Heatmap N×M** (linhas=bases, colunas=LLMs) por métrica e por `RankScore`  
2. **Boxplots** comparando `IDx_400k` vs `ID_230K` por LLM  
3. **Plots de interação** (`base × LLM`) mostrando se o efeito da base depende do modelo  
4. **Radar charts** por configuração — visualiza trade-offs entre métricas  
5. **Per-question ranking** — para cada pergunta, qual config ganhou (heatmap question × config)  
6. **Failure breakdown** — para configurações com falhas, distribuição entre retrieval/faithfulness/síntese

### 11.5. Interface CLI

\# Rodar Rodada 1 completa  
ielm-eval run \--config config/experiment\_round1.yaml

\# Rodar apenas Experimento B  
ielm-eval run \--config config/experiment\_round1.yaml \--phase B

\# Análise estatística sobre resultados existentes  
ielm-eval analyze \--run-id round\_1\_20260601 \--tests all

\# Gerar relatório  
ielm-eval report \--run-id round\_1\_20260601 \--format html

\# Interface de anotação humana (Camada 3\)  
ielm-eval annotate \--run-id round\_1\_20260601

### 11.6. Padrões de qualidade de código

- **Type hints obrigatórios** em todas as funções públicas  
- **Docstrings** em todas as classes e funções  
- **Testes unitários** para lógica de scoring e agregação (pytest)  
- **Logging estruturado** via `structlog`  
- **Tratamento explícito de NaN** nas métricas RAGAS (frequência conhecida de falhas de parsing do juiz)  
- **Configurações em YAML** versionadas no Git  
- **Determinismo onde possível** — seeds fixos, sem aleatoriedade não controlada

---

## 12\. Riscos, limitações e mitigações

| Risco | Mitigação |
| :---- | :---- |
| **n=13 perguntas é baixo** | Múltiplos seeds, testes pareados, reportar mediana/IQR/percentis em vez de só média |
| **LLM-juiz pode ter viés** | Juiz independente dos modelos avaliados; validação amostral humana; opção futura de múltiplos juízes |
| **Anotação humana é cara** | Estratificar revisão pelas respostas com scores baixos; foco em erros graves binários, não pontuação fina |
| **Falha de parsing JSON do juiz (NaN frequente em RAGAS)** | Retry com max 3 tentativas; logar falhas; em último caso, marcar métrica como NaN e excluir da agregação |
| **Mudança de versão de framework** | Versionamento explícito (`ragas==X.Y.Z`) em `requirements.txt`; lock file |
| **Curadoria de chunks-ouro consome tempo de especialista** | Fazer uma vez, reaproveitar; estimar \~2-4h para 13 perguntas |
| **Variabilidade entre seeds maior que entre configurações** | Detectável via ANOVA preliminar; se ocorrer, aumentar número de seeds ou questionar diferenças reportadas |
| **Inconsistência entre Camadas 1, 2 e 3** | Esperada — cada uma captura algo diferente. Documentar discrepâncias é insight, não bug |

---

## 13\. Glossário

### 13.1. Conceitos gerais

- **RAG (Retrieval-Augmented Generation)** — Arquitetura em que o LLM gera respostas a partir de contextos recuperados de uma base externa (no caso, Qdrant), em vez de depender apenas do conhecimento internalizado.  
- **LLM (Large Language Model)** — Modelo de linguagem de grande porte. Neste projeto, refere-se aos 5 modelos avaliados.  
- **LLM-as-judge / LLM juiz** — Uso de um LLM para avaliar a qualidade de respostas geradas por outros LLMs, tipicamente com rubrica estruturada.  
- **Ground truth** — Resposta de referência considerada correta. No InteligenciÔmica, são as 13 respostas padronizadas escritas por humanos.  
- **Chunk** — Trecho de texto extraído de um artigo científico durante a indexação. O tamanho e a estratégia de chunking afetam diretamente a qualidade do retrieval.  
- **Embedding** — Representação vetorial densa de um chunk de texto. O modelo de embedding determina como a similaridade semântica é capturada.  
- **Top-k** — Número de chunks mais similares à pergunta que o Qdrant retorna em cada busca.  
- **Reranker** — Modelo opcional aplicado após o retrieval inicial que reordena os chunks com critério mais sofisticado.  
- **Seed** — Semente de aleatoriedade que torna a geração do LLM reproduzível. Múltiplos seeds permitem estimar variabilidade.  
- **Tidy data** — Estrutura tabular em que cada linha é uma observação e cada coluna uma variável; padrão para análise estatística.  
- **Parquet** — Formato de arquivo colunar, compacto e tipado, padrão para datasets analíticos.  
- **OFAT (One-Factor-At-a-Time)** — Princípio experimental de variar um único fator por vez, isolando seu efeito.  
- **Claim (afirmação)** — Unidade factual atômica extraída de uma resposta (ex.: "BRCA1 está localizado no cromossomo 17"). Usado para decomposição factual.  
- **Faithfulness** — Grau em que a resposta gerada está ancorada (fundamentada) nos contextos recuperados.  
- **AWQ (Activation-aware Weight Quantization)** — Técnica de quantização que reduz precisão dos pesos do modelo (ex.: 4-bit) com perda mínima de qualidade, reduzindo uso de memória.  
- **vLLM** — Servidor de inferência de LLM de alto throughput, com suporte a *paged attention* e quantização.  
- **KV-cache** — Cache de chaves/valores do mecanismo de atenção, ocupa memória proporcional ao contexto e ao batch.

### 13.2. Métricas RAGAS (Camada 1\)

- **`answer_correctness`** — Combinação ponderada de **F1 factual baseada em claims** (TP, FP, FN entre afirmações da resposta gerada e da ground truth) e **`SemanticSimilarity`** (cosseno de embeddings). Score em \[0, 1\]; quanto maior, mais correta a resposta.  
- **`answer_similarity` / `SemanticSimilarity`** — Cosseno entre embeddings da resposta gerada e da ground truth. Captura paráfrases corretas, mas pode ignorar erros factuais sutis.  
- **`faithfulness`** — Fração das afirmações da resposta que podem ser inferidas dos contextos recuperados. Detecta alucinação. Score em \[0, 1\].  
- **`context_precision`** — Fração dos chunks recuperados que são relevantes para responder à pergunta. Mede sinal/ruído do retrieval.  
- **`context_recall`** — Fração das afirmações da ground truth cuja informação está nos contextos recuperados. Mede cobertura do retrieval.  
- **`answer_relevancy`** — Pertinência da resposta em relação à pergunta. Detecta respostas evasivas, tangenciais ou que não endereçam a pergunta.  
- **`FactualCorrectness`** *(opcional, alternativa a `answer_correctness`)* — Apenas o componente F1 factual baseado em claims, sem componente semântico.

### 13.3. Métricas auxiliares (Camada 1\)

- **BERTScore-F1** — Similaridade semântica entre resposta e ground truth, calculada via embeddings BERT contextuais e alinhamento token-a-token. Determinística, sem LLM.  
- **ROUGE-L** *(opcional)* — Sobreposição da maior subsequência comum (LCS) entre resposta e referência. Determinística e barata, mas penaliza paráfrases corretas.

### 13.4. Métrica customizada (Camada 2\)

- **`rubric_biomed_score`** — Score \[0, 1\] gerado pelo Prometheus-2 aplicando uma rubrica biomédica estruturada cobrindo correção factual, completude, contradições, alucinação, ressalvas omitidas e pertinência biomédica.

### 13.5. Métrica binária (Camada 3\)

- **`critical_failure_flag`** — Flag binário {0, 1} marcado por especialista humano indicando se a resposta contém erro biomédico grave (afirmação clinicamente perigosa, mecanismo molecular errado, atribuição funcional incorreta, etc.).

### 13.6. Métricas de retrieval puro (Rodada 2\)

- **`precision@k`** — Dos `k` chunks recuperados, quantos estão na lista de chunks-ouro? Mede precisão do retriever.  
- **`recall@k`** — Dos chunks-ouro, quantos foram recuperados nos top-`k`? Mede cobertura do retriever.  
- **MRR (Mean Reciprocal Rank)** — Média de `1/rank` do primeiro chunk relevante recuperado. Quanto mais cedo aparece o primeiro relevante, maior o MRR.  
- **nDCG@k (Normalized Discounted Cumulative Gain)** — Score que pondera a relevância dos chunks pela posição em que aparecem (chunks relevantes nas primeiras posições contribuem mais). Normalizado em \[0, 1\].

### 13.7. Métricas agregadas por configuração

- **`MeanScore_{b,m}`** — Média aritmética dos `FinalScore` das 13 perguntas (× 3 seeds).  
- **`MedianScore_{b,m}`** — Mediana dos `FinalScore`. Robusta a outliers, preferível à média com n pequeno.  
- **`MinScore_{b,m}`** — Mínimo, indica pior caso da configuração.  
- **`IQR_{b,m}` (Intervalo Interquartil)** — Diferença entre o 3º e 1º quartis. Métrica robusta de dispersão.  
- **`FailureRate_{b,m}`** — Proporção de respostas com `FinalScore < 0.70` (threshold ajustável).  
- **`CriticalFailureRate_{b,m}`** — Proporção de respostas com `critical_failure_flag = 1`.  
- **`WinRate_{b,m}`** — Em quantas das 13 perguntas esta configuração obteve o maior `FinalScore` entre todas as configurações.  
- **`RankScore_{b,m}`** — Score executivo final que combina mediana, FailureRate, WinRate e CriticalFailureRate. Usado para ranking único.

### 13.8. Estatística

- **Pareamento de amostras** — Quando cada observação em uma condição tem correspondência direta em outra condição (mesma pergunta em duas configurações). Permite testes com maior poder estatístico.  
- **Wilcoxon signed-rank** — Teste não-paramétrico para amostras pareadas. Compara duas condições (ex.: `IDx_400k` vs `ID_230K`) sem pressupor distribuição normal.  
- **Friedman test** — Generalização não-paramétrica do Wilcoxon para mais de duas amostras pareadas (ex.: comparação entre 5 LLMs).  
- **Nemenyi post-hoc** — Teste para identificar quais pares de grupos diferem entre si após Friedman indicar diferença global.  
- **Modelo Linear Misto (MLM, *Mixed Linear Model*)** — Regressão que combina efeitos fixos (ex.: `base`, `llm`) e aleatórios (ex.: `pergunta`), apropriada para dados pareados/hierárquicos.  
- **Efeito de interação** — Quando o efeito de um fator depende do nível de outro fator (ex.: o ganho de usar `IDx_400k` é maior para uns LLMs que para outros).  
- **Benjamini-Hochberg / Holm** — Métodos de correção para múltiplos testes, controlando a taxa de falsas descobertas (FDR) ou o erro familiar (FWER).  
- **Cohen's κ (kappa)** — Medida de concordância entre dois avaliadores (ex.: LLM-juiz vs humano), corrigindo a concordância esperada por acaso.

---

## 14\. Referências e links úteis

### 14.1. Frameworks de avaliação

- **RAGAS** — [https://docs.ragas.io](https://docs.ragas.io)  
  - Conceito de métricas disponíveis: [https://docs.ragas.io/en/stable/concepts/metrics/available\_metrics/](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)  
  - `AnswerCorrectness`: [https://docs.ragas.io/en/v0.1.21/concepts/metrics/answer\_correctness.html](https://docs.ragas.io/en/v0.1.21/concepts/metrics/answer_correctness.html)  
  - `SemanticSimilarity`: [https://docs.ragas.io/en/stable/concepts/metrics/available\_metrics/semantic\_similarity/](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/semantic_similarity/)  
- **DeepEval** — [https://www.deepeval.com](https://www.deepeval.com)  
  - G-Eval: [https://www.deepeval.com/docs/metrics-llm-evals](https://www.deepeval.com/docs/metrics-llm-evals)  
- **TruLens** — [https://www.trulens.org](https://www.trulens.org)  
  - RAG Triad: [https://www.trulens.org/getting\_started/core\_concepts/rag\_triad/](https://www.trulens.org/getting_started/core_concepts/rag_triad/)  
- **Arize Phoenix** — [https://arize.com/docs/phoenix](https://arize.com/docs/phoenix)  
- **LangSmith** — [https://docs.smith.langchain.com/evaluation](https://docs.smith.langchain.com/evaluation)  
- **Promptfoo** — [https://www.promptfoo.dev](https://www.promptfoo.dev)

### 14.2. Modelo juiz Prometheus-2

- **Paper Prometheus 2** — [https://arxiv.org/abs/2405.01535](https://arxiv.org/abs/2405.01535)  
- **Pesos 8x7B (HuggingFace)** — [https://huggingface.co/prometheus-eval/prometheus-8x7b-v2.0](https://huggingface.co/prometheus-eval/prometheus-8x7b-v2.0)  
- **Pesos 7B (HuggingFace)** — [https://huggingface.co/prometheus-eval/prometheus-7b-v2.0](https://huggingface.co/prometheus-eval/prometheus-7b-v2.0)  
- **Pacote `prometheus-eval` (GitHub)** — [https://github.com/prometheus-eval/prometheus-eval](https://github.com/prometheus-eval/prometheus-eval)

### 14.3. Servidor de inferência

- **vLLM** — [https://docs.vllm.ai](https://docs.vllm.ai)  
- **vLLM AWQ quantization** — [https://docs.vllm.ai/en/latest/quantization/auto\_awq.html](https://docs.vllm.ai/en/latest/quantization/auto_awq.html)

### 14.4. Banco vetorial

- **Qdrant** — [https://qdrant.tech/documentation/](https://qdrant.tech/documentation/)  
- **Qdrant Python Client** — [https://github.com/qdrant/qdrant-client](https://github.com/qdrant/qdrant-client)

### 14.5. Métricas auxiliares

- **BERTScore** — [https://github.com/Tiiiger/bert\_score](https://github.com/Tiiiger/bert_score)  
- **ROUGE (Python)** — [https://github.com/google-research/google-research/tree/master/rouge](https://github.com/google-research/google-research/tree/master/rouge)

### 14.6. Análise estatística

- **`statsmodels` (Python)** — [https://www.statsmodels.org](https://www.statsmodels.org)  
- **`pymer4` (binding lme4)** — [https://eshinjolly.com/pymer4/](https://eshinjolly.com/pymer4/)  
- **`scipy.stats.wilcoxon`** — [https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html)  
- **`scipy.stats.friedmanchisquare`** — [https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.friedmanchisquare.html](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.friedmanchisquare.html)  
- **`scikit-posthocs.posthoc_nemenyi_friedman`** — [https://scikit-posthocs.readthedocs.io](https://scikit-posthocs.readthedocs.io)

### 14.7. Papers de referência conceitual

- **RAGAS paper** — Shahul Es et al., "RAGAS: Automated Evaluation of Retrieval Augmented Generation", 2023 — [https://arxiv.org/abs/2309.15217](https://arxiv.org/abs/2309.15217)  
- **G-Eval paper** — Liu et al., "G-Eval: NLG Evaluation using GPT-4 with Better Human Alignment", 2023 — [https://arxiv.org/abs/2303.16634](https://arxiv.org/abs/2303.16634)  
- **BERTScore paper** — Zhang et al., "BERTScore: Evaluating Text Generation with BERT", 2020 — [https://arxiv.org/abs/1904.09675](https://arxiv.org/abs/1904.09675)  
- **Prometheus 2 paper** — Kim et al., 2024 — [https://arxiv.org/abs/2405.01535](https://arxiv.org/abs/2405.01535)

### 14.8. Guias práticos

- **HuggingFace Evaluation Guidebook** — [https://github.com/huggingface/evaluation-guidebook](https://github.com/huggingface/evaluation-guidebook)  
- **HuggingFace Metric List** — [https://huggingface.co/docs/lighteval/metric-list](https://huggingface.co/docs/lighteval/metric-list)

---

**Documento elaborado para discussão técnica com a equipe de desenvolvimento do InteligenciÔmica.** **Próximos passos sugeridos:** revisão pela equipe, definição dos parâmetros *baseline* (chunking, embedding, top-k, reranker), curadoria dos chunks-ouro pelas 13 perguntas, e definição do cronograma das Rodadas 1 e 2\.  
