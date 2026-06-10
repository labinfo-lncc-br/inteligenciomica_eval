# M3_TAREFA-316_C — Code Review Pós-Merge (Claude Code)

**Data**: 2026-06-10
**Milestone**: M3 — Orquestração das 4 GPUs
**Épico**: E3
**Skill**: code-reviewer (Claude Code)
**Prioridade / Tamanho**: P2 / M
**Revisor**: Claude Code (Fable 5) — revisão independente pós-merge, distinta das auditorias Codex (partes B/B2)

---

## Objetivo

Revisão estruturada de código da TAREFA-316 (fidelidade do prompt de geração + bundle
versionado, ADR-015), realizada **após** o merge na `main` e após as auditorias Codex
B/B2 (PASS). Identificar erros, inconsistências e melhorias residuais não cobertas
pelos ciclos anteriores.

## Escopo Avaliado

- **Commits**: `09455c0` (feat — implementação principal) + `72d2dd1` (fix A2 —
  regressões de seleção por rodada + dry-run + bug `build_fake_container`).
- **Justificativa do escopo**: não há diff de código pendente no working tree — apenas
  arquivos de documentação untracked (`docs/dev-log/M3_TAREFA-313_B_contrato-benchmark.md`,
  `docs/prompts_m5_tarefa_315_acuracia_documental.md`, `system_prompt.txt`). A TAREFA-316
  é a última mudança substantiva de `src/` na `main`.
- **Arquivos lidos** (testes primeiro, conforme workflow da skill):
  - `tests/unit/infrastructure/prompts/test_prompt_registry.py`
  - `tests/unit/infrastructure/adapters/test_vllm_generator.py`
  - `src/inteligenciomica_eval/infrastructure/prompts/registry.py`
  - `src/inteligenciomica_eval/infrastructure/adapters/vllm_generator.py`
  - `src/inteligenciomica_eval/infrastructure/config/schema.py`
  - `src/inteligenciomica_eval/infrastructure/wiring.py`
  - `src/inteligenciomica_eval/domain/ports.py` (dataclass `Chunk`)
  - `src/inteligenciomica_eval/infrastructure/adapters/qdrant_retriever.py`
  - `src/inteligenciomica_eval/application/use_cases/run_experiment.py` (uso do
    `generator_factory`)
  - `src/inteligenciomica_eval/infrastructure/prompts/rag/v1_production/{system.txt,user.j2}`
  - `src/inteligenciomica_eval/infrastructure/config/settings.py` (defaults sentinela)

## Verificações Empíricas Realizadas

1. **Fidelidade do bundle**: `diff` entre `system_prompt.txt` (raiz do repo, produção)
   e `src/inteligenciomica_eval/infrastructure/prompts/rag/v1_production/system.txt`
   → **byte-idênticos** ("IDENTICOS").
2. **Comportamento do sentinela `"<not set>"`**: executado
   `openai.AsyncOpenAI(base_url='<not set>', api_key='EMPTY', max_retries=0)` via
   `uv run python` → **constrói sem erro**, URL-encodando para `%3Cnot%20set%3E/`.
   Conclusão: a falha com endpoint não configurado **não** ocorre na construção do
   adapter; fica adiada para a primeira chamada de rede em runtime.
3. **Substituição do generator por onda**: confirmado em `run_experiment.py:318` que
   `self._gen_pass_uc._generator = self._generator_factory(...)` substitui o generator
   placeholder a cada onda — o generator construído em `build_container:688` com
   `settings.VLLM_GENERATOR_URL` é apenas placeholder inicial.
4. **Defaults de `RuntimeSettings`**: confirmado em `settings.py:27-29` que
   `VLLM_GENERATOR_URL`, `VLLM_JUDGE_URL` e `QDRANT_URL` têm default `"<not set>"`.

---

## Achados

### ⚠️ Importantes (4)

#### ⚠️ I-1 [Correção/Config] `wiring.py:453-454` + `613-617` — modo `external` pula a validação de `QDRANT_URL`

`_validate_endpoints(settings)` só é executada quando `config.server_mode == "managed"`:

```python
if config.server_mode == "managed":
    _validate_endpoints(settings)
```

Porém o `QdrantRetrieverAdapter` é construído **incondicionalmente** a partir de
`settings.QDRANT_URL` (linhas 613-617):

```python
retriever = QdrantRetrieverAdapter(
    url=settings.QDRANT_URL,
    collection_map=collection_map,
    top_k=config.retrieval.top_k,
)
```

**Impacto**: em modo `external` com a env `QDRANT_URL` ausente, o retriever nasce com
URL `"<not set>"` e a falha só aparece na **primeira retrieval** — já dentro do run,
após o build do container ter "passado". Viola a filosofia fail-fast (§14.2): a
justificativa para pular `_validate_endpoints` no modo external é que
`VLLM_GENERATOR_URL`/`VLLM_JUDGE_URL` vêm do `endpoint_env` por modelo — mas
`QDRANT_URL` é necessária em **ambos** os modos e não tem origem alternativa.

**Correção sugerida**: validar `QDRANT_URL` em ambos os modos; apenas
`VLLM_GENERATOR_URL`/`VLLM_JUDGE_URL` são dispensáveis no external. Por exemplo,
separar `_REQUIRED_ENDPOINTS` em dois conjuntos (sempre-obrigatórias vs.
managed-only) e validar o primeiro incondicionalmente.

#### ⚠️ I-2 [Correção/Config] `wiring.py:621-625` — `judge_url` pode resolver para o sentinela sem fail-fast

```python
judge_url: str = (
    _judge_url_probe
    if config.server_mode == "external" and _judge_url_probe
    else settings.VLLM_JUDGE_URL
)
```

Em modo `external`, se o modelo juiz **não** estiver no `endpoint_map` do registry
(`_judge_url_probe = None`) e `VLLM_JUDGE_URL` não estiver definida no ambiente,
`judge_url` resolve para `"<not set>"`.

**Verificação empírica**: `AsyncOpenAI(base_url="<not set>")` **aceita sem erro**
(URL-encoda para `%3Cnot%20set%3E/`). Portanto `PrometheusJudgeAdapter` e
`RAGASLayer1Adapter` são construídos "com sucesso" apontando para uma URL inválida.

**Impacto**: o erro só estoura na **passada do juiz** (Passada 3) — depois de toda a
geração ter sido concluída, ou seja, depois da parte mais cara do experimento em
horas de GPU. Esse é exatamente o cenário de produção (modo external = clusters
LNCC), o que agrava a severidade.

**Correção sugerida**: levantar `ConfigValidationError` imediatamente em
`build_container` se `judge_url` resolver para `"<not set>"` (ou string vazia).

#### ⚠️ I-3 [Robustez] `wiring.py:239` — parsing de porta frágil na `_VLLMGeneratorFactory`

```python
try:
    port = int(url.split(":")[2].split("/")[0])
    model = self._port_to_model.get(port, "model")
except (IndexError, ValueError):
    model = "model"
```

Problemas:

1. URL sem porta explícita (`"http://host/v1"`) → `url.split(":")` produz apenas 2
   partes → `IndexError` → fallback silencioso `model="model"`.
2. URLs IPv6 (`"http://[::1]:8000/v1"`) quebram o split por `:`.
3. O fallback `"model"` é enviado ao vLLM como **nome de modelo** na chamada
   `chat.completions.create(model=...)` e falharia em runtime com erro confuso
   ("model 'model' not found"), longe da causa raiz.

**Mitigação existente**: `run_experiment.py:318` substitui o generator por onda com
URLs construídas internamente (formato controlado `http://host:PORT/v1`), então o
caminho feliz não passa pelo fallback. Mas o placeholder inicial
(`build_container:688`) e o modo external (URLs arbitrárias de túneis SSH) passam
por este parsing.

**Correção sugerida**: usar `urllib.parse.urlsplit(url).port` (devolve `None` sem
porta, lida com IPv6) + log `WARNING` quando o fallback `"model"` for usado, para o
caso ser auditável.

#### ⚠️ I-4 [Correção/Edge] `vllm_generator.py:28,171` — `<think>` não-fechado não é removido

```python
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
...
text = _THINK_RE.sub("", raw_text).strip()
```

A regex exige o par completo `<think>…</think>`. Cenário de borda real: geração
**truncada por `max_tokens`** com o bloco de raciocínio ainda aberto — o modelo
emite `<think>` e é cortado antes do `</think>`. Nesse caso, **todo o conteúdo de
raciocínio permanece no texto avaliado**, contaminando BERTScore, ROUGE-L, as
métricas RAGAS e o julgamento da rubrica.

**Ressalva de fidelidade**: se o `orchestrator_service.py` de produção tem exatamente
o mesmo comportamento (a TAREFA-316 replica produção verbatim), a fidelidade está
preservada e mudar o strip aqui criaria divergência. A recomendação mínima é
**detectar e logar WARNING** quando um `<think>` sem fechamento for encontrado no
texto final (ex.: `if "<think>" in text: _log.warning("unclosed_think_tag", ...)`),
para que runs afetados sejam auditáveis sem alterar o comportamento de strip.

### 💡 Sugestões (10)

#### 💡 S-1 [Docs] `registry.py:26-35` — docstring da classe desatualizada (contradiz ADR-015 §D3)

A docstring do **módulo** (linhas 1-8) já foi atualizada: "A partir de TAREFA-316,
`prompt_version` grava `generation_prompt_version` (bundle RAG), não o `git describe`
do registry (ADR-015)". Porém a docstring da **classe** `PromptRegistry` (linhas
26-35) ainda afirma: "A versão capturada via `git describe` identifica o exato
conjunto de templates usado em cada rodada de avaliação" — que é exatamente o
comportamento anterior, revogado pelo ADR-015 §D3. Inconsistência interna no mesmo
arquivo. Atualizar a docstring da classe para refletir que o `git describe` hoje
serve apenas à rubrica (`prompt_version` property), não à proveniência do Parquet.

#### 💡 S-2 [Robustez] `registry.py:60-64` — `subprocess.run(["git", "describe"])` sem `cwd` e sem `timeout`

```python
result = subprocess.run(
    ["git", "describe", "--tags", "--dirty"],
    capture_output=True,
    text=True,
)
```

1. **Sem `cwd`**: o comando roda no diretório corrente do processo. Se o CLI
   `ielm-eval` for executado de dentro de **outro** repositório git, captura a versão
   do repositório errado — proveniência incorreta silenciosa.
2. **Sem `timeout`**: em filesystems de rede lentos (cenário LNCC), um `git describe`
   pendurado bloqueia a construção do registry indefinidamente.

**Sugestão**: `cwd=Path(__file__).parent` (ancora no pacote instalado; em instalação
via wheel sem `.git`, o returncode ≠ 0 já cai nos fallbacks existentes) e
`timeout=5` (com `subprocess.TimeoutExpired` adicionado ao `except`).

#### 💡 S-3 [Performance] `registry.py:137-152` — trabalho repetido a cada `render_rag_generation`

Duas operações executam a **cada chamada** (uma vez por pergunta × seed × LLM no
loop quente da passada de geração):

1. `self.list_rag_versions()` — varre `self._env.list_templates()` (scan do diretório
   do pacote) só para validar a versão.
2. `self._env.loader.get_source(...)` para `system.txt` — relê o arquivo do disco
   (o env Jinja cacheia `user.j2` via `get_template`, mas `get_source` direto não
   passa pelo cache de templates).

**Sugestão**: cachear ambos — ex.: `functools.lru_cache` num método privado
`_load_system(version)` e cache da lista de versões no `__init__` (o registry é
"imutável após construção" por contrato declarado na própria docstring). Impacto
individual pequeno (I/O local), mas é trabalho repetido evitável em loop quente.

#### 💡 S-4 [Legibilidade] `registry.py:85-91` — cabeçalho de seção morto

```python
# ------------------------------------------------------------------
# Renderização
# ------------------------------------------------------------------

# ------------------------------------------------------------------
# Bundles RAG versionados (ADR-015)
# ------------------------------------------------------------------
```

O cabeçalho "Renderização" ficou vazio (resíduo da refatoração da TAREFA-316),
imediatamente seguido pelo cabeçalho "Bundles RAG". Remover o bloco morto.

#### 💡 S-5 [Arquitetura] `wiring.py:533` — acesso a atributo privado do adapter

```python
_ext_map: dict[str, str] = getattr(_ext_mgr, "_endpoint_map", {})
```

O wiring acessa `_endpoint_map` (privado) do `ExternalVLLMServerManager` via
`getattr` com default silencioso. Acoplamento frágil: uma renomeação interna do
adapter quebraria o wiring sem erro de tipo (o `getattr` devolveria `{}` e o modo
external perderia todas as URLs silenciosamente). **Sugestão**: expor propriedade
pública `endpoint_map` no adapter e acessá-la diretamente.

#### 💡 S-6 [Arquitetura] `run_experiment.py:318` — mutação de atributo privado entre use cases

```python
self._gen_pass_uc._generator = self._generator_factory(...)
```

O orquestrador muta `_generator` (privado) do `RunGenerationPassUseCase` a cada onda.
O padrão está documentado na docstring do módulo, mas um setter público explícito
(ex.: `gen_pass_uc.set_generator(generator)`) tornaria o contrato visível na API do
use case e detectável por type checker. Mesma família do S-5.

#### 💡 S-7 [Recursos] `wiring.py:802` — `tempfile.mkdtemp()` nunca é limpo

```python
data_dir = Path(tempfile.mkdtemp())
```

Em `build_fake_container`, cada dry-run cria um diretório temporário que nunca é
removido — dry-runs sucessivos acumulam lixo em `/tmp`. **Sugestão**: usar prefixo
identificável (`tempfile.mkdtemp(prefix="ielm-dryrun-")`) no mínimo; idealmente
registrar cleanup (ex.: `atexit` ou documentar a responsabilidade no chamador).

#### 💡 S-8 [Simplificação] `wiring.py:404-408` — `loop.close()` fora de `finally`

```python
try:
    loop = _asyncio.new_event_loop()
    result = loop.run_until_complete(_probes())
    loop.close()
    return result
except Exception as exc:
    ...
```

Se `_probes()` levantar, o `except` captura mas o loop criado **não é fechado**
(vaza). `asyncio.run(_probes())` faz exatamente o mesmo (novo loop + close
garantido em `finally`) com menos código. Nota: ambos falham igualmente se já houver
um event loop rodando no thread — não há perda de comportamento.

#### 💡 S-9 [Observação] probes de proveniência são inócuos em modo `managed`

Em `managed`, `_run_endpoint_probes` executa durante `build_container` — **antes**
de qualquer servidor vLLM subir (os servidores sobem por onda, dentro do
`RunExperimentUseCase`). O resultado típico será `healthy=False`, `served_model_id=""`
e `vllm_version="unknown"` para todos os geradores. O comportamento best-effort está
documentado ("falha silenciosa"), mas na prática a proveniência de endpoint registrada
em managed é quase sempre vazia **por construção**, não por indisponibilidade real.
**Sugestão**: pular os probes de geradores em managed (economiza timeouts de HTTP no
startup) ou movê-los para pós-startup de cada onda, onde produziriam dados reais.

#### 💡 S-10 [Higiene de repo] `system_prompt.txt` untracked na raiz — duplicata sem dono

O arquivo `system_prompt.txt` (raiz do repo, untracked) é agora duplicata
byte-a-byte do bundle `infrastructure/prompts/rag/v1_production/system.txt`
(verificado por `diff` nesta revisão). Duplicata untracked convida a drift: uma
edição futura em um dos lados quebraria a fidelidade silenciosamente. **Sugestão**:
ou remover o arquivo da raiz (o bundle é a fonte canônica empacotada), ou
versioná-lo com uma nota apontando o bundle como fonte canônica — e, em qualquer
caso, decidir explicitamente em vez de deixá-lo untracked.

### ✅ Pontos fortes

- **Fidelidade comprovada**: `system.txt` do bundle é byte-idêntico ao
  `system_prompt.txt` de produção (verificado por `diff` nesta revisão); o teste
  `test_fidelity_against_production_fixture` ancora a fidelidade contra fixture
  versionada (`tests/fixtures/production_messages_fixture.json`).
- **Padrão de injeção consistente**: `render_fn`, `_retry_stop`, `_retry_wait`
  seguem a convenção `_` do projeto; testes do generator no nível certo de
  abstração (AsyncMock do SDK, CLAUDE.md §11), cobrindo mensagens system/user,
  strip de `<think>` inline e multiline, propagação da versão pela factory
  (`TestVLLMGeneratorFactoryVersionPropagation`) e rejeição de versão inválida no
  dry-run (`TestRunDryRunPromptVersion`).
- **Fail-fast da versão de bundle**: `load_round_config` valida
  `generation_prompt_version` contra `list_rag_versions()` com mensagem de erro
  acionável listando as versões disponíveis.
- **`max_retries=0` no `AsyncOpenAI`**: evita retry duplo tenacity × SDK
  (decisão documentada no CLAUDE.md §11).
- **`Chunk.source` aditivo**: default `""` não quebra chamadas existentes; o
  `QdrantRetrieverAdapter` preenche defensivamente de `(p.payload or {}).get("source", "")`.
- **Correção proativa no `72d2dd1`**: o bug de proveniência do dry-run
  (`prompt_version=""` no `build_fake_container`) foi detectado e corrigido no
  próprio ciclo A2, com testes de regressão.

---

## Sumário

| Categoria | Qtde | Itens |
|---|---|---|
| 🛑 Bloqueadores | 0 | — |
| ⚠️ Importantes | 4 | I-1 validação `QDRANT_URL` em external; I-2 `judge_url` sentinela sem fail-fast; I-3 parsing de porta frágil; I-4 `<think>` não-fechado |
| 💡 Sugestões | 10 | S-1 a S-10 |
| ✅ Elogios | 6 | fidelidade, injeção, fail-fast de versão, retry único, campo aditivo, fix proativo |

**Recomendação**: 💬 Comment only — o código já está na `main` com auditoria Codex
PASS (partes B/B2); nada aqui exige reverter. Os 4 itens importantes merecem
tickets: I-1 e I-2 são lacunas reais de fail-fast no modo `external` (o cenário
LNCC, justamente o de produção) e a falha resultante apareceria tarde e cara, no
meio de um run com GPU.

**Próximo passo sugerido**: abrir uma tarefa curta de hardening do modo external
(validação de `QDRANT_URL` + `judge_url` no `build_container` — itens I-1 e I-2) —
é o item com maior razão impacto/esforço. I-3 e I-4 podem entrar na mesma tarefa ou
em follow-up de observabilidade.

## Observações para Próximas Tarefas

- Esta revisão **não substitui** o protocolo de auditoria Codex (partes B) — é uma
  revisão complementar pós-merge feita pelo Claude Code a pedido do desenvolvedor.
- Os achados I-1/I-2 afetam diretamente a TAREFA-311 (modo external) e devem ser
  considerados antes do primeiro run real em cluster LNCC.
- O item S-10 (`system_prompt.txt` na raiz) deve ser resolvido antes do próximo
  commit de docs, para não deixar a duplicata acumulando drift.
