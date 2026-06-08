# Arquitetura Detalhada e Plano de Implementação — Subsistema de Validação do InteligenciÔmica

**Versão:** 1.2
**Data:** 8 de junho de 2026
**Status:** Proposta arquitetural para execução (deriva do documento de visão de alto nível v1.0, já aprovado pela equipe)
**Documento-base:** `visao_alto_nivel_validacao_inteligenciomica.md` (v1.0)
**Aprofunda:** itens 10 (stack), 11 (implementação/codificação) e 12 (riscos) do documento-base.
**Destino:** servir de espinha dorsal para os prompts da dupla **Claude Code (desenvolvedor)** + **ChatGPT Codex (verificador)**.

> **Changelog v1.2 (08/06/2026):** sincronização com o as-built de TAREFA-309/310/311/312/606. Destaques: (1) mecanismo de perguntas via `RoundConfig.questions` + campo `questions:` no YAML de rodada (multi-área, TAREFA-313); (2) CLI `run` completo com `--run-id` obrigatório, `--phase A|B|both`, `--serial`, `--require-verified-determinism` (§15); (3) modo de implantação `external` — cliente x86 ↔ túnel SSH ↔ servidores vLLM/Qdrant compartilhados no GH200 — com proveniência verificada por sonda (ADR-014, TAREFA-311); (4) três novas colunas de proveniência no schema Parquet 43→46 (`server_mode`, `served_model_id`, `determinism_verified` — **já atualizadas em §§4.3/5.3 no gate 312**, não duplicadas aqui); (5) gate de integração TAREFA-312 (PASS); (6) **ADR-013** (funil da Rodada 2, M5 adiado) e **ADR-014** (managed vs external) adicionados ao catálogo (§6); (7) topologia §7.2 e §12 expandidos com o modo external; (8) §14.6/14.9 reconciliados; (9) §15 alinhado à CLI real (8 subcomandos).

> **Changelog v1.1 (22/05/2026):** correção do hardware — o nó é um **GH200 com 4 GPUs**, integralmente disponível (antes assumido como GPU única). Impacto: Premissa P1 revisada; **ADR-004 reescrito** (alocação concorrente em 4 GPUs em vez de chaveamento sequencial); **novo ADR-012** (estratégia de alocação de GPUs e tensor parallelism); topologia (§7.2), milestone M3 (§14.6) e manual de operação (§15.4–15.8) atualizados. As três camadas de avaliação, ports, esquema de dados e demais ADRs permanecem inalterados.

---

## Sumário

1. [Como usar este documento](#1-como-usar-este-documento)
2. [Contexto arquitetural e requisitos](#2-contexto-arquitetural-e-requisitos)
3. [Visão C4](#3-visão-c4)
4. [Modelo de domínio (DDD)](#4-modelo-de-domínio-ddd)
5. [Contratos: Ports, DTOs e esquema de dados](#5-contratos-ports-dtos-e-esquema-de-dados)
6. [Catálogo de ADRs](#6-catálogo-de-adrs)
7. [Stack tecnológica detalhada (aprofunda item 10)](#7-stack-tecnológica-detalhada-aprofunda-item-10)
8. [Estrutura de código detalhada (aprofunda item 11)](#8-estrutura-de-código-detalhada-aprofunda-item-11)
9. [Estratégia de exceções](#9-estratégia-de-exceções)
10. [Estratégia de observabilidade](#10-estratégia-de-observabilidade)
11. [Estratégia de testes (paralela ao desenvolvimento)](#11-estratégia-de-testes-paralela-ao-desenvolvimento)
12. [Configuração, reprodutibilidade e proveniência](#12-configuração-reprodutibilidade-e-proveniência)
13. [Riscos aprofundados (aprofunda item 12)](#13-riscos-aprofundados-aprofunda-item-12)
14. [Plano de implementação em milestones](#14-plano-de-implementação-em-milestones)
15. [Manual de operação e ambiente (GH200 + vLLM)](#15-manual-de-operação-e-ambiente-gh200--vllm)
16. [Workflow AI-assisted: Claude Code (dev) + Codex (verificador)](#16-workflow-ai-assisted-claude-code-dev--codex-verificador)
17. [Checklists de prontidão](#17-checklists-de-prontidão)
18. [Próximos passos](#18-próximos-passos)

---

## 1. Como usar este documento

Este documento tem três audiências e três usos:

- **Para a equipe técnica** — é o contrato arquitetural. Define camadas, ports, DTOs, esquema de dados e ADRs. Mudanças estruturais passam por um novo ADR aqui.
- **Para o desenvolvedor sênior + Claude Code** — a seção 8 (estrutura de código), a seção 14 (milestones com critérios de aceitação) e a seção 16 (workflow) são o roteiro de implementação. Cada tarefa de milestone vira um prompt.
- **Para o operador (quem roda os experimentos)** — a seção 15 é o manual de bancada: como subir o vLLM no GH200, chavear modelos, conectar ao Qdrant e disparar cada rodada.

**Princípio de leitura:** as seções 3–13 descrevem *o que* construir e *por quê*; a seção 14 descreve *em que ordem*; as seções 15–16 descrevem *como operar e como produzir o código com IA*.

**Convenção de rastreabilidade:** toda decisão não-óbvia tem um `ADR-NNN`. Toda tarefa de implementação tem um `TAREFA-NNN` e pertence a um milestone `Mx`. Os prompts da dupla Code/Codex referenciam esses identificadores diretamente.

---

## 2. Contexto arquitetural e requisitos

### 2.1. Objetivo de negócio

Decidir, com **evidência estatística e reprodutível**, qual combinação `{base vetorial, LLM}` o InteligenciÔmica deve usar em produção, e diagnosticar a origem dos erros (retrieval, fundamentação ou síntese). O subsistema é uma **ferramenta de decisão offline**, não um componente de produção em tempo real.

### 2.2. Requisitos funcionais (RF)

- **RF1** — Executar o Experimento A (pipeline completo) e o Experimento B (geração controlada) sobre 13 perguntas, N bases, M LLMs e K seeds, persistindo cada resposta e suas métricas.
- **RF2** — Calcular as três camadas de avaliação: métricas automáticas (RAGAS + auxiliares), rubrica biomédica (LLM-juiz) e ingestão da anotação humana de falhas críticas.
- **RF3** — Agregar por configuração `{base, LLM}` e produzir o `RankScore` executivo.
- **RF4** — Rodar a bateria estatística (Wilcoxon, Friedman+Nemenyi, modelo linear misto) com correção para múltiplos testes.
- **RF5** — Gerar relatórios e visualizações canônicas (heatmaps, boxplots, plots de interação, breakdown de falhas).
- **RF6** — Suportar a Rodada 2 (OFAT em chunking e embedding) com o funil de retrieval puro como pré-filtro barato.
- **RF7** — Ser **resumível**: uma execução interrompida retoma sem reprocessar o que já foi persistido.
- **RF8** — Registrar proveniência total (versões, seeds, regime de determinismo, hashes de config) em cada linha do dataset.

### 2.3. Requisitos não-funcionais (RNF)

- **RNF1 — Reprodutibilidade científica.** O juiz é determinístico bit-a-bit (`VLLM_BATCH_INVARIANT=1`); os geradores são realistas (sem batch invariance). Esta distinção é arquitetural e inviolável (ADR-003). Em modo **`managed`**, o determinismo do juiz é **garantido** pelo lançamento controlado do servidor (GPU dedicada, env fixo). Em modo **`external`**, o servidor vLLM já existe e é compartilhado — o determinismo é **responsabilidade do operador** e apenas **verificado** por sonda (`probe_judge_determinism`), nunca assumido; o resultado fica gravado no campo `determinism_verified` (ADR-014).
- **RNF2 — Uso eficiente das 4 GPUs.** O nó GH200 tem **4 GPUs** integralmente disponíveis. A arquitetura aloca o juiz numa GPU dedicada (residente) e gira os 5 geradores nas 3 GPUs restantes, em ondas concorrentes, minimizando trocas de modelo (ADR-004/ADR-012).
- **RNF3 — Robustez a falha do juiz.** Falhas de parsing/NaN do LLM-juiz são esperadas e tratadas com retry + degradação explícita, nunca silenciosa (ADR-007).
- **RNF4 — Evolutibilidade.** Adicionar um LLM, uma base, uma métrica ou um juiz não pode exigir reescrever o orquestrador — só um adapter e uma entrada de config.
- **RNF5 — Testabilidade.** Domínio puro testável sem GPU/rede; adapters testáveis com fakes; um caminho E2E rodável em CPU com modelos *stub*.
- **RNF6 — Observabilidade.** Logging estruturado por `run_id`/`question_id`, com latência por etapa, tokens, custo e regime de determinismo.

### 2.4. Restrições

- Stack já em produção: **Qdrant** (bases `IDx_400k`, `ID_230K`), **vLLM** sobre **GH200**.
- Linguagem: **Python** (Clean Architecture, padrões das skills personalizadas do projeto).
- Persistência analítica: **Parquet tidy** (sem banco relacional nesta fase).
- Desenvolvimento **100% AI-assisted** (Claude Code desenvolve, Codex verifica), por um desenvolvedor sênior.

### 2.5. Premissas (marcadas explicitamente)

- **P1** — O nó **GH200 tem 4 GPUs** (presumivelmente 4× superchip Grace-Hopper, ~96–141 GB HBM cada), **integralmente disponível** para estes testes. Logo: o juiz roda numa GPU dedicada com `tensor_parallel_size=1` (pré-requisito de batch invariance) e os 5 geradores giram nas demais GPUs de forma concorrente (ADR-012). *Confirmado pela equipe de infra.*
- **P1.1** — Cada modelo, na quantização de produção, cabe em **uma** GPU. *Verificar o footprint por modelo no M0:* se `gpt-oss-120b` ou `llama4:16x17b` exceder uma GPU, esse gerador usa `tensor_parallel_size=2` (permitido — geradores são não-determinísticos por desenho; só o juiz exige TP=1).
- **P2** — Os 5 LLMs avaliados já têm artefatos de pesos disponíveis localmente ou via HuggingFace acessível pela máquina. *Confirmar acesso e quantizações.*
- **P3** — A versão do vLLM instalada suporta `VLLM_BATCH_INVARIANT=1`. *Confirmar versão exata; registrá-la em `vllm_version`.*
- **P4** — As 13 perguntas e suas respostas humanas (ground truth) estão padronizadas e versionadas antes da Rodada 1.
- **P5** — A curadoria de chunks-ouro (pré-requisito da Rodada 2) será entregue por especialista antes do milestone correspondente.

> Premissas erradas invalidam decisões a jusante. Cada uma vira um item de verificação no início do milestone M0.

---

## 3. Visão C4

### 3.1. Nível 1 — Contexto

```
                          ┌──────────────────────────────────────┐
   Desenvolvedor Sênior   │                                        │
   (opera via CLI) ──────▶│   Subsistema de Validação              │
                          │   InteligenciÔmica (offline)           │
   Especialista Biomédico │                                        │
   (anota falhas, cura ──▶│  - orquestra experimentos A/B          │
    chunks-ouro)          │  - calcula 3 camadas de avaliação      │
                          │  - agrega + ranqueia + testa estat.    │
                          │  - gera relatórios                     │
                          └───────┬───────────┬───────────┬────────┘
                                  │           │           │
                          ┌───────▼───┐ ┌─────▼─────┐ ┌───▼────────────┐
                          │  Qdrant   │ │vLLM juiz  │ │ vLLM geradores │
                          │ (2 bases) │ │Prometheus2│ │ (5 LLMs, prod) │
                          │ produção  │ │det. bit-a-│ │ realista       │
                          │           │ │bit        │ │                │
                          └───────────┘ └───────────┘ └────────────────┘
```

Atores externos: o **desenvolvedor sênior** (executa rodadas, analisa) e o **especialista biomédico** (Camada 3 e curadoria de chunks-ouro). Sistemas externos: **Qdrant** (leitura), **vLLM-juiz** e **vLLM-geradores** (dois serviços OpenAI-compatible distintos — ADR-003).

### 3.2. Nível 2 — Containers

```
┌──────────────────────────────────────────────────────────────────────────┐
│  inteligenciomica_eval  (pacote Python, monolito modular)                  │
│                                                                            │
│  ┌────────────┐   ┌──────────────────┐   ┌───────────────────────────┐    │
│  │  cli/      │   │  application/     │   │  domain/                  │    │
│  │  (Typer)   │──▶│  use cases:       │──▶│  entidades, VOs, ports    │    │
│  │  run/      │   │  - run_experiment │   │  (puro, sem I/O)          │    │
│  │  analyze/  │   │  - compute_metrics│   └───────────────────────────┘    │
│  │  report/   │   │  - aggregate      │              ▲                      │
│  │  annotate/ │   │  - statistics     │              │ implementam          │
│  │  serve/    │   └─────────┬─────────┘   ┌──────────┴───────────────┐     │
│  └────────────┘             │             │  infrastructure/adapters │     │
│                             ▼             │  - QdrantRetriever        │     │
│                   ┌───────────────────┐   │  - VLLMGenerator          │     │
│                   │ infrastructure/   │   │  - PrometheusJudge        │     │
│                   │ storage (Parquet) │   │  - RagasMetrics           │     │
│                   │ provenance        │   │  - DeepEvalGEval          │     │
│                   └─────────┬─────────┘   │  - ParquetStorage         │     │
│                             │             │  - VLLMServerManager      │     │
│                             ▼             └──────────────────────────-┘     │
│                   ┌───────────────────┐                                     │
│                   │  data lake local  │   ┌──────────────────────────┐      │
│                   │  *.parquet (tidy) │   │ visualization/ (plots)   │      │
│                   │  partição por     │   │ + report (HTML/MD)       │      │
│                   │  round/phase/...  │   └──────────────────────────┘      │
│                   └───────────────────┘                                     │
└──────────────────────────────────────────────────────────────────────────┘
        │ HTTP (OpenAI API)        │ HTTP (OpenAI API)      │ gRPC/HTTP
        ▼                          ▼                        ▼
   vllm-generator:8000        vllm-judge:8001          Qdrant:6333
   (sem batch invariance)     (VLLM_BATCH_INVARIANT=1)  (2 coleções)
```

### 3.3. Nível 3 — Componentes do núcleo de avaliação (`application` + `domain`)

O container crítico é o motor de avaliação. Decomposto por responsabilidade:

```
application/
  RunExperimentUseCase ──┬─▶ RetrieverPort        (busca chunks no Qdrant)   [só Exp. A]
                         ├─▶ GeneratorPort         (gera resposta no vLLM-gen)
                         └─▶ ResultWriterPort      (persiste linha tidy)

  ComputeMetricsUseCase ─┬─▶ MetricSuitePort       (RAGAS: camada 1)
                         ├─▶ RubricJudgePort       (DeepEval/Prometheus: camada 2)
                         ├─▶ DeterministicMetricPort (BERTScore/ROUGE: camada 1 aux)
                         └─▶ ResultWriterPort

   AggregateResultsUseCase ─▶ ResultReaderPort + ScoringService(domínio)
  StatisticalAnalysisUseCase ─▶ ResultReaderPort + StatsPort
  IngestHumanAnnotationUseCase ─▶ AnnotationReaderPort + ResultWriterPort
  RetrievalFunnelUseCase   ─▶ RetrieverPort + GoldChunkReaderPort  [Rodada 2]

domain/
  Entidades: Question, GeneratedAnswer, EvaluationResult, ConfigCell
  Value Objects: BaseId, LLMId, Seed, FinalScore, RankScore, MetricVector
  Serviços de domínio (puros): FinalScoreCalculator, RankScoreCalculator,
                               AggregationService, FunnelSelector
  Ports: (todas as interfaces acima, como typing.Protocol)
```

**Pontos de extensão explícitos** (RNF4):
- Novo LLM → nova entrada em `model_registry.yaml` + (se protocolo diferente) novo adapter de `GeneratorPort`.
- Nova métrica automática → novo adapter de `MetricSuitePort` ou `DeterministicMetricPort`; o `FinalScoreCalculator` lê pesos da config.
- Novo juiz → novo adapter de `RubricJudgePort` (ex.: Claude/GPT-4o via API), selecionável por config.
- Nova rodada/fator (chunking/embedding) → novo arquivo `experiment_*.yaml`; o orquestrador é agnóstico ao fator variado.

### 3.4. Fluxo de dados — caso de uso principal (Experimento A, happy path)

```
1. CLI `run --config round1.yaml --phase A`
2. RunExperimentUseCase itera (base, llm, seed, question) — produto cartesiano da config
3. Para cada célula:
   a. RetrieverPort.search(base, question, top_k)        → contexts + scores  [Qdrant]
   b. GeneratorPort.generate(llm, question, contexts, seed) → answer          [vLLM-gen]
   c. ResultWriterPort.append(linha parcial: pergunta, resposta, contexts, proveniência)
4. (passada separada) ComputeMetricsUseCase lê linhas sem métricas:
   a. MetricSuitePort.score(...)        → camada 1     [vLLM-judge]
   b. RubricJudgePort.score(...)        → camada 2     [vLLM-judge]
   c. DeterministicMetricPort.score(...)→ aux          [CPU/GPU local]
   d. ResultWriterPort.update(linha com métricas)
5. AggregateResultsUseCase + StatisticalAnalysisUseCase sobre o Parquet
6. report → HTML/MD + figuras
```

> A separação entre o passo 3 (geração) e o passo 4 (julgamento) permanece **logicamente** desacoplada — é a base da resumabilidade (ADR-009) e permite re-julgar com outro juiz no futuro. Com 4 GPUs (ADR-012), porém, o juiz fica **residente numa GPU dedicada** e os geradores ocupam as outras 3, de modo que os dois passos **podem rodar em paralelo (pipeline)** em tempo de parede, sem violar o determinismo do juiz (processos/GPUs separados; batch invariance é invariante à composição do batch). Na implementação inicial (M3), mantêm-se como duas fases para simplicidade, com o juiz já carregado — o pipelining é otimização opcional.

### 3.5. Fluxo de dados — cenário de falha (parsing do juiz)

```
ComputeMetricsUseCase → RubricJudgePort.score(...)
   → juiz retorna texto não-parseável como JSON
   → adapter tenta retry (até 3x) com prompt reforçado          [ADR-007]
   → ainda falha → marca rubric_biomed_score = NaN + loga WARNING estruturado
   → linha é persistida com flag de falha; agregação EXCLUI NaN explicitamente
   → run report contabiliza taxa de NaN por configuração (sinal de saúde do juiz)
```

Nunca uma falha de juiz derruba a rodada inteira; ela é isolada por célula e contabilizada.

---

## 4. Modelo de domínio (DDD)

### 4.1. Linguagem onipresente

| Termo | Significado no código | Tipo |
|---|---|---|
| **Question** | Uma das 13 perguntas + sua ground truth | Entidade |
| **ConfigCell** | Uma combinação `{base, llm, seed}` (Exp. A) ou `{llm, seed}` (Exp. B) | Value Object |
| **GeneratedAnswer** | Resposta produzida por um LLM para uma `Question` numa `ConfigCell` | Entidade |
| **EvaluationResult** | `GeneratedAnswer` + as métricas das 3 camadas + `FinalScore` | Agregado raiz |
| **MetricVector** | Conjunto imutável das métricas de Camada 1+2 de uma resposta | Value Object |
| **ConfigAggregate** | Estatísticas agregadas de uma config `{base, llm}` (Mean/Median/IQR/...) | Value Object |
| **RankScore** | Score executivo único por configuração | Value Object |
| **DeterminismRegime** | `judge` (batch-invariant) ou `generator` (realista) | Value Object (enum) |

### 4.2. Bounded contexts

O subsistema é pequeno o bastante para um único bounded context (**Evaluation**), mas com três sub-domínios coesos que justificam pastas separadas:

- **Experimentation** — orquestra geração de respostas (A e B) e o funil de retrieval (Rodada 2).
- **Scoring** — calcula métricas das 3 camadas e consolida o `FinalScore`.
- **Analysis** — agrega por configuração, calcula `RankScore` e roda a estatística.

Os três compartilham as mesmas entidades de domínio e o mesmo armazenamento Parquet; não há necessidade de microserviços (anti-pattern rejeitado — ver ADR-001).

### 4.3. Agregado raiz: `EvaluationResult`

`EvaluationResult` é a unidade de consistência: uma linha do dataset tidy. Suas invariantes (validadas na criação):

- `final_score ∈ [0, 1]` ou `NaN` explícito (nunca `None` silencioso).
- Pesos do `FinalScore` somam 1.0 (validado no `FinalScoreCalculator`, não na entidade).
- `batch_invariant == True` ⇔ a métrica veio de chamada ao juiz; `False` ⇔ veio do gerador. Coerência verificada na escrita.
- `critical_failure_flag ∈ {0, 1}` quando presente; ausente até a Camada 3 ser ingerida.
- `seed`, `temperature`, `prompt_version`, `embedding_model`, `chunk_strategy`, `judge_model`, `vllm_version` **sempre** preenchidos (proveniência — RF8).
- `server_mode ∈ {"managed", "external"}` — modo de implantação dos servidores vLLM (ADR-014; TAREFA-311). Default `"managed"`.
- `served_model_id` — identificador do modelo confirmado pelo probe `GET /v1/models`; `""` quando não verificável.
- `determinism_verified` — `False` por default; só `True` se `probe_judge_determinism` confirmar tokens idênticos (ADR-014). Nunca `True` sem prova.

### 4.4. Serviços de domínio (puros, sem I/O — testáveis sem GPU)

- **`FinalScoreCalculator`** — aplica a fórmula ponderada da seção 7.1 do doc-base. Recebe `MetricVector` + pesos da config; devolve `FinalScore`. Lança `WeightsDoNotSumToOneError` se pesos inválidos.
- **`RankScoreCalculator`** — aplica a fórmula executiva (mediana, FailureRate, WinRate, CriticalFailureRate). Pode produzir valor negativo (penalização clínica forte) — comportamento desejado, não erro.
- **`AggregationService`** — dado um conjunto de `EvaluationResult` de uma config, computa Mean/Median/Min/IQR/FailureRate/WinRate/CriticalFailureRate. Trata `NaN` por exclusão explícita e reporta a contagem de exclusões.
- **`FunnelSelector`** (Rodada 2) — dado o ranking de retrieval puro (precision@k, recall@k, MRR, nDCG@k) contra chunks-ouro, seleciona as top-3 configurações para a fase cara.

Todos recebem dados já materializados (listas de VOs) e devolvem VOs. Nenhum toca rede, disco ou GPU. São o coração da pirâmide de testes unitários (≥95% de cobertura — ver seção 11).

---

## 5. Contratos: Ports, DTOs e esquema de dados

### 5.1. Ports (interfaces) — `typing.Protocol`

Conforme `python-clean-architecture` (§2), ports são `Protocol` (estrutural, sem herança forçada). Assinaturas-alvo (Python, `from __future__ import annotations` em todos os arquivos):

```python
# domain/ports.py
from __future__ import annotations
from collections.abc import Sequence
from typing import Protocol


class RetrieverPort(Protocol):
    """Recupera chunks de uma base vetorial do Qdrant."""
    def search(
        self, *, base: BaseId, question: str, top_k: int,
    ) -> RetrievalResult: ...


class GeneratorPort(Protocol):
    """Gera resposta via vLLM (config de produção, SEM batch invariance)."""
    def generate(
        self, *, llm: LLMId, question: str,
        contexts: Sequence[Chunk], seed: int, temperature: float,
    ) -> GenerationOutput: ...


class MetricSuitePort(Protocol):
    """Camada 1 — métricas RAGAS (usa o juiz determinístico)."""
    def score(self, sample: EvaluationSample) -> Layer1Metrics: ...


class RubricJudgePort(Protocol):
    """Camada 2 — rubrica biomédica via LLM-juiz (determinístico)."""
    def score(self, sample: EvaluationSample) -> RubricResult: ...


class DeterministicMetricPort(Protocol):
    """Camada 1 auxiliar — BERTScore/ROUGE (sem LLM, determinístico)."""
    def score(self, *, answer: str, ground_truth: str) -> AuxMetrics: ...


class GoldChunkReaderPort(Protocol):
    """Lê a lista de chunks-ouro por pergunta (Rodada 2)."""
    def gold_for(self, question_id: str) -> list[str]: ...


class ResultWriterPort(Protocol):
    """Persiste/atualiza linhas tidy de forma idempotente."""
    def append(self, result: EvaluationResult) -> None: ...
    def update_metrics(self, row_id: RowId, metrics: MetricVector) -> None: ...
    def exists(self, row_id: RowId) -> bool: ...  # base da resumabilidade


class ResultReaderPort(Protocol):
    """Lê o dataset para agregação/estatística."""
    def load(self, *, round_id: str, phase: str | None = None) -> ResultFrame: ...


class StatsPort(Protocol):
    """Wilcoxon, Friedman+Nemenyi, modelo linear misto."""
    def wilcoxon_paired(self, frame: ResultFrame, metric: str) -> WilcoxonReport: ...
    def friedman_nemenyi(self, frame: ResultFrame, metric: str) -> FriedmanReport: ...
    def mixed_linear_model(self, frame: ResultFrame, formula: str) -> MLMReport: ...


class AnnotationReaderPort(Protocol):
    """Lê anotações humanas de falhas críticas (Camada 3)."""
    def read(self, run_id: str) -> list[CriticalAnnotation]: ...


class VLLMServerManagerPort(Protocol):
    """Sobe/derruba/chaveia modelos no vLLM (orquestração de GH200)."""
    def start(self, model: ModelSpec) -> ServerHandle: ...
    def wait_healthy(self, handle: ServerHandle, timeout_s: int) -> None: ...
    def stop(self, handle: ServerHandle) -> None: ...
```

> **Regra de ouro:** `application/` e `domain/` importam **apenas** ports. Nenhum import de `qdrant_client`, `openai`, `ragas`, `deepeval`, `statsmodels` fora de `infrastructure/adapters/`. Isso é verificável por lint (`import-linter`) — vira critério de aceitação (seção 16).

### 5.2. DTOs / Value Objects de fronteira (Pydantic + dataclasses)

- VOs imutáveis de domínio puro: `@dataclass(frozen=True)` (`BaseId`, `LLMId`, `Seed`, `FinalScore`, `RankScore`).
- DTOs de fronteira (entram/saem de adapters, validam dados externos): **Pydantic v2** (`EvaluationSample`, `GenerationOutput`, `Layer1Metrics`, `RubricResult`, `ModelSpec`).
- Saída de LLM **sempre** validada com Pydantic antes de virar VO (rag-engineer §9 — parsing defensivo).

```python
# domain/value_objects.py  (exemplo de invariante na criação)
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class BaseId:
    value: str
    def __post_init__(self) -> None:
        if self.value not in {"IDx_400k", "ID_230K"}:
            raise InvalidBaseIdError(f"Base desconhecida: {self.value}")

@dataclass(frozen=True)
class FinalScore:
    value: float
    def __post_init__(self) -> None:
        import math
        if not (math.isnan(self.value) or 0.0 <= self.value <= 1.0):
            raise ScoreOutOfRangeError(f"FinalScore fora de [0,1]: {self.value}")
```

### 5.3. Esquema de dados tidy (Parquet) — aprofundamento do item 11.2

Mantém-se o esquema do doc-base, com **tipagem explícita** e **anotação de origem/camada** para que Code e Codex tratem cada campo corretamente. Campos novos em relação ao doc-base estão marcados com ⊕.

| Campo | Tipo (pyarrow) | Origem | Obrigatório | Notas |
|---|---|---|---|---|
| `row_id` ⊕ | `string` | derivado | sim | hash determinístico de `(run_id, phase, base, llm, seed, question_id)` — chave de idempotência |
| `run_id` | `string` | execução | sim | identificador da execução completa |
| `experiment_phase` | `string` | config | sim | `"A"` \| `"B"` |
| `round_id` | `string` | config | sim | `round_1` \| `round_2a` \| `round_2b` |
| `base` | `string` | config | sim | Exp. B usa `"fixed"` |
| `llm` | `string` | config | sim | nome lógico do gerador |
| `judge_model` | `string` | config | sim | `prometheus-8x7b-v2.0` |
| `embedding_model` | `string` | config | sim | proveniência |
| `chunk_strategy` | `string` | config | sim | ex.: `fixed_512_overlap_50` |
| `reranker` | `string` | config | sim | ou `"none"` |
| `top_k` | `int32` | config | sim | |
| `prompt_version` | `string` | config | sim | versão do template RAG |
| `temperature` | `float32` | config | sim | gerador=0.1; juiz=0.0 |
| `seed` | `int32` | config | sim | 13 \| 42 \| 271 |
| `batch_invariant` | `bool` | execução | sim | True=juiz, False=gerador (ADR-003) |
| `vllm_version` | `string` | execução | sim | reprodutibilidade futura |
| `ragas_version` ⊕ | `string` | execução | sim | versão fixada do RAGAS |
| `config_hash` ⊕ | `string` | execução | sim | hash do YAML de config (proveniência) |
| `question_id` | `string` | dados | sim | |
| `question` | `string` | dados | sim | |
| `ground_truth` | `string` | dados | sim | resposta humana padronizada |
| `retrieved_chunk_ids` | `list<string>` | retrieval | A: sim / B: contexto fixo | |
| `retrieved_chunks_text` | `list<string>` | retrieval | sim | |
| `retrieval_scores` | `list<float32>` | retrieval | sim | scores do Qdrant |
| `generated_answer` | `string` | geração | sim | |
| `answer_correctness` | `float32` | Camada 1 | sim/NaN | |
| `answer_similarity` | `float32` | Camada 1 | sim/NaN | |
| `faithfulness` | `float32` | Camada 1 | sim/NaN | |
| `context_precision` | `float32` | Camada 1 | sim/NaN | |
| `context_recall` | `float32` | Camada 1 | sim/NaN | |
| `answer_relevancy` | `float32` | Camada 1 | sim/NaN | |
| `bertscore_f1` | `float32` | Camada 1 aux | sim/NaN | determinística |
| `rubric_biomed_score` | `float32` | Camada 2 | sim/NaN | |
| `rubric_feedback` | `string` | Camada 2 | sim | feedback textual p/ auditoria |
| `critical_failure_flag` | `int8` | Camada 3 | preenchido após anotação | 0 \| 1 \| `null` (não anotado) |
| `critical_failure_note` | `string` | Camada 3 | opcional | |
| `final_score` | `float32` | derivado | sim/NaN | |
| `metric_nan_fields` ⊕ | `list<string>` | execução | sim | quais métricas vieram NaN (saúde do juiz) |
| `retry_count` ⊕ | `int8` | execução | sim | nº de retries do juiz nesta linha |
| `latency_ms` | `int32` | execução | sim | |
| `tokens_in` | `int32` | execução | sim | |
| `tokens_out` | `int32` | execução | sim | |
| `server_mode` ⊕ | `string` | execução | sim | `"managed"` \| `"external"` — modo de implantação vLLM (ADR-014; TAREFA-311) |
| `served_model_id` ⊕ | `string` | execução | sim | modelo confirmado pelo probe `GET /v1/models`; `""` se não verificável |
| `determinism_verified` ⊕ | `bool` | execução | sim | `False` por default (ADR-014); `True` somente se probe de determinismo confirmou tokens idênticos |
| `timestamp` | `timestamp[us]` | execução | sim | UTC |

**Particionamento físico:** `round_id / experiment_phase / base / llm`. **Idempotência:** `row_id` é a chave; `ResultWriterPort.exists(row_id)` permite pular células já feitas (RF7). **Métricas de retrieval puro** (Rodada 2) vão em dataset separado `retrieval_metrics/` particionado por `round_id / chunk_strategy / embedding_model`, com colunas `precision_at_k`, `recall_at_k`, `mrr`, `ndcg_at_k`.

### 5.4. Contrato entre as duas passadas (geração → julgamento)

A passada de geração escreve linhas com métricas `null`. A passada de julgamento as completa via `update_metrics`. O contrato é o próprio esquema: a passada de julgamento seleciona `WHERE answer_correctness IS NULL AND generated_answer IS NOT NULL`. Isso torna o julgamento **resumível** e **independente** da geração — base do desacoplamento lógico que permite o pipelining com juiz residente (ADR-004/012, seção 15).

---

## 6. Catálogo de ADRs

Cada decisão não-óbvia tem um registro curto (formato `system-architect` §3). As tarefas de implementação (seção 14) referenciam estes ADRs.

### ADR-001: Monolito modular com Clean Architecture (não microserviços)

**Status:** Aceito
**Contexto:** Subsistema operado por 1 desenvolvedor, offline, sem requisito de escala horizontal nem times separados.
**Decisão:** Um único pacote Python `inteligenciomica_eval` com camadas `domain / application / infrastructure / cli`.
**Alternativas:** Microserviços (rejeitado: sobrecusto operacional esmaga ganho — anti-pattern `system-architect` §4); scripts soltos (rejeitado: sem testabilidade nem reprodutibilidade).
**Consequências:** Simples de operar e testar; troca de adapter sem tocar use cases. Perde isolamento de deploy independente (irrelevante aqui).
**Critério de reversão:** se a avaliação virar serviço contínuo multi-time.

### ADR-002: Parquet tidy como armazenamento analítico (não banco relacional)

**Status:** Aceito
**Contexto:** Dataset da ordem de centenas a alguns milhares de linhas por rodada; consumo por pandas/polars + análise estatística; necessidade de proveniência e particionamento.
**Decisão:** Persistir em Parquet tidy particionado; uma linha = uma `(config, pergunta, seed)`.
**Alternativas:** SQLite/Postgres (rejeitado nesta fase: overhead sem ganho — volume baixo, acesso analítico colunar); CSV (rejeitado: sem tipagem, sem partição, frágil para `list<...>`).
**Consequências:** Leitura colunar rápida, tipado, versionável por diretório. Updates exigem reescrever partições (mitigado: passada de julgamento reescreve por partição pequena).
**Critério de reversão:** se updates concorrentes ou consultas transacionais surgirem → pgvector/Postgres já está no catálogo do projeto.

### ADR-003: Dois servidores vLLM — juiz determinístico, geradores realistas

**Status:** Aceito (decisão central, herdada e endurecida do doc-base §9)
**Contexto:** Reprodutibilidade científica do juiz vs. fidelidade dos geradores ao comportamento de produção.
**Decisão:** `vllm-judge` roda com `VLLM_BATCH_INVARIANT=1`, `VLLM_ENABLE_V1_MULTIPROCESSING=0`, `tensor_parallel_size=1`, `temperature=0.0`. `vllm-generator` roda na config de produção (sem batch invariance, `temperature=0.1`, 3 seeds). O campo `batch_invariant` registra o regime em cada linha.
**Alternativas:** Batch invariance em todos (rejeitado: mede sistema diferente do de produção — invalida transferência); nenhum determinismo (rejeitado: validação humana e estatística ficam contaminadas por ruído do juiz).
**Consequências:** O `GeneratorPort` e o `RubricJudgePort`/`MetricSuitePort` apontam para **endpoints distintos**; a config de cada servidor é separada e versionada. Custo: juiz ~62% mais lento (aceitável, offline).
**Critério de reversão:** se uma versão do vLLM tornar produção determinística sem custo.

### ADR-004: Geração e julgamento logicamente desacoplados (com juiz residente em 4 GPUs)

**Status:** Aceito (revisado na v1.1 — a versão original assumia GPU única e chaveamento sequencial; corrigido para 4 GPUs. Ver ADR-012 para a alocação de GPUs.)
**Contexto:** O nó GH200 tem 4 GPUs disponíveis (Premissa P1). O juiz cabe folgado numa GPU; os geradores ocupam as demais.
**Decisão:** Geração e julgamento permanecem **logicamente desacoplados** no modelo de dados — a geração escreve linhas com métricas `null`; o julgamento completa as linhas que faltam (seção 5.4). Isso garante resumabilidade (ADR-009) e a opção de re-julgar com outro juiz no futuro. Fisicamente, o juiz fica **residente numa GPU dedicada** (carregado uma única vez) e os geradores giram nas outras GPUs (ADR-012), permitindo que os dois passos rodem em paralelo (pipeline) — embora o M3 inicial os execute como duas fases sequenciais com o juiz já carregado, por simplicidade.
**Alternativas:** Acoplar geração+julgamento por célula (rejeitado: perde resumabilidade e re-julgamento; força juiz e gerador no mesmo passo); manter chaveamento sequencial 1-modelo-por-vez (rejeitado: desperdiça 3 GPUs).
**Consequências:** Esquema de dados suporta linhas "geradas mas não julgadas" (seção 5.4). Juiz carregado 1×. Geradores trocam no máximo uma vez (2 ondas — ADR-012).
**Critério de reversão:** mudança no número de GPUs disponíveis.

### ADR-005: Cliente OpenAI-compatible único para geradores e juiz

**Status:** Aceito
**Contexto:** vLLM expõe API OpenAI-compatible; os 5 geradores e o juiz falam o mesmo protocolo.
**Decisão:** Um adapter base `OpenAICompatibleClient` (com `base_url`, `seed`, `temperature`, retry/backoff/timeout) reusado por `VLLMGenerator` e pela camada de juiz. `litellm` é opcional como camada de portabilidade futura, mas o default é o SDK OpenAI direto para reduzir superfície.
**Alternativas:** SDKs distintos por modelo (rejeitado: duplicação); só litellm (aceitável, mas adiciona dependência — mantido como ponto de extensão).
**Consequências:** Adicionar um gerador = uma entrada no `model_registry.yaml`. Retry/timeout/backoff centralizados.
**Critério de reversão:** se algum modelo exigir protocolo não-OpenAI.

### ADR-006: RAGAS e DeepEval atrás de ports, com versões fixadas

**Status:** Aceito
**Contexto:** RAGAS e DeepEval evoluem rápido e quebram contratos entre versões; ambos chamam o juiz por baixo.
**Decisão:** `RagasMetrics` implementa `MetricSuitePort`; `DeepEvalGEval` implementa `RubricJudgePort`. Ambos recebem o **mesmo** cliente de juiz determinístico por injeção. Versões *pinned* (`ragas==X.Y.Z`, `deepeval==X.Y.Z`) e registradas em `ragas_version`.
**Alternativas:** Implementar métricas RAGAS do zero (rejeitado: reinventar roda validada); deixar versões livres (rejeitado: irreprodutível).
**Consequências:** Domínio nunca importa RAGAS/DeepEval. Upgrade de versão é tarefa explícita com re-baseline do golden.
**Critério de reversão:** abandono de um framework → trocar só o adapter.

### ADR-007: Tratamento de NaN/parsing do juiz com retry e degradação explícita

**Status:** Aceito
**Contexto:** Falhas de parsing JSON do juiz e NaN em RAGAS são frequentes e conhecidas (doc-base §12).
**Decisão:** Toda chamada de métrica que dependa do juiz tem retry (máx. 3) com prompt reforçado; persistência de falha como `NaN` + registro em `metric_nan_fields` + `retry_count`; agregação **exclui** NaN e reporta a contagem. Nunca falha silenciosa, nunca derruba a rodada.
**Alternativas:** Abortar a rodada na primeira falha (rejeitado: frágil); imputar valor médio (rejeitado: contamina estatística).
**Consequências:** Run report expõe taxa de NaN por configuração como sinal de saúde. Estatística roda sobre dados limpos.
**Critério de reversão:** —

### ADR-008: Configuração declarativa em YAML validada por Pydantic Settings

**Status:** Aceito
**Contexto:** Rodadas diferem por combinação de fatores; reprodutibilidade exige config versionada.
**Decisão:** Cada rodada é um YAML (`experiment_round1.yaml`, etc.) validado por modelos Pydantic na carga (fail-fast). O `config_hash` (SHA-256 do YAML normalizado) é gravado em cada linha. Segredos (endpoints, tokens) via env/`pydantic-settings`, nunca no YAML versionado.
**Alternativas:** Config em código (rejeitado: não versionável como dado); argparse gigante (rejeitado: ilegível, sem validação rica).
**Consequências:** `--dry-run` valida config sem executar. Toda execução é auditável pelo hash.
**Critério de reversão:** —

### ADR-009: Resumabilidade por `row_id` idempotente

**Status:** Aceito
**Contexto:** Rodadas longas (centenas de chamadas de GPU) podem ser interrompidas; RNF7.
**Decisão:** `row_id = sha256(run_id, phase, base, llm, seed, question_id)`. Antes de gerar/julgar uma célula, consulta-se `ResultWriterPort.exists(row_id)` e pula-se o que já existe e está completo. Reexecução com mesmo `run_id` retoma; com novo `run_id` recomeça.
**Alternativas:** Checkpoint por contador (rejeitado: frágil a reordenação); sem resumabilidade (rejeitado: inaceitável a custo de GPU).
**Consequências:** Idempotência total; relançar é seguro.
**Critério de reversão:** —

### ADR-010: Anotação humana offline com merge desacoplado

**Status:** Aceito
**Contexto:** Camada 3 é humana, lenta, e não pode bloquear as camadas automáticas.
**Decisão:** `ielm-eval annotate` exporta as respostas (priorizando scores baixos — revisão estratificada) para um formato simples (CSV/JSONL) editável pelo especialista; um use case de ingestão faz o merge de `critical_failure_flag`/`note` no Parquet por `row_id`. O `RankScore` é (re)calculável antes e depois da anotação.
**Alternativas:** Bloquear pipeline até anotação (rejeitado: serializa humano e máquina); UI web dedicada (adiada: YAGNI nesta fase).
**Consequências:** Camadas automáticas entregam resultado parcial cedo; anotação refina depois.
**Critério de reversão:** volume que justifique UI dedicada.

### ADR-011: Análise estatística via `statsmodels` + `scikit-posthocs`, `pymer4` opcional

**Status:** Aceito
**Contexto:** Testes pareados (Wilcoxon, Friedman+Nemenyi) e modelo linear misto (interação base×LLM) com n=13.
**Decisão:** `scipy.stats` (Wilcoxon, Friedman) + `scikit-posthocs` (Nemenyi) + `statsmodels.mixedlm` (MLM). `pymer4` (binding lme4) fica como adapter alternativo de `StatsPort` se o MLM exigir recursos do `lme4`.
**Alternativas:** Só scipy (rejeitado: sem MLM); só R via subprocess (rejeitado: acopla a R desnecessariamente na fase 1).
**Consequências:** Pure-Python por padrão; ponte para R isolada atrás do port.
**Critério de reversão:** limitações do `mixedlm` para o desenho específico.

### ADR-012: Alocação das 4 GPUs — juiz dedicado + rotação dos geradores em ondas

**Status:** Aceito (v1.1)
**Contexto:** O nó GH200 tem 4 GPUs (P1) e há 6 modelos a servir (5 geradores + 1 juiz). Não cabem os 6 residentes ao mesmo tempo (máx. 4), mas o juiz é pequeno e cada gerador cabe em uma GPU (P1.1).
**Decisão:**
- **GPU 3 — juiz dedicado e residente.** Prometheus-2 AWQ (~26 GB) numa GPU própria, `tensor_parallel_size=1` (pré-requisito de batch invariance — ADR-003), `VLLM_BATCH_INVARIANT=1`. Carregado uma única vez por rodada.
- **GPUs 0–2 — geradores em rotação.** Os 5 geradores ocupam as 3 GPUs em **2 ondas** (onda 1: 3 modelos; onda 2: 2 modelos, 1 GPU ociosa). Cada servidor de gerador é fixado a uma GPU via `CUDA_VISIBLE_DEVICES`. Apenas **uma** troca de modelos por rodada.
- **Tensor parallelism para geradores grandes (condicional).** Se `gpt-oss-120b` ou `llama4:16x17b` não couber em uma GPU na quantização de produção (verificar — P1.1), esse gerador usa `tensor_parallel_size=2` sobre 2 das 3 GPUs de geração (reduzindo a concorrência da onda). Permitido porque os geradores são **não-determinísticos por desenho** (ADR-003) — TP>1 não os prejudica. O juiz **nunca** usa TP>1.
**Alternativas:**
- Chaveamento sequencial 1-modelo-por-vez (rejeitado: desperdiça 3 GPUs; era a decisão da v1.0 sob premissa errada de GPU única).
- 4 geradores concorrentes + juiz depois (sem GPU dedicada ao juiz): viável (onda 1: 4 modelos; onda 2: 1), mas impede pipelining e exige recarregar/realocar o juiz no fim. Mantido como **modo alternativo** selecionável por config (`gpu_layout: judge_dedicated | generators_first`).
- Co-localizar juiz + um gerador pequeno na mesma GPU (otimização de throughput): possível (determinismo preservado), mas mais frágil de operar — fora do default (YAGNI).
**Consequências:** Juiz carregado 1×; geradores trocam 1×; geração e julgamento podem pipelinar (ADR-004). `VLLMServerManager` precisa fixar GPU por servidor (`CUDA_VISIBLE_DEVICES`), subir servidores concorrentes em portas distintas e escalonar as ondas. O `model_registry.yaml` ganha `tensor_parallel_size` e atribuição de GPU por modelo.
**Critério de reversão:** mudança no número de GPUs, ou modelo que exija TP>2.

### ADR-013: Funil de retrieval da Rodada 2 (M5 — adiado)

**Status:** Aceito (M5 — implementação pendente)
**Contexto:** A Rodada 2 (OFAT chunking/embedding) requer avaliação de dezenas de configurações de retrieval. Rodar geração completa (cara) em todas é inviável.
**Decisão:** Introduzir um estágio de pré-filtragem com métricas de retrieval puro (precision@k, recall@k, MRR, nDCG@k) contra chunks-ouro; apenas as top-3 configurações seguem para o estágio caro de geração+avaliação (`FunnelSelector`). O resultado do funil é independente dos LLMs.
**Alternativas:** Geração em todas as configs (rejeitado: custo proibitivo em 4 GPUs); seleção manual (rejeitado: subjetiva, não reprodutível).
**Consequências:** Gate de entrada para M5: curadoria de chunks-ouro entregue (Premissa P5). `RetrievalFunnelUseCase` implementado em M5, stub em M4. A CLI `run` ganhou `--stage` (M5 futuro) — **ainda não implementado**.
**Referência:** `docs/adr/ADR-013-round2-funnel.md`
**Critério de reversão:** mudança no critério de seleção das top-k configs.

### ADR-014: Modo de servidor managed vs external; proveniência verificada por sonda

**Status:** Aceito (TAREFA-311)
**Contexto:** Em ambiente de cluster compartilhado (GH200 do LNCC, arquitetura ARM), o cliente Python pode não ter privilégios para lançar processos vLLM localmente. Os servidores vLLM e Qdrant podem já estar em execução, acessíveis via túnel SSH, sem controle de ciclo de vida pelo ielm-eval.
**Decisão:** Introduzir `server_mode: "managed" | "external"` no `RoundConfig`. Em modo `managed` (default), o `VLLMServerManagerAdapter` lança e derruba processos vLLM via `asyncio.create_subprocess_exec`. Em modo `external`, o `ExternalVLLMServerManager` realiza apenas sondas de saúde (`/health`) sem criar processo; `start/stop` são no-op (loga `vllm_server_external_skipped`).
**Consequências da migração de responsabilidade no modo `external`:**
- O determinismo do juiz deixa de ser *garantido pelo lançamento* e passa a ser *verificado por sonda* e gravado por linha (`determinism_verified: bool`, default `False` — "nunca `True` sem prova");
- Três probes ao iniciar: `probe_served_model` (`GET /v1/models` → `served_model_id`), `probe_vllm_version` (`GET /version`), `probe_judge_determinism` (2 completions com `seed=42, temperature=0.0`; `True` se tokens idênticos);
- `endpoints_provenance` no run report resume topologia, endpoint mascarado (`mask_url()` → `scheme://host:port`), saúde, versão vLLM e `determinism_verified` por servidor;
- `--require-verified-determinism` aborta o run se `determinism_verified=False` ao término dos probes (para runs de publicação).
**Referências:** ADR-003 (batch invariance), ADR-004 (ciclo de vida dos servidores), ADR-008 (segredos via env), ADR-012 (alocação de GPUs); `docs/operations_manual.md` Seção 4-B.
**Referência de arquivo:** `docs/adr/ADR-014-server-mode-external.md`
**Critério de reversão:** consolidação da infraestrutura em ambientes gerenciáveis pelo processo Python.

---

## 7. Stack tecnológica detalhada (aprofunda item 10)

### 7.1. Dependências com papel e *pinning*

Versões devem ser **fixadas** em `pyproject.toml` + lock (`uv.lock`). Os números abaixo são *placeholders* a confirmar no M0 e gravados em proveniência.

| Pacote | Papel na arquitetura | Camada | Pin |
|---|---|---|---|
| `python` | Runtime | — | 3.11+ |
| `uv` | Gestão de deps + venv reprodutível | tooling | última |
| `typer` | CLI (`run/analyze/report/annotate/serve`) | cli | pin |
| `pydantic` v2 + `pydantic-settings` | DTOs de fronteira, config, segredos | infra/config | pin |
| `structlog` | Logging estruturado JSON/texto | infra | pin |
| `openai` (SDK) | Cliente OpenAI-compatible p/ vLLM (gen+juiz) | adapters | pin |
| `litellm` *(opcional)* | Portabilidade multi-provider futura | adapters | pin |
| `qdrant-client` | `RetrieverPort` | adapters | pin |
| `ragas` | `MetricSuitePort` (Camada 1) | adapters | **pin estrito** |
| `deepeval` | `RubricJudgePort` (Camada 2, G-Eval) | adapters | **pin estrito** |
| `bert-score` | `DeterministicMetricPort` (aux) | adapters | pin |
| `rouge-score` *(opcional)* | métrica aux determinística | adapters | pin |
| `pandas` + `polars` | Manipulação tidy (polars p/ volume) | infra | pin |
| `pyarrow` | I/O Parquet tipado + particionado | infra | pin |
| `scipy` | Wilcoxon, Friedman | adapters/stats | pin |
| `scikit-posthocs` | Nemenyi post-hoc | adapters/stats | pin |
| `statsmodels` | Modelo linear misto (`mixedlm`) | adapters/stats | pin |
| `pymer4` *(opcional)* | MLM via lme4 (R) | adapters/stats | pin |
| `seaborn` + `matplotlib` + `plotly` | Visualizações canônicas | visualization | pin |
| `rich` | Progress em operações longas | cli | pin |
| **Dev/test** | `pytest`, `pytest-xdist`, `pytest-mock`, `hypothesis`, `coverage`, `respx`, `freezegun`, `polyfactory`, `mutmut`, `ruff`, `mypy`, `import-linter`, `pre-commit` | tooling | pin |

> **vLLM** e **Prometheus-2** não são dependências Python do pacote — são **serviços externos** acessados por HTTP. Suas versões entram em proveniência (`vllm_version`), não no `pyproject.toml`. Isso reforça ADR-003/004: o pacote não importa vLLM, só fala HTTP com ele.

### 7.2. Topologia de serviços externos

```
                          nó GH200 — 4 GPUs
   ┌──────────────────────────────────────────────────────────────┐
   │  GPU 0        GPU 1        GPU 2     │   GPU 3 (dedicada)       │
   │  ┌────────┐   ┌────────┐   ┌───────┐ │  ┌────────────────────┐ │
   │  │ gen A  │   │ gen B  │   │ gen C │ │  │ vllm-judge :8001    │ │
   │  │ :8000  │   │ :8000  │   │ :8000 │ │  │ prometheus-8x7b AWQ │ │
   │  └────────┘   └────────┘   └───────┘ │  │ VLLM_BATCH_INVARIANT│ │
   │   onda 1: 3 geradores concorrentes    │  │ =1  TP=1            │ │
   │   onda 2: gen D, gen E (1 troca)      │  │ residente o tempo  │ │
   │   ↑ cada servidor fixado via          │  │ todo (carrega 1×)  │ │
   │     CUDA_VISIBLE_DEVICES (ADR-012)    │  └────────────────────┘ │
   │   ↑ start/stop/escalona ondas:        │                         │
   │     VLLMServerManager                 │                         │
   └──────────────────────────────────────────────────────────────┘
                  Qdrant :6333  (serviço separado, sempre ativo)
```

- O **juiz** ocupa uma GPU dedicada (GPU 3), residente, `TP=1`, determinístico (ADR-003/012). Carregado uma única vez por rodada.
- Os **5 geradores** giram nas GPUs 0–2 em 2 ondas (3 + 2); cada servidor é fixado a uma GPU por `CUDA_VISIBLE_DEVICES` e usa a mesma porta `:8000` (apenas um gerador por GPU; o `base_url` aponta para a instância ativa da onda). Geradores grandes que excedam 1 GPU usam `TP=2` (ADR-012, P1.1).
- `vllm-generator` (GPUs 0–2) e `vllm-judge` (GPU 3) **coexistem** — daí o pipelining opcional geração↔julgamento (ADR-004). O `serve`/`run` da CLI orquestra esse ciclo de vida.

#### 7.2.1. Modo external (servidores via túnel SSH)

Quando `server_mode: external` (ADR-014), o ielm-eval **não lança nem derruba** os servidores vLLM/Qdrant. Eles já estão em execução no GH200 (ou em outro nó do cluster), acessíveis pelo cliente x86 via túnel SSH ou rede interna.

```
   cliente x86 (laptop / nó de controle)
   ┌─────────────────────────────────────────────────────────┐
   │  ielm-eval run --config ...                             │
   │  (ExternalVLLMServerManager — start/stop = no-op)      │
   └────────┬────────────────────┬──────────────────────────┘
            │ túnel SSH / rede   │ túnel SSH / rede
            ▼                    ▼
   ┌────────────────┐   ┌────────────────────────────────────┐
   │  Qdrant :6333  │   │  nó GH200 (serviços compartilhados)│
   │  (compartilhado│   │  vllm-gen1 :8000  vllm-gen2 :8010  │
   │   ou dedicado) │   │  vllm-judge :8001 (residente)      │
   └────────────────┘   └────────────────────────────────────┘
```

**Diferenças operacionais em relação ao modo managed:**

| Aspecto | managed (default) | external |
|---|---|---|
| Ciclo de vida vLLM | ielm-eval lança/derruba | no-op (serviços já existem) |
| Determinismo do juiz | **garantido** (env controlado) | **verificado por sonda** (ADR-014) |
| `determinism_verified` | `True` se probe OK | `True` apenas com prova; `False` por default |
| GPU fixada por | `CUDA_VISIBLE_DEVICES` | responsabilidade do operador |
| Endpoints | resolvidos no launch | declarados em `ModelEntry.endpoint_env` |

Ver `docs/operations_manual.md` Seção 4-B para fluxo operacional detalhado.

---

## 8. Estrutura de código detalhada (aprofunda item 11)

Mantém o esqueleto do doc-base §11.1, refinado para Clean Architecture estrita (`python-clean-architecture` §1) e para os ports da seção 5.1. Cada módulo tem responsabilidade única e camada explícita.

```
inteligenciomica_eval/
├── pyproject.toml                 # deps + pins + ferramentas (ruff/mypy/pytest/coverage)
├── uv.lock                        # lock reprodutível
├── ruff.toml  mypy.ini  .importlinter  .pre-commit-config.yaml
├── README.md                      # quickstart copy-paste (seção 15 resumida)
├── docs/
│   ├── operations_manual.md       # seção 15 deste documento, versionada com o código
│   └── adr/                        # ADRs vivos (seção 6 + futuros)
├── src/inteligenciomica_eval/
│   ├── domain/
│   │   ├── entities.py            # Question, GeneratedAnswer, EvaluationResult
│   │   ├── value_objects.py       # BaseId, LLMId, Seed, FinalScore, RankScore, MetricVector
│   │   ├── ports.py               # TODOS os Protocols (seção 5.1)
│   │   ├── services/
│   │   │   ├── final_score.py     # FinalScoreCalculator (puro)
│   │   │   ├── rank_score.py      # RankScoreCalculator (puro)
│   │   │   ├── aggregation.py     # AggregationService (puro)
│   │   │   └── funnel.py          # FunnelSelector (puro, Rodada 2)
│   │   └── errors.py              # hierarquia de exceções de domínio (seção 9)
│   ├── application/
│   │   ├── run_experiment.py      # RunExperimentUseCase (A e B)
│   │   ├── compute_metrics.py     # ComputeMetricsUseCase (camadas 1+2)
│   │   ├── ingest_annotation.py   # IngestHumanAnnotationUseCase (camada 3)
│   │   ├── aggregate_results.py   # AggregateResultsUseCase
│   │   ├── statistical_analysis.py# StatisticalAnalysisUseCase
│   │   └── retrieval_funnel.py    # RetrievalFunnelUseCase (Rodada 2)
│   ├── infrastructure/
│   │   ├── adapters/
│   │   │   ├── qdrant_retriever.py
│   │   │   ├── openai_compatible_client.py  # base: retry/backoff/timeout (ADR-005)
│   │   │   ├── vllm_generator.py            # GeneratorPort
│   │   │   ├── prometheus_judge.py          # cliente do juiz (det.)
│   │   │   ├── ragas_metrics.py             # MetricSuitePort (ADR-006)
│   │   │   ├── deepeval_geval.py            # RubricJudgePort (ADR-006)
│   │   │   ├── deterministic_metrics.py     # BERTScore/ROUGE
│   │   │   ├── stats_statsmodels.py         # StatsPort (ADR-011)
│   │   │   └── vllm_server_manager.py       # VLLMServerManagerPort (ADR-004)
│   │   ├── repositories/
│   │   │   ├── parquet_storage.py           # ResultWriter/ResultReader
│   │   │   ├── gold_chunks.py               # GoldChunkReaderPort
│   │   │   └── annotation_store.py          # AnnotationReaderPort
│   │   ├── prompts/                          # templates versionados (.txt) — NUNCA inline
│   │   │   ├── rag_answer.txt
│   │   │   └── biomed_rubric.txt
│   │   └── config/
│   │       ├── settings.py                   # pydantic-settings (env/segredos)
│   │       ├── schema.py                      # modelos Pydantic do YAML de rodada
│   │       └── provenance.py                  # config_hash, versões, lineage
│   ├── visualization/
│   │   ├── heatmaps.py  boxplots.py  interaction_plots.py
│   │   ├── radar.py  per_question.py  failure_breakdown.py
│   │   └── report.py                          # monta HTML/MD
│   └── cli.py                                 # Typer: run/analyze/report/annotate/serve
├── config/
│   ├── experiment_round1.yaml
│   ├── experiment_round2a.yaml                # variação de chunking
│   ├── experiment_round2b.yaml                # variação de embedding
│   └── model_registry.yaml                    # nome lógico → pesos + params de serving
└── tests/
    ├── unit/{domain,application}/             # espelha src/
    ├── integration/adapters/                  # Qdrant/vLLM reais (skip se ausentes)
    ├── e2e/                                    # rodada mínima com stubs em CPU
    ├── fakes/                                  # InMemory* dos ports
    ├── factories/                              # builders de Question/Result (polyfactory)
    ├── golden/                                 # golden dataset de scoring/agregação
    └── conftest.py
```

**Garantia arquitetural verificável:** `import-linter` declara o contrato "domain não importa nada de infrastructure/third-party; application só importa domain". Quebra de camada falha o CI — vira critério de aceitação em toda tarefa (seção 16).

---

## 9. Estratégia de exceções

Hierarquia específica de domínio (`python-clean-architecture` §5), em `domain/errors.py`. Nunca `raise Exception(...)` genérico.

```python
class InteligenciomicaEvalError(Exception):
    """Base de todas as exceções do subsistema."""

# --- Domínio / validação ---
class InvalidBaseIdError(InteligenciomicaEvalError): ...
class InvalidLLMIdError(InteligenciomicaEvalError): ...
class ScoreOutOfRangeError(InteligenciomicaEvalError): ...
class WeightsDoNotSumToOneError(InteligenciomicaEvalError): ...

# --- Configuração ---
class ConfigValidationError(InteligenciomicaEvalError): ...
class ModelNotInRegistryError(InteligenciomicaEvalError): ...

# --- Adapters / I/O externo ---
class RetrievalError(InteligenciomicaEvalError): ...        # Qdrant
class GenerationError(InteligenciomicaEvalError): ...        # vLLM gerador
class JudgeUnavailableError(InteligenciomicaEvalError): ...  # vLLM juiz fora
class LLMOutputParseError(InteligenciomicaEvalError): ...    # JSON inválido do juiz
class MetricComputationError(InteligenciomicaEvalError): ... # RAGAS/DeepEval
class StorageError(InteligenciomicaEvalError): ...           # Parquet

# --- Orquestração de servidores (GH200) ---
class ServerStartTimeoutError(InteligenciomicaEvalError): ...
class ModelSwitchError(InteligenciomicaEvalError): ...

# --- Estatística ---
class InsufficientSampleError(InteligenciomicaEvalError): ...
```

**Regras de tratamento:**
- Erros de **célula** (uma `{config, pergunta, seed}`) são isolados: logam, marcam a linha com falha/NaN e seguem. Não derrubam a rodada (ADR-007).
- Erros de **configuração** (YAML inválido, modelo fora do registry) falham *fast*, antes de qualquer chamada de GPU.
- `LLMOutputParseError` aciona o retry do adapter de juiz; só após esgotar retries vira NaN persistido.
- `subprocess` (gestão do vLLM) sempre com `timeout`, `check=False` + verificação manual; nunca `shell=True` (`python-clean-architecture` §6).
- Mensagens acionáveis, sem vazar segredos (endpoints/tokens nunca em log).

---

## 10. Estratégia de observabilidade

### 10.1. Logging estruturado (`structlog`)

- **JSON em execução real, texto colorido em dev.**
- **Correlação** por `run_id` (toda a rodada), `row_id` (célula), `question_id`.
- `logger.debug` no caminho feliz; `logger.info` em marcos (modelo carregado, fase concluída); `logger.warning` em NaN/retry; `logger.exception` ao propagar erro.
- **Nunca logar** ground truth completa, textos de chunk inteiros nem tokens de autenticação (PII/segredos — `python-clean-architecture` §5).

Exemplo de log por célula (inspirado em `rag-engineer` §13):

```python
logger.info(
    "cell_completed",
    run_id=run_id, row_id=row_id, phase="A",
    base=base.value, llm=llm.value, seed=seed, question_id=qid,
    batch_invariant=False,                 # gerador (ADR-003)
    retrieved_count=len(contexts),
    final_score=score.value,
    metric_nan_fields=nan_fields, retry_count=retries,
    latency_breakdown={"retrieve_ms": t1, "generate_ms": t2},
    tokens_in=usage.prompt_tokens, tokens_out=usage.completion_tokens,
)
```

### 10.2. Relatório de execução (run report)

Ao final de cada rodada, emitir um sumário (também persistido):
- Total de células planejadas vs. concluídas vs. puladas (resumabilidade) vs. falhas.
- **Taxa de NaN por configuração** (saúde do juiz — ADR-007).
- Latência agregada e tokens por modelo.
- Regime de determinismo confirmado por fase (auditoria de ADR-003).
- `config_hash` + versões de todas as dependências e serviços.

### 10.3. Métricas de processo (não-primárias)

Latência, throughput e contagem de tokens são **registrados** (doc-base §2.2) mas não entram no `RankScore`. Ficam disponíveis no Parquet e no run report para diagnóstico de custo/desempenho.

---

## 11. Estratégia de testes (paralela ao desenvolvimento)

Testes são escritos **junto** com cada tarefa, não no fim (regra de ouro `test-engineer`). Pirâmide: ~75% unit, ~20% integração, ~5% E2E.

### 11.1. O que testar em cada camada

| Camada | Tipo | Cobertura-alvo | Como |
|---|---|---|---|
| `domain/services` (FinalScore, RankScore, Aggregation, Funnel) | Unit | ≥95% line+branch | Casos numéricos exatos + bordas (pesos não somam 1, NaN, RankScore negativo). Property-based (`hypothesis`) para invariantes. |
| `domain/value_objects` | Unit | ≥95% | Invariantes em `__post_init__` (base inválida, score fora de [0,1]). |
| `application/use_cases` | Unit | ≥90% | Fakes tipados de **todos** os ports (`InMemoryResultWriter`, `FakeGenerator`, `FakeJudge`, `StubRetriever`). Verifica orquestração, idempotência (pula `row_id` existente), isolamento de falha de célula. |
| `infrastructure/adapters` | Integração | ≥80% | Qdrant/vLLM reais quando disponíveis; `@pytest.mark.skipif` quando ausentes. `respx` para mockar HTTP do vLLM em testes determinísticos. |
| Parsing do juiz | Unit + property | alta | `parse(serialize(x)) == x`; outputs rebeldes (fences, JSON parcial, texto livre) → `LLMOutputParseError` ou retry. |
| Estatística | Unit | — | Datasets sintéticos com resultado conhecido (Wilcoxon/Friedman em dados com diferença plantada). |
| Fluxo completo | E2E | poucos | Rodada mínima (2 perguntas, 1 base, 2 LLMs *stub* em CPU, juiz *stub*) gerando Parquet + relatório. |

### 11.2. Fakes das ports (preferidos a mocks)

Para cada port, um fake in-memory em `tests/fakes/` (ex.: `FakeGenerator` devolve resposta canônica determinística; `FakeJudge` devolve score fixo configurável; `StubRetriever` devolve chunks plantados). Isso permite testar use cases **sem GPU, sem rede** e detecta quebra de contrato em tempo de tipo (`test-engineer` §6).

### 11.3. Golden dataset de scoring

`tests/golden/` guarda um conjunto de `EvaluationResult` sintéticos com `FinalScore`/`RankScore`/agregados **esperados**. Regressões no cálculo de score quebram o golden e exigem justificativa + novo golden revisado (`test-engineer` §13). Distinto do golden de qualidade de RAG (que é o próprio experimento) — aqui o golden testa a **matemática do scoring**, não a qualidade dos modelos.

### 11.4. Determinismo dos testes

Seeds fixas, `freezegun` para timestamps, sem `sleep` real, sem chamadas externas em unit. `pytest --randomly` deve passar (sem dependência de ordem). Testes paralelizáveis (`pytest-xdist -n auto`).

### 11.5. Mutation testing nos serviços de scoring

`mutmut` sobre `domain/services` (lógica crítica de ranking). Mutation score-alvo >80%; mutações sobreviventes em `RankScore`/`FinalScore` são priorizadas — é onde um bug silencioso distorceria a decisão de produção.

### 11.6. CI

Pipeline (GitHub Actions, `test-engineer` §15): `ruff check` + `ruff format --check` + `mypy --strict` + `import-linter` + `pytest --cov --cov-fail-under=85 -n auto`. Integração com Qdrant/vLLM roda só onde os serviços existem (job opcional/self-hosted no GH200).

---

## 12. Configuração, reprodutibilidade e proveniência

### 12.1. YAML de rodada (validado por Pydantic — ADR-008)

Exemplo (`config/experiment_round1.yaml`, esquema validado em `config/schema.py`):

```yaml
round_id: round_1
phases: [A, B]
bases: [IDx_400k, ID_230K]
llms: [gpt-oss-120b, gemma4:31b, qwen3.6:35b, glm-4.7-flash, llama4:16x17b]
seeds: [13, 42, 271]
temperature: 0.1
retrieval:
  top_k: 8
  reranker: none
  embedding_model: <baseline-a-definir>
  chunk_strategy: <baseline-a-definir>
judge:
  model: prometheus-eval/prometheus-8x7b-v2.0
  endpoint_env: VLLM_JUDGE_URL        # valor real vem de env (segredo)
  batch_invariant: true
  temperature: 0.0
scoring:
  weights:                            # devem somar 1.0 (validado)
    answer_correctness: 0.45
    faithfulness: 0.20
    rubric_biomed_score: 0.15
    context_recall: 0.10
    context_precision: 0.05
    answer_relevancy: 0.05
  failure_threshold: 0.70
experiment_b:
  canonical_context_source: IDx_400k  # ou "expert_curated"
  canonical_top_k: 8
```

### 12.2. Proveniência gravada por linha (RF8)

`config/provenance.py` calcula e injeta em cada `EvaluationResult`: `config_hash` (SHA-256 do YAML normalizado), `vllm_version`, `ragas_version`, `vllm` por fase, `batch_invariant`, `prompt_version`, timestamp UTC. **Sem isso, a reprodução futura é impossível** (doc-base §9.4).

### 12.3. Reprodutibilidade

- Mesmo `run_id` + mesmo YAML + mesmo código + mesmas versões → resultado idêntico **no juiz** (determinístico) e **estatisticamente equivalente** nos geradores (realistas, por desenho — ADR-003).
- `--dry-run` valida config, resolve o registry, checa endpoints e imprime o plano de execução (nº de células, ordem de chaveamento de modelos) sem chamar GPU.
- Lock file (`uv.lock`) commitado; ambiente recriável por `uv sync --frozen`.

### 12.4. Reprodutibilidade no modo external (ADR-014)

No modo **`managed`**, o ielm-eval lança o servidor vLLM com env explícito (`VLLM_BATCH_INVARIANT=1`, `tensor_parallel_size=1`, `temperature=0.0`, `seed=42`), garantindo determinismo bit-a-bit do juiz. No modo **`external`**, o servidor já está em execução — o ielm-eval **não** controla seu env, sua versão nem seu modelo carregado.

Para não assumir silenciosamente determinismo não-verificado, o ielm-eval executa três probes ao iniciar em modo external:

| Probe | Endpoint | O que verifica |
|---|---|---|
| `probe_served_model` | `GET /v1/models` | Modelo realmente carregado (`served_model_id`) |
| `probe_vllm_version` | `GET /version` | Versão do servidor vLLM |
| `probe_judge_determinism` | 2× completion `seed=42` | Tokens idênticos → `determinism_verified=True` |

O campo `determinism_verified` default é **`False`** — nunca assume `True` sem prova (ADR-014). O run report inclui `endpoints_provenance` com topologia, endpoint mascarado, saúde e resultado das probes por servidor.

Para runs de publicação, use `--require-verified-determinism`: o comando aborta se `determinism_verified` não for `True` ao final das probes.

```bash
uv run ielm-eval run --config config/experiment_round1.yaml \
    --run-id <run_id> \
    --require-verified-determinism   # falha se juiz não confirmou determinismo
```

---

## 13. Riscos aprofundados (aprofunda item 12)

Mantém a tabela do doc-base §12 e adiciona, para cada risco relevante à arquitetura, **onde no código** a mitigação vive e **como é verificada**.

| Risco | Mitigação arquitetural | Onde vive | Verificação |
|---|---|---|---|
| Juiz não-determinístico corrompe validação | `vllm-judge` com `VLLM_BATCH_INVARIANT=1`, TP=1, temp=0; campo `batch_invariant` por linha | `prometheus_judge.py`, `vllm_server_manager.py`, esquema | Teste de integração: mesma entrada 2× → score idêntico (quando juiz disponível) |
| Geradores em config não-realista | Geradores **sem** batch invariance; 3 seeds; regime gravado | `vllm_generator.py`, config | Run report audita `batch_invariant=False` na fase A/B |
| Modelo grande não cabe em 1 GPU | Gerador usa `TP=2` entre GPUs (permitido — não-determinístico por desenho); juiz sempre TP=1 (ADR-012, P1.1) | `model_registry.yaml`, `VLLMServerManager` | M0 verifica footprint por modelo; E2E simula onda com TP |
| Subutilizar as 4 GPUs | Juiz dedicado + 3 geradores concorrentes por onda; pipelining opcional | ADR-004/012, `VLLMServerManager` | Run report traz mapa GPU→modelo por onda |
| NaN/parsing do juiz | Retry (máx 3) + degradação explícita + `metric_nan_fields`/`retry_count`; agregação exclui NaN | `openai_compatible_client.py`, `ragas_metrics.py`, `aggregation.py` | Unit: outputs rebeldes; agregação ignora NaN e conta exclusões |
| n=13 baixo | Mediana/IQR/percentis; testes pareados; 3 seeds aumentam N efetivo | `aggregation.py`, `stats_*` | Golden de scoring; datasets sintéticos com diferença plantada |
| Variabilidade entre seeds > entre configs | ANOVA preliminar; run report destaca; conclusão "diferença é ruído" é resultado válido | `statistical_analysis.py`, report | Teste com seeds de alta variância plantada |
| Quebra de versão de framework | Pins estritos + `ragas_version`/`vllm_version` em proveniência; upgrade é tarefa explícita c/ re-baseline | `pyproject.toml`, `provenance.py` | CI com `uv sync --frozen`; golden re-rodado em upgrade |
| Vazar camada (domínio importando infra) | Contrato `import-linter` | `.importlinter` | CI falha em violação |
| Curadoria de chunks-ouro atrasa Rodada 2 | Desacoplada: Rodada 1 não depende dela; M de curadoria é gate da Rodada 2 | milestones | Go/no-go do milestone de Rodada 2 |
| Segredo (endpoint/token) vazado no Git | Endpoints via env/`pydantic-settings`; YAML só referencia `*_env` | `settings.py`, YAML | `ruff`/revisão; nenhum segredo no YAML versionado |
| Prompt injection indireta via chunk | Delimitação clara dados×instrução no template; saída validada por Pydantic | `prompts/*.txt`, parsing | Teste com chunk malicioso plantado |
| Execução longa interrompida | Resumabilidade por `row_id` idempotente | `parquet_storage.py`, use cases | Unit: reexecução pula células existentes |


---

## 14. Plano de implementação em milestones

Decomposição em **épicos verticais** (capabilities), depois em **milestones** entregáveis ponta-a-ponta (3–10 dias cada), depois em **tarefas** com critério de aceitação verificável (`tech-lead`). Cada tarefa indica a skill responsável e os ADRs que a governam.

### 14.1. Épicos (capabilities)

| Épico | Capability | Skill primária |
|---|---|---|
| **E0** | Fundação: repo, CI, contratos, domínio + scoring testável | python-engineer + test-engineer |
| **E1** | Geração de respostas — Experimento A (retrieval+gerador+storage) | rag-engineer + backend-engineer |
| **E2** | Avaliação automática — Camadas 1+2 (juiz determinístico) | rag-engineer |
| **E3** | Geração controlada — Experimento B (contextos fixos) | rag-engineer |
| **E4** | Orquestração das 4 GPUs (juiz dedicado + ondas de geradores) | backend-engineer |
| **E5** | Camada 3 (anotação humana) + ingestão | python-engineer |
| **E6** | Agregação + RankScore + Estatística | ml-engineer + data-engineer |
| **E7** | Relatórios + visualizações | python-engineer |
| **E8** | Rodada 2 (funil de retrieval + OFAT chunking/embedding) | rag-engineer + data-engineer |
| **E9** | Hardening + validação do juiz (Cohen's κ) + docs finais | test-engineer + code-reviewer |

### 14.2. Critério transversal de "Definition of Done" (toda tarefa)

Aplica-se a **todas** as tarefas, herdado das skills:

- [ ] `from __future__ import annotations` no topo; type hints em toda API pública.
- [ ] Docstrings Google style nas funções/classes públicas.
- [ ] Testes (happy + borda + erro) escritos junto; cobertura não regride.
- [ ] `ruff check` + `ruff format --check` + `mypy --strict` + `import-linter` sem erros.
- [ ] Logging estruturado nos pontos significativos; sem PII/segredos em log.
- [ ] Exceções específicas de domínio (nunca `Exception` cru).
- [ ] Nenhum import de third-party/infra em `domain`/`application`.

---

### 14.3. Milestone M0 — Bootstrap e contratos (esqueleto executável com stubs)

**Objetivo:** O esqueleto roda ponta-a-ponta com modelos *stub* em CPU, calcula `FinalScore`/`RankScore` corretos sobre dados sintéticos e persiste Parquet. Prova os contratos antes de tocar GPU.
**Épicos:** E0. **Duração estimada:** ~8 dias.

| Tarefa | Descrição | Skill | Prio | Tam | Critério de aceitação |
|---|---|---|---|---|---|
| TAREFA-001 | Bootstrap do repo (`pyproject`, `uv`, ruff/mypy/import-linter/pre-commit, CI) | python-engineer | P0 | S | `uv sync --frozen` ok; CI verde em repo vazio; hooks instalados |
| TAREFA-002 | Hierarquia de exceções (`domain/errors.py`) | python-engineer | P0 | XS | Todas as classes da seção 9; teste de hierarquia |
| TAREFA-003 | Value Objects + invariantes (`BaseId`, `LLMId`, `Seed`, `FinalScore`, `RankScore`, `MetricVector`) | python-engineer | P0 | S | Invariantes validadas em `__post_init__`; unit ≥95%; property-based para faixas |
| TAREFA-004 | Entidades (`Question`, `GeneratedAnswer`, `EvaluationResult`) | python-engineer | P0 | S | Invariantes do agregado (seção 4.3); unit |
| TAREFA-005 | Ports como `Protocol` (`domain/ports.py`) | python-engineer | P0 | S | Todos os ports da seção 5.1; mypy passa; `import-linter` configurado |
| TAREFA-006 | `FinalScoreCalculator` (fórmula 7.1) | ml-engineer | P0 | S | Pesos somam 1 (senão `WeightsDoNotSumToOneError`); golden numérico; NaN tratado |
| TAREFA-007 | `RankScoreCalculator` (fórmula 7.3) | ml-engineer | P0 | S | Permite valor negativo; golden numérico; bordas |
| TAREFA-008 | `AggregationService` (Mean/Median/Min/IQR/Failure/Win/CriticalFailure) | data-engineer | P0 | M | Exclui NaN e conta exclusões; golden de agregação |
| TAREFA-009 | `ParquetStorage` (`ResultWriter`/`ResultReader`) + `row_id` idempotente | data-engineer | P0 | M | Esquema seção 5.3; `exists(row_id)`; round-trip; particionamento |
| TAREFA-010 | Config YAML + schema Pydantic + `config_hash` + `--dry-run` | python-engineer | P0 | M | YAML inválido falha fast; hash estável; dry-run imprime plano |
| TAREFA-011 | Fakes de todos os ports (`tests/fakes/`) + factories (polyfactory) | test-engineer | P0 | M | Fakes tipados satisfazem os Protocols; usados nos unit |
| TAREFA-012 | E2E stub: rodada mínima em CPU (2 perguntas, 2 LLMs stub, juiz stub) → Parquet + score | test-engineer | P0 | M | `pytest -m e2e` gera Parquet válido e `RankScore` esperado sem GPU |

**DAG (M0):**
```
001 ─┬─ 002 ── 003 ── 004 ─┐
     ├─ 005 ───────────────┼─ 006 ─┐
     └─ 010                 │       ├─ 008 ─┐
                            └─ 007 ─┘       ├─ 009 ── 011 ── 012
                                            └───────────────┘
```
**Caminho crítico:** 001 → 005 → 006/007 → 008 → 009 → 011 → 012.
**Go/no-go:** E2E stub verde + cobertura de `domain` ≥95% → libera M1.

---

### 14.4. Milestone M1 — Geração A ponta-a-ponta (real, 1 configuração)

**Objetivo:** Gerar respostas **reais** para uma `{base, llm}` via Qdrant + vLLM-gerador, persistindo tidy e sendo resumível.
**Épicos:** E1. **Duração:** ~6 dias.

| Tarefa | Descrição | Skill | Prio | Tam | Critério de aceitação |
|---|---|---|---|---|---|
| TAREFA-101 | `OpenAICompatibleClient` base (retry/backoff/timeout) | backend-engineer | P0 | M | Retry exponencial + timeout; testado com `respx`; sem `shell=True` |
| TAREFA-102 | `QdrantRetriever` (`RetrieverPort`) | rag-engineer | P0 | M | `search(base, q, top_k)` retorna chunks+scores; integração c/ Qdrant real (skip se ausente) |
| TAREFA-103 | Template RAG versionado (`prompts/rag_answer.txt`) + loader | rag-engineer | P0 | S | Prompt fora do código; `prompt_version` registrado; delimitação dados×instrução |
| TAREFA-104 | `VLLMGenerator` (`GeneratorPort`, sem batch invariance) | rag-engineer | P0 | M | `generate(...)` com seed/temp; saída validada Pydantic; `GenerationError` em falha |
| TAREFA-105 | `RunExperimentUseCase` (Exp. A, idempotente) | rag-engineer | P0 | M | Itera produto cartesiano; pula `row_id` existente; isola falha de célula |
| TAREFA-106 | CLI `run --phase A` (Typer + rich progress) | backend-engineer | P1 | S | `--dry-run`, progress, `KeyboardInterrupt` tratado |
| TAREFA-107 | Integração: 1 config real → N linhas em Parquet | test-engineer | P0 | S | Contra Qdrant+vLLM reais; resumabilidade comprovada (mata e relança) |

**Go/no-go:** uma `{base, llm}` real gera 13×3 linhas com proveniência completa; relançar não duplica.

---

### 14.5. Milestone M2 — Avaliação automática (Camadas 1+2, juiz determinístico)

**Objetivo:** Completar as métricas das respostas geradas usando o **juiz determinístico**, consolidando `FinalScore`.
**Épicos:** E2. **Duração:** ~7 dias.

| Tarefa | Descrição | Skill | Prio | Tam | Critério de aceitação |
|---|---|---|---|---|---|
| TAREFA-201 | `PrometheusJudge` client (det.: temp=0, endpoint juiz) | rag-engineer | P0 | M | Aponta para `vllm-judge`; `batch_invariant=True` registrado; `JudgeUnavailableError` |
| TAREFA-202 | `RagasMetrics` (`MetricSuitePort`, Camada 1) | rag-engineer | P0 | L | Métricas da seção 5.1; usa juiz injetado; pin de versão; NaN tratado |
| TAREFA-203 | `DeterministicMetricPort` (BERTScore/ROUGE) | rag-engineer | P1 | S | Sem LLM; determinístico; sanity check |
| TAREFA-204 | Rubrica biomédica (`prompts/biomed_rubric.txt`) + `DeepEvalGEval` (Camada 2) | rag-engineer | P0 | M | Score [0,1] + feedback; rubrica da seção 5.2 do doc-base |
| TAREFA-205 | Parsing defensivo + retry (máx 3) → NaN explícito (ADR-007) | rag-engineer | P0 | M | Outputs rebeldes viram retry; esgotado → NaN + `metric_nan_fields`/`retry_count` |
| TAREFA-206 | `ComputeMetricsUseCase` (passada de julgamento, resumível) | rag-engineer | P0 | M | Seleciona linhas sem métricas; completa via `update_metrics`; idempotente |
| TAREFA-207 | Integração: determinismo do juiz | test-engineer | P0 | S | Mesma entrada 2× → score idêntico (juiz disponível) |

**Go/no-go:** respostas de M1 ganham as 3 camadas automáticas; determinismo do juiz comprovado; taxa de NaN reportada.

---

### 14.6. Milestone M3 — Rodada 1 completa + orquestração das 4 GPUs

**Objetivo:** Rodar **toda** a Rodada 1 (Exp. A: 10 configs; Exp. B: 5 configs) com o juiz residente na GPU dedicada e os 5 geradores em rotação por ondas nas 3 GPUs restantes (ADR-012), emitindo run report.
**Épicos:** E3, E4. **Duração:** ~8 dias.

| Tarefa | Descrição | Skill | Prio | Tam | Critério de aceitação |
|---|---|---|---|---|---|
| TAREFA-301 | `model_registry.yaml` + resolução (nome lógico → pesos + `quantization` + `tensor_parallel_size` + GPU) | backend-engineer | P0 | S | `ModelNotInRegistryError` se ausente; params de serving e TP por modelo (ADR-012) |
| TAREFA-302 | `VLLMServerManager` (`start/wait_healthy/stop`) com fixação de GPU via `CUDA_VISIBLE_DEVICES` | backend-engineer | P0 | L | Sobe/derruba vLLM via subprocess seguro; servidores concorrentes em GPUs distintas; healthcheck; `ServerStartTimeoutError` |
| TAREFA-303 | Escalonador de ondas (3 geradores concorrentes → onda 2; juiz residente desde o início) | backend-engineer | P0 | M | Juiz carregado 1×; geradores trocam ≤1×; plano de ondas no `--dry-run`; `ModelSwitchError` recuperável; modo `gpu_layout` selecionável (ADR-012) |
| TAREFA-304 | `build_canonical_contexts` (Exp. B: top-8 IDx_400k ou curado) | rag-engineer | P0 | S | Contextos congelados idênticos para os 5 LLMs |
| TAREFA-305 | Experimento B no `RunExperimentUseCase` (`base="fixed"`) | rag-engineer | P0 | S | 5×3×13 linhas; mesmos contextos por pergunta |
| TAREFA-306 | Run report (planejado/concluído/pulado/falha, NaN, latência, versões, **mapa GPU→modelo por onda**) | python-engineer | P0 | M | Sumário persistido; audita regime de determinismo por fase e alocação de GPU |
| TAREFA-307 | E2E orquestração com stubs simulando 4 GPUs (concorrência + ondas) | test-engineer | P0 | M | Juiz "residente" + 2 ondas de geradores stub, sem GPU real |
| TAREFA-308 | `AnnotationWorkflowUseCase` + CLI `annotate` (Camada 3) | python-engineer | P0 | M | Export JSONL estratificado; ingest com merge idempotente por `row_id` |
| TAREFA-309 | DI Wiring + CLI `run` completo + `BenchmarkLoader` | backend-engineer | P0 | L | `--run-id` obrigatório; `--phase A/B/both`; `--serial`; `BenchmarkLoader` resolve `questions:` do YAML |
| TAREFA-310 | Gate E2E ciclo completo M3 | test-engineer | P0 | M | Pipeline completo (stubs) em ≤60 s; 5 fases Pass |
| TAREFA-311 | `ExternalVLLMServerManager` + probes de proveniência (ADR-014) | backend-engineer | P0 | M | `server_mode=external`; probes served_model/version/determinism; `determinism_verified=False` default |
| TAREFA-312 | Gate de integração 309/310/311/606 (PASS) | test-engineer | P0 | S | Retrocompat de logs; `determinism_verified` default confirmado; schema §4.3/§5.3 em 46 colunas |

**Go/no-go (as-built):** Rodada 1 (585 respostas) avaliada e persistida; juiz carregado 1× e geradores em ≤2 ondas; run report limpo com mapa GPU→modelo; modo external + probes de proveniência implementados e auditados; **gate para análise**.

---

### 14.7. Milestone M4 — Decisão executiva da Rodada 1 (Camada 3 + Agregação + Estatística + Relatório)

**Objetivo:** Produzir o ranking executivo e a leitura estatística que respondem às 5 perguntas do doc-base §2.1.
**Épicos:** E5, E6, E7. **Duração:** ~9 dias.

| Tarefa | Descrição | Skill | Prio | Tam | Critério de aceitação |
|---|---|---|---|---|---|
| TAREFA-401 | CLI `annotate` (export estratificado por score baixo) | python-engineer | P0 | M | Exporta CSV/JSONL priorizando baixos; instrução ao especialista |
| TAREFA-402 | `IngestHumanAnnotationUseCase` (merge `critical_failure_flag` por `row_id`) | python-engineer | P0 | S | Merge idempotente; recalcula `CriticalFailureRate` |
| TAREFA-403 | `AggregateResultsUseCase` (todas as métricas da seção 7.2) | data-engineer | P0 | M | Tabela por `{base,llm}`; exclui NaN; `WinRate` correto |
| TAREFA-404 | `StatsPort`: Wilcoxon (base×base) | ml-engineer | P0 | S | Pareado; por métrica; dataset sintético valida |
| TAREFA-405 | `StatsPort`: Friedman + Nemenyi (entre LLMs) | ml-engineer | P0 | M | Global + post-hoc pares; correção múltipla (BH/Holm) |
| TAREFA-406 | `StatsPort`: Modelo linear misto (`score ~ base*llm + (1|question)`) | ml-engineer | P0 | M | Efeitos principais + interação; `statsmodels.mixedlm` |
| TAREFA-407 | `StatisticalAnalysisUseCase` + correção múltipla | ml-engineer | P0 | S | Orquestra os 3 testes; relatório de p-valores corrigidos |
| TAREFA-408 | Visualizações canônicas (heatmap, boxplot, interação, radar, per-question, failure breakdown) | python-engineer | P1 | L | 6 figuras da seção 11.4 do doc-base |
| TAREFA-409 | `report` (HTML/MD consolidado) | python-engineer | P1 | M | Junta agregados + estatística + figuras + run report |

**Go/no-go:** as 5 perguntas operacionais respondidas com evidência; melhor `{base,llm}` por `RankScore` identificada → decisão de produção habilitada.

---

### 14.8. Milestone M5 — Rodada 2 (funil de retrieval + OFAT chunking/embedding)

**Objetivo:** Variar chunking (2a) e embedding (2b) com o funil barato de retrieval puro antes da geração cara.
**Épicos:** E8. **Duração:** ~9 dias. **Gate de entrada:** curadoria de chunks-ouro entregue (Premissa P5).

| Tarefa | Descrição | Skill | Prio | Tam | Critério de aceitação |
|---|---|---|---|---|---|
| TAREFA-501 | `GoldChunkReader` + formato de chunks-ouro | rag-engineer | P0 | S | Lê lista esperada por pergunta; validação de formato |
| TAREFA-502 | Métricas de retrieval puro (precision@k, recall@k, MRR, nDCG@k) | data-engineer | P0 | M | Contra chunks-ouro; dataset `retrieval_metrics/` separado |
| TAREFA-503 | `FunnelSelector` (top-3 configs de retrieval) | rag-engineer | P0 | S | Seleção determinística; unit com ranking conhecido |
| TAREFA-504 | `RetrievalFunnelUseCase` (estágio 1 barato) | rag-engineer | P0 | M | Roda sem LLM; alimenta estágio 2 |
| TAREFA-505 | Variação de chunking (2a) — config + reindex parametrizado | data-engineer | P1 | M | 3–5 variantes; `chunk_strategy` registrado |
| TAREFA-506 | Variação de embedding (2b) — config + reindex | data-engineer | P1 | M | 3–5 variantes; `embedding_model` registrado |
| TAREFA-507 | Reuso do pipeline A nas top-3 (estágio 2 caro) | rag-engineer | P0 | S | Orquestrador agnóstico ao fator variado |

**Go/no-go:** melhor combinação de chunking+embedding identificada via funil, com custo de geração restrito ao top-3.

---

### 14.9. Milestone M6 — Hardening, validação do juiz e documentação final

**Objetivo:** Robustez de produção-de-pesquisa e auditabilidade.
**Épicos:** E9. **Duração:** ~6 dias.

| Tarefa | Descrição | Skill | Prio | Tam | Critério de aceitação |
|---|---|---|---|---|---|
| TAREFA-601 | Mutation testing em `domain/services` | test-engineer | P1 | M | Mutation score >80% em scoring/ranking |
| TAREFA-602 | Validação amostral humana do juiz (Cohen's κ em ~10%) | ml-engineer | P0 | M | κ calculado e reportado; determinismo do juiz garante validade |
| TAREFA-603 | Property-based em parsers/serializers | test-engineer | P1 | S | Roundtrip e idempotência cobertos |
| TAREFA-604 | Manual de operação final (`docs/operations_manual.md`) | python-engineer | P0 | M | Seção 15 deste doc versionada + validada por execução real |
| TAREFA-605 | Revisão final de segurança (segredos, prompt injection) | code-reviewer | P1 | S | Nenhum segredo no Git; teste de chunk malicioso |
| TAREFA-606 | Manual de operação — emenda modo external (ADR-014, Seção 4-B) | python-engineer | P0 | S | Seção 4-B detalhada; `validate_manual.py` PASS |
| TAREFA-607 | Doc-sync: arquitetura v1.2 + visão v1.1 (TAREFA-309/310/311/312) | python-engineer | P0 | M | Versões bumpadas; ADR-013/014 no catálogo; §7.2/§12/§14 reconciliados |

**Go/no-go:** subsistema reprodutível, auditado e documentado para uso recorrente nas próximas rodadas.

---

### 14.10. Caminho crítico do sistema e matriz skills × épicos

**Caminho crítico (sequencial):** M0 → M1 → M2 → M3 → M4. (M5 e M6 dependem de M4 e podem paralelizar parcialmente com a curadoria de chunks-ouro.)

```
M0 (contratos)──▶M1 (geração A)──▶M2 (avaliação)──▶M3 (Rodada 1 + GH200)──▶M4 (decisão)
                                                                          │
                                              chunks-ouro (especialista) ─┤
                                                                          ▼
                                                                M5 (Rodada 2) ──▶ M6 (hardening)
```

**Matriz skills × épicos:**

| | E0 | E1 | E2 | E3 | E4 | E5 | E6 | E7 | E8 | E9 |
|---|---|---|---|---|---|---|---|---|---|---|
| python-engineer | ● | | | | | ● | | ● | | ● |
| backend-engineer | | ● | | | ● | | | | | |
| rag-engineer | | ● | ● | ● | | | | | ● | |
| data-engineer | ● | | | | | | ● | | ● | |
| ml-engineer | ● | | | | | | ● | | | ● |
| test-engineer | ● | ● | ● | ● | ● | | | | | ● |
| code-reviewer | (todos os PRs — papel do Codex, seção 16) | | | | | | | | | ● |

**Riscos estratégicos de execução:** (1) atraso da curadoria de chunks-ouro → isola Rodada 1 de Rodada 2; (2) instabilidade da orquestração das 4 GPUs (concorrência + troca de onda + fixação por `CUDA_VISIBLE_DEVICES`) → M3 tem spike de risco, atacar `VLLMServerManager` cedo com E2E stub que simula 4 GPUs; (3) drift de versão RAGAS/vLLM → pins + proveniência desde M0.

---

## 15. Manual de operação e ambiente (GH200 + vLLM)

> Este manual é a fonte de bancada do operador. A TAREFA-604 o versiona em `docs/operations_manual.md` e o valida por execução real. Comandos com versões/paths são *placeholders* a confirmar no M0.

### 15.1. Pré-requisitos da máquina

- GH200 com driver NVIDIA + CUDA compatível com a versão alvo do vLLM (registrar em `vllm_version`).
- vLLM instalado **com suporte a batch invariance** (Premissa P3 — confirmar com `python -c "import vllm; print(vllm.__version__)"` e checar a doc da versão para a flag `VLLM_BATCH_INVARIANT`).
- Qdrant acessível (porta 6333) com as coleções `IDx_400k` e `ID_230K`.
- Pesos dos 5 LLMs + Prometheus-2 8x7B disponíveis (local ou HuggingFace acessível).

### 15.2. Setup do ambiente Python (reprodutível)

```bash
git clone <repo> && cd inteligenciomica_eval
uv sync --frozen                 # cria venv idêntico ao lock
uv run ielm-eval --help          # smoke test da CLI

# Segredos/endpoints via ambiente (NUNCA no YAML versionado — ADR-008)
export VLLM_GENERATOR_URL="http://localhost:8000/v1"
export VLLM_JUDGE_URL="http://localhost:8001/v1"
export QDRANT_URL="http://localhost:6333"
# tokens, se houver, também via env
```

### 15.3. O `model_registry.yaml` — alocação declarativa

A alocação de modelos é **declarativa**: cada modelo lógico mapeia para pesos, parâmetros de serving, **GPU(s)** e tensor parallelism. O orquestrador (`VLLMServerManager`) lê este arquivo; o operador nunca decora flags. As GPUs 0–2 são da rotação de geradores; a GPU 3 é dedicada ao juiz (ADR-012).

```yaml
# config/model_registry.yaml
gpu_layout: judge_dedicated      # ou "generators_first" (ADR-012)
generators:
  # tensor_parallel_size: 1 → cabe em 1 GPU; 2 → ocupa 2 GPUs da rotação (P1.1)
  gpt-oss-120b:
    model_path: <hf-or-local-path>
    quantization: <conforme-produção>     # NÃO alterar params de produção (ADR-003)
    max_model_len: 8192
    tensor_parallel_size: 1               # se não couber em 1 GPU, use 2 (verificar no M0)
    extra_args: ["--gpu-memory-utilization", "0.92"]
  gemma4:31b:    { model_path: <...>, quantization: <...>, max_model_len: 8192, tensor_parallel_size: 1 }
  qwen3.6:35b:   { model_path: <...>, quantization: <...>, max_model_len: 8192, tensor_parallel_size: 1 }
  glm-4.7-flash: { model_path: <...>, quantization: <...>, max_model_len: 8192, tensor_parallel_size: 1 }
  llama4:16x17b: { model_path: <...>, quantization: <...>, max_model_len: 8192, tensor_parallel_size: 1 }

judge:
  prometheus-8x7b-v2.0:
    model_path: prometheus-eval/prometheus-8x7b-v2.0
    quantization: awq
    tensor_parallel_size: 1               # OBRIGATÓRIO (batch invariance) — ADR-003
    gpu: 3                                 # GPU dedicada
    max_model_len: 8192
    env:                                   # regime determinístico (ADR-003)
      VLLM_BATCH_INVARIANT: "1"
      VLLM_ENABLE_V1_MULTIPROCESSING: "0"
```

> O orquestrador atribui dinamicamente as GPUs 0–2 aos geradores de cada onda (via `CUDA_VISIBLE_DEVICES`); só o juiz tem GPU fixa (3). Geradores com `tensor_parallel_size: 2` consomem 2 das 3 GPUs da rotação naquela onda.

### 15.4. Modelo mental da alocação no GH200 (4 GPUs)

O nó tem **4 GPUs** (Premissa P1). São 6 modelos (5 geradores + juiz) — não cabem os 6 ao mesmo tempo, mas cabem **4 simultâneos**. Estratégia (ADR-012):

> **Regra de ouro operacional:** a **GPU 3 hospeda o juiz** o tempo todo (residente, carregado 1×). As **GPUs 0–2 giram os 5 geradores em 2 ondas** — onda 1 com 3 geradores concorrentes, onda 2 com os 2 restantes. Apenas **uma** troca de modelos por rodada.

Cada servidor vLLM serve **um** modelo (flag `--model`) e é fixado a uma GPU por `CUDA_VISIBLE_DEVICES`. "Trocar de onda" = parar os 3 geradores da onda 1 e subir os 2 da onda 2 nas mesmas GPUs. O juiz nunca é tocado entre ondas. Como juiz e geradores coexistem (GPUs diferentes), o julgamento pode rodar **em paralelo** à geração (pipeline) — opcional; o modo padrão executa geração e depois julgamento, com o juiz já carregado. (Otimizações como *sleep mode*/hot-swap, se a versão do vLLM oferecer, podem acelerar a troca de onda — avaliar, não é pré-requisito.)

### 15.5. Subindo o juiz (determinístico, GPU dedicada) — manual

```bash
# Juiz fixo na GPU 3, residente o tempo todo
CUDA_VISIBLE_DEVICES=3 \
VLLM_BATCH_INVARIANT=1 \
VLLM_ENABLE_V1_MULTIPROCESSING=0 \
python -m vllm.entrypoints.openai.api_server \
    --model prometheus-eval/prometheus-8x7b-v2.0 \
    --quantization awq \
    --tensor-parallel-size 1 \
    --max-model-len 8192 \
    --port 8001
# healthcheck:
curl -s http://localhost:8001/v1/models | jq .
```

### 15.6. Subindo os geradores (realistas, uma onda) — manual

Onda 1 — três geradores concorrentes, um por GPU (0, 1, 2), todos sem batch invariance (ADR-003). Use portas distintas para coexistirem:

```bash
# gerador A → GPU 0 : porta 8000
CUDA_VISIBLE_DEVICES=0 python -m vllm.entrypoints.openai.api_server \
    --model <modelo-A> --quantization <prod> --max-model-len 8192 \
    --gpu-memory-utilization 0.92 --port 8000 &

# gerador B → GPU 1 : porta 8010
CUDA_VISIBLE_DEVICES=1 python -m vllm.entrypoints.openai.api_server \
    --model <modelo-B> --quantization <prod> --max-model-len 8192 \
    --gpu-memory-utilization 0.92 --port 8010 &

# gerador C → GPU 2 : porta 8020
CUDA_VISIBLE_DEVICES=2 python -m vllm.entrypoints.openai.api_server \
    --model <modelo-C> --quantization <prod> --max-model-len 8192 \
    --gpu-memory-utilization 0.92 --port 8020 &

# healthchecks
for p in 8000 8010 8020; do curl -s http://localhost:$p/v1/models | jq -r '.data[0].id'; done
```

Para a **onda 2**: encerrar os 3 processos de geradores (não o juiz na GPU 3), aguardar `nvidia-smi` liberar as GPUs 0–2, e subir os 2 geradores restantes. Para um gerador grande que precise de `TP=2`: `CUDA_VISIBLE_DEVICES=0,1 ... --tensor-parallel-size 2` (ocupa 2 GPUs da rotação naquela onda).

### 15.7. Orquestração automática (modo recomendado)

A CLI `ielm-eval` tem **8 subcomandos**: `version`, `run`, `annotate`, `analyze`, `report`, `status`, `show-config`, `validate-judge`. Para detalhes operacionais do modo `external`, ver `docs/operations_manual.md` Seção 4-B.

O `VLLMServerManager` (TAREFA-302/303) automatiza tudo: sobe o juiz na GPU 3, sobe a onda 1 de geradores nas GPUs 0–2, gera, troca para a onda 2, e (em paralelo ou em seguida) avalia com o juiz residente. O operador roda **um** comando:

```bash
# Rodada completa (ambos os experimentos A e B): juiz residente + 2 ondas de geradores
uv run ielm-eval run --config config/experiment_round1.yaml --run-id <run_id>
# (internamente: start juiz@GPU3 → onda1 [3 geradores@GPU0-2] → gera → onda2 [2 geradores] → gera
#  → julga tudo com o juiz residente; resumível por row_id)
```

Flags disponíveis em `ielm-eval run`:

| Flag | Obrigatória | Descrição |
|---|---|---|
| `--config` | Sim | Caminho para o YAML de rodada |
| `--run-id` | Sim | Identificador único da execução (para resumibilidade) |
| `--phase` | Não | `A`, `B` ou `both` (default `both`) |
| `--serial` | Não | Executa ondas em série em vez de concorrente (debug) |
| `--dry-run` | Não | Imprime plano sem tocar GPU/rede |
| `--require-verified-determinism` | Não | Aborta se `determinism_verified=False` (publicação) |

`--dry-run` imprime o plano antes de tocar a GPU:

```bash
uv run ielm-eval run --config config/experiment_round1.yaml --run-id <run_id> --dry-run
# imprime: mapa GPU→modelo por onda, nº de células por modelo, células já existentes (puladas), endpoints
```

### 15.8. Fluxo completo de uma rodada (operador)

```bash
# 0. Sanidade — valida config sem tocar GPU
uv run ielm-eval run --config config/experiment_round1.yaml --run-id round_1_<data> --dry-run
curl -s "$QDRANT_URL/collections" | jq .          # bases existem?

# 1. Execução completa (geração em ondas concorrentes + julgamento com juiz residente; resumível)
uv run ielm-eval run --config config/experiment_round1.yaml --run-id round_1_<data>
# Experimento A apenas: --phase A | Experimento B apenas: --phase B
# Modo serial (debug, 1 onda por vez): adicionar --serial
# Verificação de determinismo obrigatória (publicação): adicionar --require-verified-determinism

# 2. Anotação humana (Camada 3) — exporta priorizando scores baixos
uv run ielm-eval annotate --run-id round_1_<data> --export annotations.jsonl
#    ... especialista preenche critical_failure_flag ...
uv run ielm-eval annotate --run-id round_1_<data> --ingest annotations.jsonl

# 3. Agregação + estatística + relatório
uv run ielm-eval analyze --run-id round_1_<data> --tests all
uv run ielm-eval report  --run-id round_1_<data> --format html
```

### 15.9. Rodada 2 (M5 — pendente)

> **Status M5:** adiado até curadoria de chunks-ouro (Premissa P5) e decisão da Rodada 1.
> Os subcomandos `--stage retrieval-funnel` e `--stage full` **ainda não existem** na CLI;
> chegam com o Milestone M5 (ADR-013). Não executar os comandos abaixo até o M5 ser iniciado.

```bash
# [M5 FUTURO] Estágio 1 — funil de retrieval puro (barato, sem LLM)
# uv run ielm-eval run --config config/experiment_round2a.yaml --stage retrieval-funnel
# seleciona top-3 configs de chunking; idem 2b para embedding

# [M5 FUTURO] Estágio 2 — geração+avaliação só nas top-3 (reusa o fluxo da Rodada 1)
# uv run ielm-eval run --config config/experiment_round2a.yaml --stage full --top-configs 3
```

### 15.10. Troubleshooting

| Sintoma | Causa provável | Ação |
|---|---|---|
| OOM ao subir gerador | Modelo + sobra do anterior na GPU, ou onda 2 antes da onda 1 liberar | Confirmar `nvidia-smi` das GPUs 0-2 zerado antes da próxima onda; o manager aguarda liberação |
| Gerador caiu mas o juiz também | Gerador subiu sem `CUDA_VISIBLE_DEVICES` e invadiu a GPU 3 | Sempre fixar GPU por servidor; juiz isolado na GPU 3 (ADR-012) |
| Juiz dá scores diferentes p/ mesma entrada | `VLLM_BATCH_INVARIANT` não ativo / TP>1 | Verificar env do `vllm-judge` e `tensor_parallel_size=1` (ADR-003) |
| Muitos NaN em `rubric_biomed_score` | Juiz devolvendo não-JSON | Ver `retry_count`/`rubric_feedback`; ajustar template; é tolerado (ADR-007) |
| Rodada reinicia do zero | `run_id` diferente | Reusar o **mesmo** `run_id` para retomar (ADR-009) |
| Endpoint recusado | Servidor não saudável | `curl /v1/models`; o manager tem `ServerStartTimeoutError` |

---

## 16. Workflow AI-assisted: Claude Code (dev) + Codex (verificador)

O desenvolvimento é conduzido por um desenvolvedor sênior usando **dois agentes em papéis distintos**: **Claude Code implementa** uma tarefa; **ChatGPT Codex verifica** a aderência à especificação (este documento + as skills). O humano arbitra. O ciclo é por **tarefa** (`TAREFA-NNN`), não por milestone — granularidade pequena reduz alucinação e facilita revisão.

### 16.1. O ciclo dev↔verify

```
   [Humano] seleciona TAREFA-NNN do milestone corrente
        │
        ▼
   [Claude Code]  ── implementa: código + testes + docstrings + logs
        │            (segue ADRs, ports da seção 5, padrões das skills)
        ▼
   [Codex] ── verifica contra checklist de aceitação da tarefa + DoD §14.2
        │      produz: PASS / FAIL + lista de divergências citando linha/critério
        ▼
   [Humano] arbitra:  PASS → merge   |   FAIL → devolve divergências ao Code
        │                                         (loop até PASS)
        ▼
   próxima tarefa (respeitando o DAG)
```

A assimetria é proposital: quem escreve não é quem aprova. O Codex no papel de `code-reviewer` aplica a mesma régua para todo PR (seção 14.10).

### 16.2. Anatomia de um prompt de implementação (para Claude Code)

Cada prompt referencia este documento por identificadores. Template:

```
CONTEXTO: Subsistema de Validação InteligenciÔmica. Arquitetura em
`arquitetura_detalhada_validacao_inteligenciomica.md`. Skills do projeto valem
como padrão (python-clean-architecture, test-engineer, rag-engineer).

TAREFA: TAREFA-104 — implementar VLLMGenerator (GeneratorPort).

ESPECIFICAÇÃO:
- Implementa o Protocol `GeneratorPort` (seção 5.1).
- Governado por ADR-003 (SEM batch invariance) e ADR-005 (cliente OpenAI-compatible).
- Reusa OpenAICompatibleClient (TAREFA-101) por injeção de dependência.
- Saída validada por Pydantic; falha → GenerationError (seção 9).
- Endpoint via env VLLM_GENERATOR_URL (nunca hardcoded).

ENTREGÁVEL:
- src/.../infrastructure/adapters/vllm_generator.py
- tests/integration/adapters/test_vllm_generator.py (respx p/ HTTP determinístico)
- tests/unit/... se houver lógica pura extraível

RESTRIÇÕES (DoD §14.2):
- from __future__ import annotations; type hints; docstrings Google.
- Sem import de infra em domain/application; import-linter deve passar.
- mypy --strict, ruff, cobertura não regride.
- Logging estruturado; batch_invariant=False registrado.

CRITÉRIO DE ACEITAÇÃO (copiar da tabela da TAREFA-104):
- generate(...) respeita seed/temperature; valida saída; GenerationError em falha.
```

### 16.3. Anatomia de um prompt de verificação (para Codex)

```
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-104 + arquitetura_detalhada (seções 5, 9, ADR-003/005)
+ skill code-reviewer.

VERIFIQUE, item a item, citando arquivo:linha:
1. Implementa GeneratorPort exatamente (assinatura da seção 5.1)?
2. Respeita ADR-003 (sem batch invariance) e ADR-005 (cliente reusado)?
3. Saída validada por Pydantic? Falhas viram GenerationError?
4. import-linter: domain/application limpos de infra? (cheque imports)
5. Testes cobrem happy + borda + erro? respx usado (sem rede real em teste)?
6. DoD §14.2 integralmente?

SAÍDA: veredito PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade
bloqueador/importante/sugestão). Sem bloqueadores ⇒ PASS.
```

### 16.4. Regras do loop

- **Uma tarefa por PR.** PRs grandes mascaram regressão (anti-pattern `tech-lead`).
- **O verificador cita a especificação**, não opina solto — cada FAIL aponta ADR/seção/critério violado.
- **Ordem do DAG é lei.** Não iniciar tarefa com dependência não-mergeada (ex.: TAREFA-105 espera 102+104).
- **Spikes de risco primeiro.** `VLLMServerManager` (TAREFA-302) e parsing do juiz (TAREFA-205) são os desconhecidos; atacá-los cedo dentro de seus milestones.
- **Golden e import-linter são gates automáticos** — antes mesmo do Codex, o CI barra violação de camada e regressão de scoring.
- **Proveniência desde o primeiro PR.** Nenhuma linha de Parquet sem `config_hash`/versões (RF8) — verificável já em M0.

### 16.5. Ordem de geração de prompts

A sequência de prompts segue o caminho crítico: todas as tarefas de M0 (na ordem do DAG §14.3), depois M1, M2, M3, M4; M5/M6 após o gate de M4. Tarefas paralelizáveis dentro de um milestone (sem aresta entre si) podem ser despachadas em lote ao Code, desde que o Codex as verifique individualmente.

---

## 17. Checklists de prontidão

### 17.1. Prontidão arquitetural (`system-architect` §6)

- [x] Requisitos funcionais (RF1–8) e não-funcionais (RNF1–6) capturados (seção 2).
- [x] Bounded context único (Evaluation) com 3 sub-domínios nomeados (seção 4.2).
- [x] Contratos explícitos: ports `Protocol` + DTOs Pydantic + esquema Parquet (seção 5).
- [x] Decisões não-óbvias com ADR (seção 6, ADR-001..011).
- [x] Riscos com mitigação localizada no código (seção 13).
- [x] Plano incremental com MVP claro (M0 esqueleto → M4 decisão).
- [x] Observabilidade definida (seção 10).
- [x] Superfícies de segurança mapeadas (segredos via env, prompt injection — seção 13).
- [x] Handoff para tech-lead com backlog suficiente (seção 14).

### 17.2. Prontidão para implementação (`tech-lead` §7)

- [x] Cada tarefa tem critério de aceitação verificável (tabelas da seção 14).
- [x] Cada tarefa tem skill responsável.
- [x] DAG e caminho crítico explícitos (seções 14.3–14.10).
- [x] Milestones com go/no-go mensurável.
- [x] Estimativas relativas (T-shirt; nada > L sem subdividir).
- [x] Riscos de execução mapeados (seção 14.10).
- [x] ADRs linkados nas tarefas que dependem deles.
- [x] Testes planejados em paralelo (DoD §14.2, seção 11).
- [x] Observabilidade desde M0 (seção 10).

### 17.3. Itens a confirmar no M0 (premissas)

- [x] P1 — GH200 com **4 GPUs**, integralmente disponível (confirmado). Define a alocação juiz-dedicado + ondas (ADR-012).
- [ ] P1.1 — Footprint por modelo na quantização de produção: cada gerador cabe em 1 GPU? Se não, marcar `tensor_parallel_size: 2` no registry.
- [ ] P2 — Pesos dos 5 LLMs + quantizações acessíveis?
- [ ] P3 — Versão do vLLM suporta `VLLM_BATCH_INVARIANT`? (registrar)
- [ ] P4 — 13 perguntas + ground truth padronizadas e versionadas?
- [ ] P5 — Cronograma da curadoria de chunks-ouro (gate de M5)?
- [ ] *baseline* de chunking, embedding, top-k e reranker definidos (próximos passos do doc-base)?

---

## 18. Próximos passos

1. **Validar este documento** com a equipe e fechar os itens da seção 17.3 (premissas + *baseline*).
2. **Registrar os ADRs** em `docs/adr/` no repositório (vivem com o código a partir de M0).
3. **Disparar M0** gerando os prompts da TAREFA-001 em diante para a dupla Code/Codex, na ordem do DAG (seção 16.5).
4. **Curadoria de chunks-ouro** em paralelo (não bloqueia M0–M4; é gate de M5).
5. **Confirmar versões** de vLLM/RAGAS/DeepEval e congelá-las no `uv.lock` antes da primeira linha de Parquet (proveniência).

---

**Documento de arquitetura detalhada — pronto para servir de base aos prompts de Claude Code (desenvolvimento) e ChatGPT Codex (verificação).**
**Rastreabilidade:** ADR-001..011 · M0..M6 · TAREFA-001..605 · RF1..8 · RNF1..6 · P1..5.
