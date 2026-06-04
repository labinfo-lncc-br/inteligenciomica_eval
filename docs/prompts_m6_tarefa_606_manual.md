# Prompt M6 — TAREFA-606 (Claude Code ↔ ChatGPT Codex)

**Milestone:** M6 (épico de documentação E9) — emenda do manual de operação
**Tarefa:** TAREFA-606 — Atualizar `docs/operations_manual.md` para: `--run-id` obrigatório,
perguntas via `config/questions.yaml` (multi-área) e **modo `external`** com a
**responsabilidade de proveniência/reprodutibilidade do operador**
**Documentos de referência:**
- `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1, §§ 12, 15; RF8; RNF6;
  ADR-003/008/012/013)
- `prompts_m6_tarefas_601_605_corrigido.md` — TAREFA-604 (manual original)
- `auditoria_m6.md` — pendências pré-existentes do manual (I4 `--force-rows`, M3 `funnel`)
- `prompts_m3_tarefa_309.md` (questions.yaml, `--run-id`), `prompts_m3_tarefa_311.md`
  (modo `external`, ADR-013, colunas de proveniência, run report)
**Formato:** **Prompt A (implementação — Claude Code)** + **Prompt B (verificação — ChatGPT Codex)**.
**Épico coberto:** E9 (operações/documentação). **Camadas:** docs (não altera código de produção).

> **Pressupõe** TAREFA-309, 310 e **311 mergeadas e verdes** — o manual documenta comandos
> **validados por execução real**, incluindo o modo `external`. O `docs/operations_manual.md`
> já existe (TAREFA-604); esta tarefa **edita** seções específicas, **não regenera o manual
> do zero** (preservar pré-requisitos, model_registry, ondas, anotação, análise que não mudam).
> **O M5 permanece adiado** — a Seção 9 (Rodada 2) mantém a ressalva de "comando a confirmar
> quando o M5 sair" (não preencher agora).

---

## Protocolo de desenvolvimento em pares (Claude Code ↔ ChatGPT Codex)

Cada prompt é dividido em **Parte A — implementação (Claude Code)** e **Parte B — revisão e
auditoria (ChatGPT Codex)**. Toda execução gera relatório em `docs/dev-log/`. Processo
iterativo A→B→A→B até **PASS por ambos**. Avanço só com **minha autorização explícita** e
após `add`/`commit`/`push`. `CLAUDE.md` mantido atualizado.

> **Início:** execute a **Parte A** e produza o relatório. A **Parte B** roda em seguida
> (relatório + diff). Itere A↔B até PASS.

---

## Nota de operacionalização — escopo da emenda (606)

Edição **cirúrgica** do `docs/operations_manual.md`. As mudanças:

1. **`--run-id` obrigatório (Seção 5).** O comando de execução hoje aparece sem `--run-id`;
   com a TAREFA-309 ele é obrigatório na execução real. Corrigir para
   `ielm-eval run --config config/experiment_round1.yaml --run-id <run_id>` e citar
   `--phase`/`--serial`.

2. **Perguntas via `config/questions.yaml` (nova subseção).** Explicar: as perguntas vivem
   em `config/questions.yaml` (RF4/P4), o path é declarado no campo `questions:` do YAML de
   rodada, e **cada área de conhecimento** usa seu próprio arquivo
   (`config/questions_<area>.yaml`) referenciado por um YAML de rodada próprio. Sem env var,
   sem re-release. Formato do arquivo (lista de `{question_id, text, ground_truth}`) e a
   regra de que `question_id` deve casar com `config/gold_chunks.jsonl` na Rodada 2 (M5).

3. **Nova seção: "Modo `external` — servidores pré-existentes via túnel SSH" (ADR-013).**
   - **Quando usar:** cluster compartilhado/air-gapped, GH200 com build ARM custoso; o
     ielm-eval roda numa máquina x86 com internet e acessa vLLM/Qdrant por túnel.
   - **Topologia** (diagrama textual): cliente x86 ↔ túnel SSH ↔ nodes GH200 (vLLM) + Qdrant.
   - **Configuração:** `server_mode: external` no YAML de rodada; `endpoint_env` por modelo
     em `model_registry.yaml`; as env vars das URLs tuneladas (mascarar valores reais).
   - **Túnel SSH:** exemplos de `ssh -L localhost:<porta>:<node>:<porta>` para cada porta
     vLLM e para o Qdrant (6333), e como verificar (`curl localhost:<porta>/health`,
     `curl localhost:6333/healthz`).
   - **RESPONSABILIDADE DO OPERADOR (bloco em destaque):** neste modo o ielm-eval **NÃO**
     controla o lançamento do vLLM. O operador é responsável por subir o **juiz** com
     `VLLM_BATCH_INVARIANT=1`, `temperature=0`, `tensor_parallel_size=1`,
     `VLLM_ENABLE_V1_MULTIPROCESSING=0` (ADR-003) e por garantir que cada endpoint serve o
     modelo esperado. O ielm-eval **verifica por sonda** e **grava** o resultado, mas não o
     garante.
   - **Como auditar a rodada:** ler as colunas de proveniência por linha (`server_mode`,
     `served_model_id`, `determinism_verified`) e a seção `endpoints_provenance` do run
     report; usar `--require-verified-determinism` para runs de qualidade de publicação
     (aborta se o probe do juiz falhar).
   - Deixar claro que **`managed` continua o default** e inalterado (GH200 local, ielm-eval
     dono do ciclo de vida).

4. **Seção 2 (env vars):** sem nova variável obrigatória global; documentar que, em
   `external`, as URLs tuneladas vão nas env vars referenciadas por `endpoint_env`
   (apenas nomes, nunca valores).

5. **Pendências pré-existentes (auditoria M6):** já que o arquivo será tocado, aplicar
   I4 (substituir `--force-rows` por `--force` na Seção 11) e a ressalva do `ielm-eval
   funnel` na Seção 9 (M5 — "verificar o nome exato na CLI quando o M5 sair").

6. **Smoke-test do manual:** manter/atualizar o teste que valida que os comandos citados
   existem na CLI (`ielm-eval --help`), incluindo `run --run-id`, e a flag
   `--require-verified-determinism`.

---

## TAREFA-606 — Emenda do manual de operação

**Épico:** E9 · **Skill:** python-engineer · **Prioridade:** P1 · **Tamanho:** M
**Dependências:** TAREFA-309, 310, 311 (mergeadas) · **ADRs:** ADR-003, ADR-008, ADR-012,
**ADR-013** · **RF:** RF8 · **RNF:** RNF6 · **Camadas:** docs (sem código de produção)

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §§12, 15; RF8; RNF6;
ADR-003/008/012/013). Skill: python-engineer. TAREFA-309/310/311 mergeadas e verdes. Esta
tarefa EDITA `docs/operations_manual.md` (criado na TAREFA-604) — não regenera o manual.
Os valores citados devem ser REAIS, confirmados por execução. VER "Nota de operacionalização
— escopo da emenda (606)", itens 1–6.

LEIA ANTES DE EDITAR: o `docs/operations_manual.md` atual; a saída de `ielm-eval --help`,
`ielm-eval run --help`; ADR-013; o schema §5.3 (colunas de proveniência) e o run report
(endpoints_provenance) entregues na TAREFA-311.

TAREFA: TAREFA-606 — aplicar as edições abaixo no manual, preservando o restante.

ESPECIFICAÇÃO (edições):

1. Seção 5 (Executando a Rodada 1): comando passa a
   `ielm-eval run --config config/experiment_round1.yaml --run-id <run_id>`; citar
   `--phase A|B|both` e `--serial`. Atualizar quaisquer exemplos derivados.

2. Nova subseção (em Seção 2 ou 5, onde fizer sentido) — "De onde vêm as perguntas":
   - `config/questions.yaml` (RF4/P4), referenciado pelo campo `questions:` do YAML de rodada.
   - Multi-área: um arquivo por área (`config/questions_<area>.yaml`) + YAML de rodada próprio.
   - Formato (lista de {question_id, text, ground_truth}); `question_id` casa com
     `config/gold_chunks.jsonl` na Rodada 2 (M5).

3. Nova seção "Modo external (servidores via túnel SSH) — ADR-013" com: quando usar;
   diagrama textual da topologia; `server_mode: external` + `endpoint_env` por modelo;
   exemplos de túnel SSH e verificação (curl /health, /healthz); **bloco em destaque de
   responsabilidade do operador** (flags do juiz ADR-003; identidade de modelo); como
   auditar (colunas server_mode/served_model_id/determinism_verified + endpoints_provenance
   do run report; `--require-verified-determinism`); nota de que `managed` é o default.

4. Seção 2 (env vars): em external, URLs tuneladas nas env vars de `endpoint_env`
   (apenas NOMES, valores mascarados). Sem nova var global obrigatória.

5. Pendências auditoria M6: Seção 11 `--force-rows` → `--force`; Seção 9 (funnel) com a
   ressalva de verificação de nome quando o M5 sair.

6. Smoke-test: atualizar `tests/docs/test_operations_manual.py` (ou equivalente da
   TAREFA-604) para validar que todos os comandos citados no manual existem em
   `ielm-eval --help`, incluindo `run --run-id` e `--require-verified-determinism`.

ENTREGÁVEL:
- docs/operations_manual.md (editado — diff cirúrgico)
- tests/docs/test_operations_manual.py (atualizado)
- docs/dev-log/M6_TAREFA-606_A_<slug>.md (relatório com o diff de seções e a saída de
  `ielm-eval --help` usada para validar)

RESTRIÇÕES (DoD §14.2):
- Não regenerar o manual; preservar seções inalteradas.
- Valores reais (versões/paths/flags) confirmados por execução, não placeholders.
- Mascarar quaisquer endpoints/segredos nos exemplos.
- Markdown válido; links/âncoras internas consistentes.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-606):
- Seção 5 mostra `run ... --run-id`; subseção de perguntas presente (multi-área).
- Seção de modo `external` presente com bloco de responsabilidade do operador (flags do
  juiz) e instruções de auditoria de proveniência.
- Seção 2 cita as env vars de endpoint_env (nomes) sem novos obrigatórios globais.
- Pendências M6 (I4 `--force`; ressalva funnel) aplicadas.
- Smoke-test do manual PASS (todos os comandos citados existem na CLI; cole a saída).
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer (documentação + smoke-test). NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-606 + manual anterior + ADR-013 + saída de `ielm-eval --help`
+ relatório (Parte A).

VERIFIQUE, item a item, citando seção/linha:

1. Seção 5: comando de execução inclui `--run-id` (obrigatório)? `--phase`/`--serial` citados?
2. Subseção de perguntas: `config/questions.yaml` + campo `questions:` no YAML de rodada +
   multi-área (um arquivo por área)? Formato e regra de casamento com gold_chunks (M5)?
3. Seção modo external:
   a. Quando usar + topologia (túnel SSH) + `server_mode: external` + `endpoint_env`?
   b. Exemplos de túnel e verificação (curl /health, /healthz)?
   c. BLOCO de responsabilidade do operador com as flags do juiz (VLLM_BATCH_INVARIANT=1,
      temperature=0, tp=1, VLLM_ENABLE_V1_MULTIPROCESSING=0) e identidade de modelo?
   d. Auditoria: colunas server_mode/served_model_id/determinism_verified +
      endpoints_provenance + `--require-verified-determinism`?
   e. Deixa claro que `managed` é o default e inalterado?
4. Seção 2: env vars de endpoint_env por NOME (valores mascarados); sem novo obrigatório global?
5. Pendências M6: `--force-rows`→`--force` (Seção 11); ressalva do funnel (Seção 9)?
6. M5 adiado: Seção 9 NÃO foi preenchida com comandos inexistentes (mantém ressalva)?
7. Não-regeneração: seções inalteradas preservadas (diff é cirúrgico)?
8. Smoke-test: todos os comandos citados existem em `ielm-eval --help` (incl. run --run-id,
   --require-verified-determinism)? Teste PASS (cole a saída)?
9. Markdown válido; sem endpoints/segredos expostos?

SAÍDA: PASS/FAIL + tabela de divergências (seção/linha | gravidade:
BLOQUEADOR | IMPORTANTE | SUGESTÃO). Cole a saída do smoke-test e de `ielm-eval --help`.
~~~
