# TAREFA-315 — Acurácia documental (Claude Code ↔ ChatGPT Codex)

**Origem:** `auditoria-completa-inteligenciomica-eval-2026-06-07.md` (veredito *PASS com ressalvas*)
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

### Prompt A — execução (Claude Code)

~~~text
CONTEXTO: Skills: system-architect, python-engineer. Tarefa DOCS+TOOLING: alinhar documentação
normativa/operacional ao as-built corrigido pela TAREFA-313/314. NÃO altera código de produção
(exceto scripts/validate_manual.py). Pressupõe 313 mergeada (contrato de benchmark já definido).

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

3. VALIDADOR (I6) — `scripts/validate_manual.py`:
   Estender (sem quebrar o que já valida):
   - para blocos shell que referenciam arquivos locais versionados (ex.: `--config config/...`,
     paths sob config/ ou src/), verificar que o arquivo EXISTE no repo; ausência = FAIL,
     salvo se o trecho estiver explicitamente marcado como operador/PENDENTE;
   - asserir que claims numéricas sobre o conjunto empacotado batem com a contagem real de
     questions_rf1.jsonl (perguntas não-comentário);
   - manter o skip de seções [PENDENTE: ...] e a robustez de parsing já existentes.
   Rodar o validador e colar PASS.

ENTREGÁVEL:
- Edições 1–2 (docs) + 3 (script) + testes do script.
- RELATÓRIO GRAVADO em docs/dev-log/M6_TAREFA-315_A_<slug>.md com diffs das seções tocadas, a
  saída de validate_manual.py (PASS) e `git diff --name-only`.

RESTRIÇÕES: não tocar código de produção (só docs + scripts/validate_manual.py); markdown válido;
o validador estendido deve passar contra o manual corrigido.

CRITÉRIO: ADR-014 coincide com o código; manual sem arquivos inexistentes e sem o claim "13
empacotadas"; validate_manual.py detecta arquivo referenciado inexistente e claim numérica errada
(teste que falharia contra o manual antigo); `git diff --name-only` só em docs/ e scripts/;
relatório da Parte A gravado em docs/dev-log/.
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
3. validate_manual.py: agora FALHA se o manual citar arquivo local versionado inexistente? Verifica
   a contagem do conjunto empacotado? Há teste que falharia contra o manual antigo? Mantém skip de PENDENTE?
4. git diff só em docs/ e scripts/ (sem código de produção)? (cole `git diff --name-only`)
5. validate_manual.py PASS contra o manual corrigido (reproduza)?

SAÍDA: PASS/FAIL + tabela. FAIL se: ADR ainda contradiz o código; manual cita arquivo inexistente
ou claim numérica errada; validador não detecta esses casos; código de produção tocado.
Conclua se a base documental está pronta para o doc-sync (TAREFA-607).

GRAVAÇÃO OBRIGATÓRIA: grave este relatório de auditoria em
docs/dev-log/M6_TAREFA-315_B_<slug>.md (versionado, commitado no PR) — não apenas no chat.
~~~

---

## Sequência

313 (contrato de benchmark) → 314 (observabilidade) → 315 (esta — PASS A/B) → 607 (doc-sync).
Os achados S1 (prompts antigos como fonte de drift) e S2 (índice de validade no dev-log) são de
processo/governança — endereçados como nota no 607 (atualizar os prompts M3/M6 obsoletos: external
= ADR-014, não ADR-013; e marcar relatórios superseded), sem bloquear esta rodada.
