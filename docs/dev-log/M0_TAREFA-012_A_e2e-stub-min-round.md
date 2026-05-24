# M0_TAREFA-012_A — E2E stub: rodada mínima em CPU

**Data**: 2026-05-24
**Milestone**: M0 — Esqueleto e Validação Local
**Épico**: E0
**Skill**: test-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Implementar o teste E2E que fecha o M0: rodar uma rodada mínima ponta-a-ponta
usando **apenas fakes/stubs em CPU** (sem GPU, sem rede), materializando Parquet
real + scores + agregados e validando o resultado contra valores esperados
calculados à mão (golden).

---

## Arquivos Criados / Modificados

| Arquivo | Ação |
|---------|------|
| `tests/e2e/test_min_round_stub.py` | Criado — 7 testes `@pytest.mark.e2e` |
| `tests/e2e/_harness.py` | Criado — orquestrador interno do fluxo §3.4 |
| `tests/golden/e2e_min_round_expected.json` | Criado — valores golden do cenário |

---

## Decisões Técnicas

### Cenário mínimo determinístico

| Dimensão | Valores |
|----------|---------|
| Perguntas | `q01` ("O que é RAG?"), `q02` ("O que é embedding?") |
| Base | `IDx_400k` |
| LLMs | `llm-alpha`, `llm-beta` |
| Seeds | `42` |
| Fase | `A` |
| Total de células | 4 (2 perguntas × 1 base × 2 LLMs × 1 seed) |

Uma célula — `(IDx_400k, llm-beta, 42, q02)` — recebe métricas NaN via
`FakeMetricSuite(inject_nan=True)` + `FakeRubricJudge(inject_nan=True)`, exercitando
o caminho ADR-007 de propagação de NaN e a exclusão na agregação.

### rubric_biomed_score normalizado

O `FakeRubricJudge` padrão retorna `score=4.0` (escala 1–5). Para que
`FinalScore` permaneça em `[0.0, 1.0]`, o harness usa um `RubricResult` customizado
com `score=0.80` (correspondente a 4/5). Isso é declarado no golden
(`normal_metrics.rubric_biomed_score = 0.80`).

### FinalScore esperado (calculado à mão)

```
FinalScore = 0.45 × 0.80 + 0.20 × 0.90 + 0.15 × 0.80
           + 0.10 × 0.70 + 0.05 × 0.85 + 0.05 × 0.88
           = 0.360 + 0.180 + 0.120 + 0.070 + 0.0425 + 0.044
           = 0.8165
```

### Tolerância float32

O Parquet armazena métricas em `float32`; a comparação usa `pytest.approx(abs=1e-4)`
para acomodar arredondamento (~7 dígitos significativos).

### Harness: `tests/e2e/_harness.py`

Função `run_min_round(*)` — interface keyword-only, sem antecipação de use-cases de M1+.
Wira diretamente: StubRetriever → FakeGenerator → FakeMetricSuite / FakeRubricJudge →
FinalScoreCalculator → ParquetStorage → AggregationService + RankScoreCalculator.

Recebe `nan_cells: frozenset[NanCellKey]` (tipo `tuple[str, str, int, str]`) para
selecionar por célula qual suite de métricas usar.

Retorna `(newly_appended, aggregates)`:
- `newly_appended`: apenas linhas escritas na chamada corrente (idempotência — linhas
  já existentes são puladas e excluídas do retorno).
- `aggregates`: agregação completa lida do storage após a passada.

### Idempotência (ADR-009)

O harness chama `storage.exists(row_id)` antes de cada célula. Na segunda execução
com o mesmo `run_id`, todas as células já existem → `generator.calls == 0` → nenhuma
linha duplicada no Parquet.

---

## Valores Golden

### Métricas normais

| Campo | Valor |
|-------|-------|
| `answer_correctness` | 0.80 |
| `answer_similarity` | 0.75 |
| `faithfulness` | 0.90 |
| `context_precision` | 0.85 |
| `context_recall` | 0.70 |
| `answer_relevancy` | 0.88 |
| `bertscore_f1` | 0.82 |
| `rubric_biomed_score` | 0.80 |
| **`final_score`** | **0.8165** |

### Agregados por config

| Config | n_obs | n_excl | win_rate | rank_score |
|--------|-------|--------|----------|------------|
| IDx_400k / llm-alpha | 2 | 0 | 0.75 | 0.72075 |
| IDx_400k / llm-beta | 1 | 1 | 0.25 | 0.64575 |

**win_rate** calculado cruzando as duas configs por pergunta:
- q01: empate 0.8165 = 0.8165 → cada config ganha 0.5
- q02: llm-beta sem observação válida → llm-alpha ganha 1.0 inteiro

**rank_score** (pesos canônicos §7.3):
```
llm-alpha = 0.50 × 0.8165 + 0.20 × (1 - 0) + 0.15 × 0.75 - 0.15 × 0.0 = 0.72075
llm-beta  = 0.50 × 0.8165 + 0.20 × (1 - 0) + 0.15 × 0.25 - 0.15 × 0.0 = 0.64575
```

---

## Problemas Encontrados e Soluções

### 1. `from tests.e2e._harness` falhava com `ModuleNotFoundError`

`tests/` não tem `__init__.py`, portanto pytest o adiciona ao `sys.path` como raiz.
Os sub-pacotes (`fakes/`, `e2e/`, `factories/`) são importáveis como pacotes de
nível superior. Corrigido usando `from e2e._harness import ...` e
`from fakes.X import ...`.

### 2. Ordenação de imports (ruff I001)

ruff isort classifica `fakes.*` e `e2e.*` como third-party (não estão em
`known-first-party`) e os separa dos imports de `inteligenciomica_eval.*` (first-party).
Resolvido aplicando `ruff check --fix` e reordenando: stdlib → third-party (pytest,
fakes, e2e) → first-party (inteligenciomica_eval).

### 3. RUF002: caractere `×` em docstring

O símbolo Unicode `×` (MULTIPLICATION SIGN) é sinalizado como ambíguo pelo ruff.
Substituído por `x` (ASCII) na docstring do harness.

### 4. RUF059: variável `results1` nunca usada

No teste de idempotência o retorno da primeira chamada não é inspecionado.
Renomeado para `_results1` (convenção de variável descartável).

---

## Validação (DoD)

```
uv run ruff check .            # ✅ All checks passed
uv run ruff format --check .   # ✅ 61 files already formatted
uv run mypy --strict src       # ✅ Success: no issues found in 22 source files
uv run lint-imports             # ✅ 4 contracts KEPT
uv run pytest -m e2e -v        # ✅ 7 passed in 0.66s
uv run pytest --cov=src --cov-fail-under=85 -n auto -q
                               # ✅ 540 passed in 4.13s — 96.43% coverage
```

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| `pytest -m e2e` gera Parquet válido (schema §5.3) e RankScore esperado, SEM GPU/rede | ✅ |
| NaN excluído e contado em `n_excluded_nan`; idempotência por run_id comprovada | ✅ |
| Roundtrip Parquet fiel; valores batem com golden | ✅ |
| Tempo de execução baixo (< poucos segundos); roda no CI de CPU | ✅ (0.66s) |

---

## Observações para Próximas Tarefas

- O harness `run_min_round` é reutilizável para cenários com 2 seeds ou 2 bases — basta
  ampliar as listas `base_ids` / `seeds` na chamada.
- O golden JSON está estruturado para suportar múltiplas configs; adicionar mais
  configs apenas requer novos objetos em `"configs"`.
- A separação `(newly_appended, aggregates)` permitirá, em M1, que os use-cases
  retornem exatamente o mesmo contrato — o harness pode ser trocado por chamadas
  reais sem mudar as asserções do teste.
- `rubric_biomed_score` no `MetricVector` é tratado como métrica já normalizada
  para `[0, 1]`; a normalização 4/5 deve ocorrer no adapter RAGAS (M2+), não no
  domínio.
