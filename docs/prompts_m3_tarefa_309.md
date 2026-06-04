# Prompt M3 — TAREFA-309 (Claude Code ↔ ChatGPT Codex)

**Milestone:** M3 — Rodada 1 completa + orquestração das 4 GPUs (penúltima tarefa)
**Tarefa:** TAREFA-309 — DI wiring real + CLI `run` completo + `BenchmarkLoader` (`config/questions.yaml`)
**Documentos de referência:**
- `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1, §§ 2.2 RF1/RF4/P4, 4, 5.1, 5.3, 8, 14.6)
- `visao_alto_nivel_validacao_inteligenciomica.md` (v1.0, §§ 2.3, 3.1, 11)
- `prompts_m5_tarefas_501_507_corrigido.md` — **fonte canônica** do mecanismo de perguntas
  (`config/questions.yaml`, `load_question_ids(...)`, RF4) que esta tarefa concretiza.
**Continuação de:** `prompts_m3_tarefas_301_310.md` — TAREFA-301…308 mergeadas e verdes.
**Formato:** **Prompt A (implementação — Claude Code)** + **Prompt B (verificação — ChatGPT Codex)**.
**Épico coberto:** E3 (orquestração GH200).

> **Pressupõe** que **M0–M2 (TAREFA-001..028) e M3 parcial (TAREFA-301..308)** estão
> mergeados e verdes: domínio puro, todos os adapters (M1), pipeline de métricas
> (Camadas 1–3, M1+M3), `VLLMServerManager` real (TAREFA-302), `WaveSchedulerService`
> (TAREFA-303), use cases de geração/métricas/juiz (TAREFA-304–307) e
> `AnnotationWorkflowUseCase` (TAREFA-308).
> **Pressupõe também** que o **M4 já foi mergeado** e que o `cli.py` já expõe os
> subcomandos `version`, `compute-metrics`, `analyze`, `report`, `annotate`, `status`,
> `show-config`, `run-round2` (auditoria M4) e que o **M6** adicionou `validate-judge`.
> **Esta tarefa NÃO pode regredir nenhum desses subcomandos** — apenas COMPLETA o `run`.
> **O M5 (Rodada 2 — funil OFAT) permanece adiado**, mas seu **mecanismo de perguntas é a
> referência canônica**: `config/questions.yaml` (RF4). 309 implementa o loader que o M5
> consumirá via `load_question_ids(round2a.questions)`.
> Convenções de M0–M3 continuam valendo (libs proibidas em `domain`/`application`;
> `import-linter`; DoD §14.2; `from __future__ import annotations` no topo de todo arquivo).

---

## Protocolo de desenvolvimento em pares (Claude Code ↔ ChatGPT Codex)

Estamos desenvolvendo o **inteligenciômica-eval**, executando prompts organizados por
marcos (milestones). Cada marco reúne vários prompts, e **cada prompt é sempre dividido
em duas partes**: a **Parte A — implementação**, executada pelo **Claude Code**, e a
**Parte B — revisão e auditoria**, executada pelo **ChatGPT Codex**.

**Toda execução gera obrigatoriamente um relatório** do que foi feito e dos resultados
obtidos. O processo é **iterativo**: implementação (A) → revisão/auditoria (B) →
correção e recodificação (A) → nova revisão/auditoria (B), repetindo até que **Claude
Code e ChatGPT Codex concordem** que não há mais falhas e a tarefa seja
**aprovada (PASS) por ambos**.

O avanço para a próxima tarefa **nunca é automático**: ocorre somente com a **minha
autorização explícita** e após o `add` / `commit` / `push` no GitHub.

O **`CLAUDE.md`** contém a padronização de como escrever os relatórios e gravá-los em
`docs/dev-log/`. O `CLAUDE.md` **deve ser mantido atualizado** com os padrões e as
decisões que impactam a continuidade do desenvolvimento.

> **Início desta tarefa:** execute primeiro a **Parte A (Claude Code)** abaixo e produza
> o relatório de implementação. A **Parte B (ChatGPT Codex)** roda em seguida, a partir
> da resposta do desenvolvedor (relatório + diff do PR da Parte A). Itere A↔B até PASS.
> Só então (com minha autorização) passe para a TAREFA-310.

---

## Nota de operacionalização — decisões fixadas para 309

Decisões que Code e Codex precisam tratar como contrato. Foram **revisadas para alinhar
com o M5/RF4** (o esboço anterior divergia ao empacotar as perguntas na wheel).

### 1. Carregamento das perguntas RF1 (P4/RF4) — `config/questions.yaml`

**Decisão canônica (alinhada ao M5):** as perguntas vivem em **`config/questions.yaml`**,
versionado no repositório, e o **path é declarado no YAML de rodada** (campo `questions:`),
nunca empacotado na wheel nem lido de env var de valor. Motivação:

- **P4/RF4** exigem 13 perguntas + ground truth padronizadas e versionadas, com
  `question_id` estável (o M5 casa o `gold_chunks.jsonl` por esse `question_id`).
- O M5 já assume `questions: config/questions.yaml` no YAML de rodada e chama
  `load_question_ids(round2a.questions)`. 309 **implementa** esse loader; assim a mesma
  função serve M3 (Rodada 1) e M5 (Rodada 2) sem reescrita.
- **Multi-área:** cada área de conhecimento é um arquivo próprio
  (`config/questions_infecto.yaml`, `config/questions_onco.yaml`, …), selecionado pelo
  YAML de rodada correspondente. Zero re-release, zero env var. (Atende ao plano de
  rodar pares P&R de áreas diferentes.)

Concretização:

- **Schema da rodada** (`infrastructure/config/schema.py`): adicionar a `RoundConfig`
  o campo `questions: str = "config/questions.yaml"` (path relativo, validado como
  string não-vazia). Manter `model_registry_path` (TAREFA-301) inalterado. Documentar
  o campo no docstring do modelo.
- **Arquivo `config/questions.yaml`** — lista YAML de perguntas, uma por item:
  ```yaml
  # config/questions.yaml — benchmark RF1 (P4/RF4).
  # Área atual: infecciologia / resistência antimicrobiana.
  # TODO(P4): completar para 13 perguntas curadas antes da Rodada 1 de produção
  #           (responsabilidade do especialista biomédico). Hoje: 3 representativas.
  - question_id: amr-mecanismo-betalactamase-01
    text: "<enunciado em PT>"
    ground_truth: "<resposta de referência em PT>"
  - question_id: amr-carbapenemase-kpc-02
    text: "..."
    ground_truth: "..."
  - question_id: amr-colistina-resistencia-mcr1-03
    text: "..."
    ground_truth: "..."
  ```
  Conteúdo mínimo para o gate: **3 perguntas biomédicas** coerentes com o domínio e com
  `tests/fixtures/integration_question.json`. Os `question_id` em kebab-case, estáveis.
- **Loader** em `src/inteligenciomica_eval/infrastructure/repositories/questions.py`
  (mesma camada/pasta do `GoldChunkReaderAdapter` do M5, §8):
  - `load_questions(path: Path) -> list[Question]` — lê o YAML (lista de mappings),
    devolve `list[Question]` na ordem do arquivo.
  - `load_question_ids(path: Path) -> list[str]` — `[q.question_id for q in load_questions(path)]`
    (assinatura exigida pelo M5; já entregue aqui para fechar a dependência futura).
  - Validações: arquivo inexistente → `StorageError`; YAML que não seja uma lista
    → `StorageError`; lista vazia → `StorageError`; item sem `question_id`/`text`/
    `ground_truth`, ou com campo vazio → `StorageError` com **índice do item** e nome do
    arquivo na mensagem; `question_id` duplicado → `StorageError`.
  - `Question` construído como `Question(question_id=..., text=..., ground_truth=...)`
    (campos confirmados em M0/M1). Campos vazios também são barrados por
    `Question.__post_init__` — propagar como `StorageError`.
  - `path` é **obrigatório** (sem default empacotado): o wiring resolve `Path(config.questions)`.

### 2. `DIContainer` e `wiring.py` — regras de camada

- `infrastructure/wiring.py` é **extensão aprovada do blueprint §8** (registrar ADR inline
  no topo do arquivo, referenciando ADR-001; vale a "Nota §8" do `prompts_m3_tarefas_301_310.md`).
- `@dataclass(frozen=True) DIContainer` — **sem framework DI de terceiros** (ADR-001).
  Campos obrigatórios (todos tipados com o Protocol/Port correto, **sem imports de fakes**):
  ```
  retriever: RetrieverPort
  generator_factory: GeneratorFactory
  metric_suite: MetricSuitePort
  deterministic_metric: DeterministicMetricPort
  rubric_judge: RubricJudgePort
  server_manager: VLLMServerManagerPort
  wave_scheduler: WaveSchedulerService
  gen_pass_uc: RunGenerationPassUseCase
  metrics_pass_uc: RunMetricsPassUseCase
  judge_pass_uc: RunJudgePassUseCase
  experiment_uc: RunExperimentUseCase
  annotation_uc: AnnotationWorkflowUseCase
  writer: ResultWriterPort
  reader: ResultReaderPort
  agg_service: AggregationService
  rank_calc: RankScoreCalculator
  benchmark_loader: Callable[[], list[Question]]
  ```
  `benchmark_loader` é callable zero-arg: `functools.partial(load_questions, Path(config.questions))`.
- `build_container(config: RoundConfig, settings: <CLASSE REAL DE SETTINGS>) -> DIContainer`:
  instancia adapters **reais**. **NÃO inventar o nome da classe de settings** — usar a
  classe que TAREFA-010 de fato implementou em `infrastructure/config/settings.py`
  (ler o arquivo e confirmar antes de codar). Sem imports de fakes neste caminho.
- **Validação de endpoints obrigatórios:** seguir **o contrato real de `settings.py`**.
  Se a resolução de `VLLM_GENERATOR_URL`, `VLLM_JUDGE_URL` ou `QDRANT_URL` falhar/estiver
  ausente, levantar `ConfigValidationError` com o **nome da env var** faltante.
  **Confirmar primeiro** se o mecanismo é "ausência estoura na instanciação do
  pydantic-settings" ou "default sentinela" — e validar de acordo (não assumir a string
  literal `"<not set>"` sem confirmar que `settings.py` a usa).
- `build_fake_container(config: RoundConfig) -> DIContainer`: substitui adapters de rede
  pelos **fakes de TAREFA-011** (imports **lazy**, dentro da função — nunca no topo).
  `benchmark_loader` retorna as **2 primeiras** perguntas de `load_questions(Path(config.questions))`.
  Usado no `--dry-run` e nos testes unitários. **O `--dry-run` prova a fiação sem GPU/rede.**

### 3. CLI `ielm-eval run` completo — contrato de UX

- Assinatura: `ielm-eval run --config PATH --run-id ID [--phase A|B|both] [--dry-run] [--serial]`
  - `--run-id TEXT` **obrigatório na execução real** (identifica o run no Parquet; ignorado no dry-run).
  - `--phase [A|B|both]` (default `both`) — seleciona quais experimentos rodar.
  - `--serial` — mapeia para `allow_concurrent_models=False` no `WaveSchedulerService`
    (ADR-012, modo conservador: 1 modelo por onda; útil em 1 GPU ou depuração). Sem a
    flag → default ADR-012 (concorrente, ondas 3+2).
- **Preservar todos os subcomandos existentes** (`version`, `compute-metrics`, `analyze`,
  `report`, `annotate`, `status`, `show-config`, `run-round2`, `validate-judge`). Esta
  tarefa **só** completa o `run`; **não** recria o `cli.py` do zero. Os placeholders
  `analyze`/`report` que o 309 original previa **não existem mais** — foram substituídos
  pelos comandos reais do M4; **não reintroduzir placeholders**.
- **Rich Progress** com 3 barras (ondas concluídas/total; células geradas/total; células
  avaliadas/total) via `progress_callback` injetado no `RunExperimentUseCase.execute()`
  (TAREFA-307). **Nunca `print()`** em código de produção.
- **Stacktrace NUNCA no `stdout`** em erro → log structlog em `DEBUG`. Ao usuário: Rich
  Panel vermelho com mensagem amigável + exit code 1. `ServerStartTimeoutError` e
  `ConfigValidationError` tratados explicitamente.
- **SIGINT/SIGTERM:** `"⚠ Encerramento solicitado — aguardando onda atual..."` + seta a
  flag de graceful shutdown do `RunExperimentUseCase` (RNF7, TAREFA-307) + exit 130.
- **Sumário de sucesso:** tabela Rich com células geradas/avaliadas/puladas/falhas e
  top-3 configurações por `RankScore`. Se `report.failed_waves`: Panel amarelo listando-as.

### 4. Impacto no manual de operação (TAREFA-604, M6) — registrar como follow-up

Esta tarefa muda o contrato do `run` (passa a exigir `--run-id`) e materializa o
mecanismo de perguntas. O **`docs/operations_manual.md` (TAREFA-604)** precisará de
atualização (fora do escopo de código desta tarefa, mas **documentar no dev-log**):
Seção 5 (incluir `--run-id` no comando de execução; hoje aparece sem ele), nova
subseção sobre `config/questions.yaml` e troca por área de conhecimento, e menção ao
campo `questions:` no YAML de rodada. **Anotar isso na seção "Observações para Próximas
Tarefas" do relatório.**

---

## TAREFA-309 — DI wiring real + CLI `run` completo + `BenchmarkLoader`

**Épico:** E3 · **Skill:** python-engineer · **Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-302 (`VLLMServerManagerAdapter`), TAREFA-303 (`WaveSchedulerService`),
TAREFA-307 (`RunExperimentUseCase`), TAREFA-308 (`AnnotationWorkflowUseCase`),
TAREFA-010 (config/settings) · **ADRs:** ADR-001 (Clean Architecture), ADR-008 (config
declarativa), ADR-012 (ondas/GPU) · **RNF:** RNF7 (graceful shutdown) · **Camadas:**
`infrastructure/wiring`, `infrastructure/repositories`, `infrastructure/config`, `cli`

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §§8, 5.1, 5.3,
14.6 TAREFA-309 + ADR-001/008/012). Skills ativos: python-engineer, python-clean-architecture §1.
Padrão: CLI chama wiring; wiring instancia adapters reais; use cases recebem ports.
M0–M3 parcial (301–308), M4 e M6 já mergeados. Esta tarefa fecha o wiring e completa o
comando `ielm-eval run`, conectando os adapters reais ao `RunExperimentUseCase` e
materializando o carregamento das perguntas a partir de `config/questions.yaml`.
VER "Nota de operacionalização — decisões fixadas para 309", itens 1–4.

LEIA ANTES DE CODAR: `infrastructure/config/settings.py` (TAREFA-010) para confirmar o
NOME REAL da classe de settings e o contrato de resolução de endpoints (ausência vs
sentinela). NÃO inventar nomes. Confirmar também a entidade `Question`
(campos question_id/text/ground_truth) e a assinatura de `RunExperimentUseCase.execute`.

TAREFA: TAREFA-309 — implementar:
  (a) loader `infrastructure/repositories/questions.py` (`load_questions`, `load_question_ids`)
      + arquivo `config/questions.yaml` com 3 perguntas biomédicas;
  (b) campo `questions: str` em `RoundConfig` (schema.py);
  (c) `infrastructure/wiring.py` com `DIContainer`, `build_container`, `build_fake_container`;
  (d) comando `ielm-eval run` completo (execução real), PRESERVANDO os demais subcomandos.

ESPECIFICAÇÃO:

1. ARQUIVO DE PERGUNTAS — `config/questions.yaml`
   Lista YAML; cada item: {question_id (kebab-case), text (PT), ground_truth (PT)}.
   3 perguntas de infecciologia/resistência antimicrobiana, coerentes com o domínio e
   com `tests/fixtures/integration_question.json`. Comentário no topo com o TODO(P4)
   de completar para 13. Arquivo versionado em `config/` (NÃO empacotado na wheel).

2. LOADER — `src/inteligenciomica_eval/infrastructure/repositories/questions.py`
   ```python
   from __future__ import annotations
   from pathlib import Path
   from inteligenciomica_eval.domain.entities import Question
   from inteligenciomica_eval.domain.errors import StorageError

   def load_questions(path: Path) -> list[Question]:
       """Carrega perguntas do benchmark (RF4) de um YAML.

       Args:
           path: caminho do YAML (lista de {question_id, text, ground_truth}).

       Returns:
           Lista ordenada de :class:`Question` (na ordem do arquivo).

       Raises:
           StorageError: arquivo ausente, YAML não-lista, lista vazia, item
               malformado/campo vazio, ou question_id duplicado.
       """

   def load_question_ids(path: Path) -> list[str]:
       """IDs estáveis do benchmark (consumido pelo M5)."""
   ```
   - Ler via `yaml.safe_load(path.read_text(encoding="utf-8"))`.
   - Top-level não-lista → StorageError. Lista vazia → StorageError.
   - Item malformado / campo vazio → StorageError com índice (0-based) + nome do arquivo.
   - question_id duplicado → StorageError listando o id repetido.
   - `__init__.py` da pasta exporta `load_questions` e `load_question_ids`.

3. SCHEMA — `infrastructure/config/schema.py`
   Adicionar a `RoundConfig`: `questions: str = "config/questions.yaml"`
   (path relativo; validar string não-vazia). Docstring explica o campo e que cada
   área de conhecimento usa seu próprio arquivo, referenciado pelo YAML de rodada.
   NÃO embutir as perguntas no YAML de rodada — apenas o path.

4. WIRING — `src/inteligenciomica_eval/infrastructure/wiring.py`
   ```python
   from __future__ import annotations
   # ADR-001 (extensão aprovada do §8): wiring em infrastructure/ conecta adapters ↔ use
   # cases sem framework DI de terceiros (um dataclass frozen é suficiente e auditável).
   ```
   - `@dataclass(frozen=True) DIContainer` com os 17 campos da Nota item 2
     (incluindo `benchmark_loader: Callable[[], list[Question]]`).
   - `build_container(config, settings)`:
       * Validar endpoints obrigatórios conforme o contrato REAL de settings.py
         (VLLM_GENERATOR_URL, VLLM_JUDGE_URL, QDRANT_URL) → ConfigValidationError com o
         nome da var faltante.
       * Carregar `ModelRegistryConfig` de `config.model_registry_path` (TAREFA-301);
         converter `ModelEntry` → `ModelWaveSpec` para o WaveSchedulerService.
       * Ordem: storage → retriever → generator_factory → metric_suite →
         deterministic_metric → rubric_judge → server_manager → wave_scheduler →
         3 passadas UC → experiment_uc → annotation_uc.
       * `generator_factory`: closure/callable que instancia `VLLMGeneratorAdapter` com
         a URL resolvida de env (ADR-008: URL vem de env, nunca do YAML).
       * `QdrantRetrieverAdapter`: `collection_map` derivado das `bases` do config.
       * `AnnotationWorkflowUseCase`: `AnnotationConfig` a partir de `config.annotation`
         (defaults do dataclass se None).
       * `benchmark_loader = functools.partial(load_questions, Path(config.questions))`.
   - `build_fake_container(config)`:
       * Imports de `tests.fakes.*` LAZY (dentro da função; nunca no topo do módulo).
       * Fakes de TAREFA-011 (FakeGenerator, FakeMetricSuite, FakeRubricJudge,
         FakeDeterministicMetric, FakeVLLMServerManager, FakeGoldChunkReader, etc).
       * `ParquetStorage(base_dir=Path(tempfile.mkdtemp()))` para isolamento.
       * `benchmark_loader`: 2 primeiras perguntas de `load_questions(Path(config.questions))`.
       * Log structlog `"wiring_fake_container_built"`.

5. CLI — `src/inteligenciomica_eval/cli.py` (COMPLETAR o `run`, preservar o resto)
   Assinatura: `ielm-eval run --config PATH --run-id ID [--phase A|B|both] [--dry-run] [--serial]`
   - `--run-id` obrigatório na execução real; `--serial` → allow_concurrent_models=False.
   - Sem `--dry-run`:
       ```
       cfg = load_round_config(config)
       settings = <ClasseReal>()
       try:
           container = build_container(cfg, settings)
       except ConfigValidationError as exc:
           _err_console.print(Panel(str(exc), title="Erro de configuração", style="red"))
           raise typer.Exit(1) from exc
       questions = container.benchmark_loader()
       with Progress(...) as progress:
           # 3 barras: ondas, geração, avaliação
           report = asyncio.run(container.experiment_uc.execute(
               run_id=run_id, questions=questions, phase=phase,
               serial=serial, progress_callback=...))
       _print_run_summary(report)
       ```
     * `ServerStartTimeoutError` → Panel vermelho "Timeout ao iniciar vLLM" + exit 1.
     * `KeyboardInterrupt` (SIGINT) → "⚠ Encerramento solicitado — aguardando onda atual..."
       + flag de graceful shutdown + exit 130.
     * Exceção não esperada → `log.exception("run_unexpected_error")` + Panel amigável +
       exit 1. NUNCA stacktrace no stdout.
   - Com `--dry-run`: `build_fake_container(cfg)` → imprime plano de ondas (TAREFA-303)
     e "Perguntas carregadas: N" (via `container.benchmark_loader()`). NÃO executa o UC real.
   - `_print_run_summary(report: ExperimentReport) -> None`: tabela Rich
     (geradas/avaliadas/puladas/falhas) + top-3 por RankScore; Panel amarelo se failed_waves.

6. TESTES UNITÁRIOS
   `tests/unit/infrastructure/test_questions_loader.py`:
   - test_load_questions_ok: YAML tmp com 3 perguntas → 3 Question, campos não-vazios.
   - test_load_question_ids: devolve os 3 ids na ordem.
   - test_not_a_list_raises: YAML que é mapping → StorageError.
   - test_empty_list_raises: lista vazia → StorageError.
   - test_missing_field_raises: item sem ground_truth → StorageError com índice.
   - test_empty_field_raises: text="" → StorageError (via Question.__post_init__).
   - test_duplicate_id_raises: dois itens com mesmo question_id → StorageError.
   - test_file_not_found_raises: path inexistente → StorageError.

   `tests/unit/infrastructure/test_wiring.py`:
   - test_build_fake_container_constructs: retorna DIContainer; isinstance de cada campo
     contra seu Protocol/Port.
   - test_fake_benchmark_loader_returns_questions: container.benchmark_loader() não-vazio.
   - test_build_container_missing_generator_url_raises / _judge_url / _qdrant_url:
     ConfigValidationError com o nome da var (montar settings conforme contrato real).
   - test_no_fakes_imported_at_module_level: `import ...wiring` não puxa `tests.fakes`
     em sys.modules.

   `tests/unit/cli/test_run_real.py`:
   - test_run_with_fake_container_succeeds (patch build_container → build_fake_container):
     exit 0; exibe sumário.
   - test_run_missing_env_var_exits_1: env ausente → exit 1, sem stacktrace no stdout.
   - test_run_keyboard_interrupt_exits_130: execute lança KeyboardInterrupt → exit 130.
   - test_dry_run_shows_question_count: --dry-run exibe "Perguntas carregadas: N".
   - test_existing_subcommands_preserved: `ielm-eval --help` ainda lista version,
     compute-metrics, analyze, report, annotate, status, show-config, run-round2,
     validate-judge (regressão dos comandos M4/M6).

ENTREGÁVEL:
- src/inteligenciomica_eval/infrastructure/repositories/questions.py
- src/inteligenciomica_eval/infrastructure/repositories/__init__.py (exporta loaders)
- config/questions.yaml (3 perguntas + comentário TODO P4)
- src/inteligenciomica_eval/infrastructure/config/schema.py (+ campo `questions`)
- src/inteligenciomica_eval/infrastructure/wiring.py
- src/inteligenciomica_eval/cli.py (run completo: --run-id, --phase, --serial, progresso, sumário)
- tests/unit/infrastructure/test_questions_loader.py
- tests/unit/infrastructure/test_wiring.py
- tests/unit/cli/test_run_real.py
- docs/dev-log/M3_TAREFA-309_A_<slug>.md (relatório + Observações p/ Próximas Tarefas:
  registrar o follow-up no operations_manual.md — ver Nota item 4)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations` no topo de TODOS os arquivos novos.
- Type hints em todas as assinaturas públicas; docstrings Google-style.
- Zero `Any` sem comentário justificando.
- `ruff check .`, `ruff format --check .`, `mypy --strict src`, `lint-imports` verdes.
- `tests/fakes` NUNCA importado no topo de módulos de produção (apenas lazy).
- CLI enxuto: NÃO instancia adapters diretamente — delega para `wiring.py`.
- NÃO regredir nenhum subcomando existente. Sem placeholders analyze/report.
- Sem segredos hardcoded; sem framework DI de terceiros; sem `print()` em produção.
- Cobertura: gate 85% (--cov-fail-under=85).

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-309):
- `load_questions(Path("config/questions.yaml"))` → ≥ 3 Question válidas; YAML malformado
  → StorageError com índice. `load_question_ids` retorna os mesmos ids.
- `RoundConfig.questions` presente (default `config/questions.yaml`).
- `build_fake_container` constrói sem erro; cada campo satisfaz seu Protocol.
- `build_container` com env var ausente → ConfigValidationError com o nome da var.
- `ielm-eval run --config ... --run-id test --dry-run`: exit 0; plano + "Perguntas
  carregadas: N". (Cole a saída.)
- `ielm-eval run --config ... --run-id test` (sem --dry-run, env ausente): exit 1,
  mensagem clara, sem stacktrace no stdout. (Cole a saída.)
- `ielm-eval --help` ainda lista TODOS os subcomandos de M4/M6 (regressão verde).
- Pytest (unit): novos testes PASS; cobertura ≥ 85%.
- `lint-imports` verde; wiring não importa `tests.*` no nível de módulo.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-309 + arquitetura §§8/5.1/5.3/14.6 + ADR-001/008/012 +
"Nota de operacionalização 309" itens 1–4 + prompts_m5 (mecanismo `config/questions.yaml`)
+ relatório de implementação do Claude Code (Parte A).

VERIFIQUE, item a item, citando arquivo:linha:

1. Loader (`infrastructure/repositories/questions.py`):
   a. `load_questions(path)` lê YAML com `yaml.safe_load`; top-level não-lista e lista
      vazia → StorageError?
   b. Item malformado/campo vazio → StorageError com ÍNDICE do item + nome do arquivo?
   c. question_id duplicado → StorageError?
   d. `load_question_ids(path)` existe e retorna os ids na ordem (dependência do M5)?
   e. path é obrigatório (sem default empacotado via importlib.resources)?
   f. `from __future__ import annotations`?

2. `config/questions.yaml`:
   a. É lista YAML de {question_id, text, ground_truth}; 3 perguntas biomédicas PT?
   b. Comentário com TODO(P4) de completar para 13?
   c. Está em `config/` e NÃO empacotado na wheel (não há `package-data` para ele)?

3. Schema:
   a. `RoundConfig.questions: str = "config/questions.yaml"` adicionado e validado?
   b. As perguntas NÃO foram embutidas no YAML de rodada (apenas o path)?

4. `DIContainer` (`infrastructure/wiring.py`):
   a. `@dataclass(frozen=True)`; 17 campos tipados com Protocol/Port correto?
   b. `benchmark_loader: Callable[[], list[Question]]` presente?
   c. ADR inline justificando a extensão do §8?

5. `build_container`:
   a. Usa o NOME REAL da classe de settings (confirmar contra settings.py — não um nome
      inventado)?
   b. Validação de VLLM_GENERATOR_URL/VLLM_JUDGE_URL/QDRANT_URL → ConfigValidationError
      com nome da var, COERENTE com o contrato real de settings.py (não a string literal
      "<not set>" se settings.py não a usa)?
   c. `benchmark_loader = functools.partial(load_questions, Path(config.questions))`?
   d. `generator_factory` instancia VLLMGeneratorAdapter com URL de env (nunca do YAML)?
   e. Sem imports de `tests.fakes` no topo? Sem segredos hardcoded?

6. `build_fake_container`:
   a. Imports de `tests.fakes` LAZY (dentro da função)?
   b. ParquetStorage em diretório temporário?
   c. benchmark_loader retorna as 2 primeiras perguntas reais?

7. CLI `run`:
   a. `--run-id` obrigatório na execução real?
   b. `--serial` mapeia para allow_concurrent_models=False (ADR-012)?
   c. Rich Progress com 3 barras? Nenhum `print()`?
   d. Stacktrace NUNCA no stdout (vai p/ log DEBUG)? KeyboardInterrupt → exit 130?
      ServerStartTimeoutError → Panel + exit 1?
   e. `--dry-run` usa build_fake_container e exibe contagem de perguntas?
   f. REGRESSÃO: `ielm-eval --help` lista version, compute-metrics, analyze, report,
      annotate, status, show-config, run-round2, validate-judge? NENHUM removido?
   g. NENHUM placeholder analyze/report reintroduzido?

8. Testes unitários:
   a. test_questions_loader.py: 8 casos (ok, ids, not_a_list, empty_list, missing_field,
      empty_field, duplicate_id, file_not_found)?
   b. test_wiring.py: fake OK, benchmark_loader, 3× env var ausente, no-fakes-at-module-level?
   c. test_run_real.py: fake OK, env ausente, KeyboardInterrupt, dry-run, subcomandos preservados?

9. Camadas/import-linter:
   a. `infrastructure/repositories/questions.py` importa só `domain.entities`/`domain.errors`?
   b. `wiring.py` não importa `tests.*` no nível de módulo?
   c. `cli.py` não instancia adapters diretamente (delega ao wiring)?
   d. `lint-imports` verde (cole o resultado)?

10. DoD §14.2:
    a. `from __future__ import annotations` em todos os arquivos novos?
    b. Type hints + docstrings Google-style?
    c. `ruff check .` e `ruff format --check .` verdes?
    d. `mypy --strict src` verde?
    e. Pytest (unit) verde, cobertura ≥ 85% (cole o relatório)?

11. Follow-up documentado: o relatório registra na seção "Observações para Próximas
    Tarefas" que o operations_manual.md (TAREFA-604) precisa de `--run-id` na Seção 5 e
    de uma subseção sobre `config/questions.yaml`/multi-área?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade:
BLOQUEADOR | IMPORTANTE | SUGESTÃO).
Cole a saída de `ielm-eval run --help`, `ielm-eval --help` (lista de subcomandos) e
`ielm-eval run --config ... --run-id test --dry-run`.
~~~
