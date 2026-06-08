# TAREFA-313 — Contrato de benchmark (Claude Code ↔ ChatGPT Codex)

**Origem:** `auditoria-completa-inteligenciomica-eval-2026-06-07.md` (veredito *PASS com ressalvas*)
**Contexto:** o gate 312 fechou PASS (commit `86d18e6`), mas a auditoria completa expôs deriva
residual entre runtime, config, ADRs e manual. Achados confirmados linha-a-linha contra o
as-built. Esta tarefa abre a rodada de saneamento que precede o doc-sync (TAREFA-607).
**Decisão de arquitetura (do usuário):** contrato de benchmark = **honrar a decisão original** —
`RoundConfig.questions` é o caminho canônico (resolvido relativo ao YAML, como
`model_registry_path`); `BENCHMARK_QUESTIONS_PATH` vira **override** opcional; `questions_rf1.jsonl`
empacotado permanece **default**. Re-alinha M5/RF4.

> **Sequência obrigatória da rodada de saneamento:** **313 (esta — código: contrato de benchmark)**
> → 314 (código: observabilidade) → 315 (docs/tooling: acurácia) → 607 (doc-sync, já redigido). O
> 315 e o 607 dependem do contrato definido AQUI. O M5 permanece adiado. DoD §14.2 vale.

---

## Protocolo de desenvolvimento em pares (Claude Code ↔ ChatGPT Codex)

Esta tarefa tem **Parte A — execução (Claude Code)** e **Parte B — auditoria (ChatGPT Codex)**.
Processo iterativo A→B→A→B até **PASS por ambos**. Avanço só com **autorização explícita** do
usuário e após `add`/`commit`/`push`. `CLAUDE.md` mantido atualizado.

> **GRAVAÇÃO OBRIGATÓRIA DOS RELATÓRIOS.** Tanto o relatório de execução (Parte A) quanto o de
> auditoria (Parte B) **DEVEM ser GRAVADOS como arquivos versionados** em `docs/dev-log/`,
> **commitados no mesmo PR** — não basta exibir no chat. Convenção:
> - Parte A → `docs/dev-log/M3_TAREFA-313_A_<slug>.md`
> - Parte B → `docs/dev-log/M3_TAREFA-313_B_<slug>.md`
> - Ciclos subsequentes incrementam o sufixo (`_A2_`, `_B2_`, …).
> Cada relatório contém as saídas coladas dos gates/testes que aquela parte rodou. Um ciclo sem o
> arquivo de relatório gravado é considerado **incompleto**.

---

**Épico:** E3 · **Skill:** backend-engineer, test-engineer · **Prioridade:** P0 · **Tamanho:** M ·
**ADRs:** ADR-008, ADR-014 · **Camada:** infrastructure (config/wiring) + tests

**Diagnóstico (as-built confirmado):** o runtime carrega perguntas só via
`settings.BENCHMARK_QUESTIONS_PATH` (env) + `questions_rf1.jsonl` empacotado; `RoundConfig.questions`
existe no schema mas **não é lido por ninguém** (campo morto, I2); o path da env é resolvido
contra o `cwd`, ao contrário de `model_registry_path`, que é resolvido contra o YAML (I1); o
`model_registry.yaml` canônico não tem `endpoint_env`, então `external` exige edição manual (I5);
e o gate 312 checou "config/questions.yaml parseia" no vazio (o arquivo nunca existiu).

### Prompt A — execução (Claude Code)

~~~text
CONTEXTO: Subsistema InteligenciÔmica Eval. Skills: backend-engineer, test-engineer.
DECISÃO DE ARQUITETURA: RoundConfig.questions é o caminho CANÔNICO do conjunto de perguntas,
resolvido relativo ao YAML de rodada (mesma semântica de model_registry_path). A env var
BENCHMARK_QUESTIONS_PATH passa a ser OVERRIDE opcional. O questions_rf1.jsonl empacotado é o
DEFAULT. Objetivo: ligar o campo morto, unificar a resolução de path e tornar o registry
dual-mode — corrigindo os achados I1, I2 e I5 da auditoria, com regressão que teria pego a deriva.

TAREFA: TAREFA-313.

1. WIRING DO CAMPO (I2) + RESOLUÇÃO DE PATH (I1) — `infrastructure/wiring.py::build_container`:
   Definir a precedência explícita de origem das perguntas:
     (a) BENCHMARK_QUESTIONS_PATH (env), se definida → OVERRIDE (precedência máxima);
     (b) senão, config.questions, se definido → resolvido como `config_dir / config.questions`
         (relativo ao YAML, idêntico a model_registry_path);
     (c) senão → default empacotado (`load_questions(None)`).
   Passar o Path resolvido a `load_questions`. Logar a origem escolhida em
   `wiring_questions_source` (source ∈ {"env_override","round_config","packaged_default"}),
   com o path MASCARADO se aplicável (não vazar layout sensível; reutilizar helper de masking).
   Aplicar a MESMA precedência e resolução relativa ao YAML em `cli.py::_run_dry_run`
   (hoje usa só a env var) — o dry-run deve refletir a fonte real do run.

2. SCHEMA (`infrastructure/config/schema.py::RoundConfig`):
   Manter `questions: str | None = None`, mas atualizar o docstring/comentário: agora é o
   caminho CANÔNICO (relativo ao YAML) para o arquivo de perguntas; default None → empacotado;
   BENCHMARK_QUESTIONS_PATH faz override. Não é mais "campo fantasma".

3. REGISTRY DUAL-MODE (I5) — `config/model_registry.yaml`:
   Adicionar `endpoint_env: <NOME_ENV>` a TODAS as 6 entradas (5 geradores + juiz), com nomes
   coerentes com a Seção 4-B do manual (ex.: VLLM_<MODELO>_EXTERNAL_URL para geradores e
   VLLM_JUDGE_EXTERNAL_URL para o juiz). O campo é opcional e ignorado em managed
   (ModelEntry.endpoint_env: str | None) — managed continua funcionando sem env vars novas;
   external deixa de exigir edição manual do registry. NÃO alterar nada de VRAM/quantization/gpu.

4. CONFIG DE RODADA (`config/experiment_round1.yaml`):
   Deixar `questions` AUSENTE (usa o default empacotado) e adicionar um comentário explicando a
   precedência (override env > questions no YAML > empacotado). NÃO referenciar arquivos
   inexistentes. (A correção do manual é da TAREFA-315.)

5. GATE 312 CORRIGIDO + REGRESSÃO (a parte mais importante):
   Substituir a checagem vazia de "config/questions.yaml parseia" por um teste que PROVA o wiring:
   - teste de integração: criar um JSONL temporário com N perguntas conhecidas, apontar
     `RoundConfig.questions` para ele (path relativo ao diretório do YAML temporário) e asseverar
     que `build_container(...).benchmark_loader()` devolve exatamente essas N perguntas
     (prova (b) — o campo está ligado E o path resolve relativo ao YAML);
   - teste: com BENCHMARK_QUESTIONS_PATH setada, asseverar que ela VENCE config.questions (prova (a));
   - teste: sem nenhum dos dois, asseverar o default empacotado (3 perguntas) (prova (c));
   - teste: cli `--dry-run` imprime "Perguntas carregadas: N" coerente com a fonte escolhida.
   Esses testes falhariam ANTES desta tarefa (o campo era morto) — é o critério DoD §14.2.

ENTREGÁVEL:
- Código de 1–4 + testes de 5.
- RELATÓRIO GRAVADO em docs/dev-log/M3_TAREFA-313_A_<slug>.md com a precedência documentada e as
  saídas coladas de ruff/ruff format/mypy/lint-imports/pytest e dos dry-runs (managed e external).

RESTRIÇÕES (DoD §14.2):
- Não quebrar managed (env vars de endpoint não viram obrigatórias por causa do registry dual-mode).
- Toda correção com teste que falharia antes. `from __future__ import annotations`; mypy --strict;
  ruff; lint-imports verdes. Sem import de fakes em produção; sem endpoint/segredo cru em log.
- NÃO remover RoundConfig.questions (a decisão é LIGÁ-LO, não removê-lo) — re-alinha M5/RF4.

CRITÉRIO DE ACEITAÇÃO:
- RoundConfig.questions efetivamente carrega o conjunto quando definido (regressão verde).
- Resolução relativa ao YAML para config.questions; override via env documentado e testado.
- model_registry.yaml com endpoint_env em todas as entradas; managed e external dry-run verdes.
- Suíte completa verde ≥85%; gate de perguntas prova as 3 origens.
- Relatório da Parte A gravado em docs/dev-log/.
~~~

### Prompt B — auditoria (ChatGPT Codex)

~~~text
PAPEL: code-reviewer + test-engineer. Auditoria independente — reproduza onde possível.
ENTRADA: diff da TAREFA-313 + relatório A (lido de docs/dev-log/) + arquitetura §§5.3/12 + ADR-014.

VERIFIQUE:
1. `RoundConfig.questions` é REALMENTE lido pelo wiring? Existe teste que, apontando o campo a um
   arquivo conhecido, prova que o benchmark_loader devolve aquelas perguntas? (campo morto eliminado)
2. Resolução de path: config.questions resolve relativo ao YAML (igual a model_registry_path)?
   Há teste cobrindo? A env BENCHMARK_QUESTIONS_PATH vence (override) com teste? Default empacotado com teste?
3. cli `_run_dry_run` usa a MESMA precedência/resolução (não só a env)?
4. model_registry.yaml: todas as entradas têm endpoint_env? Managed ainda roda sem env vars novas?
   External dry-run não exige mais edição manual do registry?
5. Nenhum path/endpoint cru em log (origem das perguntas mascarada quando aplicável)?
6. Gates: ruff, ruff format, mypy --strict, lint-imports, pytest ≥85%. Verdes (reproduza)?
7. O campo NÃO foi removido (a decisão era ligá-lo)?

SAÍDA: PASS/FAIL + tabela (achado | arquivo:símbolo | gravidade). FAIL se: campo ainda morto;
path não resolve relativo ao YAML; sem regressão provando o wiring; managed quebrado; vazamento.
Conclua se o contrato de benchmark está reconciliado para o M5 futuro.

GRAVAÇÃO OBRIGATÓRIA: grave este relatório de auditoria em
docs/dev-log/M3_TAREFA-313_B_<slug>.md (versionado, commitado no PR) — não apenas no chat.
~~~

---

## Sequência

313 (esta — PASS A/B) → 314 (observabilidade) → 315 (acurácia documental) → 607 (doc-sync).
Quando o M5 sair do adiamento, o seletor de IDs do funil (`load_question_ids`) deve ser construído
**sobre** o contrato definido aqui, não em paralelo.
