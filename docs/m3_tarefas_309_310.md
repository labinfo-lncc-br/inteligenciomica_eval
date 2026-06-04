# Prompts M3 — TAREFA-309 e TAREFA-310 (Claude Code ↔ ChatGPT Codex)

**Milestone:** M3 — Rodada 1 completa + orquestração das 4 GPUs (tarefas finais)
**Documentos de referência:**
- `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1, §§ 2.2 RF1/P4, 4, 5.1, 8, 11, 14.6)
- `visao_alto_nivel_validacao_inteligenciomica.md` (v1.0, §§ 2.3, 3.1, 11)
**Continuação de:** `prompts_m3_tarefas_301_310.md` — TAREFA-301…308 mergeadas e verdes;
faltam **TAREFA-309** (DI wiring + CLI `run` completo + carregamento de perguntas) e
**TAREFA-310** (E2E gate M3).
**Formato:** **Prompt A (implementação — Claude Code)** + **Prompt B (verificação —
ChatGPT Codex)**, conforme seção 16 do documento de arquitetura.
**Épico coberto:** E3 (orquestração GH200) — encerramento do M3.

> Pressupõe que **M0–M2 (TAREFA-001..028) e M3 parcial (TAREFA-301..308) já estão
> mergeados e verdes**: domínio puro, todos os adapters (M1), pipeline de métricas
> (Camadas 1–3, M1+M3), `VLLMServerManager` real (TAREFA-302),
> `WaveSchedulerService` (TAREFA-303), todos os use cases de geração/métricas/juiz
> (TAREFA-304–307) e `AnnotationWorkflowUseCase` (TAREFA-308).
> **O M5 (Rodada 2 — funil OFAT) permanece adiado** — nenhum módulo de M5 é
> importado ou referenciado em 309/310.
> As convenções da "Nota de operacionalização" de M0–M3 **continuam valendo**
> (lista canônica de libs proibidas em `domain`/`application`; `import-linter`;
> DoD §14.2; `from __future__ import annotations` no topo de todo arquivo).

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

> **Início desta tarefa:** execute primeiro a **Parte A (Claude Code)** da TAREFA-309
> abaixo e produza o relatório de implementação. A **Parte B (ChatGPT Codex)** roda em
> seguida, a partir da resposta do desenvolvedor (relatório + diff do PR da Parte A).
> Itere A↔B até PASS. Só então passe para a TAREFA-310.

---

## Nota de operacionalização de M3 — TAREFA-309/310

Seis decisões que 309–310 precisam fixar para Code e Codex não divergirem (vetáveis
pela equipe antes da TAREFA-309 iniciar):

### 1. Carregamento das perguntas RF1 (P4) — `BenchmarkLoader`

A Premissa **P4** exige que as 13 perguntas e suas ground truths estejam
padronizadas e versionadas antes da Rodada 1. A arquitetura não define um `BenchmarkPort`
(decisão explícita: as perguntas são fornecidas como `Sequence[Question]` ao use case
pelo orquestrador). A TAREFA-309 concretiza o mecanismo de carregamento:

- **Arquivo canônico**: `src/inteligenciomica_eval/infrastructure/benchmark/questions_rf1.jsonl`
  — uma linha JSON por pergunta: `{"question_id": "...", "text": "...", "ground_truth": "..."}`.
  Este arquivo é **parte do pacote instalado** (declarado em `pyproject.toml` como
  `package-data`, carregado via `importlib.resources`). As 13 perguntas biomédicas reais
  devem ser preenchidas antes da Rodada 1 de produção; para o gate de M3, o arquivo pode
  conter 3–5 perguntas representativas (conforme item 5 desta nota).
- **`BenchmarkLoader`** em `src/inteligenciomica_eval/infrastructure/benchmark/loader.py`:
  função `load_questions(path: Path | None = None) -> list[Question]`. Sem `path` →
  lê o arquivo empacotado via `importlib.resources.files`. Com `path` → lê arquivo
  externo (para testes e futuras rodadas). Linha malformada → `StorageError` com `lineno`
  e nome do arquivo.
- **`RuntimeSettings`** ganha campo opcional `BENCHMARK_QUESTIONS_PATH: str = ""`
  (env var; string vazia = usar o arquivo empacotado).
- **Motivação**: perguntas são dado de benchmark, versionadas com o código (P4); não são
  configuração de rodada (não vão no YAML); não são segredo (não vão em env var de valor).
  Override por env var preserva a flexibilidade para testes de integração e Rodada 2.

### 2. `DIContainer` e `wiring.py` — regras de camada

- `infrastructure/wiring.py` é uma **extensão aprovada do blueprint §8** (registrar como
  ADR inline no próprio arquivo, referenciando ADR-001).
- `@dataclass(frozen=True) DIContainer` — sem framework DI de terceiros (ADR-001).
  Campos obrigatórios (todos tipados):
  `retriever`, `generator_factory`, `metric_suite`, `deterministic_metric`,
  `rubric_judge`, `server_manager`, `wave_scheduler`, `gen_pass_uc`, `metrics_pass_uc`,
  `judge_pass_uc`, `experiment_uc`, `annotation_uc`, `writer`, `reader`,
  `agg_service`, `rank_calc`, `benchmark_loader`.
- `build_container(config: RoundConfig, settings: RuntimeSettings) -> DIContainer`:
  instancia adapters **reais**. Se env var obrigatória ausente (VLLM_GENERATOR_URL,
  VLLM_JUDGE_URL, QDRANT_URL com valor `"<not set>"`) → `ConfigValidationError` com
  nome da variável faltante. Sem imports de fakes neste path.
- `build_fake_container(config: RoundConfig) -> DIContainer`: substitui adapters de rede
  pelos fakes de TAREFA-011. Usado no `--dry-run` e nos testes unitários do wiring.
  **O `--dry-run` do CLI prova que a fiação está correta sem tocar GPU/rede.**

### 3. CLI `ielm-eval run` completo — contrato de UX

- Assinatura: `ielm-eval run --config PATH --run-id ID [--phase A|B|both] [--dry-run] [--serial]`
  - `--run-id` é **obrigatório** na execução real (identifica o run no Parquet).
  - Sem `--dry-run`: `build_container(cfg, settings)` → `benchmark_loader.load_questions()`
    → `RunExperimentUseCase.execute(run_id, questions, ...)`.
  - Com `--dry-run`: `build_fake_container(cfg)` + imprime plano de ondas (já implementado
    em TAREFA-303); NÃO executa use case real.
- **Rich Progress** com 3 barras de progresso (ondas concluídas / total; células geradas /
  total; células avaliadas / total). Nunca `print()` em código de produção.
- **Stacktrace** NUNCA aparece no `stdout` em condição de erro — vai para log structlog
  em `DEBUG`. Ao usuário: Rich Panel vermelho com mensagem amigável + exit code 1.
- **SIGINT/SIGTERM**: mensagem `"⚠ Encerramento solicitado — aguardando onda atual..."`
  + seta flag de graceful shutdown já implementada em TAREFA-307 (`RunExperimentUseCase`).
- Sumário de sucesso: tabela Rich com nº de células geradas/avaliadas/puladas/falhas e
  top-3 configurações por `RankScore`.

### 4. E2E gate (TAREFA-310) — escopo e limites

- Usa `build_fake_container` + `ParquetStorage(base_dir=tmp_path)` — zero rede/GPU.
- Dataset mínimo: **2 perguntas** do `BenchmarkLoader` (carregadas do arquivo empacotado,
  não de fixture separada), **1 base**, **2 LLMs stub**, **1 seed** → 4 células por passe.
  Fakes devem ser determinísticos (mesmo `question_id + llm + seed` → mesmo output).
- Critério de performance: `pytest -m e2e tests/e2e/test_m3_full_cycle.py` < **30 s**
  (CPU; fakes são rápidos).
- Testa **idempotência** (segunda execução com mesmo `run_id` → 0 células novas, RF7).
- Testa **graceful shutdown** via `mock.patch("signal.signal")`.
- Testa **NaN handling**: uma célula com métrica NaN → `final_score` NaN → excluída da
  agregação (`ConfigAggregate.n_excluded_nan > 0`), mas NÃO impede o restante.

### 5. Perguntas RF1 — conteúdo do arquivo de gate

Para o gate de M3 (TAREFA-310), o arquivo `questions_rf1.jsonl` deve conter no mínimo
**3 perguntas biomédicas** (em português, área infecciologia/resistência antimicrobiana,
consistentes com o domínio do InteligenciÔmica). O ficheiro será estendido para as 13
perguntas reais antes da Rodada 1 de produção (P4 — responsabilidade do especialista
biomédico). A TAREFA-309 entrega a **estrutura e 3 perguntas representativas**; o TODO
de completar as 13 é documentado em comentário no topo do JSONL e na seção
"Observações para Próximas Tarefas" do dev-log.

### 6. M5 continua adiado — zero impacto

Nenhum módulo de M5 (`funnel.py`, `RetrievalFunnelUseCase`, `experiment_round2*.yaml`)
é importado ou referenciado em 309/310. O DIContainer não inclui campo `funnel`.
Quando M5 entrar, o wiring será estendido por PR separado.

---

## TAREFA-309 — DI wiring real + CLI `run` completo + `BenchmarkLoader`

**Épico:** E3 · **Skill:** python-engineer · **Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-302 (`VLLMServerManagerAdapter`), TAREFA-303
(`WaveSchedulerService`), TAREFA-307 (`RunExperimentUseCase`), TAREFA-308
(`AnnotationWorkflowUseCase`), TAREFA-010 (config/settings) · **ADRs:** ADR-001
(Clean Architecture), ADR-008 (config declarativa) · **Camadas:** `infrastructure/wiring`,
`infrastructure/benchmark`, `cli`

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §14.6
TAREFA-309). Skills ativos: python-engineer, python-clean-architecture §1.
M0–M3 parcial (301–308) já mergeados e verdes. Esta tarefa fecha o wiring e completa
o CLI `run`, conectando todos os adapters reais ao use case `RunExperimentUseCase`.
VER "Nota de operacionalização M3" itens 1–3 e 6 deste arquivo de prompts.

TAREFA: TAREFA-309 — implementar:
  (a) `BenchmarkLoader` + arquivo `questions_rf1.jsonl` com 3 perguntas biomédicas;
  (b) `infrastructure/wiring.py` com `DIContainer`, `build_container`, `build_fake_container`;
  (c) comando `ielm-eval run` completo (execução real, sem limitar ao --dry-run).

ESPECIFICAÇÃO:

1. ARQUIVO DE PERGUNTAS — `src/inteligenciomica_eval/infrastructure/benchmark/questions_rf1.jsonl`
   Formato: uma linha JSON por pergunta.
   Schema de cada linha:
     {"question_id": "<slug-kebab-case>", "text": "<enunciado em PT>", "ground_truth": "<resposta de referência em PT>"}
   Conteúdo mínimo: 3 perguntas da área de infecciologia/resistência antimicrobiana
   (domínio do InteligenciÔmica, coerentes com a pergunta de exemplo em
   `tests/fixtures/integration_question.json`).
   Inserir comentário no topo (linha de texto simples, JSONL não suporta comentários —
   usar convenção `{"_comment": "RF1 benchmark — 13 perguntas reais a preencher antes da
   Rodada 1 de produção (P4). Atualmente 3 placeholders representativos."}`  como
   PRIMEIRA linha do arquivo, seguida das 3 perguntas reais. O `BenchmarkLoader` deve
   pular linhas cujo JSON contenha a chave `_comment`).
   Declarar em `pyproject.toml` como `package-data`:
     [tool.hatch.build.targets.wheel]
     packages = ["src/inteligenciomica_eval"]
     # include benchmark data
   (verificar se o hatchling já inclui arquivos não-.py dentro do pacote; se não,
   adicionar `include = ["src/inteligenciomica_eval/infrastructure/benchmark/*.jsonl"]`).

2. `BenchmarkLoader` — `src/inteligenciomica_eval/infrastructure/benchmark/loader.py`
   ```python
   from __future__ import annotations
   import json
   from importlib.resources import files
   from pathlib import Path
   from inteligenciomica_eval.domain.entities import Question
   from inteligenciomica_eval.domain.errors import StorageError

   def load_questions(path: Path | None = None) -> list[Question]:
       """Carrega as perguntas do benchmark RF1.

       Args:
           path: caminho externo para um JSONL de perguntas.
                 None → usa `questions_rf1.jsonl` empacotado no módulo.

       Returns:
           Lista ordenada de :class:`Question` (na ordem do arquivo).

       Raises:
           StorageError: se o arquivo não existir ou uma linha for malformada.
       """
   ```
   - Sem `path`: lê via `importlib.resources.files("inteligenciomica_eval.infrastructure.benchmark").joinpath("questions_rf1.jsonl").read_text(encoding="utf-8")`.
   - Com `path`: `path.read_text(encoding="utf-8")`.
   - Linhas em branco: ignorar.
   - Linhas com `"_comment"` key no JSON: ignorar (não geram `Question`).
   - Linha malformada (JSONDecodeError, campo ausente, campo vazio): `StorageError`
     com mensagem incluindo `lineno` e nome do arquivo.
   - `Question` construído como `Question(question_id=..., text=..., ground_truth=...)`.
   - `__init__.py` em `infrastructure/benchmark/` exporta apenas `load_questions`.

3. `RuntimeSettings` — atualizar `infrastructure/config/settings.py`
   Adicionar campo `BENCHMARK_QUESTIONS_PATH: str = ""`
   (string vazia = usar arquivo empacotado; path absoluto = arquivo externo).
   Documentar no atributo que o override existe para testes e futuras rodadas.

4. `DIContainer` + funções — `src/inteligenciomica_eval/infrastructure/wiring.py`

   ```python
   from __future__ import annotations
   # ADR-001 extensão aprovada: wiring em infrastructure/ conecta adapters ↔ use cases
   # sem framework DI de terceiros (containers de DI violam a inversão de dependência
   # limpa; um dataclass simples é suficiente e auditável).
   ```

   `@dataclass(frozen=True) DIContainer`:
   Campos (todos tipados com o Protocol/Port correto, SEM imports de fakes):
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
   `benchmark_loader` é um callable zero-args que retorna `list[Question]` —
   `build_container` o instancia como `functools.partial(load_questions, path or None)`;
   `build_fake_container` pode injetar uma função que retorna as 2 perguntas de teste.

   `build_container(config: RoundConfig, settings: RuntimeSettings) -> DIContainer`:
   - Valida env vars: para cada URL de adapter que usa `settings`, se o valor for
     `"<not set>"`, levantar `ConfigValidationError` com nome da variável faltante.
     Verificar `VLLM_GENERATOR_URL`, `VLLM_JUDGE_URL`, `QDRANT_URL`.
   - Instancia adapters reais na ordem: storage → retriever → generators →
     metric_suite → deterministic_metric → rubric_judge → server_manager →
     schedulers → use cases.
   - `generator_factory`: implementar como closure ou classe interna que instancia
     `VLLMGeneratorAdapter` com a URL resolvida (ADR-008: URL vem de env var, nunca
     do YAML).
   - `QdrantRetrieverAdapter`: usar `collection_map` derivado das `bases` do `config`
     (mapeia `BaseId.value → nome da coleção no Qdrant`, convenção: mesmo nome da base).
   - `AnnotationWorkflowUseCase`: construir `AnnotationConfig` a partir de
     `config.annotation` (se None, usar defaults do dataclass).
   - `benchmark_loader`: `functools.partial(load_questions, Path(settings.BENCHMARK_QUESTIONS_PATH) if settings.BENCHMARK_QUESTIONS_PATH else None)`.

   `build_fake_container(config: RoundConfig) -> DIContainer`:
   - Importa `tests.fakes.*` DENTRO da função (lazy import, nunca no topo do módulo —
     evita que `tests/` entre no grafo de importação de produção).
   - Usa `FakeGenerator`, `FakeMetricSuite`, `FakeRubricJudge`, `FakeDeterministicMetric`,
     `FakeVLLMServerManager`, `FakeGoldChunkReader`, `FakeAnnotationReader`.
   - `ParquetStorage` com `base_dir=Path(tempfile.mkdtemp())` para isolamento.
   - `benchmark_loader`: retorna as primeiras 2 perguntas do arquivo empacotado
     (suficiente para dry-run e testes).
   - Log structlog `"wiring_fake_container_built"` ao construir.

5. CLI `ielm-eval run` — atualizar `src/inteligenciomica_eval/cli.py`

   Assinatura final do comando:
   ```
   ielm-eval run --config PATH --run-id ID [--phase A|B|both] [--dry-run] [--serial]
   ```
   - `--run-id TEXT` [obrigatório na execução real; ignorado no dry-run].
   - `--phase [A|B|both]` [default: "both"] — seleciona quais experimentos rodar.

   Fluxo sem `--dry-run`:
   ```
   cfg = load_round_config(config)
   settings = RuntimeSettings()
   try:
       container = build_container(cfg, settings)
   except ConfigValidationError as exc:
       _err_console.print(Panel(str(exc), title="Erro de configuração", style="red"))
       raise typer.Exit(1) from exc
   questions = container.benchmark_loader()
   with Progress(...) as progress:
       task_waves = progress.add_task("Ondas", total=n_waves)
       task_gen   = progress.add_task("Geração", total=total_celulas)
       task_eval  = progress.add_task("Avaliação", total=total_celulas)
       report = asyncio.run(
           container.experiment_uc.execute(
               run_id=run_id,
               questions=questions,
               progress_callback=...,  # atualiza as 3 barras
           )
       )
   # Sumário final
   _print_run_summary(report)
   ```
   - `ServerStartTimeoutError` → Panel vermelho "Timeout ao iniciar vLLM" + exit 1.
   - `KeyboardInterrupt` (SIGINT) → "⚠ Encerramento solicitado — aguardando onda atual..."
     + seta flag de graceful shutdown do `RunExperimentUseCase` + exit 130.
   - Stacktrace NUNCA no stdout: capturar exceções não esperadas com
     `log.exception("run_unexpected_error")` + mensagem amigável + exit 1.

   Fluxo com `--dry-run` (já parcialmente implementado — MANTER o comportamento atual):
   - `build_fake_container(cfg)` → imprime plano de ondas + cell counts.
   - NÃO executa use case real.
   - Exibir também: `"Perguntas carregadas: N"` (chama `container.benchmark_loader()`).

   Função auxiliar `_print_run_summary(report: ExperimentReport) -> None`:
   - Tabela Rich: células geradas / avaliadas / puladas / com falha.
   - Top-3 configurações por `RankScore` (decrescente).
   - Se `report.failed_waves`: Panel amarelo listando ondas com falha.

6. TESTES UNITÁRIOS

   `tests/unit/infrastructure/test_benchmark_loader.py`:
   - `test_load_questions_bundled`: chama `load_questions()` sem path →
     devolve `list[Question]` não-vazia; todos os campos não-vazios; sem "_comment".
   - `test_load_questions_external`: escreve JSONL temporário via `tmp_path` com 2 perguntas
     válidas → `load_questions(path)` devolve lista com 2 `Question`.
   - `test_skip_comment_line`: arquivo com `{"_comment": "..."}` + 1 pergunta válida →
     retorna apenas a pergunta válida.
   - `test_malformed_line_raises_storage_error`: linha com JSON inválido → `StorageError`
     com `lineno` na mensagem.
   - `test_missing_field_raises_storage_error`: linha sem `"ground_truth"` → `StorageError`.
   - `test_empty_field_raises_storage_error`: linha com `"text": ""` → `StorageError`
     (propagado do `Question.__post_init__`).

   `tests/unit/infrastructure/test_wiring.py`:
   - `test_build_fake_container_constructs_without_error`: `build_fake_container(cfg_stub)`
     retorna `DIContainer` completo; `isinstance` para cada campo (verifica os Protocols).
   - `test_build_fake_container_benchmark_loader_returns_questions`:
     `container.benchmark_loader()` retorna `list[Question]` não-vazia.
   - `test_build_container_missing_generator_url_raises`: `RuntimeSettings` com
     `VLLM_GENERATOR_URL="<not set>"` → `ConfigValidationError` com "VLLM_GENERATOR_URL"
     na mensagem.
   - `test_build_container_missing_judge_url_raises`: idem para `VLLM_JUDGE_URL`.
   - `test_build_container_missing_qdrant_url_raises`: idem para `QDRANT_URL`.
   - `test_no_fakes_imported_at_module_level`: verifica que `import wiring` não puxa
     `tests.fakes` no `sys.modules` (lazy import).

   `tests/unit/cli/test_run_real.py`:
   - `test_run_with_fake_container_succeeds` (patch `build_container` →
     `build_fake_container`): `ielm-eval run --config ... --run-id test-run` executa
     sem erro; exibe sumário; exit code 0.
   - `test_run_missing_env_var_exits_1`: env var ausente → exit code 1 + mensagem
     sem stacktrace no stdout.
   - `test_run_keyboard_interrupt_exits_130`: mock `RunExperimentUseCase.execute` lança
     `KeyboardInterrupt` → exit code 130 + mensagem amigável.
   - `test_dry_run_shows_question_count`: `--dry-run` exibe "Perguntas carregadas: N".

ENTREGÁVEL:
- `src/inteligenciomica_eval/infrastructure/benchmark/__init__.py`
- `src/inteligenciomica_eval/infrastructure/benchmark/loader.py`
- `src/inteligenciomica_eval/infrastructure/benchmark/questions_rf1.jsonl` (3 perguntas + _comment)
- `src/inteligenciomica_eval/infrastructure/wiring.py`
- `src/inteligenciomica_eval/infrastructure/config/settings.py` (+ `BENCHMARK_QUESTIONS_PATH`)
- `src/inteligenciomica_eval/cli.py` (run completo: --run-id, --phase, progresso, sumário)
- `tests/unit/infrastructure/test_benchmark_loader.py`
- `tests/unit/infrastructure/test_wiring.py`
- `tests/unit/cli/test_run_real.py`
- `pyproject.toml` (package-data para o JSONL, se necessário)
- `docs/dev-log/M3_TAREFA-309_A_<slug>.md` (relatório de implementação)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations` no topo de TODOS os arquivos Python novos.
- Type hints em todas as assinaturas públicas; docstrings Google-style.
- Zero `Any` sem comentário justificando.
- `ruff check .`, `ruff format --check .`, `mypy --strict src`, `lint-imports` verdes.
- `tests/fakes` NUNCA importado no topo de módulos de produção (apenas lazy, dentro de funções).
- CLI permanece enxuto: NÃO instancia adapters diretamente — delega para `wiring.py`.
- Sem segredos hardcoded; sem framework DI de terceiros.
- Nenhum `print()` em código de produção — usar `structlog` ou `rich.Console`.
- Cobertura: gate 85% (--cov-fail-under=85 no job `unit`).

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-309):
- `load_questions()` sem args carrega o arquivo empacotado → retorna ≥ 3 `Question`.
- `load_questions(path)` com arquivo externo funciona; linha malformada → `StorageError`.
- `build_fake_container` constrói sem erro; cada campo satisfaz seu Protocol.
- `build_container` com env var ausente → `ConfigValidationError` com nome da variável.
- `ielm-eval run --config ... --run-id test --dry-run`: exit 0, exibe plano + contagem
  de perguntas. (Cole a saída completa no relatório.)
- `ielm-eval run --config ... --run-id test` (sem --dry-run, com env var ausente):
  exit 1, mensagem clara, sem stacktrace no stdout. (Cole a saída no relatório.)
- Pytest (unit): todos os novos testes PASS; cobertura ≥ 85%.
- `lint-imports` verde: `infrastructure/benchmark/` não importa `domain` diretamente
  (só via `domain.entities` e `domain.errors`, que são permitidos); wiring não importa
  `tests.fakes` no nível de módulo.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-309 + arquitetura §14.6 + "Nota de operacionalização M3
items 1–3 e 6" + relatório de implementação do Claude Code (Parte A).

VERIFIQUE, item a item, citando arquivo:linha:

1. BenchmarkLoader (`infrastructure/benchmark/loader.py`):
   a. `load_questions()` sem path usa `importlib.resources.files` (não `__file__` hardcoded)?
   b. Linhas com `"_comment"` key são ignoradas? Linhas em branco são ignoradas?
   c. Linha malformada → `StorageError` com `lineno` na mensagem?
   d. Linha com campo vazio (`text: ""`) → `StorageError` (via `Question.__post_init__`)?
   e. `from __future__ import annotations` no topo?

2. Arquivo `questions_rf1.jsonl`:
   a. Primeira linha é o objeto `{"_comment": "..."}` com o TODO de completar para 13?
   b. Contém ao menos 3 perguntas biomédicas válidas (PT, área infecciologia)?
   c. Todos os campos presentes e não-vazios em cada linha de pergunta?
   d. Declarado como package-data (incluído na wheel)? Verificar `pyproject.toml`.

3. `RuntimeSettings`:
   a. Campo `BENCHMARK_QUESTIONS_PATH: str = ""` adicionado?
   b. Docstring explica que string vazia = arquivo empacotado?

4. `DIContainer` (`infrastructure/wiring.py`):
   a. `@dataclass(frozen=True)`? Todos os 17 campos tipados com o Protocol/Port correto?
   b. `benchmark_loader: Callable[[], list[Question]]` presente?
   c. ADR inline justificando a extensão do blueprint §8 (ADR-001)?

5. `build_container`:
   a. Validação de `"<not set>"` para VLLM_GENERATOR_URL, VLLM_JUDGE_URL, QDRANT_URL
      → `ConfigValidationError` com nome da variável?
   b. Sem imports de `tests.fakes` no topo do módulo?
   c. Sem segredos hardcoded?
   d. `generator_factory` é closure/callable que instancia `VLLMGeneratorAdapter`
      com URL de env var (nunca do YAML, ADR-008)?

6. `build_fake_container`:
   a. Imports de `tests.fakes` DENTRO da função (lazy, não no topo)?
   b. `ParquetStorage` com `base_dir` em diretório temporário (isolamento)?
   c. `isinstance(container.retriever, RetrieverPort)` passaria (Protocol satisfeito)?

7. CLI `ielm-eval run`:
   a. `--run-id` obrigatório na execução real?
   b. Rich Progress com 3 barras (ondas, geração, avaliação)?
   c. Stacktrace NUNCA no stdout — capturado e logado em DEBUG?
   d. `KeyboardInterrupt` → exit 130 + mensagem amigável?
   e. `ServerStartTimeoutError` → Panel vermelho + exit 1?
   f. `--dry-run` chama `build_fake_container` (não `build_container`)?
   g. `--dry-run` exibe contagem de perguntas carregadas?
   h. Nenhum `print()` no código do CLI (apenas `rich.Console` ou `structlog`)?

8. Testes unitários:
   a. `test_benchmark_loader.py`: 6 casos presentes (bundled, external, skip_comment,
      malformed, missing_field, empty_field)?
   b. `test_wiring.py`: 5 casos presentes (fake OK, benchmark_loader, 3 × env var ausente)?
   c. `test_run_real.py`: 4 casos presentes (fake OK, env var ausente, KeyboardInterrupt, dry-run)?
   d. Nenhum teste usa `--no-cov` ou `# pragma: no cover` indevidamente?

9. Camadas e import-linter:
   a. `infrastructure/benchmark/` importa apenas `domain.entities` e `domain.errors`?
   b. `infrastructure/wiring.py` não importa `tests.*` no nível de módulo?
   c. `cli.py` não instancia adapters diretamente (delega para wiring)?
   d. `lint-imports` verde (cole resultado)?

10. DoD §14.2:
    a. `from __future__ import annotations` em todos os arquivos Python novos?
    b. Type hints em todas as assinaturas públicas?
    c. Docstrings Google-style nas classes/funções públicas?
    d. `ruff check .` e `ruff format --check .` verdes?
    e. `mypy --strict src` verde?
    f. Pytest (unit) verde com ≥ 85% de cobertura (cole o relatório)?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Gravidades: BLOQUEADOR (falha automática) | IMPORTANTE (deve corrigir antes do merge) |
SUGESTÃO (melhoria não bloqueante).
Cole a saída de `ielm-eval run --help` e `ielm-eval run --config ... --dry-run`.
~~~

---

## TAREFA-310 — E2E gate M3: ciclo completo com adapters semi-reais

**Épico:** E3 · **Skill:** test-engineer · **Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-309 (wiring + CLI) — **ESTA É A ÚLTIMA TAREFA DO M3**
**ADRs:** ADR-001, ADR-007 (NaN policy), ADR-009 (idempotência) · **Camadas:** `tests/e2e`

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §14.6
TAREFA-310, gate de saída do M3). Skills ativos: test-engineer §11, python-clean-architecture §1.
TAREFA-301..309 já mergeadas e verdes. Esta tarefa entrega o E2E gate do M3:
um ciclo completo com `build_fake_container` + `ParquetStorage` real em `tmp_path`,
sem GPU/rede, em < 30 s. VER "Nota de operacionalização M3" items 4–5.

TAREFA: TAREFA-310 — implementar `tests/e2e/test_m3_full_cycle.py` (E2E gate M3).

ESPECIFICAÇÃO:

O teste usa EXCLUSIVAMENTE `build_fake_container` (TAREFA-309) + `ParquetStorage`
real em `tmp_path`. Nenhum adapter de rede é instanciado. Nenhuma GPU.

1. FIXTURE DE CONFIGURAÇÃO (`conftest.py` local ou no topo do arquivo de teste):
   - `round_config_stub: RoundConfig` — config mínima válida:
     `round_id="e2e_m3_round"`, `phases=["A"]`, `bases=["IDx_400k"]`,
     `llms=["stub-gen-a", "stub-gen-b"]`, `seeds=[42]`, `temperature=0.0`,
     retrieval/judge/scoring mínimos válidos.
   - `questions_stub: list[Question]` — 2 perguntas carregadas de
     `load_questions()` (arquivo empacotado, primeiras 2 entradas).
     Usar as perguntas reais do JSONL, não fabricar strings ad-hoc — o test
     valida que o arquivo empacotado funciona no contexto E2E.
   - `tmp_storage(tmp_path): ParquetStorage` — `ParquetStorage(base_dir=tmp_path,
     round_id="e2e_m3_round")`.
   - `container(round_config_stub, tmp_storage)` — `build_fake_container(round_config_stub)`
     com `writer` e `reader` substituídos pelo `tmp_storage` (injeção direta no
     `@dataclass(frozen=True)` via `dataclasses.replace`).

2. CENÁRIO PRINCIPAL — `test_m3_full_cycle_generates_and_evaluates`:
   a. Executar `RunExperimentUseCase.execute(run_id="e2e_m3_run_1", questions=questions_stub)`.
   b. **n_generated == 4** (2 perguntas × 1 base × 2 LLMs × 1 seed, fase A).
   c. **n_evaluated == 4** (métricas calculadas para todas as células).
   d. **n_judged == 4** (rubrica calculada para todas as células).
   e. Parquet lido de volta via `tmp_storage.load(round_id="e2e_m3_round", phase="A")`:
      - 4 linhas; schema correto (colunas: `row_id`, `run_id`, `round_id`, `phase`,
        `base`, `llm`, `seed`, `question_id`, `final_score` e demais campos do §5.3).
      - `run_id` de todas as linhas == `"e2e_m3_run_1"`.
   f. Roundtrip: todos os `EvaluationResult` reconstruídos correspondem aos persistidos
      (comparação por `row_id` + `final_score` + `question_id`).
   g. `ExperimentReport.failed_waves == ()`.

3. CENÁRIO NaN HANDLING — `test_m3_nan_cell_excluded_from_aggregation`:
   - Configurar `FakeMetricSuite` para retornar NaN em `answer_correctness` para a
     pergunta com `question_id == questions_stub[0].question_id` (primeira pergunta).
   - Executar `RunExperimentUseCase.execute(...)`.
   - `final_score` da célula NaN == `float("nan")` no Parquet.
   - `AggregateResultsUseCase.execute(...)`: `ConfigAggregate.n_excluded_nan >= 1`.
   - Restante das células (3 células) gera `RankScore` válido (não-NaN).
   - Verificar via `assert not math.isnan(rank_scores[0].rank_score)`.

4. CENÁRIO IDEMPOTÊNCIA — `test_m3_idempotent_second_run`:
   - Executar `RunExperimentUseCase.execute(run_id="e2e_m3_idempotent", ...)` → 4 células novas.
   - Executar novamente com o MESMO `run_id` e mesmas perguntas.
   - Segunda execução: `n_generated == 0` e `n_skipped == 4` (RF7 — idempotência por `row_id`).
   - Contagem de linhas no Parquet permanece 4 (sem duplicatas).

5. CENÁRIO GRACEFUL SHUTDOWN — `test_m3_graceful_shutdown_on_sigint`:
   - Configurar `FakeGenerator` para levantar `KeyboardInterrupt` na **segunda** chamada
     (simula interrupção durante onda 2).
   - Executar `RunExperimentUseCase.execute(...)`.
   - Asserção: onda 1 completou (≥ 2 células persistidas no Parquet — as da primeira
     pergunta + primeiro LLM).
   - Asserção: `FakeVLLMServerManager.stop_calls` não-vazio (servidores encerrados).
   - Asserção: nenhuma exceção não tratada propagada — o use case captura `KeyboardInterrupt`
     e finaliza de forma limpa (log structlog + exit via flag de shutdown).

6. ARQUIVO GOLDEN — `tests/golden/e2e_m3_expected.json`:
   Registrar os valores esperados para o cenário principal (cenário 2):
   ```json
   {
     "n_generated": 4,
     "n_evaluated": 4,
     "n_judged": 4,
     "n_rows_parquet": 4,
     "schema_columns": ["row_id", "run_id", "round_id", "phase", "base", "llm",
                         "seed", "question_id", "generated_answer", "final_score",
                         "bertscore_f1", "rubric_biomed_score"]
   }
   ```
   O teste verifica contra este arquivo (não hardcoda os valores inline).

7. MARCADOR pytest: `@pytest.mark.e2e` em todos os 4 testes do arquivo.
   Verificar que `pyproject.toml` registra `e2e` como marcador válido.

8. CRITÉRIO DE PERFORMANCE: o arquivo completo deve rodar em < 30 s:
   `pytest -m e2e tests/e2e/test_m3_full_cycle.py --timeout=30`
   Adicionar `pytest-timeout` como dev dep se não estiver presente.

ENTREGÁVEL:
- `tests/e2e/test_m3_full_cycle.py` (4 testes: full_cycle, nan, idempotência, shutdown)
- `tests/golden/e2e_m3_expected.json`
- Atualização de `pyproject.toml` (marcador `e2e` + `pytest-timeout` se necessário)
- Atualização de `tests/e2e/_harness.py` se necessário
- `docs/dev-log/M3_TAREFA-310_A_<slug>.md` (relatório de implementação)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings no harness.
- `asyncio_mode = "auto"` — `async def test_*` basta (sem `@pytest.mark.asyncio`).
- Determinístico: seeds fixos, `FakeGenerator` retorna output derivado de `question_id +
  llm + seed` (mesmo input → mesmo output → idempotência verificável).
- Zero rede/GPU em nenhum caminho de código exercitado pelos testes.
- Nenhum `sleep()` em nenhum teste.

CRITÉRIO DE ACEITAÇÃO (gate de saída do M3):
- `pytest -m e2e tests/e2e/test_m3_full_cycle.py -v` → 4 PASSED em < 30 s (cole a saída).
- Cenário principal: 4 linhas no Parquet; roundtrip fiel; colunas do golden presentes.
- Cenário NaN: `n_excluded_nan >= 1`; `RankScore` das outras células não é NaN.
- Cenário idempotência: segunda execução `n_generated == 0`, `n_skipped == 4`.
- Cenário shutdown: ≥ 2 células persistidas; `stop_calls` não-vazio; sem exceção propagada.
- `pytest --cov=src --cov-fail-under=85` (suite completa) ainda PASS.
- `lint-imports` verde (testes não puxam infra de produção para domínio).
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer + test-engineer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-310 + arquitetura §14.6 + "Nota de operacionalização M3
items 4–5" + relatório de implementação do Claude Code (Parte A) + saída do pytest.

VERIFIQUE, item a item, citando arquivo:linha:

1. Fixture `container`:
   a. Usa `build_fake_container` (não `build_container`)?
   b. `writer` e `reader` substituídos por `ParquetStorage(tmp_path)` via
      `dataclasses.replace`? (Não instancia `ParquetStorage` com path fixo.)
   c. `questions_stub` carregados de `load_questions()` (arquivo empacotado, primeiras 2)?
      Não são strings hardcoded no teste?

2. Cenário principal (`test_m3_full_cycle_generates_and_evaluates`):
   a. `n_generated == 4` verificado via `report.n_generated`?
   b. Parquet lido via `tmp_storage.load(...)` (não via `pq.read_table` com tree Hive)?
   c. Roundtrip: `row_id` + `final_score` + `question_id` comparados para cada linha?
   d. `ExperimentReport.failed_waves == ()` asserted?
   e. Valores contra `tests/golden/e2e_m3_expected.json` (não hardcoded inline)?

3. Cenário NaN (`test_m3_nan_cell_excluded_from_aggregation`):
   a. `FakeMetricSuite` configurado para retornar NaN em `answer_correctness` para
      `questions_stub[0].question_id` apenas?
   b. `math.isnan(parquet_row["final_score"])` para a célula NaN?
   c. `ConfigAggregate.n_excluded_nan >= 1`?
   d. `not math.isnan(rank_scores[0].rank_score)` para os restantes?

4. Cenário idempotência (`test_m3_idempotent_second_run`):
   a. Mesmo `run_id` nas duas execuções?
   b. Segunda execução: `report.n_generated == 0` e `report.n_skipped == 4`?
   c. Contagem de linhas no Parquet permanece 4 (len do DataFrame lido)?

5. Cenário graceful shutdown (`test_m3_graceful_shutdown_on_sigint`):
   a. `FakeGenerator` lança `KeyboardInterrupt` na segunda chamada (não na primeira)?
   b. Parquet tem ≥ 2 linhas após a interrupção?
   c. `FakeVLLMServerManager.stop_calls` não-vazio?
   d. Nenhuma exceção propagada para fora do `execute()` (o teste não usa `pytest.raises`)?

6. Performance e marcadores:
   a. `@pytest.mark.e2e` em todos os 4 testes?
   b. Marcador `e2e` registrado em `pyproject.toml`?
   c. Saída de `pytest -m e2e tests/e2e/test_m3_full_cycle.py --timeout=30`:
      4 PASSED em < 30 s (cole o trecho de tempo)?
   d. `pytest-timeout` em dev deps se não estava antes?

7. Qualidade dos testes:
   a. Nenhum `sleep()` nos testes?
   b. `asyncio_mode = "auto"` em uso (sem `@pytest.mark.asyncio`)?
   c. Determinismo: `FakeGenerator` usa `question_id + llm + seed` para output
      (mesma entrada → mesma saída)?
   d. Zero rede/GPU: nenhum import de adapter real de rede nos testes?

8. Arquivo golden `tests/golden/e2e_m3_expected.json`:
   a. Presente e válido (JSON parsável)?
   b. Contém `n_generated`, `n_evaluated`, `n_judged`, `n_rows_parquet`,
      `schema_columns`?
   c. `schema_columns` inclui `row_id`, `question_id`, `final_score`, `rubric_biomed_score`?

9. DoD §14.2:
   a. `from __future__ import annotations` no topo?
   b. Type hints em fixtures e helpers?
   c. `ruff check .` verde?
   d. `mypy --strict src` verde (tests/ não precisa)?
   e. `pytest --cov=src --cov-fail-under=85` PASS (cole o relatório)?
   f. `lint-imports` verde?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Cole a saída completa de:
  `pytest -m e2e tests/e2e/test_m3_full_cycle.py -v --timeout=30`
  `pytest --cov=src --cov-fail-under=85 -n 4 -q` (sumário final)
Confirme que o M3 está completo: TAREFA-301..310 todas PASS.
~~~
