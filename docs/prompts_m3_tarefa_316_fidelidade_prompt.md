# TAREFA-316 — Fidelidade do prompt de geração + prompt selecionável por rodada (Claude Code ↔ ChatGPT Codex)

**Origem:** discussão de arquitetura sobre o uso do eval para **melhorar o prompt de produção** e
decidir o LLM padrão do InteligenciÔmica. Constatou-se que o gerador do eval **não é fiel** ao
estímulo que a produção envia, e que o `prompts/rag_answer.txt` previsto na TAREFA-103 **nunca foi
implementado** para a geração (o `PromptRegistry` só renderiza a rubrica do juiz).
**Contexto:** a rodada de saneamento (313→314→315→607) trata deriva doc/observabilidade; esta tarefa
é **feature work** que a sucede. O InteligenciÔmica de **produção é referência congelada** (código de
outra equipe, não alterado agora); é o **eval** que se adapta a ele para medir prompt e modelo de
forma fiel ao que o usuário final vive.
**Decisão de arquitetura (do usuário):** **D1 = o prompt passa a ser um fator selecionável por
rodada.** O prompt de geração vira um **bundle versionado** (system + user), escolhido no YAML da
rodada e gravado em proveniência (`prompt_version`), para A/B-ar redações com a estatística
automática (Wilcoxon/Friedman/RankScore). O bundle **default** replica a produção **verbatim**.
**Introduz:** **ADR-015** — "Prompt de geração versionado e selecionável por rodada; fidelidade ao
prompt de produção (system+user, contexto com PMID, strip de `<think>`)".

> **Sequência:** roda **após** a rodada de saneamento (313✔ → 314✔ → 315 → 607). Hard-depende apenas
> da **313 mergeada** (contrato de benchmark — perguntas via `RoundConfig.questions`), já satisfeita;
> recomenda-se rodar após o 607 para editar sobre a documentação já consolidada. **Veículo de uso:**
> Experimento B (contextos fixos — TAREFA-304/305), que congela o retrieval para os 5 modelos e
> isola o efeito do prompt/modelo. O M5 permanece adiado. DoD §14.2 vale.

---

## Protocolo de desenvolvimento em pares (Claude Code ↔ ChatGPT Codex)

Esta tarefa tem **Parte A — execução (Claude Code)** e **Parte B — auditoria (ChatGPT Codex)**.
Processo iterativo A→B→A→B até **PASS por ambos**. Avanço só com **autorização explícita** do
usuário e após `add`/`commit`/`push`. `CLAUDE.md` mantido atualizado.

> **GRAVAÇÃO OBRIGATÓRIA DOS RELATÓRIOS.** Tanto o relatório de execução (Parte A) quanto o de
> auditoria (Parte B) **DEVEM ser GRAVADOS como arquivos versionados** em `docs/dev-log/`,
> **commitados no mesmo PR** — não basta exibir no chat. Convenção:
> - Parte A → `docs/dev-log/M3_TAREFA-316_A_<slug>.md`
> - Parte B → `docs/dev-log/M3_TAREFA-316_B_<slug>.md`
> - Ciclos subsequentes incrementam o sufixo (`_A2_`, `_B2_`, …).
> Cada relatório contém as saídas coladas dos gates/testes que aquela parte rodou. Um ciclo sem o
> arquivo de relatório gravado é considerado **incompleto**.

---

**Épico:** E2 (geração) / E3 (orquestração) · **Skill:** rag-engineer, python-engineer, test-engineer ·
**Prioridade:** P0 · **Tamanho:** M · **ADRs:** ADR-003 (regimes), ADR-005 (cliente OpenAI-compatible),
ADR-008 (config declarativa), **ADR-015 (novo)** · **Camadas:** infrastructure + domain (aditivo) + config + tests

**Diagnóstico (as-built confirmado contra o código):**
- `infrastructure/adapters/vllm_generator.py` → `_default_prompt_fn` monta
  `"Contexts:\n- {text}...\n\nQuestion: {question}\n\nAnswer:"` e envia
  `messages=[{"role":"user",...}]` — **uma única mensagem `user`, SEM `system`**; a saída é
  `choice.message.content` **cru** (sem strip de `<think>`).
- `infrastructure/prompts/registry.py` → **não há** render de geração (só `render_biomed_rubric`).
- `infrastructure/adapters/qdrant_retriever.py` → `Chunk(id=str(p.id), text=payload.get("text",""), ...)`
  **descarta o `source` (PMID)** do payload.
- **Referência de produção (replicar verbatim):** `prompt_runner/interfaces/system_prompt.txt`
  (mensagem `system`); wrapper `user` do `orchestrator_service.py::_build_prompt_with_context`
  (`"Context information is below.\n---------------------\n{context}\n---------------------\nGiven the
  context information and not prior knowledge, answer the query.\nQuery: {question}"`); contexto
  `"[PMID:{source}] {text}"` unido por `\n\n` (`vector_database_logic_w_docs.py`); pós-processamento
  `re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL)`.

> **Nota (fora do escopo desta tarefa, mas relacionada):** a fábrica de geradores no wiring infere o
> nome do modelo pela porta; produção usa `GET /models`. O alinhamento (usar `served_model_id` da
> sonda) segue como item próprio do smoke-run external — **não** entra aqui.

### Prompt A — execução (Claude Code)

~~~text
CONTEXTO: Subsistema InteligenciÔmica Eval. Skills: rag-engineer, python-engineer, test-engineer.
Padrão python-clean-architecture (infra→domain; Pydantic v2; mypy --strict; docstrings Google).
ADR-003 (gerador batch_invariant=False), ADR-005 (cliente OpenAI-compatible), ADR-008 (config;
segredos por env), ADR-015 (NOVO — esta tarefa). Objetivo: tornar o gerador FIEL ao prompt de
produção e o prompt um FATOR SELECIONÁVEL por rodada (D1). Veículo de uso: Experimento B.

TAREFA: TAREFA-316.

1. ADR-015 (docs/adr/ADR-015-prompt-geracao-versionado.md):
   Registrar a decisão: prompt de geração = bundle versionado {system, user} selecionável no YAML da
   rodada; default replica produção verbatim; contexto formatado com PMID; strip de <think>;
   `prompt_version` (schema §5.3, coluna "versão do template RAG") passa a gravar a versão do bundle
   de GERAÇÃO selecionado. Status: Aceito. Referenciar ADR-003/005/008.

2. BUNDLES DE PROMPT VERSIONADOS (novos ativos em infrastructure/prompts/rag/):
   Estrutura por versão (discoverable por listagem de diretório):
     infrastructure/prompts/rag/<version>/system.txt   # estático, sem variáveis Jinja
     infrastructure/prompts/rag/<version>/user.j2       # variáveis {{ context }} e {{ question }}
   Criar o bundle default `v1_production`:
     - system.txt = CÓPIA VERBATIM de prompt_runner/interfaces/system_prompt.txt (produção).
     - user.j2 = wrapper VERBATIM de _build_prompt_with_context:
         Context information is below.
         ---------------------
         {{ context }}
         ---------------------
         Given the context information and not prior knowledge, answer the query.
         Query: {{ question }}
   Garantir que `infrastructure/prompts/rag/**` seja empacotado no wheel (package data /
   PackageLoader). NÃO colocar segredos nesses arquivos.

3. PromptRegistry (infrastructure/prompts/registry.py) — novo método:
     render_rag_generation(*, version: str, question: str, contexts: Sequence[Chunk]) -> tuple[str, str]
   - Carrega `rag/<version>/system.txt` (texto puro) e `rag/<version>/user.j2` (Jinja).
   - Monta o contexto: "\n\n".join(f"[PMID:{c.source}] {c.text}" for c in contexts)
     (PMID SEM espaço — replica produção; se `c.source` vazio, usar "N/A").
   - Renderiza user.j2 com {context, question}. Retorna (system_content, user_content).
   - Versão ausente → erro claro (ValueError/ConfigValidationError) listando as versões disponíveis.
   - Expor utilitário para LISTAR versões disponíveis (para validação no dry-run).
   - `render_biomed_rubric` permanece inalterado.

4. Chunk (domain/ports.py) — extensão ADITIVA:
   Adicionar campo `source: str = ""` (PMID), default vazio (não quebra chamadas existentes).
   `id` continua sendo o ponto do Qdrant (retrieval integrity). retrieved_chunk_ids permanece em
   IDs de ponto NESTA tarefa; o uso de PMID como id (Rodada 2 gold-match) fica anotado como item
   futuro — NÃO resolver aqui.

5. QdrantRetrieverAdapter (infrastructure/adapters/qdrant_retriever.py):
   Preencher `Chunk.source = str((p.payload or {}).get("source", ""))` ao montar cada chunk.
   `text` e `id` inalterados. Log inalterado.

6. VLLMGeneratorAdapter (infrastructure/adapters/vllm_generator.py):
   - Receber um renderer/bundle: trocar o `prompt_fn` atual (que devolve uma string única) por um
     `render_fn: Callable[[str, Sequence[Chunk]], tuple[str, str]]` que devolve (system, user).
     Default: usar PromptRegistry.render_rag_generation com a versão injetada. Manter compat de
     teste por injeção.
   - generate(): enviar DUAS mensagens:
       messages=[{"role":"system","content":system}, {"role":"user","content":user}]
     mantendo temperature/seed via extra_body como hoje; batch_invariant=False (ADR-003).
   - Pós-processar a saída: text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
     ANTES de montar GenerationOutput.
   - Logs: NÃO logar system/user crus (apenas tamanhos/contagem de chunks); manter política de
     observabilidade da 314.

7. RoundConfig (infrastructure/config/schema.py):
   Adicionar `generation_prompt_version: str = "v1_production"`. Validar no carregamento que a
   versão existe (cross-check com as versões disponíveis no PromptRegistry) — senão
   ConfigValidationError citando as versões disponíveis. Documentar no docstring.

8. Wiring (infrastructure/wiring.py) + proveniência:
   - Construir o VLLMGeneratorAdapter com a versão `config.generation_prompt_version`.
   - Propagar `generation_prompt_version` para a proveniência: a coluna §5.3 `prompt_version`
     passa a gravar ESSA versão (hoje vinha do git-describe do registry e não correspondia a
     template de geração real). Ajustar provenance.py/_ExperimentConfig conforme o ponto onde
     `prompt_version` é preenchido, mantendo coerência com o schema §5.3.

9. config/experiment_round1.yaml:
   Adicionar `generation_prompt_version: v1_production` com comentário explicando que é o bundle
   fiel à produção e que novas redações entram como novas versões em infrastructure/prompts/rag/.

ENTREGÁVEL:
- docs/adr/ADR-015-prompt-geracao-versionado.md
- src/inteligenciomica_eval/infrastructure/prompts/rag/v1_production/system.txt
- src/inteligenciomica_eval/infrastructure/prompts/rag/v1_production/user.j2
- Atualização de src/inteligenciomica_eval/infrastructure/prompts/registry.py (render_rag_generation + lista de versões)
- Atualização de src/inteligenciomica_eval/domain/ports.py (Chunk.source aditivo)
- Atualização de src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py (preenche source)
- Atualização de src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py (system+user; strip <think>)
- Atualização de src/inteligenciomica_eval/infrastructure/config/schema.py (generation_prompt_version)
- Atualização de src/inteligenciomica_eval/infrastructure/wiring.py + provenance.py (proveniência do prompt)
- config/experiment_round1.yaml (campo novo + comentário)
- Atualização de pyproject.toml/packaging se necessário (incluir prompts/rag/** como package data)
- tests/unit/... e tests/integration/... (ver abaixo)
- docs/dev-log/M3_TAREFA-316_A_<slug>.md (relatório de execução GRAVADO)

TESTES (obrigatórios):
- Renderer: dado um bundle de teste e chunks com source, render_rag_generation devolve (system,user)
  com o contexto em "[PMID:<source>] <text>" unido por "\n\n"; versão inexistente levanta erro.
- Gerador: capturar as `messages` enviadas (via mock do client) e asserir que há EXATAMENTE duas —
  system (== conteúdo do bundle) e user (== wrapper renderizado); asserir strip de <think> na saída.
- Fidelidade de referência: comparar a `messages` gerada para um caso conhecido contra um arquivo de
  referência derivado de logs_prompt/messages_*.json da produção (incluir o fixture no repo).
- Seleção por rodada: trocar generation_prompt_version muda o bundle usado e o `prompt_version`
  gravado na linha; default = v1_production.
- Retriever: Chunk.source é preenchido a partir de payload["source"]; ausência → "".
- Dry-run: valida generation_prompt_version (existente passa; inexistente falha com mensagem clara).

RESTRIÇÕES (DoD §14.2):
- from __future__ import annotations; Pydantic v2; type hints; docstrings Google; mypy --strict.
- infrastructure → domain (nunca o contrário); import-linter verde; Chunk.source é aditivo e não
  introduz import de infra no domínio.
- Nenhum segredo nos bundles; nenhum system/user cru em log (política da 314).
- NÃO alterar a assinatura pública de GeneratorPort.generate (question, contexts, seed, temperature).
- NÃO tocar nos adapters do JUIZ (rubrica permanece como está) nem no pipeline A (reranker/encoder —
  item separado, fora do escopo).
- Cobertura ≥ 85%; ruff limpo.
~~~

### Prompt B — verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer + security-auditor. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-316 + ADR-015 + arquivos de referência de produção citados
(system_prompt.txt, _build_prompt_with_context, formato de contexto com PMID, strip de <think>) +
skill python-clean-architecture.

VERIFIQUE, item a item, citando arquivo:linha:
1. ADR-015 presente, status Aceito, descreve bundle versionado {system,user} selecionável, contexto
   com PMID, strip <think>, e que `prompt_version` grava a versão do bundle de GERAÇÃO?
2. Bundle v1_production: system.txt é CÓPIA VERBATIM do system_prompt.txt de produção (sem
   reescrita)? user.j2 reproduz o wrapper de _build_prompt_with_context com {{context}}/{{question}}?
   Bundles empacotados no wheel (PackageLoader/package data)?
3. render_rag_generation: monta contexto "[PMID:{source}] {text}" (SEM espaço) unido por "\n\n";
   source vazio → "N/A"; versão inexistente levanta erro listando disponíveis; render_biomed_rubric
   intacto?
4. Chunk.source: campo aditivo com default ""; domínio NÃO importa infraestrutura (import-linter)?
5. QdrantRetrieverAdapter preenche source de payload["source"]; id continua o ponto do Qdrant?
6. VLLMGeneratorAdapter envia EXATAMENTE messages=[system,user] (não mensagem única); strip de
   <think> (DOTALL) aplicado ANTES de GenerationOutput; batch_invariant=False; system/user NÃO
   logados crus?
7. RoundConfig.generation_prompt_version (default v1_production) validado contra versões disponíveis
   no carregamento (ConfigValidationError com lista)?
8. Wiring constrói o gerador com a versão da config; proveniência grava `prompt_version` = versão do
   bundle selecionado (coerente com schema §5.3); experiment_round1.yaml traz o campo + comentário?
9. Testes cobrem: estrutura system+user, strip <think>, fidelidade contra fixture de produção,
   seleção por rodada altera bundle e prompt_version gravado, retriever preenche source, dry-run
   valida a versão? Cobertura ≥85%?
10. Assinatura de GeneratorPort.generate inalterada; adapters do juiz e pipeline A (reranker) NÃO
    tocados; sem segredo nos bundles; DoD §14.2?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Confirme execução de pytest (unit + integração), mypy --strict, ruff e lint-imports, com saídas coladas.

> Ao final, GRAVE o relatório de auditoria em docs/dev-log/M3_TAREFA-316_B_<slug>.md (não apenas no
> chat) e inclua-o no PR.
~~~

---

**Sequência geral atualizada:** 313✔ → 314✔ → 315 → 607 → **316 (esta)**. Após 316, uma nota de
doc-sync pode consolidar ADR-015 na narrativa da arquitetura (similar ao papel do 607). Itens
correlatos que permanecem em aberto e **fora** desta tarefa: (a) fix do nome do modelo por porta no
wiring (alinhar a `served_model_id` — smoke-run external); (b) fidelidade do **pipeline A** (cross-
encoder rerank + query-encoder externos) para realismo end-to-end do Experimento A.
