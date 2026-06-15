# M6_TAREFA-608_A — Doc-sync pós-316: prompt de geração versionado

**Data**: 2026-06-15
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: system-architect
**Prioridade / Tamanho**: P2 / S

---

## Objetivo

Sincronizar a documentação normativa com o as-built da TAREFA-316 (ADR-015 — prompt de
geração fiel à produção, bundle versionado `{system, user}`, selecionável por rodada):

- `docs/arquitetura_detalhada_validacao_inteligenciomica.md` v1.2 → **v1.3**
- `docs/visao_alto_nivel_validacao_inteligenciomica.md` v1.1 → **v1.2**

---

## Arquivos Modificados

```
git diff --name-only
docs/arquitetura_detalhada_validacao_inteligenciomica.md
docs/visao_alto_nivel_validacao_inteligenciomica.md
```

Nenhum arquivo de código, schema, config ou teste foi tocado (DOCS-ONLY).

---

## Edições Aplicadas

### Arquitetura (A1–A11)

#### A1 — Cabeçalho + Changelog v1.3

- Versão bumped de `1.2` → `1.3`; data `08/06/2026` → `15/06/2026`
- Changelog v1.3 adicionado ACIMA do v1.2 com 9 itens:
  (i) ADR-015; (ii) system+user+PMID+strip `<think>`; (iii) `Chunk.source`;
  (iv) semântica refinada de `prompt_version`; (v) estrutura de `prompts/rag/<version>/`;
  (vi) `generation_prompt_version` no YAML; (vii) proveniência; (viii) risco novo §13;
  (ix) §14.6/14.9/17.1/rodapé reconciliados.

#### A2 — §6 Catálogo de ADRs — ADR-015

Entrada completa adicionada APÓS ADR-014, com:
- **Status**: Aceito (TAREFA-316)
- **Contexto**: divergências do gerador vs produção (mensagem única vs system+user; sem PMID; sem strip)
- **Decisão**: bundle `{system.txt, user.j2}` em `infrastructure/prompts/rag/<version>/`; default `v1_production`; `generation_prompt_version` no YAML; `prompt_version` = bundle gravado
- **Alternativas**: prompt inline (rejeitado); bundle único sem versão (rejeitado)
- **Consequências**: fidelidade, A/B de prompt, semântica de `prompt_version`, `Chunk.source`
- **Referências**: ADR-003, ADR-005, ADR-008
- **Referência de arquivo**: `docs/adr/ADR-015-prompt-geracao-versionado.md`

#### A3 — §3.4 Fluxo de dados — passo 3b

Passo 3b anotado com:
- `QdrantRetrieverAdapter` preenche `Chunk.source` (PMID)
- `VLLMGeneratorAdapter` monta DUAS mensagens (system + user)
- contexto `"[PMID:{source}] {text}"` unido por `"\n\n"`
- strip de `<think>...</think>` antes de `GenerationOutput`
- nota explícita: assinatura de `GeneratorPort` (§5.1) permanece inalterada

#### A4 — §5.3 Esquema de dados — `prompt_version`

Nota alterada de "versão do template RAG" para:
> versão do **bundle de geração** (system+user) selecionado via `generation_prompt_version` (ADR-015)

#### A5 — §8 Estrutura de código — `infrastructure/prompts/`

Substituída listagem `rag_answer.txt / biomed_rubric.txt` por:
```
prompts/
├── rag/
│   └── <version>/
│       ├── system.txt   # mensagem system — texto puro, fiel à produção
│       └── user.j2      # mensagem user — Jinja2 com {{ context }}/{{ question }}
└── biomed_rubric*.j2    # rubrica do juiz (Camada 2)
# Novas redações de prompt entram como nova <version>/ — sem alterar código
```

#### A6 — §12.1 YAML de rodada

Campo adicionado ao exemplo `experiment_round1.yaml`:
```yaml
generation_prompt_version: v1_production  # bundle fiel à produção; novas redações = nova <version>/
```

#### A7 — §12.2 Proveniência por linha

Descrição de `prompt_version` atualizada: "grava o bundle de geração selecionado
(= `generation_prompt_version` do YAML)".

#### A8 — §13 Riscos aprofundados — nova linha

| Risco | Mitigação | Onde vive | Verificação |
|---|---|---|---|
| Prompt do eval diverge do de produção | Bundle `v1_production` verbatim (system+user); contexto `"[PMID:n]"`; strip `<think>`; `prompt_version` rastreia bundle | `infrastructure/prompts/rag/`, `vllm_generator.py` | Teste de fidelidade contra fixture (messages system+user verificadas) |

#### A9 — §14.6 Milestone M3 — novas linhas

Adicionadas TAREFA-313, 314 e 316 com critérios de aceitação.
Go/no-go atualizado mencionando "saneamento + prompt versionado fiel à produção (ADR-015)".

#### A10 — §14.9 Milestone M6 — novas linhas

Adicionadas TAREFA-315 (acurácia documental) e TAREFA-608 (este doc-sync).

#### A11 — §17.1 Checklist + rodapé

- Checklist: `ADR-001..011` → `ADR-001..015`
- Rodapé: `ADR-001..011 · TAREFA-001..605` → `ADR-001..015 · TAREFA-001..608`

---

### Visão (B1–B4)

#### B1 — Cabeçalho + Changelog v1.2

- Versão bumped: `1.1` → `1.2`; data `08/06/2026` → `15/06/2026`
- Changelog v1.2 adicionado ACIMA do v1.1 (1 linha sobre ADR-015, bundle versionado, `generation_prompt_version`)

#### B2 — §2.3 Princípios — versionamento

Linha de "Versionamento rigoroso" estendida com:
> `prompt_version` registra a versão do **bundle de geração selecionado** — bundle versionado
> `{system, user}` fiel ao prompt de produção, escolhido por `generation_prompt_version`;
> novas redações entram como novas versões (ADR-015)

#### B3 — §6.2/§6.3 Experimento B

- §6.2: parágrafo de objetivo estendido com nota de que Exp B é o cenário canônico para
  comparar redações de prompt (`generation_prompt_version`), mantendo retrieval fixo
- §6.3: célula "LLM bom em A e em B" complementada com nota sobre A/B de `generation_prompt_version`

#### B4 — §11.2 Schema — `prompt_version`

Linha atualizada: "versão do bundle de geração selecionado (= `generation_prompt_version` do YAML; ADR-015)"

---

## Validação (DoD)

- [x] `git diff --name-only` lista apenas `docs/arquitetura_...md` e `docs/visao_...md`
- [x] Nenhum arquivo de código/schema/config/testes modificado
- [x] Arquitetura bumped para v1.3; visão bumped para v1.2
- [x] ADR-015 posicionada APÓS ADR-014 no §6
- [x] §3.4 descreve system+user/PMID/strip SEM alterar assinatura do port (§5.1 intacto)
- [x] §5.3 `prompt_version` redefinida como bundle de geração
- [x] §8 subárvore `prompts/` reflete `rag/<version>/{system.txt,user.j2}` + rubrica
- [x] §12.1 YAML com `generation_prompt_version: v1_production`
- [x] §12.2 proveniência cita `generation_prompt_version`
- [x] §13 linha de risco "prompt diverge da produção" adicionada
- [x] §14.6 reconciliado (TAREFA-313/314/316); §14.9 reconciliado (TAREFA-315/608)
- [x] §17.1 `ADR-001..015`; rodapé `TAREFA-001..608`
- [x] TAREFA-317 NÃO documentada (não mergeada)
- [x] `retrieved_chunk_ids` NÃO alterado (continua IDs de ponto)
- [x] Markdown válido; seções não citadas preservadas

## Observações para Próximas Tarefas

- **TAREFA-317** (smoke/fix — `served_model_id` + comando `smoke`) tem rastro doc próprio
  (atualiza o manual) e um doc-sync futuro (v1.3 → v1.4) consolidará na arquitetura.
- Após execução real com `v1_production`, o refresh do quickstart pode ser necessário.
