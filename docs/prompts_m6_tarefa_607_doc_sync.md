# Prompt M6 — TAREFA-607 (Claude Code ↔ ChatGPT Codex)

**Milestone:** M6 (épico de documentação E9) — sincronização de documentos com o *as-built*
**Tarefa:** TAREFA-607 — Doc-sync: **arquitetura v1.1 → v1.2** e **visão v1.0 → v1.1**,
refletindo TAREFA-309/310/311/606 e o gate 312 (commit `86d18e6`)
**Documentos de referência (estado real / as-built):**
- `docs/arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1 — §§4.3/5.3 já trazem as
  3 colunas de proveniência; faltam versão, ADRs, topologia, §12, milestones)
- `docs/visao_alto_nivel_validacao_inteligenciomica.md` (v1.0)
- `docs/operations_manual.md` (TAREFA-606 — Seção 4-B modo `external`, ADR-014)
- `docs/adr/ADR-013-round2-funnel.md` (M5/Rodada 2) e `docs/adr/ADR-014-*.md` (modo external + proveniência)
- Relatórios `M3_TAREFA-312_A/A2/B/B2` (gate íntegro, PASS)
**Formato:** **Prompt A (edição dos documentos — Claude Code)** + **Prompt B (auditoria — ChatGPT Codex)**.
**Natureza:** **DOCS-ONLY.** NÃO altera código, schema, testes nem config — apenas
sincroniza a documentação com o que já foi implementado e auditado.

> **Pressupõe** que o gate **TAREFA-312** fechou em PASS (commit `86d18e6`) e que 309/310/311
> e o manual 606 estão mergeados. Este doc-sync é o passo final que discutimos: subir as
> versões e consolidar a narrativa que ficou de fora das edições inline do 312.
> **Correções do as-built a respeitar (NÃO inverter):**
> - O modo `external` + proveniência verificada é o **ADR-014** (NÃO ADR-013).
> - O **ADR-013** é o **funil da Rodada 2 (M5, adiado)** — já existe como arquivo.
> - A CLI real tem **8 subcomandos**: `version`, `run`, `annotate`, `analyze`, `report`,
>   `status`, `show-config`, `validate-judge`. **NÃO** existem `compute-metrics` (use case
>   interno) nem `run-round2` (pertence ao M5 futuro).
> - O schema §5.3 tem **46 colunas** (as 3 de proveniência já documentadas).
> - `determinism_verified` defaulta a **`False`** ("nunca `True` sem prova" — ADR-014).
> **O M5 permanece adiado.** DoD §14.2 (na parte aplicável a docs) vale.

---

## Protocolo de desenvolvimento em pares (Claude Code ↔ ChatGPT Codex)

Cada prompt é dividido em **Parte A — execução (Claude Code)** e **Parte B — auditoria
(ChatGPT Codex)**. Toda execução gera relatório em `docs/dev-log/`. Processo iterativo
A→B→A→B até **PASS por ambos**. Avanço só com **minha autorização explícita** e após
`add`/`commit`/`push`. `CLAUDE.md` mantido atualizado.

> **Início:** execute a **Parte A** (edição dos dois documentos) e produza o relatório. A
> **Parte B** audita coerência doc↔código e ausência de regressão. Itere A↔B até PASS.

---

## Nota de operacionalização — escopo do doc-sync

Edição **cirúrgica** e **docs-only**. O 312 já atualizou §4.3 e §5.3 da arquitetura (3
colunas de proveniência). Este sync faz o **entorno** que ficou pendente + a visão.

**Arquitetura (v1.1 → v1.2):**
1. Cabeçalho/versão + bloco **Changelog v1.2**.
2. Seção de ADRs: adicionar **ADR-013** (stub/índice — funil Rodada 2, M5) e **ADR-014**
   (managed vs external; proveniência verificada por sonda) — hoje a seção para em ADR-012.
3. Topologia (§7.2): nova subseção do modo **`external`** (cliente x86 ↔ túnel SSH ↔ GH200
   vLLM + Qdrant), contrastando com o managed; `managed` permanece o default.
4. §12 (reprodutibilidade/proveniência): subseção sobre a **migração de responsabilidade**
   no modo external — o determinismo do juiz deixa de ser *garantido pelo lançamento* e
   passa a ser *verificado por sonda e gravado* (`server_mode`, `served_model_id`,
   `determinism_verified` + `endpoints_provenance` no run report).
5. RNF1: nuance — determinismo bit-a-bit é **garantido** em `managed`; em `external` é
   **responsabilidade do operador, verificada (não garantida)** pelo probe (ADR-014).
6. §14.6 (milestone M3): reconciliar a tabela com o as-built — acrescentar TAREFA-308
   (anotação), **309/310/311/312** e o gate de integração; §14.9 (M6) referencia **606**.
7. §15 (manual): alinhar a lista de subcomandos à CLI real (8); citar `run --run-id`
   (obrigatório), `--phase`, `--serial`, `--require-verified-determinism`; cross-ref ao
   `operations_manual.md` (Seção 4-B, modo external). NÃO listar `compute-metrics`/`run-round2`.

**Visão (v1.0 → v1.1) — toque leve:**
8. Versão + Changelog v1.1.
9. Um parágrafo (em §9 ou §10) reconhecendo as **duas topologias de implantação**
   (managed co-localizado no GH200 vs external/tunelado para serviços compartilhados) e que,
   no external, a garantia de reprodutibilidade é **compartilhada com o operador e verificada
   por sonda** (cross-ref ADR-014).
10. §9.4 ("Registro do regime de determinismo"): nota de que o dataset agora registra também
    `server_mode`, `served_model_id`, `determinism_verified` (verificado, não só declarado).

---

## TAREFA-607 — Doc-sync (arquitetura v1.2 + visão v1.1)

**Épico:** E9 · **Skill:** system-architect, python-engineer · **Prioridade:** P1 ·
**Tamanho:** M · **Dependências:** TAREFA-309/310/311/606 mergeadas; **312 PASS** ·
**ADRs:** ADR-013, ADR-014 (índice) · **Camadas:** docs (sem código)

### Prompt A — Edição dos documentos (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica. Skill: system-architect, python-engineer.
TAREFA-309/310/311/606 mergeadas; gate 312 PASS (commit 86d18e6). Esta tarefa é DOCS-ONLY:
sincroniza a arquitetura (v1.1→v1.2) e a visão (v1.0→v1.1) com o as-built. NÃO altera código,
schema, testes ou config. VER "Nota de operacionalização — doc-sync", itens 1–10, e respeitar
as CORREÇÕES DO AS-BUILT do cabeçalho (ADR-014 é o external; ADR-013 é o funil M5; 8 subcomandos;
46 colunas; determinism_verified default False).

LEIA ANTES DE EDITAR: o estado atual de docs/arquitetura_*.md (confirmar que §4.3 e §5.3 JÁ
têm server_mode/served_model_id/determinism_verified — NÃO duplicar), docs/visao_*.md,
docs/operations_manual.md (Seção 4-B), docs/adr/ADR-013-round2-funnel.md e o ADR-014; e a
saída de `ielm-eval --help` (8 subcomandos) para alinhar §15.

TAREFA: aplicar as edições abaixo, preservando todo o resto dos documentos.

A. ARQUITETURA v1.1 → v1.2:
   1. Cabeçalho: Versão 1.1 → 1.2. Acrescentar bloco "Changelog v1.2 (2026-06-07)" resumindo:
      mecanismo de perguntas via config/questions.yaml + RoundConfig.questions (multi-área,
      TAREFA-309); CLI `run` completo com --run-id obrigatório, --phase, --serial; modo de
      implantação `external` + proveniência verificada por sonda (ADR-014, TAREFA-311), com
      3 colunas novas (server_mode, served_model_id, determinism_verified — já em §§4.3/5.3,
      schema 43→46); gate de integração TAREFA-312 (PASS). Observar: §§4.3/5.3 já atualizadas
      no 312; demais ADRs/seções inalterados exceto os itens 2–7.
   2. Seção de ADRs (onde hoje vai até ADR-012): adicionar
      - ADR-013 (stub/índice): "Funil de retrieval da Rodada 2" — Status Aceito; pertence ao
        M5 (adiado); apontar para docs/adr/ADR-013-round2-funnel.md.
      - ADR-014: "Modo de servidor managed vs external; proveniência verificada por sonda
        (não declarada)". Decisão, contexto (cluster compartilhado/air-gapped, GH200 ARM),
        consequências (responsabilidade de determinismo/identidade migra para o operador no
        external; probes de served_model/version/determinismo; determinism_verified=False sem
        prova). Referenciar ADR-003/004/008/012 e o operations_manual Seção 4-B.
   3. Topologia (§7.2): nova subseção "Modo external (servidores via túnel SSH)" com diagrama
      textual cliente x86 ↔ túnel SSH ↔ nodes GH200 (vLLM) + Qdrant; deixar claro que start/
      stop são no-op no external (não derruba serviço compartilhado) e que `managed` é default.
   4. §12: nova subseção "Reprodutibilidade no modo external (ADR-014)" — no external o
      determinismo do juiz não é garantido pelo lançamento; o ielm-eval VERIFICA por sonda e
      GRAVA (server_mode, served_model_id, determinism_verified por linha + endpoints_provenance
      no run report); --require-verified-determinism para runs de publicação.
   5. RNF1: acrescentar a nuance managed (garantido) vs external (verificado, não garantido —
      responsabilidade do operador), com cross-ref a ADR-014.
   6. §14.6 (milestone M3): reconciliar a tabela com o as-built — acrescentar linhas TAREFA-308
      (workflow de anotação), 309 (wiring+CLI run+BenchmarkLoader), 310 (gate E2E), 311
      (external+proveniência), 312 (gate de integração). §14.9 (M6): citar TAREFA-606 (manual)
      e este doc-sync (607). Não renumerar tarefas existentes.
   7. §15 (manual): alinhar a lista de subcomandos à CLI real (version, run, annotate, analyze,
      report, status, show-config, validate-judge); `run` usa --run-id (obrigatório), --phase,
      --serial, --require-verified-determinism; cross-ref a operations_manual.md (Seção 4-B).
      NÃO listar compute-metrics nem run-round2 (registrar que run-round2 chega com o M5).

B. VISÃO v1.0 → v1.1:
   8. Cabeçalho: Versão 1.0 → 1.1 + bloco "Changelog v1.1 (2026-06-07)": acréscimo das duas
      topologias de implantação e da proveniência verificada (ADR-014); demais seções inalteradas.
   9. Em §9 (ou §10): parágrafo curto sobre managed (co-localizado no GH200) vs external
      (tunelado para serviços compartilhados) e a reprodutibilidade compartilhada/verificada
      no external (cross-ref ADR-014). Manter o tom de alto nível — sem detalhes de implementação.
   10. §9.4: nota de que o dataset agora registra server_mode, served_model_id e
       determinism_verified (verificado por sonda, não só declarado).

ENTREGÁVEL:
- docs/arquitetura_detalhada_validacao_inteligenciomica.md (v1.2 — edições A.1–A.7)
- docs/visao_alto_nivel_validacao_inteligenciomica.md (v1.1 — edições B.8–B.10)
- docs/dev-log/M6_TAREFA-607_A_<slug>.md (relatório com o diff de seções e a confirmação de
  que nenhuma alteração tocou código/schema/testes/config)

RESTRIÇÕES:
- DOCS-ONLY: `git diff --name-only` deve listar SOMENTE arquivos sob docs/.
- NÃO duplicar §4.3/§5.3 (já atualizadas no 312); NÃO alterar a tabela de colunas (46).
- Respeitar o as-built: ADR-014=external; ADR-013=funil M5; 8 subcomandos; determinism_verified=False.
- Markdown válido; índice/âncoras internas consistentes; cross-refs corretas.

CRITÉRIO DE ACEITAÇÃO:
- Arquitetura em v1.2 com Changelog; ADR-013 (stub) e ADR-014 presentes na seção de ADRs.
- §7.2 com a subseção external; §12 com a subseção de reprodutibilidade external; RNF1 com a nuance.
- §14.6 reconciliada (308–312); §14.9 cita 606/607; §15 com 8 subcomandos e run --run-id.
- Visão em v1.1 com o parágrafo de topologias e a nota em §9.4.
- `git diff --name-only` só sob docs/ (cole a saída).
~~~

### Prompt B — Auditoria (ChatGPT Codex)

~~~text
PAPEL: code-reviewer (documentação). NÃO reescreva; AUDITE coerência doc↔código e regressão.

ENTRADA: diff do PR da TAREFA-607 + arquitetura v1.1 anterior + visão v1.0 + operations_manual
(606) + ADR-013/ADR-014 + relatório (Parte A) + saída de `ielm-eval --help`.

VERIFIQUE, citando seção/arquivo:

1. DOCS-ONLY: `git diff --name-only` lista SOMENTE docs/? Nenhum .py/.yaml/teste tocado?
2. Versões: arquitetura 1.1→1.2 com Changelog; visão 1.0→1.1 com Changelog?
3. ADRs: ADR-014 é o modo external + proveniência? ADR-013 é o funil da Rodada 2 (M5)? Os
   dois NÃO estão trocados? Apontam para os arquivos corretos em docs/adr/?
4. Não-duplicação: §4.3/§5.3 NÃO foram duplicadas/alteradas (continuam com as 3 colunas, 46 total)?
5. Topologia §7.2: subseção external presente (start/stop no-op; managed default)?
6. §12: subseção de reprodutibilidade external (verificação por sonda; determinism_verified=False
   sem prova; --require-verified-determinism)? RNF1 com a nuance managed/external?
7. §14.6: tabela reconciliada com 308/309/310/311/312? §14.9 cita 606/607? Sem renumeração indevida?
8. §15: lista exatamente os 8 subcomandos reais? `run --run-id` obrigatório citado? NÃO
   inventa compute-metrics/run-round2 como existentes (run-round2 marcado como M5 futuro)?
9. Coerência doc↔código (re-rodar a checagem do 312-H): a lista de colunas de §5.3 continua ==
   schema real do ParquetStorage (46)? `ielm-eval --help` == lista de §15?
10. Visão: parágrafo de duas topologias + reprodutibilidade verificada (cross-ref ADR-014);
    nota em §9.4 sobre server_mode/served_model_id/determinism_verified? Tom mantido alto nível?
11. Markdown/âncoras válidos; nenhuma cross-ref quebrada?

SAÍDA: PASS/FAIL + tabela de divergências (seção/arquivo | critério | gravidade:
BLOQUEADOR | IMPORTANTE | COSMÉTICO).
FAIL se: tocou código; ADR-013/014 trocados; §5.3 divergente do schema real; §15 lista
subcomando inexistente; versões não bumpadas. Cole `git diff --name-only` e `ielm-eval --help`.
Conclua se a documentação (arq v1.2 / visão v1.1) está coerente com o as-built de 309–312+606.
~~~
