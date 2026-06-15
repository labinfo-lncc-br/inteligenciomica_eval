# M6_TAREFA-608_B — Auditoria Codex do doc-sync pós-316

**Data**: 2026-06-15  
**Milestone**: M6  
**Épico**: E9  
**Papel**: code-reviewer (docs)  
**Escopo auditado**: commit `782ea1f` (`docs(M6-TAREFA-608): doc-sync pós-316 — arquitetura v1.3 + visão v1.2`)

---

## Veredito

**PASS**

Nenhum achado bloqueador ou importante. A arquitetura v1.3 e a visão v1.2 estão coerentes com o
as-built das TAREFAs 313–316, não documentam a TAREFA-317 e preservam corretamente que
`retrieved_chunk_ids` continua a representar IDs de ponto.

---

## Divergências

| Critério | Seção / arquivo:linha | Gravidade |
|---|---|---|
| Nenhuma divergência identificada | — | — |

---

## Verificação item a item

1. **Arquitetura v1.3 + changelog acima do v1.2**  
   PASS — `Versão: 1.3` em `docs/arquitetura_detalhada_validacao_inteligenciomica.md:3` e
   changelog v1.3 acima do v1.2 em `:10-12`.

2. **ADR-015 adicionada após ADR-014, com conteúdo correto**  
   PASS — ADR-014 termina em `docs/arquitetura_detalhada_validacao_inteligenciomica.md:584-596`
   e ADR-015 começa imediatamente em `:598`. Contexto, decisão, consequências, referências e
   ponte para `docs/adr/ADR-015-prompt-geracao-versionado.md` estão em `:600-607`, coerentes com
   `docs/adr/ADR-015-prompt-geracao-versionado.md:10-97`.

3. **§3.4 passo 3b descreve system+user / PMID / strip `<think>` sem alterar a assinatura do port**  
   PASS — o passo 3b está documentado em
   `docs/arquitetura_detalhada_validacao_inteligenciomica.md:205-210`. A assinatura do
   `GeneratorPort` segue intacta em `:307-315` (sem parâmetros `system` ou `user`).
   Isso bate com o adapter real em
   `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py:114-179`, que envia duas
   mensagens, usa o bundle versionado e faz strip de `<think>`.

4. **§5.3 redefine `prompt_version` como bundle de geração**  
   PASS — `docs/arquitetura_detalhada_validacao_inteligenciomica.md:412` descreve
   `prompt_version` como versão do bundle de geração selecionado via
   `generation_prompt_version`. Isso está alinhado a
   `src/inteligenciomica_eval/infrastructure/config/schema.py:165-171` e
   `src/inteligenciomica_eval/infrastructure/wiring.py:625-638`.

5. **§8 reflete `rag/<version>/{system.txt,user.j2}` + rubrica do juiz**  
   PASS — árvore atualizada em
   `docs/arquitetura_detalhada_validacao_inteligenciomica.md:746-753`, com `rag/<version>/`,
   `system.txt`, `user.j2` e `biomed_rubric*.j2`.

6. **§12.1 com `generation_prompt_version: v1_production`; §12.2 com proveniência do campo**  
   PASS — YAML em `docs/arquitetura_detalhada_validacao_inteligenciomica.md:934-938` e
   proveniência em `:940-942`. Coerente com o schema real:
   `src/inteligenciomica_eval/infrastructure/config/schema.py:171` e com o storage:
   `src/inteligenciomica_eval/infrastructure/wiring.py:637`.

7. **§13 inclui o risco "prompt do eval diverge da produção"**  
   PASS — nova linha em
   `docs/arquitetura_detalhada_validacao_inteligenciomica.md:993`, cobrindo mitigação,
   localização e verificação.

8. **§14.6 / §14.9 reconciliados; §17.1 e rodapé atualizados**  
   PASS — TAREFA-313/314/316 em
   `docs/arquitetura_detalhada_validacao_inteligenciomica.md:1121-1125`; TAREFA-315/608 em
   `:1181-1184`; checklist com `ADR-001..015` em `:1509`; rodapé com `TAREFA-001..608` em `:1551`.

9. **Visão v1.2 com B1–B4 (toque leve)**  
   PASS — versão/changelog em
   `docs/visao_alto_nivel_validacao_inteligenciomica.md:3-7`; princípio de versionamento em
   `:77-83`; Experimento B em `:236-253`; linha de schema em `:452-465`.

10. **Coerência com o as-built; 317 não documentada; `retrieved_chunk_ids` não alterado**  
    PASS — não há menção normativa à TAREFA-317 nos documentos auditados. A semântica de
    `retrieved_chunk_ids` segue intacta em
    `docs/arquitetura_detalhada_validacao_inteligenciomica.md:422` e
    `docs/visao_alto_nivel_validacao_inteligenciomica.md:470`. A nova narrativa de prompt e de
    `Chunk.source` é compatível com:
    `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py:145-158`,
    `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py:140-179`,
    `src/inteligenciomica_eval/infrastructure/config/schema.py:165-171` e
    `src/inteligenciomica_eval/infrastructure/wiring.py:625-638`.

11. **Diff só em `docs/`**  
    PASS — o `git diff --name-only` atual está vazio porque a Parte A já foi commitada.
    O relatório A registrou, durante a execução, apenas:

    ```text
    docs/arquitetura_detalhada_validacao_inteligenciomica.md
    docs/visao_alto_nivel_validacao_inteligenciomica.md
    ```

    No commit real auditado (`782ea1f`), o escopo continua `docs-only`:

    ```text
    docs/arquitetura_detalhada_validacao_inteligenciomica.md
    docs/dev-log/M6_TAREFA-608_A_doc-sync-prompt-geracao-versionado.md
    docs/visao_alto_nivel_validacao_inteligenciomica.md
    ```

---

## Evidências coladas

### `git diff --name-only` (estado atual)

```text
<sem diferenças não commitadas>
```

### `git show --name-only --format=fuller 782ea1f`

```text
commit 782ea1fa8e9ca561734aa7866c7b770b9d215594
Author:     lgp-almeida <lgp.almeida@gmail.com>
AuthorDate: Mon Jun 15 16:56:58 2026 -0300
Commit:     lgp-almeida <lgp.almeida@gmail.com>
CommitDate: Mon Jun 15 16:56:58 2026 -0300

    docs(M6-TAREFA-608): doc-sync pós-316 — arquitetura v1.3 + visão v1.2

docs/arquitetura_detalhada_validacao_inteligenciomica.md
docs/dev-log/M6_TAREFA-608_A_doc-sync-prompt-geracao-versionado.md
docs/visao_alto_nivel_validacao_inteligenciomica.md
```

### `git show --stat --format=medium 782ea1f`

```text
 ...itetura_detalhada_validacao_inteligenciomica.md |  50 +++++--
 ...EFA-608_A_doc-sync-prompt-geracao-versionado.md | 166 +++++++++++++++++++++
 .../visao_alto_nivel_validacao_inteligenciomica.md |  12 +-
 3 files changed, 213 insertions(+), 15 deletions(-)
```

---

## Conclusão

Arquitetura v1.3 e visão v1.2 estão coerentes com o as-built 313–316 e com a ADR-015. O commit
auditado permaneceu `docs-only`, não alterou contratos de código nem antecipou a documentação da
TAREFA-317. Recomendação: **approve / merge** do escopo de documentação da TAREFA-608.
