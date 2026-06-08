# ADR-015 — Prompt de Geração Versionado e Selecionável por Rodada

**Status**: Aprovado
**Data**: 2026-06-08
**Milestone**: M3 — TAREFA-316
**Autores**: lgp-almeida

---

## Contexto

O avaliador mede a qualidade de respostas geradas pelo mesmo sistema InteligenciÔmica que
a produção executa. Para que o A/B entre modelos e prompts seja fidedigno, o gerador do
eval deve enviar **exatamente o mesmo estímulo** que a produção envia ao LLM.

**Divergências constatadas (as-built, confirmadas contra o código):**

1. `VLLMGeneratorAdapter` enviava uma única mensagem `user` com formato livre
   (`"Contexts:\n- {text}...\nQuestion: {q}\nAnswer:"`), sem mensagem `system`.
2. A produção (`orchestrator_service.py`) envia **duas mensagens**: uma `system`
   (conteúdo de `system_prompt.txt`) e uma `user` (wrapper de
   `_build_prompt_with_context`).
3. O contexto da produção inclui o PMID de cada trecho — `"[PMID:{source}] {text}"` —
   unido por `"\n\n"`. O `QdrantRetrieverAdapter` descartava o campo `source` do payload.
4. A produção aplica `re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL)` à
   saída antes de exibir. O adapter não fazia o strip.

Essas divergências invalidam comparações directas entre o comportamento do eval e o da
produção, prejudicando especialmente o Experimento B (contextos fixos, 5 modelos).

## Decisão

**D1 — Prompt de geração é um bundle versionado `{system, user}` selecionável no YAML.**

O bundle é composto por dois artefatos:
- `system.txt` — mensagem system, texto puro (sem variáveis Jinja2).
- `user.j2` — mensagem user, template Jinja2 com variáveis `{{ context }}` e
  `{{ question }}`.

Bundles ficam em `src/inteligenciomica_eval/infrastructure/prompts/rag/<version>/`.
O bundle **padrão** (`v1_production`) replica verbatim o prompt de produção:
- `system.txt` = cópia exacta de `system_prompt.txt` da produção.
- `user.j2` = wrapper de `_build_prompt_with_context` com formato de contexto
  `"[PMID:{source}] {text}"` unido por `"\n\n"`.

**D2 — `generation_prompt_version` no YAML da rodada controla o bundle.**

O campo `RoundConfig.generation_prompt_version: str = "v1_production"` é validado no
carregamento contra as versões disponíveis. Novas redações de prompt entram como novas
versões no directório `rag/`, sem alterar código.

**D3 — `prompt_version` no schema §5.3 passa a gravar a versão do bundle de geração.**

Anteriormente, `prompt_version` gravava o `git describe` do `PromptRegistry`, que
correspondia ao template de rubrica do juiz (não ao prompt de geração). A partir desta
decisão, `prompt_version` grava `generation_prompt_version` — tornando o rastreio
coerente com o significado semântico do campo.

**D4 — `Chunk.source` (PMID) é populado pelo `QdrantRetrieverAdapter`.**

`Chunk.source: str = ""` adicionado como campo aditivo com default vazio. O adapter
preenche com `payload.get("source", "")`. A formataçao do contexto usa
`c.source or "N/A"`.

**D5 — Strip de `<think>` aplicado no adapter antes de montar `GenerationOutput`.**

`re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()` antes de
`GenerationOutput.text`. Alinha ao comportamento de produção.

## Consequências

### Positivas

- Fidelidade total ao estímulo de produção no Experimento B.
- Prompt é um factor de A/B controlável (diferentes bundles → diferentes `prompt_version`
  no Parquet → Wilcoxon/Friedman com grupo claramente identificável).
- `prompt_version` passa a ter semântica directa: qual versão do prompt de geração.
- Logs de observabilidade incluem `system_len`, `user_len`, `num_chunks` sem expor
  conteúdo sensível (ADR-008).

### Negativas / Riscos

- Bundles `.txt`/`.j2` são artefatos de dados empacotados no wheel; um erro tipográfico
  no `system.txt` afecta todos os runs que usem aquela versão. Mitigação: o campo
  `prompt_version` no Parquet rastreia exatamente qual bundle foi usado.
- Histórico de resultados anteriores (runs M0–M3) usava o prompt simples — não são
  comparáveis directamente com runs `v1_production`. Mitigação: `prompt_version` os
  distingue no Parquet.

## ADRs relacionados

- **ADR-003** (regimes de determinismo): `batch_invariant=False` para o gerador — não
  alterado por esta decisão.
- **ADR-005** (cliente OpenAI-compatible): `messages=[system, user]` é formato padrão da
  API OpenAI chat; vLLM suporta plenamente.
- **ADR-008** (config declarativa / sem segredos): bundles não contêm endpoints nem
  credenciais; conteúdo do prompt não é logado cru.
