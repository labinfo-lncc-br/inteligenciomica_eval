# ADR-013 — Funil de dois estágios para Rodada 2 (OFAT)

**Status:** Aceito  
**Data:** 2026-06-02  
**Autores:** Equipe InteligenciÔmica  
**Milestone:** M4 (gate TAREFA-409) — Pré-operacionalização M5  

---

## Context

A Rodada 2 executa experimentos OFAT (One-Factor-At-a-Time) para otimização de
retrieval (chunking, embedding, top-k). O custo de geração via LLM é O(N_configs ×
N_perguntas × N_seeds):

- Rodada 1: 2 bases × 5 LLMs × 3 seeds × 13 perguntas = 390 células por passada
- Rodada 2 (OFAT): estimativa de 5 configs × 13 perguntas × 3 seeds = 195 chamadas
  de geração LLM por fase, **por configuração OFAT candidata**

Com múltiplas configurações OFAT candidatas (chunk size, embedding model, top-k),
o custo total de geração pode chegar a milhares de chamadas de LLM, tornando a
avaliação exaustiva computacionalmente proibitiva dentro do orçamento de compute
do projeto.

### Problema

Configurações ruins em retrieval produzem contextos pobres → gerações pobres. Se
as métricas de retrieval (nDCG@k, recall@k) já discriminam candidatos claramente,
a passada de geração completa (cara) é desnecessária para a maioria dos candidatos.

---

## Decision

Implementar um funil de dois estágios para a Rodada 2:

**Estágio 1 — Filtro de retrieval puro (sem LLM, barato):**
- Calcula métricas de retrieval (nDCG@k, recall@k) para todas as configurações
  OFAT candidatas contra as 13 perguntas × gold chunks.
- Ordena candidatos por `nDCG@k` médio.
- Seleciona os `top_n=3` candidatos (default configurável).

**Estágio 2 — Avaliação completa (apenas top-N):**
- Executa o pipeline completo (retrieval + geração LLM + métricas Camada 1+2)
  somente para os `top_n=3` candidatos selecionados no Estágio 1.
- Produz `EvaluationResult` completos para comparação estatística via M4.

**Parâmetro:** `top_n: int = 3` (configurável via round config da Rodada 2).

---

## Consequences

### Positivas

- Reduz chamadas de LLM em ~60% (de N_total_configs para 3 × passada completa),
  mantendo a qualidade de seleção — configurações boas em retrieval tendem a
  produzir contextos melhores para geração.
- Mantém compatibilidade total com o pipeline M3/M4: o Estágio 2 gera os mesmos
  artefatos Parquet/Relatório que a Rodada 1.
- `top_n=3` cobre a maioria dos cenários OFAT com margem para empates.

### Negativas / Riscos aceitos

- Configurações excepcionais (boas em geração, ruins em retrieval) podem ser
  descartadas no Estágio 1. **Mitigação:** este risco é considerado aceitável
  porque retrieval ruim → contexto pobre → geração provavelmente ruim; a
  correlação entre qualidade de retrieval e geração é bem estabelecida na
  literatura RAG.
- Requer implementação de métricas de retrieval offline (fora do escopo de M4;
  planejadas para M5 via `RetrievalMetricsPort`).

### Implementação

Esta decisão não altera contratos de domínio de M0–M4. A implementação do Estágio
1 é planejada para M5 (TAREFA-501/502 — `RetrievalMetricsPort` +
`Round2FunnelUseCase`). O parâmetro `top_n=3` será exposto como opção do round
config da Rodada 2 (`round_config_round2.yaml`).

---

## Referências

- §8 (doc-base): planejamento da Rodada 2 (OFAT)
- §14.7: tabela de tarefas M4
- ADR-011: análise estatística (Wilcoxon, Friedman, MLM)
- ADR-012: orquestração de GPUs (wave scheduler)
