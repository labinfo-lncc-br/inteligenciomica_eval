# TAREFA-315 — Acurácia documental (Claude Code ↔ ChatGPT Codex)

**Origem:** `auditoria-completa-inteligenciomica-eval-2026-06-07.md` (veredito *PASS com ressalvas*)
+ revisão de cobertura do manual para uso **end-to-end no modo `external`** (lacunas operacionais
identificadas: smoke run, download de embeddings, baseline de retrieval).
**Contexto:** o gate 312 fechou PASS (commit `86d18e6`), mas a auditoria completa expôs deriva
residual entre runtime, config, ADRs e manual. Achados confirmados linha-a-linha contra o
as-built. Esta tarefa fecha a rodada de saneamento que precede o doc-sync (TAREFA-607).
**Decisão de arquitetura (do usuário):** contrato de benchmark = **honrar a decisão original** —
`RoundConfig.questions` é o caminho canônico (TAREFA-313); a documentação aqui é alinhada a esse
contrato já implementado.

> **Sequência obrigatória da rodada de saneamento:** 313 (código: contrato de benchmark) →
> 314 (código: observabilidade) → **315 (esta — docs/tooling: acurácia)** → 607 (doc-sync, já
> redigido). **Esta tarefa depende da 313 mergeada** (o contrato de benchmark precisa estar
> definido antes de documentá-lo). O M5 permanece adiado.

---

## Protocolo de desenvolvimento em pares (Claude Code ↔ ChatGPT Codex)

Esta tarefa tem **Parte A — execução (Claude Code)** e **Parte B — auditoria (ChatGPT Codex)**.
Processo iterativo A→B→A→B até **PASS por ambos**. Avanço só com **autorização explícita** do
usuário e após `add`/`commit`/`push`. `CLAUDE.md` mantido atualizado.

> **GRAVAÇÃO OBRIGATÓRIA DOS RELATÓRIOS.** Tanto o relatório de execução (Parte A) quanto o de
> auditoria (Parte B) **DEVEM ser GRAVADOS como arquivos versionados** em `docs/dev-log/`,
> **commitados no mesmo PR** — não basta exibir no chat. Convenção:
> - Parte A → `docs/dev-log/M6_TAREFA-315_A_<slug>.md`
> - Parte B → `docs/dev-log/M6_TAREFA-315_B_<slug>.md`
> - Ciclos subsequentes incrementam o sufixo (`_A2_`, `_B2_`, …).
> Cada relatório contém as saídas coladas dos gates/checagens que aquela parte rodou. Um ciclo sem
> o arquivo de relatório gravado é considerado **incompleto**.

---

**Épico:** E9 (docs) · **Skill:** system-architect, python-engineer · **Prioridade:** P1 ·
**Tamanho:** M · **Depende de:** TAREFA-313 (contrato de benchmark definido) · **Camada:** docs + scripts

**Diagnóstico (as-built confirmado):** ADR-014 (o arquivo) ainda descreve `determinism_verified`
default `True`, contradizendo o código (B2); o manual cita `config/questions.jsonl`,
`questions_resistencia.jsonl`, `questions_sepse.jsonl` inexistentes (I3) e afirma "13 perguntas
empacotadas" quando há 3 placeholders (I4); o `validate_manual.py` não detecta arquivos
referenciados inexistentes nem claims numéricas (I6).
**Lacunas de cobertura do manual (revisão end-to-end `external`)** — o manual **não documenta**:
(G1) **smoke run 1×1** antes da rodada completa; (G2) **download dos modelos de embedding**
(RAGAS `hf_embed_model` e BERTScore `bert-base-multilingual-cased`, `lang="pt"`) na 1ª execução,
exigindo internet/cache no micro; (G3) a **definição do baseline de retrieval**
(`embedding_model`/`chunk_strategy`, hoje `PENDENTE-rodada1`) como passo de operação.

### Prompt A — execução (Claude Code)

~~~text
CONTEXTO: Skills: system-architect, python-engineer. Tarefa DOCS+TOOLING: alinhar documentação
normativa/operacional ao as-built corrigido pela TAREFA-313/314 E fechar as lacunas de cobertura
do manual para uso end-to-end no modo external. NÃO altera código de produção (exceto
scripts/validate_manual.py). Pressupõe 313 mergeada (contrato de benchmark já definido).

TAREFA: TAREFA-315.

1. ADR-014 (B2) — `docs/adr/ADR-014-*.md`:
   Corrigir o default de determinism_verified para `False` ("nunca True sem prova"), coincidindo
   com entities.py/RowProvenance/from_row/_ExperimentConfig e com a arquitetura. Varrer a ADR por
   qualquer outra afirmação que contradiga o as-built (ex.: mecanismo de perguntas, se citado).

2. MANUAL (I3/I4) — `docs/operations_manual.md`, seção de benchmark/perguntas:
   Reescrever para o contrato da 313: RoundConfig.questions canônico (path relativo ao YAML),
   BENCHMARK_QUESTIONS_PATH como override, questions_rf1.jsonl empacotado como default.
   - Remover referências a config/questions.jsonl / questions_resistencia.jsonl / questions_sepse.jsonl
     (inexistentes). Onde exemplos forem arquivos do operador, marcá-los EXPLICITAMENTE como
     "arquivo a ser criado pelo operador" (não versionado), ou apontar para artefatos reais.
   - Corrigir "13 perguntas empacotadas" → "3 perguntas placeholder; as 13 reais a curar pelo
     especialista antes da Rodada 1 de produção (P4)".
   - Atualizar a nota de que `questions:` NÃO está wired — agora ESTÁ (corrigir o texto).

3. MANUAL — lacunas operacionais do uso end-to-end (`docs/operations_manual.md`):
   Adicionar conteúdo NOVO, sem reescrever as seções que já estão corretas. São três adições:

   (G1) SMOKE RUN 1×1 (modo external) — novo passo na Seção 5 (antes da "Execução completa") ou
   subseção da 4-B:
     - Rodar com 1 gerador e 1 pergunta antes da rodada cheia. Conferir, via auditoria de
       proveniência (Seção 4-B "Auditando a proveniência"): served_model_id presente; geração sem
       404 de modelo; juiz devolve score (sem NaN); métricas de embedding carregam sem erro.
     - Documentar o SINTOMA: se a geração retornar 404 de "modelo não encontrado", trata-se de
       divergência entre o nome do modelo esperado pelo endpoint e o resolvido pelo cliente —
       reportar antes de tocar a rodada cheia. (A correção é item separado de engenharia; o manual
       apenas orienta a detecção.)

   (G2) DOWNLOAD DOS EMBEDDINGS na 1ª execução — adicionar aos Pré-requisitos (Seção 1/2) e citar
   na Seção 5:
     - A 1ª execução baixa do HuggingFace: o modelo de embedding do RAGAS (config `hf_embed_model`
       do adapter de Camada 1, quando `vllm_embed_url` não está definido — origem `hf_local`) e o
       modelo do BERTScore (`bert-base-multilingual-cased`, `lang="pt"`).
     - No micro, garantir internet nessa 1ª execução OU pré-cachear (definir `HF_HOME` e pré-baixar)
       — especialmente relevante se o micro for air-gapped. Descrever a alternativa de apontar um
       endpoint de embedding (`vllm_embed_url`) para evitar o download local.

   (G3) BASELINE DE RETRIEVAL como passo — novo passo na Seção 5 (antes do dry-run):
     - Definir `embedding_model` e `chunk_strategy` no `config/experiment_round1.yaml` (hoje
       `PENDENTE-rodada1`); ambos entram em PROVENIÊNCIA (§5.3).
     - Esclarecer que, no eval, o retrieval usa o embedding SERVER-SIDE do Qdrant
       (Qdrant Inference); portanto `embedding_model` registrado deve ser COERENTE com o modelo de
       embedding configurado na coleção Qdrant usada. `chunk_strategy` descreve a estratégia de
       chunking da base já ingerida (a montante do eval).

4. VALIDADOR (I6) — `scripts/validate_manual.py`:
   Estender (sem quebrar o que já valida):
   - para blocos shell que referenciam arquivos locais versionados (ex.: `--config config/...`,
     paths sob config/ ou src/), verificar que o arquivo EXISTE no repo; ausência = FAIL,
     salvo se o trecho estiver explicitamente marcado como operador/PENDENTE;
   - asserir que claims numéricas sobre o conjunto empacotado batem com a contagem real de
     questions_rf1.jsonl (perguntas não-comentário);
   - manter o skip de seções [PENDENTE: ...] e a robustez de parsing já existentes;
   - GARANTIR que o conteúdo novo do item 3 passe limpo: os comandos do smoke run e o passo de
     baseline referenciam `config/experiment_round1.yaml` (existe); o passo de baseline, enquanto
     `PENDENTE-rodada1`, deve estar marcado como PENDENTE/operador para o validador não falhar; a
     nota de embeddings não referencia arquivos locais versionados (modelos são remotos).
   Rodar o validador e colar PASS.

ENTREGÁVEL:
- Edições 1–3 (docs) + 4 (script) + testes do script.
- RELATÓRIO GRAVADO em docs/dev-log/M6_TAREFA-315_A_<slug>.md com diffs das seções tocadas
  (incluindo as três adições do item 3), a saída de validate_manual.py (PASS) e `git diff --name-only`.

RESTRIÇÕES: não tocar código de produção (só docs + scripts/validate_manual.py); markdown válido;
o validador estendido deve passar contra o manual corrigido; as adições do item 3 são
operacionais — não inventar nomes de arquivo versionados que não existam (G2/G3 referenciam
config/modelos reais ou marcam como operador/PENDENTE).

CRITÉRIO: ADR-014 coincide com o código; manual sem arquivos inexistentes e sem o claim "13
empacotadas"; manual passa a documentar smoke run (G1), download de embeddings (G2) e definição do
baseline de retrieval (G3); validate_manual.py detecta arquivo referenciado inexistente e claim
numérica errada (teste que falharia contra o manual antigo) e passa limpo no conteúdo novo;
`git diff --name-only` só em docs/ e scripts/; relatório da Parte A gravado em docs/dev-log/.
~~~

### Prompt B — auditoria (ChatGPT Codex)

~~~text
PAPEL: code-reviewer (docs+tooling). Independente.
ENTRADA: diff da TAREFA-315 + relatório A (lido de docs/dev-log/) + ADR-014 + manual + saída de
validate_manual.py + contrato definido na 313.

VERIFIQUE:
1. ADR-014: default de determinism_verified = False, coincidindo com o código? Resto coerente?
2. Manual: descreve o contrato real de 313 (RoundConfig.questions canônico, env override,
   empacotado default)? Não cita mais arquivos inexistentes? Claim "13" corrigido para "3 placeholders"?
3. Manual — lacunas operacionais (item 3):
   (G1) Há passo de smoke run 1×1 (modo external) com os checks de served_model_id/404/NaN/embeddings
        e o sintoma do 404 de modelo documentado?
   (G2) Há nota de download dos embeddings na 1ª execução (RAGAS hf_embed_model + BERTScore
        bert-base-multilingual-cased/lang=pt), com a orientação de internet/cache (HF_HOME) ou
        endpoint de embedding?
   (G3) Há passo de definição do baseline de retrieval (embedding_model/chunk_strategy, proveniência)
        com a ressalva do embedding server-side do Qdrant?
4. validate_manual.py: agora FALHA se o manual citar arquivo local versionado inexistente? Verifica
   a contagem do conjunto empacotado? Há teste que falharia contra o manual antigo? Mantém skip de
   PENDENTE? Passa limpo no conteúdo novo do item 3 (sem falso-FAIL nos comandos do smoke run / passo
   de baseline / nota de embeddings)?
5. git diff só em docs/ e scripts/ (sem código de produção)? (cole `git diff --name-only`)
6. validate_manual.py PASS contra o manual corrigido (reproduza)?

SAÍDA: PASS/FAIL + tabela. FAIL se: ADR ainda contradiz o código; manual cita arquivo inexistente
ou claim numérica errada; qualquer das três lacunas (G1/G2/G3) ausente; validador não detecta os
casos exigidos ou dá falso-FAIL no conteúdo novo; código de produção tocado.
Conclua se a base documental está pronta para o doc-sync (TAREFA-607).

GRAVAÇÃO OBRIGATÓRIA: grave este relatório de auditoria em
docs/dev-log/M6_TAREFA-315_B_<slug>.md (versionado, commitado no PR) — não apenas no chat.
~~~

---

## Sequência

313 (contrato de benchmark) → 314 (observabilidade) → 315 (esta — PASS A/B) → 607 (doc-sync) →
316 (fidelidade do prompt de geração, feature work posterior).
Os achados S1 (prompts antigos como fonte de drift) e S2 (índice de validade no dev-log) são de
processo/governança — endereçados como nota no 607 (atualizar os prompts M3/M6 obsoletos: external
= ADR-014, não ADR-013; e marcar relatórios superseded), sem bloquear esta rodada.
