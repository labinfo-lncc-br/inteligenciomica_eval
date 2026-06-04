# Prompt M3 — TAREFA-310 (Claude Code ↔ ChatGPT Codex)

**Milestone:** M3 — Rodada 1 completa + orquestração das 4 GPUs (**última tarefa / gate de saída**)
**Tarefa:** TAREFA-310 — E2E gate do M3: ciclo completo com fakes + Parquet real, sem GPU/rede
**Documentos de referência:**
- `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1, §§ 4, 5.3, 14.6)
- `prompts_m3_tarefas_301_310.md` — TAREFA-310 original (escopo de 12 células A+B + ADR-012)
- `prompts_m3_tarefa_309.md` — fornece `build_fake_container` e `config/questions.yaml`
**Formato:** **Prompt A (implementação — Claude Code)** + **Prompt B (verificação — ChatGPT Codex)**.
**Épico coberto:** E3 — **encerramento do M3**.

> **Pressupõe** que **TAREFA-301..309** estão mergeadas e verdes — em especial o
> `build_fake_container` (TAREFA-309), o loader `load_questions` lendo
> `config/questions.yaml`, o `WaveSchedulerService` (TAREFA-303, ADR-012), o
> `RunExperimentUseCase` com `progress_callback`/graceful shutdown (TAREFA-307) e o
> `FakeVLLMServerManager` (TAREFA-011).
> **O M5 permanece adiado** — nenhum módulo de M5 é importado ou referenciado aqui.
> Convenções de M0–M3 continuam valendo (DoD §14.2; `from __future__ import annotations`;
> `import-linter`; libs proibidas em `domain`/`application`).

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

O avanço **nunca é automático**: ocorre somente com a **minha autorização explícita** e
após o `add` / `commit` / `push` no GitHub. O **`CLAUDE.md`** padroniza os relatórios em
`docs/dev-log/` e deve ser mantido atualizado.

> **Início desta tarefa:** execute a **Parte A (Claude Code)** abaixo e produza o
> relatório. A **Parte B (ChatGPT Codex)** roda em seguida (relatório + diff + saída do
> pytest). Itere A↔B até PASS. Esta é a **última tarefa do M3**: o PASS de ambos, com a
> confirmação de que TAREFA-301..310 estão verdes, **encerra o gate de saída do M3**.

---

## Nota de operacionalização — escopo do gate (TAREFA-310)

Decisão fixada (gate **forte**, restaurado do 310 original):

### 1. Dimensão do cenário — 12 células (Fases A + B)

- **2 perguntas** (carregadas de `config/questions.yaml` via `load_questions`, primeiras 2),
  **2 bases**, **2 LLMs stub**, **1 seed**.
- **Fase A:** perguntas(2) × bases(2) × LLMs(2) × seeds(1) = **8 células**.
- **Fase B:** perguntas(2) × base_fixed(1) × LLMs(2) × seeds(1) = **4 células**.
- **Total: 12 células** (A + B somados, não multiplicados).
- As perguntas vêm do arquivo real (`config/questions.yaml`) — **não** strings ad-hoc;
  o teste prova que o loader e o arquivo funcionam no contexto E2E.

### 2. Componentes reais vs fakes (zero GPU/rede)

- **Reais:** `ParquetStorage(tmp_path)` (schema §5.3), `FinalScoreCalculator`,
  `RankScoreCalculator`, `AggregationService` (domínio), `WaveSchedulerService`
  (aplicação), as 3 passadas UC + `RunExperimentUseCase` (aplicação).
- **Fakes (TAREFA-011):** `StubRetriever`/`FakeGoldChunkReader`, `FakeGenerator`,
  `FakeMetricSuite`, `FakeRubricJudge`, `FakeDeterministicMetric`,
  `FakeVLLMServerManager` (simula start/wait_healthy/stop sem subprocesso).
- Montagem via `build_fake_container` (TAREFA-309) + `writer`/`reader` substituídos pelo
  `ParquetStorage(tmp_path)` por `dataclasses.replace` (o container é frozen).
- Determinismo: `FakeGenerator` deriva saída de `question_id + llm + seed`
  (mesma entrada → mesma saída → idempotência verificável). Sem `sleep()`.

### 3. ADR-012 (juiz residente + ondas) — checagem mantida

O gate **verifica a orquestração** (objetivo central do M3), via a sequência de chamadas
registrada no `FakeVLLMServerManager`:
- **Juiz residente** (ADR-012): `start` do servidor-juiz chamado **uma única vez** e
  **não** encerrado entre ondas de geradores (permanece up durante toda a geração).
- **Geradores em ondas** (ADR-012, default concorrente 3+2; aqui com 2 LLMs, conferir o
  layout que o `WaveSchedulerService` de fato produz para 2 modelos).
- **Desacoplamento geração/julgamento** (ADR-004): a passada de julgamento ocorre após a
  geração concluir. A asserção exata da ordem deve **corresponder ao que TAREFA-303/307
  implementam** (o auditor confere contra o código real) — registrar no relatório a
  sequência observada de `start/wait_healthy/stop`.
- `wait_healthy` (não `wait_until_ready`) é o método do `VLLMServerManagerPort` (§5.1).

### 4. Política NaN (ADR-007) e idempotência (ADR-009)

- 1 célula com métrica NaN → `final_score` NaN → **excluída da agregação**
  (`ConfigAggregate.n_excluded_nan > 0`), sem impedir o restante.
- 2ª execução com o mesmo `run_id` → `n_generated == 0`, `n_skipped == 12`; contagem de
  linhas no Parquet permanece 12.

### 5. Golden — colunas com nomes reais do §5.3

O `tests/golden/e2e_m3_expected.json` usa os **nomes reais** das colunas (atenção:
`experiment_phase`, **não** `phase`). A asserção de schema é **subconjunto** (as colunas
do golden estão presentes no Parquet), não igualdade exata. Inclui também o RankScore
esperado por `{base, llm}` para o cenário determinístico.

---

## TAREFA-310 — E2E gate M3: ciclo completo (12 células A+B)

**Épico:** E3 · **Skill:** test-engineer · **Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-301..309 (todas mergeadas) — **ESTA É A ÚLTIMA TAREFA DO M3**
**ADRs:** ADR-004 (geração/julgamento desacoplados), ADR-007 (NaN), ADR-009 (idempotência),
ADR-012 (ondas/GPU) · **RNF:** RNF7 (graceful shutdown) · **Camadas:** `tests/e2e`

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §§4, 5.3, 14.6
TAREFA-310 — gate de saída do M3). Skills ativos: test-engineer, python-clean-architecture §1.
TAREFA-301..309 mergeadas e verdes. Este teste FECHA o M3: prova o ciclo completo
(3 passadas + agregação + rank) com Parquet real em tmp_path e serviços de domínio
reais, mas SEM GPU/rede, em < 30 s. VER "Nota de operacionalização — escopo do gate 310".

LEIA ANTES DE CODAR: a assinatura real de `RunExperimentUseCase.execute` (TAREFA-307),
o contrato do `FakeVLLMServerManager` (TAREFA-011: registra start/wait_healthy/stop), o
`ParquetStorage.load(...)` (TAREFA-009) e o schema §5.3 (colunas — atenção a
`experiment_phase`). Confirmar o método de leitura do Parquet exposto pelo storage.

TAREFA: TAREFA-310 — implementar `tests/e2e/test_m3_full_cycle.py` (marcado @pytest.mark.e2e)
com 5 cenários, + `tests/golden/e2e_m3_expected.json`.

ESPECIFICAÇÃO:

O teste usa EXCLUSIVAMENTE `build_fake_container` (TAREFA-309) + `ParquetStorage` real
em tmp_path. Nenhum adapter de rede. Nenhuma GPU.

1. FIXTURES (conftest.py local ou topo do arquivo):
   - round_config_stub: RoundConfig mínima válida — round_id="e2e_m3_round",
     phases=["A","B"], bases=["IDx_400k","ID_230K"], llms=["stub-gen-a","stub-gen-b"],
     seeds=[42], temperature=0.0, retrieval/judge/scoring/experiment_b mínimos válidos,
     `questions` apontando para o `config/questions.yaml` real (ou um YAML de fixture com
     ≥ 2 perguntas, se preferir isolar do arquivo de produção — documente a escolha).
   - questions_stub: list[Question] = load_questions(Path(round_config_stub.questions))[:2]
     (2 primeiras; perguntas REAIS do arquivo, não fabricadas).
   - tmp_storage(tmp_path): ParquetStorage(base_dir=tmp_path, round_id="e2e_m3_round").
   - container: build_fake_container(round_config_stub) com writer/reader substituídos
     pelo tmp_storage via dataclasses.replace.

2. CENÁRIO PRINCIPAL — test_m3_full_cycle_generates_and_evaluates:
   a. RunExperimentUseCase.execute(run_id="e2e_m3_run_1", questions=questions_stub,
      phase="both").
   b. n_generated == 12 (Fase A: 2×2×2×1 = 8; Fase B: 2×1×2×1 = 4).
   c. n_evaluated == 12; n_judged == 12.
   d. Parquet lido via tmp_storage.load(round_id="e2e_m3_round"):
      - 12 linhas; colunas do §5.3 presentes (incl. row_id, run_id, experiment_phase,
        round_id, base, llm, seed, question_id, generated_answer, final_score,
        bertscore_f1, rubric_biomed_score).
      - run_id de todas == "e2e_m3_run_1".
      - 8 linhas com experiment_phase == "A"; 4 com experiment_phase == "B".
   e. Roundtrip fiel: reconstruir EvaluationResult e comparar por
      (row_id, final_score, question_id) com os persistidos.
   f. ExperimentReport.failed_waves == ().
   g. Valores conferidos contra tests/golden/e2e_m3_expected.json (não hardcoded inline).

3. CENÁRIO ADR-012 (ORQUESTRAÇÃO) — test_m3_judge_resident_generators_in_waves:
   - Após a execução, inspecionar a sequência registrada no FakeVLLMServerManager.
   - Asserção (juiz residente): start do servidor-juiz chamado EXATAMENTE 1×; o juiz NÃO
     é encerrado entre ondas de geradores (stop do juiz só no fim, se houver).
   - Asserção (ondas): geradores iniciados/encerrados conforme o plano do
     WaveSchedulerService (≤ 2 ondas); NUNCA juiz e gerador na mesma onda (ADR-003/012).
   - Asserção (ADR-004): a passada de julgamento ocorre após a geração — registrar no
     relatório a sequência observada de start/wait_healthy/stop e confirmar coerência
     com TAREFA-303/307.
   - Usar wait_healthy (não wait_until_ready).

4. CENÁRIO NaN (ADR-007) — test_m3_nan_cell_excluded_from_aggregation:
   - FakeMetricSuite retorna NaN em answer_correctness apenas para
     question_id == questions_stub[0].question_id.
   - final_score da célula NaN == float("nan") no Parquet.
   - AggregateResultsUseCase.execute(...): ConfigAggregate.n_excluded_nan >= 1.
   - RankScore das demais células é válido: assert not math.isnan(rank_scores[0].rank_score).

5. CENÁRIO IDEMPOTÊNCIA (ADR-009) — test_m3_idempotent_second_run:
   - execute(run_id="e2e_m3_idempotent", ...) → 12 células novas.
   - Reexecutar com o MESMO run_id e mesmas perguntas → n_generated == 0,
     n_skipped == 12; contagem de linhas no Parquet permanece 12 (sem duplicatas).

6. CENÁRIO GRACEFUL SHUTDOWN (RNF7) — test_m3_graceful_shutdown_on_sigint:
   - Configurar FakeGenerator para levantar KeyboardInterrupt durante a onda 2.
   - execute(...): onda 1 completa (≥ células da onda 1 persistidas no Parquet);
     FakeVLLMServerManager.stop_calls não-vazio (servidores encerrados);
     nenhuma exceção não tratada propaga (o UC captura e finaliza via flag de shutdown +
     log structlog). O teste NÃO usa pytest.raises.

7. GOLDEN — tests/golden/e2e_m3_expected.json:
   ```json
   {
     "n_generated": 12,
     "n_evaluated": 12,
     "n_judged": 12,
     "n_rows_parquet": 12,
     "n_rows_phase_a": 8,
     "n_rows_phase_b": 4,
     "schema_columns": ["row_id", "run_id", "experiment_phase", "round_id", "base",
                        "llm", "seed", "question_id", "generated_answer", "final_score",
                        "bertscore_f1", "rubric_biomed_score"],
     "rank_scores_by_config": { "<base>::<llm>": <valor recomputado à mão> }
   }
   ```
   O teste verifica contra este arquivo. Recompute ≥ 1 RankScore manualmente (via
   FinalScoreCalculator + AggregationService isolados) e cite o cálculo no comentário.

8. MARCADOR/PERF:
   - @pytest.mark.e2e em todos os testes; marcador `e2e` registrado em pyproject.toml.
   - `pytest -m e2e tests/e2e/test_m3_full_cycle.py --timeout=30` < 30 s
     (adicionar pytest-timeout como dev dep se ausente).

ENTREGÁVEL:
- tests/e2e/test_m3_full_cycle.py (5 testes: full_cycle, adr012_waves, nan, idempotência, shutdown)
- tests/golden/e2e_m3_expected.json
- Atualização de pyproject.toml (marcador e2e + pytest-timeout se necessário)
- Atualização de tests/e2e/_harness.py se necessário
- docs/dev-log/M3_TAREFA-310_A_<slug>.md (relatório + sequência observada do server_manager)

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings no harness.
- asyncio_mode = "auto" (async def test_* basta; sem @pytest.mark.asyncio).
- Determinístico: seeds fixos; FakeGenerator deriva output de question_id+llm+seed;
  freezegun para timestamp se necessário. Zero rede/GPU. Nenhum sleep().

CRITÉRIO DE ACEITAÇÃO (gate de saída do M3):
- `pytest -m e2e tests/e2e/test_m3_full_cycle.py -v --timeout=30` → 5 PASSED em < 30 s
  (cole a saída).
- Principal: 12 linhas (8 A + 4 B); roundtrip fiel; colunas do golden presentes;
  RankScore confere com o golden.
- ADR-012: juiz iniciado 1× e residente; geradores em ondas; julgamento após geração.
- NaN: n_excluded_nan >= 1; RankScore das demais não é NaN.
- Idempotência: 2ª execução n_generated == 0, n_skipped == 12.
- Shutdown: onda 1 completa; stop_calls não-vazio; sem exceção propagada.
- `pytest --cov=src --cov-fail-under=85` (suite completa) ainda PASS.
- `lint-imports` verde (testes não puxam infra de produção para o domínio).
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer + test-engineer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-310 + arquitetura §§14.6/5.3 + ADR-004/007/009/012 + RNF7
+ "Nota de operacionalização 310" + relatório do Claude Code (Parte A) + saída do pytest.

VERIFIQUE, item a item, citando arquivo:linha:

1. Fixtures:
   a. container usa build_fake_container (não build_container)?
   b. writer/reader substituídos por ParquetStorage(tmp_path) via dataclasses.replace
      (não ParquetStorage com path fixo)?
   c. questions_stub = load_questions(Path(config.questions))[:2] (perguntas reais do
      YAML, não strings hardcoded)?

2. Cenário principal:
   a. n_generated == 12 (8 A + 4 B), não 4 nem 20?
   b. Parquet lido via API do storage (não pq.read_table com tree Hive manual)?
   c. 8 linhas experiment_phase=="A" e 4 =="B"? Coluna é `experiment_phase` (não `phase`)?
   d. Roundtrip por (row_id, final_score, question_id)?
   e. ExperimentReport.failed_waves == () asserted?
   f. Valores contra tests/golden/e2e_m3_expected.json (não inline)?

3. Cenário ADR-012:
   a. start do juiz chamado 1× e o juiz NÃO encerrado entre ondas (residente)?
   b. Geradores em ≤ 2 ondas; nunca juiz+gerador na mesma onda?
   c. Julgamento após geração (ADR-004) — sequência observada coerente com TAREFA-303/307?
   d. Usa wait_healthy (não wait_until_ready)?

4. Cenário NaN:
   a. FakeMetricSuite NaN só para questions_stub[0]?
   b. math.isnan(final_score) na célula NaN no Parquet?
   c. ConfigAggregate.n_excluded_nan >= 1?
   d. not math.isnan(rank_scores[0].rank_score) para os restantes?

5. Cenário idempotência:
   a. Mesmo run_id nas duas execuções?
   b. 2ª execução: n_generated == 0 e n_skipped == 12?
   c. Linhas no Parquet permanecem 12?

6. Cenário shutdown:
   a. FakeGenerator levanta KeyboardInterrupt na onda 2 (não na 1)?
   b. Parquet com ≥ células da onda 1 após a interrupção?
   c. FakeVLLMServerManager.stop_calls não-vazio?
   d. Nenhuma exceção propaga (sem pytest.raises)?

7. Golden:
   a. JSON válido com n_generated/n_evaluated/n_judged/n_rows_parquet/n_rows_phase_a/
      n_rows_phase_b/schema_columns/rank_scores_by_config?
   b. schema_columns usa `experiment_phase` (não `phase`)?
   c. Inclui row_id, question_id, final_score, bertscore_f1, rubric_biomed_score?
   d. Pelo menos 1 RankScore recomputado à mão e citado?

8. Perf/marcadores:
   a. @pytest.mark.e2e nos 5 testes; marcador registrado em pyproject.toml?
   b. `pytest -m e2e ... --timeout=30`: 5 PASSED em < 30 s (cole o tempo)?
   c. pytest-timeout em dev deps se não estava antes?

9. Qualidade:
   a. Nenhum sleep()? asyncio_mode="auto" (sem @pytest.mark.asyncio)?
   b. Determinismo: FakeGenerator usa question_id+llm+seed?
   c. Zero rede/GPU: nenhum import de adapter real de rede nos testes?

10. DoD §14.2:
    a. `from __future__ import annotations`? Type hints em fixtures/helpers?
    b. `ruff check .` verde? `mypy --strict src` verde (tests/ não precisa)?
    c. `pytest --cov=src --cov-fail-under=85` PASS (cole o relatório)?
    d. `lint-imports` verde?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade:
BLOQUEADOR | IMPORTANTE | SUGESTÃO).
Este é o gate do M3 — qualquer item 1–6 como FAIL bloqueia o avanço.
Inclua sua recomputação de 1 RankScore. Cole a saída completa de:
  `pytest -m e2e tests/e2e/test_m3_full_cycle.py -v --timeout=30`
  `pytest --cov=src --cov-fail-under=85 -q` (sumário final)
Confirme que o M3 está completo: TAREFA-301..310 todas PASS.
~~~
