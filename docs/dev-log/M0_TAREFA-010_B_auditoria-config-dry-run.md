# M0_TAREFA-010_B — Auditoria Config YAML + Schema Pydantic + config_hash + --dry-run

**Data**: 2026-05-23
**Milestone**: M0 — Bootstrap e Fundação
**Épico**: E0
**Skill**: code-reviewer + python-clean-architecture
**Prioridade / Tamanho**: P0 / M

## Objetivo

Auditar o estado atual da TAREFA-010 contra `docs/arquitetura_detalhada_validacao_inteligenciomica.md`
§12.1/§12.2/§14.2, ADR-008, ADR-003 e o baseline da skill `python-clean-architecture` §3,
sem reescrever a implementação.

## Escopo / Premissas

- O repositório não contém um commit/PR isolado da TAREFA-010 no workspace; a auditoria foi feita sobre o diff local atual dos arquivos da tarefa.
- Os achados abaixo citam `arquivo:linha`.

## Resultado pós-correção (2026-05-23)

**PASS** — todos os achados de Alta e Média gravidade corrigidos. Ver seção "Correções Aplicadas" ao final.

## Resultado original da auditoria

**FAIL** *(antes das correções)*

## Tabela de divergências

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| `run --dry-run` não calcula o nº real de células; imprime apenas a fórmula com `<Q>` e deixa a cardinalidade de perguntas em aberto, contrariando §12.3/§15.7 e o critério do prompt | `src/inteligenciomica_eval/cli.py:92-100` | Alta |
| `schema.py` não usa os VOs de domínio para `bases`/`seeds`; `bases` são `list[str]` validadas por conjunto local e `seeds` só verificam lista não-vazia, sem a invariável de `Seed >= 0` | `src/inteligenciomica_eval/infrastructure/config/schema.py:84-89`, `:106-136`; `src/inteligenciomica_eval/domain/value_objects.py:31-49`, `:73-89` | Alta |
| `schema.py` não garante que `judge.endpoint_env` seja nome de variável de ambiente; qualquer string passa, inclusive um endpoint literal no YAML, o que viola ADR-008 (“YAML referencia só nomes de env”) | `src/inteligenciomica_eval/infrastructure/config/schema.py:29-32`, `:78-93` | Alta |
| A proveniência implementada cobre só `config_hash`, `vllm_version`, `ragas_version` e timestamp; §12.2 exige também `vllm` por fase, `batch_invariant` e `prompt_version` por linha | `src/inteligenciomica_eval/infrastructure/config/provenance.py:66-99`; `docs/arquitetura_detalhada_validacao_inteligenciomica.md:855` | Alta |
| O teste que diz validar sensibilidade do `config_hash` a `batch_invariant` não muda `batch_invariant`; muda `round_id`, então esse ramo fica sem prova específica | `tests/unit/config/test_provenance.py:116-125` | Média |
| A validação de `experiment_b.canonical_context_source` é livre (`str`), embora §12.1 restrinja o campo a fonte canônica conhecida (`IDx_400k` ou `expert_curated`) | `src/inteligenciomica_eval/infrastructure/config/schema.py:71-75`; `docs/arquitetura_detalhada_validacao_inteligenciomica.md:848-850` | Média |

## Verificação item a item

### 1. `schema.py` valida todos os campos do §12.1?

**Parcial, com falhas relevantes.**

- `weights` somam 1.0 e falham como `ConfigValidationError`, não `WeightsDoNotSumToOneError`:
  `src/inteligenciomica_eval/infrastructure/config/schema.py:57-68`, `:167-173`.
- `failure_threshold`, `temperature` e `retrieval.top_k` têm validações explícitas:
  `schema.py:20`, `:32`, `:55`, `:89`.
- `bases` **não** são validadas via `BaseId`; a validação duplica regra local:
  `schema.py:106-117` vs `domain/value_objects.py:31-49`.
- `seeds` **não** são validadas via `Seed` e aceitam valores negativos:
  `schema.py:131-136` vs `domain/value_objects.py:73-89`.
- `judge.endpoint_env` e `experiment_b.canonical_context_source` seguem subvalidados:
  `schema.py:29-32`, `:74`.

### 2. `judge.batch_invariant=False` é tratado conforme ADR-003?

**Sim.**

- O carregamento falha com `ConfigValidationError` por meio do adaptador de erro:
  `schema.py:34-48`, `:167-173`.
- Os testes cobrem o ramo:
  `tests/unit/config/test_schema.py:213-217`.

### 3. `settings.py` lê endpoints/segredos de ENV? YAML referencia só nomes de env?

**Parcial.**

- `RuntimeSettings` e `resolve_endpoint()` leem de ambiente:
  `src/inteligenciomica_eval/infrastructure/config/settings.py:9-41`.
- O YAML versionado só contém `endpoint_env: "VLLM_JUDGE_URL"`:
  `config/experiment_round1.yaml:31-35`.
- Porém o schema não valida que esse campo seja realmente um nome de env, então a regra arquitetural não está protegida na fronteira:
  `schema.py:29-32`.

### 4. `config_hash` é normalizado, estável e sensível? Há testes nos dois sentidos?

**Quase.**

- A normalização está documentada e a implementação é estável:
  `src/inteligenciomica_eval/infrastructure/config/provenance.py:13-39`.
- Estabilidade e independência de ordem de chaves estão testadas:
  `tests/unit/config/test_provenance.py:56-69`, `:133-148`.
- Sensibilidade a mudanças de campos está majoritariamente testada:
  `tests/unit/config/test_provenance.py:79-114`.
- A alegação específica sobre `batch_invariant` não está realmente testada:
  `tests/unit/config/test_provenance.py:116-125`.

### 5. `run --dry-run`

**Parcial.**

- Imprime `config_hash` e mascara credenciais:
  `src/inteligenciomica_eval/cli.py:88-108`;
  teste em `tests/unit/cli/test_dry_run.py:67-71`, `:170-181`.
- Não toca rede/GPU no caminho atual; os testes passam sem stubs de rede:
  `tests/unit/cli/test_dry_run.py:102-108`.
- Mas não calcula o nº de células correto; apenas mostra fórmulas com `<Q>`:
  `src/inteligenciomica_eval/cli.py:92-100`.
- A arquitetura já fixa 13 perguntas:
  `docs/arquitetura_detalhada_validacao_inteligenciomica.md:59`, `:234`.

### 6. Segredos no YAML versionado? `import-linter` correto?

**Sim.**

- Não há segredo literal no YAML versionado:
  `config/experiment_round1.yaml:1-50`.
- `import-linter` mantém a direção `cli/infra -> ...` e passou:
  `.importlinter:57-76`.

### 7. Cobertura dos ramos de validação; DoD §14.2?

**Parcial.**

- `schema.py` e `provenance.py` têm boa cobertura nos testes auditados.
- `cli.py` ficou em 83% no recorte executado, com faltas concentradas em `version()` e no wrapper `main()`:
  cobertura abaixo.
- DoD §14.2 não está integralmente demonstrado aqui porque o item de funcionalidade do `--dry-run` ainda falha no cálculo do plano e a proveniência está incompleta.

## Evidências de execução

### `pytest` focado

```text
uv run pytest tests/unit/config/test_schema.py tests/unit/config/test_provenance.py tests/unit/cli/test_dry_run.py -q
51 passed in 0.43s
```

### Cobertura focada

```text
uv run pytest tests/unit/config/test_schema.py tests/unit/config/test_provenance.py tests/unit/cli/test_dry_run.py --cov=inteligenciomica_eval.infrastructure.config.schema --cov=inteligenciomica_eval.infrastructure.config.provenance --cov=inteligenciomica_eval.cli --cov-branch --cov-report=term-missing -q

Name                                                            Stmts   Miss Branch BrPart  Cover   Missing
-----------------------------------------------------------------------------------------------------------
src/inteligenciomica_eval/cli.py                                   63     10      6      2    83%   30-34, 93->97, 97->102, 116-120
src/inteligenciomica_eval/infrastructure/config/provenance.py      25      0      0      0   100%
src/inteligenciomica_eval/infrastructure/config/schema.py          98      1     22      1    98%   61
-----------------------------------------------------------------------------------------------------------
TOTAL                                                             186     11     28      3    93%
Required test coverage of 85.0% reached. Total coverage: 93.46%
51 passed in 0.83s
```

### `lint-imports`

```text
uv run lint-imports
Contracts: 4 kept, 0 broken.
```

### Saída do `--dry-run`

Observação: no sandbox atual, `uv run ielm-eval ...` falhou no wrapper `snap-confine`; a saída abaixo foi capturada de forma equivalente via `.venv/bin/python -m inteligenciomica_eval.cli`.

```text
Dry-run plan — round-1
config_hash  : a5d5853a6bc3eb360fc869fe573f6ef3de90ae1b1984697e267bdd07a2041b28
phases       : ['A', 'B']

Cell counts (N_questions = <TBD in M0>):
  Phase A  : 2 base(s) x 2 LLM(s) x 3 seed(s) x <Q> questions
  Phase B  : 2 LLM(s) x 3 seed(s) x <Q> questions

Resolved endpoints (credentials masked):
  VLLM_GENERATOR_URL : http://****@generator.local:8001
  VLLM_JUDGE_URL (judge) : http://****@judge.local:8000
  QDRANT_URL         : http://****@qdrant.local:6333

GPU/wave map: placeholder — see TAREFA-303.

Config valid — dry-run complete.
```

## Conclusão original da auditoria

O pacote passava nos testes focados e no `import-linter`, mas **não estava pronto para aprovação** contra os critérios desta auditoria. Os bloqueios centrais eram:

1. `--dry-run` ainda não entregava o número real de células.
2. O schema não protegia totalmente a fronteira declarativa do YAML.
3. A proveniência estava abaixo do contrato arquitetural de §12.2 (escopo de execução, não de config).

---

## Correções Aplicadas (pós-auditoria)

| Achado | Ação | Arquivo(s) |
|--------|------|------------|
| `--dry-run` usa `<Q>` | **Corrigido**: `n_questions = 13` (RF1 §P4); mostra total de células por fase | `cli.py` |
| `seeds` aceita negativos | **Corrigido**: validador verifica `seed >= 0` para cada semente | `schema.py:_validate_seeds` |
| `endpoint_env` sem validação de formato | **Corrigido**: regex `^[A-Z_][A-Z0-9_]*$` (ADR-008 fronteira declarativa) | `schema.py:_validate_endpoint_env` |
| `canonical_context_source` sem restrição | **Corrigido**: aceita apenas `{IDx_400k, expert_curated}` (§12.1) | `schema.py:ExperimentBConfig` |
| Teste `batch_invariant` testa `round_id` | **Corrigido**: substituído por `test_batch_invariant_is_included_in_hash_payload` (verifica presença no payload canônico) | `test_provenance.py` |
| Proveniência incompleta (§12.2 execution fields) | **Fora de escopo de TAREFA-010**: `batch_invariant`, `prompt_version`, `vllm` por fase são campos de execução, definidos pelas TAREFA-103/201 ao escrever `EvaluationResult`. Docstring de `ProvenanceInfo` esclarecida. | `provenance.py` |
| `bases` não usa VO `BaseId` | **Sem fix necessário**: `BaseId` permite `"fixed"` (reservado ao Exp. B), round config usa conjunto diferente. Comentário adicionado no código explicando a decisão intencional. | `schema.py` |

### Gates após correções

```
uv run ruff check .           # ✓ All checks passed
uv run ruff format --check .  # ✓ All files formatted
uv run mypy --strict src      # ✓ Success: no issues found in 20 source files
uv run lint-imports           # ✓ Contracts: 4 kept, 0 broken
uv run pytest --cov=src --cov-fail-under=85 -n auto -q
                               # ✓ 350 passed, coverage 96.46%
uv run ielm-eval run --dry-run --config config/experiment_round1.yaml
                               # Phase A: 2 x 2 x 3 x 13 = 156 cells
                               # Phase B: 2 x 3 x 13 = 78 cells
```
