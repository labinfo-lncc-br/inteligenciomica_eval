# TAREFA-317 — Resolução do nome do modelo (served_model_id) + smoke run external (Claude Code ↔ ChatGPT Codex)

**Origem:** alerta de arquitetura confirmado no as-built (`infrastructure/wiring.py`): no modo
`external`, a fábrica de geradores infere o nome do modelo pela porta da URL e cai no fallback
`"model"` para portas de túnel — provável 404 "model not found". É o degrau entre "código mergeado"
e "rodar de verdade".
**Contexto:** a rodada de saneamento (313–315) e o doc-sync (607) fecharam; a 316 tornou o prompt de
geração fiel à produção e selecionável. A 316 **não** tocou na resolução do nome do modelo de
propósito — fica aqui, junto do smoke run que a detecta/valida.
**Achado-chave (as-built):** `_VLLMGeneratorFactory.__call__` faz
`port = int(url.split(":")[2]...)` → `self._port_to_model.get(port, "model")`, e `port_to_model`
só contém as chaves `8000 + gpu_index` (`_entry_to_model_spec`). Em URL de túnel (porta arbitrária)
→ `"model"`. **Porém** `build_container` já executa `_run_endpoint_probes`, que obtém
`served_model_id` por gerador via `probe_served_model(url)` e o guarda em `_gen_served_ids`
(`{llm: served_model_id}`) e em `endpoints_provenance`. O `served_model_id` correto **já está
disponível** no wiring.

> **Sequência:** independente do doc-sync (TAREFA-608). É o item de **maior alavancagem** para
> destravar a execução real no modo `external`. Hard-depende apenas do estado atual mergeado
> (313–316). O M5 permanece adiado. DoD §14.2 vale.

---

## Protocolo de desenvolvimento em pares (Claude Code ↔ ChatGPT Codex)

Esta tarefa tem **Parte A — execução (Claude Code)** e **Parte B — auditoria (ChatGPT Codex)**.
Processo iterativo A→B→A→B até **PASS por ambos**. Avanço só com **autorização explícita** do
usuário e após `add`/`commit`/`push`. `CLAUDE.md` mantido atualizado.

> **GRAVAÇÃO OBRIGATÓRIA DOS RELATÓRIOS.** Tanto o relatório de execução (Parte A) quanto o de
> auditoria (Parte B) **DEVEM ser GRAVADOS como arquivos versionados** em `docs/dev-log/`,
> **commitados no mesmo PR** — não basta exibir no chat. Convenção:
> - Parte A → `docs/dev-log/M3_TAREFA-317_A_<slug>.md`
> - Parte B → `docs/dev-log/M3_TAREFA-317_B_<slug>.md`
> - Ciclos subsequentes incrementam o sufixo (`_A2_`, `_B2_`, …).
> Cada relatório contém as saídas coladas dos gates/testes que aquela parte rodou. Um ciclo sem o
> arquivo de relatório gravado é considerado **incompleto**.

---

**Épico:** E3/E4 (orquestração + proveniência) · **Skill:** backend-engineer, python-engineer, test-engineer ·
**Prioridade:** P0 · **Tamanho:** M · **ADRs:** ADR-005, ADR-008, ADR-012, ADR-014 · **Camada:** infrastructure + cli + docs + tests

**Diagnóstico (as-built confirmado):**
- `infrastructure/wiring.py::_VLLMGeneratorFactory.__call__` resolve o nome do modelo pela porta
  (`port_to_model` = `{8000+gpu_index: name}`); em URL de túnel → `"model"` → 404 provável.
- `_run_endpoint_probes` já popula `_gen_served_ids = {llm: served_model_id}` e
  `endpoints_provenance["generators"][name]["served_model_id"]` (probe `probe_served_model`).
- `_gen_urls` mapeia `{llm: url}` em external (URLs distintas por modelo) e, em managed,
  `dict.fromkeys(config.llms, VLLM_GENERATOR_URL)` (degenerado — todas iguais; probes no wiring
  tendem a falhar pois os servidores ainda não subiram).

### Prompt A — execução (Claude Code)

~~~text
CONTEXTO: Skills: backend-engineer, python-engineer, test-engineer. Padrão python-clean-architecture.
ADR-014 (proveniência verificada por sonda), ADR-005 (cliente OpenAI-compatible), ADR-012 (layout de
porta managed). Objetivo: (1) corrigir a resolução do nome do modelo usando o served_model_id já
sondado, sem quebrar o managed; (2) entregar um comando `smoke` que valida 1 modelo × 1 pergunta
ponta a ponta no modo external e detecta o problema antes de qualquer rodada cheia.

TAREFA: TAREFA-317.

1. FIX — resolução do nome do modelo (infrastructure/wiring.py):
   - `_VLLMGeneratorFactory.__init__`: adicionar parâmetro
     `served_model_by_url: dict[str, str] | None = None` (default None → {}).
   - `_VLLMGeneratorFactory.__call__(url)`: PRECEDÊNCIA de resolução do nome:
       (a) `served = (self._served_model_by_url or {}).get(url, "")` — se NÃO vazio, `model = served`;
       (b) senão, fallback ATUAL por porta (`port_to_model.get(port, "model")`), preservando o
           comportamento managed (ADR-012);
       (c) senão, `"model"`.
     Logar (com `mask_url(url)`) qual caminho resolveu (`served_probe` | `port_layout` | `fallback`)
     e o nome resolvido — sem vazar a URL crua (política da 314).
   - `build_container`: APÓS os probes, montar
     `served_model_by_url = {url: _gen_served_ids[name] for name, url in _gen_urls.items()
                             if _gen_served_ids.get(name)}`
     e passá-lo ao `_VLLMGeneratorFactory(port_to_model, prompt_registry=..., prompt_version=...,
     served_model_by_url=served_model_by_url)`.
     RACIONAL (documentar em comentário): em external, `_gen_urls` traz URLs distintas por modelo e
     `_gen_served_ids` foi sondado → resolução correta; em managed, `_gen_urls` é degenerado e os
     probes no wiring tendem a falhar (servidores ainda não subiram) → `served_model_by_url` vazio →
     mantém o layout por porta. NÃO alterar `_entry_to_model_spec` nem a convenção 8000+gpu_index.

2. COMANDO `smoke` (cli.py): `ielm-eval smoke --config <yaml> [--llm <name>] [--question-id <id>]`
   - Constrói o container REAL (respeita server_mode do YAML; external usa endpoint_env).
   - Seleciona 1 modelo (o `--llm`, ou o 1º de `config.llms`), 1 pergunta (o `--question-id`, ou a
     1ª do benchmark carregado) e 1 seed (o 1º de `config.seeds`).
   - Executa em sequência, SOMENTE para essa célula: Passada 1 (geração) → Passada 2 (métricas:
     RAGAS + BERTScore — força o carregamento dos embeddings) → Passada 3 (juiz).
   - NÃO gravar no dataset de produção: usar diretório temporário (ex.: `tempfile.TemporaryDirectory`)
     para o `ParquetStorage` do smoke (injetar via `config_dir`/parâmetro dedicado — não poluir `data/`).
   - Imprime DIAGNÓSTICO estruturado (tabela legível + JSON em log):
       * server_mode;
       * por gerador alvo: served_model_id resolvido e o nome efetivamente enviado ao endpoint —
         se o nome == "model" (fallback), marcar **WARN** com a dica "nome não resolvido: confira
         endpoint_env/served_model_id";
       * status da geração: ok (texto não vazio) | 404 (modelo não encontrado) | erro (mensagem);
       * score do juiz (ou NaN);
       * origem dos embeddings (hf_local | vllm_endpoint) e se carregaram sem erro;
       * determinism_verified (do probe do juiz).
   - EXIT CODE: 0 se geração produziu texto não vazio E juiz devolveu score não-NaN; != 0 caso
     contrário, com hint acionável (ex.: 404 → "provável divergência de nome do modelo: rode após o
     FIX do item 1; confira endpoint_env e o served_model_id sondado").
   - Reaproveitar use cases existentes (gen_pass_uc/metrics_pass_uc/judge_pass_uc) e a proveniência
     já coletada; não duplicar lógica de probe.

3. MANUAL (docs/operations_manual.md):
   - Atualizar a subseção de smoke run (G1, introduzida na TAREFA-315) para apontar o comando real
     `ielm-eval smoke --config ... [--llm ...] [--question-id ...]`, descrevendo a leitura do
     diagnóstico (served_model_id, 404, NaN, embeddings) e o exit code. Manter a orientação de
     rodar o smoke ANTES da rodada cheia.

ENTREGÁVEL:
- Atualização de src/inteligenciomica_eval/infrastructure/wiring.py (fix + served_model_by_url).
- Atualização de src/inteligenciomica_eval/infrastructure/cli.py (subcomando `smoke`).
- Atualização de docs/operations_manual.md (G1 → comando real).
- tests/unit/... (fix da fábrica) e tests/integration/... (comando smoke com fakes).
- docs/dev-log/M3_TAREFA-317_A_<slug>.md (relatório de execução GRAVADO).

TESTES (obrigatórios):
- REGRESSÃO da fábrica (falha contra o código atual):
   * URL de túnel (ex.: "http://localhost:8010/v1") COM served_model_by_url → retorna o
     served_model_id sondado (NÃO "model");
   * URL no layout managed (porta 8000+gpu_index) SEM served_model_by_url → retorna o nome do
     registry (port_layout);
   * URL desconhecida e sem served → "model" (fallback) + log do caminho.
- Comando `smoke` com fakes (sem rede): roda 1×1, imprime diagnóstico, EXIT 0 com fakes saudáveis;
  EXIT != 0 quando o fake gerador devolve texto vazio (simula 404) ou o juiz devolve NaN; confirma
  que não grava em `data/` (usa temp).
- mypy --strict, ruff, import-linter verdes; cobertura ≥ 85%.

RESTRIÇÕES (DoD §14.2):
- from __future__ import annotations; type hints; docstrings Google; mypy --strict.
- NÃO alterar a convenção de porta managed (ADR-012) nem a assinatura de GeneratorPort.generate.
- NÃO logar URL/endpoint crus (política da 314 — usar mask_url); smoke não grava no dataset real.
- infrastructure → domain; sem dependência nova de terceiros.

CRITÉRIO: em external, o gerador passa a usar o served_model_id sondado (sem 404 por nome "model");
managed inalterado; `ielm-eval smoke` roda 1×1, diagnostica served_model_id/404/NaN/embeddings e
retorna exit code coerente; teste de regressão falharia contra o código atual; manual aponta o
comando; relatório da Parte A gravado em docs/dev-log/.
~~~

### Prompt B — auditoria (ChatGPT Codex)

~~~text
PAPEL: code-reviewer + security-auditor. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-317 + relatório A (de docs/dev-log/) + wiring.py + endpoint_probe.py +
cli.py + manual + ADR-014.

VERIFIQUE, item a item, citando arquivo:linha:
1. FIX: `_VLLMGeneratorFactory.__call__` prefere served_model_by_url[url]; só cai no layout por porta
   quando vazio; "model" é último recurso? Loga o caminho de resolução com mask_url (sem URL crua)?
2. build_container monta served_model_by_url a partir de `_gen_served_ids`/`_gen_urls` (somente
   entradas com served não-vazio) e o injeta na fábrica? Comentário explica por que managed não
   regride (degenerado/probe-falha → vazio → layout por porta)?
3. Convenção de porta managed (8000+gpu_index) e `_entry_to_model_spec` intactos? Assinatura de
   GeneratorPort.generate inalterada?
4. Comando `smoke`: constrói container real respeitando server_mode; roda 1 llm × 1 pergunta × 1 seed
   nas 3 passadas; usa storage TEMPORÁRIO (não grava em data/); diagnóstico cobre server_mode,
   served_model_id/nome enviado (WARN se "model"), status geração (ok/404/erro), score do juiz (NaN?),
   origem/carregamento dos embeddings, determinism_verified; exit code 0/≠0 coerente com hints?
5. Reaproveita os use cases e a proveniência existentes (sem duplicar probes)?
6. Testes: há regressão da fábrica que FALHARIA contra o código atual (túnel → "model")? Teste do
   smoke com fakes cobre EXIT 0 e EXIT != 0 (texto vazio / juiz NaN) e o uso de temp?
7. Manual atualizado para o comando `smoke` real (G1)? Sem URL/endpoint cru em log (314)?
8. mypy --strict, ruff, import-linter, cobertura ≥85% (cole as saídas)?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
FAIL se: o nome ainda resolve para "model" em external; managed regride; smoke grava no dataset real
ou não diagnostica os campos exigidos; falta o teste de regressão; URL crua em log.

> Ao final, GRAVE o relatório de auditoria em docs/dev-log/M3_TAREFA-317_B_<slug>.md (não apenas no
> chat) e inclua-o no PR.
~~~

---

**Sequência geral:** 313✔ → 314✔ → 315✔ → 607✔ → 316✔ → **317 (esta — destrava execução real)** ·
em paralelo: 608 (doc-sync do 316, docs-only). Após o 317 e a execução real, o **refresh do
quickstart** (derivado do manual já atualizado). Item ainda aberto e fora desta tarefa: fidelidade
do **pipeline A** (cross-encoder rerank + query-encoder externos) para realismo end-to-end do Exp A.
