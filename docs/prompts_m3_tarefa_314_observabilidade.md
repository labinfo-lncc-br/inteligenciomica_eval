# TAREFA-314 — Observabilidade segura (Claude Code ↔ ChatGPT Codex)

**Origem:** `auditoria-completa-inteligenciomica-eval-2026-06-07.md` (veredito *PASS com ressalvas*)
**Contexto:** o gate 312 fechou PASS (commit `86d18e6`), mas a auditoria completa expôs deriva
residual entre runtime, config, ADRs e manual. Achados confirmados linha-a-linha contra o
as-built. Esta tarefa integra a rodada de saneamento que precede o doc-sync (TAREFA-607).
**Decisão de arquitetura (do usuário):** contrato de benchmark = **honrar a decisão original** —
`RoundConfig.questions` é o caminho canônico (TAREFA-313); aqui o foco é observabilidade segura.

> **Sequência obrigatória da rodada de saneamento:** 313 (código: contrato de benchmark) →
> **314 (esta — código: observabilidade)** → 315 (docs/tooling: acurácia) → 607 (doc-sync, já
> redigido). Pode rodar após a 313. O M5 permanece adiado. DoD §14.2 vale.

---

## Protocolo de desenvolvimento em pares (Claude Code ↔ ChatGPT Codex)

Esta tarefa tem **Parte A — execução (Claude Code)** e **Parte B — auditoria (ChatGPT Codex)**.
Processo iterativo A→B→A→B até **PASS por ambos**. Avanço só com **autorização explícita** do
usuário e após `add`/`commit`/`push`. `CLAUDE.md` mantido atualizado.

> **GRAVAÇÃO OBRIGATÓRIA DOS RELATÓRIOS.** Tanto o relatório de execução (Parte A) quanto o de
> auditoria (Parte B) **DEVEM ser GRAVADOS como arquivos versionados** em `docs/dev-log/`,
> **commitados no mesmo PR** — não basta exibir no chat. Convenção:
> - Parte A → `docs/dev-log/M3_TAREFA-314_A_<slug>.md`
> - Parte B → `docs/dev-log/M3_TAREFA-314_B_<slug>.md`
> - Ciclos subsequentes incrementam o sufixo (`_A2_`, `_B2_`, …).
> Cada relatório contém as saídas coladas dos gates/testes que aquela parte rodou. Um ciclo sem o
> arquivo de relatório gravado é considerado **incompleto**.

---

**Épico:** E9 (hardening) · **Skill:** backend-engineer, security-auditor, test-engineer ·
**Prioridade:** P0 (B1) / P2 (S3) · **Tamanho:** S · **ADRs:** ADR-008 · **Camada:** infrastructure + tests

**Diagnóstico (as-built confirmado):** `infrastructure/provenance/endpoint_probe.py` loga a URL
crua (`url=models_url`/`version_url`/`completions_url`) em todos os eventos — mascaramento parcial,
enquanto `external_vllm_server_manager.py` e `wiring.py` já mascaram (e duplicam o helper). O
`prometheus_judge.py` loga `raw_content=content[:500]` / `str(exc)[:500]` em falha de parsing.

### Prompt A — execução (Claude Code)

~~~text
CONTEXTO: Skills: backend-engineer, security-auditor, test-engineer. Política do projeto:
nenhum endpoint/credencial cru em log; nenhum payload textual completo. Hoje há mascaramento
PARCIAL — pior que política explícita. Unificar e fechar.

TAREFA: TAREFA-314.

1. HELPER ÚNICO DE MASKING (B1):
   Há HOJE duas implementações de _mask_url (external_vllm_server_manager.py e wiring.py) e ainda
   mask_endpoint em settings.py. Consolidar em UM helper compartilhado (escolher um local de infra,
   ex.: infrastructure/provenance ou settings) que (a) remova credenciais `user:pass@` e (b) reduza
   a `scheme://host:port` sem path. Reapontar os dois adapters e o wiring para o helper único
   (remover as duplicatas). Sem mudança de comportamento observável nos pontos já mascarados.

2. PROBES (B1) — `infrastructure/provenance/endpoint_probe.py`:
   Em probe_served_model / probe_vllm_version / probe_judge_determinism, mascarar a URL em TODOS
   os eventos de log (probe_*_ok / *_empty / *_unavailable / *_failed). Nenhum `url=<crua>`.

3. PAYLOAD DO JUIZ (S3) — `infrastructure/adapters/prometheus_judge.py`:
   Reduzir a exposição de raw_content: em vez de [:500], logar `raw_len`, um snippet curto
   (ex.: [:120]) e, opcionalmente, um prefixo de hash sha256 do conteúdo — suficiente para triagem,
   sem despejar o payload. Aplicar em `prometheus_judge_parse_failure` e em `prometheus_judge_nan`.
   (Conteúdo é saída do juiz, não segredo — é defesa em profundidade/consistência, P2.)

4. TESTES:
   - capturar os logs structlog dos 3 probes e asseverar que NENHUM evento contém a URL crua nem
     credenciais (teste que falharia antes — B1);
   - teste do juiz asseverando que o evento de falha NÃO contém o raw_content completo (S3);
   - se possível, um teste do helper único de masking cobrindo user:pass@ e path-stripping.

ENTREGÁVEL:
- Código 1–3 + testes 4.
- RELATÓRIO GRAVADO em docs/dev-log/M3_TAREFA-314_A_<slug>.md com diffs e as saídas coladas dos
  gates (ruff/ruff format/mypy/lint-imports/pytest ≥85%).

RESTRIÇÕES (DoD §14.2): teste que falharia antes; mypy/ruff/lint-imports/pytest ≥85% verdes;
sem regressão nos pontos já mascarados.

CRITÉRIO: zero URL/credencial crua em qualquer log de infra (probes inclusive); um único helper de
masking; payload do juiz reduzido; testes provando ambos; relatório da Parte A gravado em docs/dev-log/.
~~~

### Prompt B — auditoria (ChatGPT Codex)

~~~text
PAPEL: security-auditor + test-engineer. Independente.
ENTRADA: diff da TAREFA-314 + relatório A (lido de docs/dev-log/) + security_review.md.

VERIFIQUE:
1. grep nos 3 probes: algum log ainda passa url crua? Há teste de log/masking para probes
   (não só para adapters)?
2. Existe UM helper de masking compartilhado (duplicatas removidas)? Comportamento preservado nos
   pontos antigos?
3. prometheus_judge: raw_content reduzido (sem [:500] de payload)? Teste cobre?
4. security_review.md descreve o estado real agora (mascaramento total, não parcial)?
5. Gates verdes (reproduza ruff/mypy/lint-imports/pytest ≥85%)?

SAÍDA: PASS/FAIL + tabela. FAIL se: qualquer url/credencial crua em log de infra; sem teste de
masking de probe; helper ainda duplicado; payload completo ainda logado.

GRAVAÇÃO OBRIGATÓRIA: grave este relatório de auditoria em
docs/dev-log/M3_TAREFA-314_B_<slug>.md (versionado, commitado no PR) — não apenas no chat.
~~~

---

## Sequência

313 (contrato de benchmark) → 314 (esta — PASS A/B) → 315 (acurácia documental) → 607 (doc-sync).
