# Prompt M3 — TAREFA-312 (Claude Code ↔ ChatGPT Codex)

**Milestone:** M3 (gate transversal) — integração e completude de 309/310/311 (+ coerência com 606)
**Tarefa:** TAREFA-312 — Verificação completa de código e testes: varredura de **pontas soltas
que quebram ou bloqueiam a execução**, com correção dos bloqueadores e relatório de completude
**Documentos de referência:**
- `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1, §§ 4.3, 5.1, 5.3, 8, 12, 14.2, 14.6)
- `prompts_m3_tarefa_309.md`, `prompts_m3_tarefa_310.md`, `prompts_m3_tarefa_311.md`,
  `prompts_m6_tarefa_606_manual.md`
**Formato:** **Prompt A (varredura + correção de bloqueadores — Claude Code)** +
**Prompt B (auditoria independente — ChatGPT Codex)**.
**Natureza:** **NÃO** implementa funcionalidades novas. É um **gate de integração**: prova
que 309+310+311 estão completos e coerentes, sem pontas soltas, e que 606 casa com a CLI real.

> **Pressupõe** TAREFA-309, 310 e 311 implementadas (idealmente já com PASS individual A/B)
> e a 606 redigida. As mudanças foram muitas (novo mecanismo de perguntas, CLI `run`
> completo, modo `external`, ADR-013, **3 colunas novas no schema §5.3**, novo campo na
> entidade `EvaluationResult` §4.3, run report estendido, novos config fields). Este gate
> existe justamente porque alterações desse alcance deixam **pontas soltas**: construtores
> de entidade que não passam os campos novos, leitura de Parquet antigo, fakes
> desatualizados, configs que não parseiam, comandos do manual que não existem, etc.
> **O M5 permanece adiado.** DoD §14.2 vale integralmente.
> **Princípio:** bloqueadores (quebram/impedem execução) são **corrigidos neste PR**;
> achados não-bloqueadores são **registrados** com proposta, sem alterar escopo das tarefas.

---

## Protocolo de desenvolvimento em pares (Claude Code ↔ ChatGPT Codex)

Cada prompt é dividido em **Parte A — execução (Claude Code)** e **Parte B — auditoria
(ChatGPT Codex)**. Toda execução gera relatório em `docs/dev-log/`. Processo iterativo
A→B→A→B até **PASS por ambos**. Avanço só com **minha autorização explícita** e após
`add`/`commit`/`push`. `CLAUDE.md` mantido atualizado.

> **Início:** execute a **Parte A** (varredura completa + correção dos bloqueadores) e
> produza o **relatório de completude**. A **Parte B** reproduz a varredura de forma
> independente e audita o relatório. Itere A↔B até PASS.

---

## Nota de operacionalização — o que "completude sem pontas soltas" significa

O gate cobre **seis superfícies de risco** abertas por 309/310/311/606. Para cada uma há
invariantes objetivos a provar. O Claude Code **roda tudo**, **corrige os bloqueadores** e
preenche a **matriz de completude** (tarefa × entregue? × testado? × gates verdes?).

1. **Ripple do schema §5.3 / entidade §4.3.** Os 3 campos novos (`server_mode`,
   `served_model_id`, `determinism_verified`) tocam TODO construtor de `EvaluationResult`,
   o writer/reader Parquet, os fakes e os goldens.
2. **Leitura retrocompatível.** Parquet escrito ANTES da 311 não tem as 3 colunas — o
   reader (M2/M4) precisa ter comportamento **definido e testado** (tolerar/defaultar ou
   falhar com mensagem clara — decisão a registrar).
3. **CLI / config.** `run` exige `--run-id`; `RoundConfig` ganhou `questions` e
   `server_mode`; `ModelEntry` ganhou `endpoint_env`. Todos os YAML em `config/` precisam
   parsear; todos os subcomandos preservados.
4. **Modo `external` end-to-end.** Seleção de adapter, probes mockáveis (zero rede em
   teste), `start` sem subprocess, `stop` no-op, `EndpointUnreachableError` tratado,
   Panel de responsabilidade, `--require-verified-determinism`.
5. **Proveniência.** `endpoints_provenance` no run report (ambos os modos); nenhum valor
   inventado (`"unknown"`/`false` quando não verificável); **endpoints mascarados** em
   logs/Panels (sem vazamento de segredo).
6. **Coerência doc↔código (606 + §§4.3/5.3).** A lista de colunas documentada == o schema
   real do `ParquetStorage`; todo comando citado no manual existe em `ielm-eval --help`.

---

## TAREFA-312 — Gate de integração e completude

**Épico:** E3 (transversal) · **Skills:** code-reviewer, test-engineer · **Prioridade:** P0 ·
**Tamanho:** M · **Dependências:** TAREFA-309, 310, 311 (implementadas), 606 (redigida) ·
**ADRs:** ADR-003/004/008/012/013 · **DoD:** §14.2 · **Camadas:** transversal (sem feature nova)

### Prompt A — Varredura + correção de bloqueadores (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica. Skills: code-reviewer, test-engineer.
TAREFA-309/310/311 implementadas e 606 redigida. As mudanças foram amplas e provavelmente
deixaram PONTAS SOLTAS que quebram/bloqueiam a execução. Esta tarefa NÃO cria features:
faz uma VARREDURA COMPLETA de código e testes, CORRIGE os bloqueadores no mesmo PR e produz
um RELATÓRIO DE COMPLETUDE. VER "Nota de operacionalização — 312", superfícies 1–6.

TAREFA: TAREFA-312 — executar a varredura abaixo na ordem, corrigir bloqueadores e relatar.

A. GATES ESTÁTICOS E SUÍTE (rodar e colar saídas):
   1. `uv sync` (ou equivalente) sem erro; `python -c "import inteligenciomica_eval"` ok.
   2. `ruff check .` e `ruff format --check .` verdes.
   3. `mypy --strict src` verde.
   4. `lint-imports` verde.
   5. `pytest -m unit -q`, `pytest -m integration -q`, `pytest -m e2e -q --timeout=30`,
      e `pytest --cov=src --cov-fail-under=85 -q`. TODOS verdes. Colar sumários.

B. RIPPLE SCHEMA §5.3 / ENTIDADE §4.3 (superfície 1):
   1. `grep -rn "EvaluationResult(" src tests` — listar TODOS os pontos de construção e
      confirmar que cada um fornece server_mode, served_model_id, determinism_verified.
      Qualquer construtor sem os campos é BLOQUEADOR → corrigir.
   2. Roundtrip Parquet com as 3 colunas (escrita→leitura) preserva valores e tipos.
   3. Checagem de coerência de escrita (batch_invariant==True ⇔ juiz) ainda dispara.
   4. Fakes (tests/fakes/*) que produzem EvaluationResult/linhas fornecem os 3 campos.

C. LEITURA RETROCOMPATÍVEL (superfície 2):
   1. Construir um Parquet "legado" (sem as 3 colunas) e ler via o reader real.
   2. Comportamento DEFINIDO: ou (a) defaulta as colunas ausentes com mensagem de log, ou
      (b) falha com erro claro. Documentar a decisão no relatório e cobrir com teste.
      Comportamento indefinido/quebra silenciosa = BLOQUEADOR.

D. CLI / CONFIG (superfície 3):
   1. `ielm-eval --help` lista version, run, compute-metrics, analyze, report, annotate,
      status, show-config, run-round2, validate-judge (NENHUM removido). Colar.
   2. `ielm-eval run --help` mostra --run-id (obrigatório), --phase, --serial, --dry-run,
      --require-verified-determinism. Colar.
   3. Parsear TODOS os YAML de `config/` contra os schemas (RoundConfig com questions +
      server_mode; model_registry com endpoint_env). `config/experiment_round1.yaml` e
      `config/questions.yaml` parseiam. Qualquer YAML que quebra = BLOQUEADOR → corrigir.
   4. `ielm-eval run --config config/experiment_round1.yaml --run-id smoke --dry-run`
      (managed): exit 0; imprime plano de ondas + "Perguntas carregadas: N". Colar.

E. MODO EXTERNAL E2E (superfície 4):
   1. Caminho `server_mode=external` em dry-run/fake (sem rede real): build seleciona
      ExternalVLLMServerManager; imprime Panel de responsabilidade + resultado dos probes
      (mockados). Colar.
   2. Teste prova: start NÃO chama subprocess.Popen; stop é no-op; wait_healthy faz probe;
      endpoint inacessível → EndpointUnreachableError tratado pela CLI (Panel + exit 1).
   3. `--require-verified-determinism` + probe de juiz falho (mock) → exit 1.
   4. `grep -rn "tests.fakes\|tests/fakes" src` — NENHUM import de fakes no nível de módulo
      de produção (só lazy dentro de build_fake_container). Violação = BLOQUEADOR.

F. PROVENIÊNCIA (superfície 5):
   1. Run report contém endpoints_provenance (server_mode + por-endpoint served_model_id,
      vllm_version, healthy, determinism_verified) em managed E external.
   2. `grep` por valores inventados: version indisponível → "unknown"; determinismo não
      verificado → false explícito (nunca True por default).
   3. Mascaramento: `grep` em logs/Panels por URLs cruas/segredos; endpoints sempre
      mascarados. Vazamento = BLOQUEADOR.

G. RIPPLE 310 / M4 (superfícies 1 e 6):
   1. `pytest -m e2e tests/e2e/test_m3_full_cycle.py -v --timeout=30`: 5 PASSED < 30 s; o
      golden inclui as 3 colunas novas. Colar.
   2. Suíte do M4 (analyze/report/status) verde com as colunas novas. Colar.

H. COERÊNCIA DOC↔CÓDIGO (superfície 6):
   1. Verificar programaticamente que a lista de colunas em §5.3 (doc) == o schema real do
      ParquetStorage (extrair ambos e comparar; divergência = BLOQUEADOR de doc).
   2. Smoke-test do manual (TAREFA-606): todo comando citado existe em `ielm-eval --help`,
      incluindo `run --run-id` e `--require-verified-determinism`. Colar.
   3. §§4.3/5.3 e ADR-013 presentes e consistentes com o código.

I. VARREDURA DE PONTAS SOLTAS (transversal):
   1. `grep -rn "NotImplementedError\|TODO\|FIXME\|not yet implemented\|placeholder\|pass  #"`
      em src — classificar cada ocorrência nos módulos tocados por 309/310/311. Qualquer
      uma no caminho de execução do `run` (managed ou external) = BLOQUEADOR → resolver.
   2. Confirmar que NÃO restaram os placeholders antigos de analyze/report (substituídos por
      comandos reais do M4).
   3. Confirmar que não há referências mortas a símbolos renomeados/removidos.

ENTREGÁVEL:
- Correções de TODOS os bloqueadores encontrados (commits no mesmo PR).
- docs/dev-log/M3_TAREFA-312_A_<slug>.md contendo:
  * MATRIZ DE COMPLETUDE: linhas {309, 310, 311, 606} × colunas {entregue, testado,
    gates verdes, pendências}.
  * Lista de achados classificados: BLOQUEADOR (corrigido — citar commit) | IMPORTANTE
    (registrado) | COSMÉTICO (registrado).
  * Saídas coladas de: gates estáticos, suíte completa+cobertura, ambos os dry-runs
    (managed e external), e2e 310, suíte M4, smoke-test do manual, `ielm-eval --help`.
  * Decisão registrada de leitura retrocompatível (item C).

RESTRIÇÕES (DoD §14.2):
- NÃO adicionar features nem ampliar escopo de 309/310/311/606; só corrigir o que quebra/bloqueia.
- Toda correção acompanhada de teste que falharia antes dela.
- `from __future__ import annotations`; mypy --strict; ruff; lint-imports verdes ao final.
- Nada de import de fakes em produção; nada de segredo/endpoint exposto.

CRITÉRIO DE ACEITAÇÃO (gate de integração):
- A–I executados; todas as saídas coladas.
- ZERO bloqueadores remanescentes; cada bloqueador encontrado foi corrigido com teste.
- Matriz de completude preenchida; 309/310/311 "entregue+testado+gates verdes"; 606
  coerente com a CLI real.
- Suíte completa verde, cobertura ≥ 85%, e2e 310 < 30 s, suíte M4 verde, smoke-test do
  manual verde, dry-runs managed e external verdes.
~~~

### Prompt B — Auditoria independente (ChatGPT Codex)

~~~text
PAPEL: code-reviewer + test-engineer. Auditoria INDEPENDENTE — não confie só no relatório:
reproduza a varredura você mesmo onde for possível.

ENTRADA: diff do PR da TAREFA-312 + os 4 prompts (309/310/311/606) + arquitetura
§§4.3/5.1/5.3/8/12/14.2 + ADR-013 + relatório de completude (Parte A).

REPRODUZA E VERIFIQUE (cole as saídas que você mesmo rodar):

1. Gates estáticos + suíte: ruff, mypy --strict, lint-imports, `pytest -m "unit or
   integration or e2e" -q --timeout=30`, cobertura ≥ 85. Verdes?

2. Ripple schema/entidade: `grep -rn "EvaluationResult("` — algum construtor sem os 3
   campos? Roundtrip Parquet preserva as 3 colunas? Coerência de escrita dispara?

3. Retrocompatibilidade: existe teste lendo Parquet legado (sem as 3 colunas) com
   comportamento definido (default+log OU erro claro)? Quebra silenciosa = FAIL.

4. CLI/config: `ielm-eval --help` lista TODOS os subcomandos? `run --help` mostra
   --run-id obrigatório + --require-verified-determinism? Todo YAML de config/ parseia?
   Dry-run managed exit 0?

5. External: dry-run/fake external imprime Panel de responsabilidade + probes? start sem
   subprocess (mock comprova)? stop no-op? EndpointUnreachableError tratado? probe falho +
   --require-verified-determinism → exit 1? Nenhum import de fakes em produção?

6. Proveniência: endpoints_provenance no run report (ambos os modos)? "unknown"/false em
   vez de valores inventados? Endpoints mascarados (sem URL/segredo cru em logs/Panels)?

7. Ripple 310/M4: e2e 310 5 PASSED < 30 s com 3 colunas no golden? Suíte M4 verde?

8. Doc↔código: lista de colunas §5.3 == schema real do ParquetStorage? Smoke-test do
   manual verde (comandos citados existem)? ADR-013 e §§4.3/5.3 consistentes?

9. Pontas soltas: `grep` por NotImplementedError/TODO/FIXME/placeholder nos módulos do
   caminho de execução do `run` — alguma remanescente bloqueia execução? Placeholders
   antigos de analyze/report sumiram? Referências mortas?

10. Matriz de completude do relatório: bate com o que você observou? Algum "verde"
    declarado que na verdade falha?

SAÍDA: PASS/FAIL + tabela de divergências (superfície | critério | arquivo:linha |
gravidade: BLOQUEADOR | IMPORTANTE | COSMÉTICO).
FAIL se: qualquer bloqueador remanescente; matriz divergente da realidade; suíte/cobertura/
e2e/M4/smoke-test não verdes; doc↔schema incoerente; vazamento de endpoint.
Cole: gates estáticos, suíte+cobertura, dry-runs managed e external, e2e 310, smoke-test
do manual. Conclua se 309/310/311 estão íntegros e prontos para o doc-sync (arq v1.2 / visão v1.1).
~~~
