# M0_TAREFA-008_A — AggregationService (domain/services/aggregation.py)

**Data**: 2026-05-24
**Milestone**: M0 — Core Domain
**Épico**: E0
**Skill**: data-engineer / python-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Implementar `AggregationService` em `src/inteligenciomica_eval/domain/services/aggregation.py`,
que recebe `EvaluationResult` materializados e produz os agregados por configuração
`{base, llm}` (§7.2 doc-base). Serviço de domínio **puro**: stdlib apenas, sem I/O.

---

## Arquivos Criados / Modificados

| Arquivo | Ação |
|---------|------|
| `src/inteligenciomica_eval/domain/services/aggregation.py` | Criado — 250 linhas |
| `src/inteligenciomica_eval/domain/services/__init__.py` | Atualizado — exporta `AggregationService`, `ConfigAggregate` |
| `tests/unit/domain/services/test_aggregation.py` | Criado — 47 testes |
| `tests/golden/aggregation_cases.json` | Criado — 4 casos golden |

---

## Decisões Técnicas

### 1. VO de saída `ConfigAggregate`

`frozen dataclass` com `slots=True` e 12 campos (spec §7.2):
`base`, `llm`, `mean_score`, `median_score`, `min_score`, `iqr`, `failure_rate`,
`critical_failure_rate`, `win_rate`, `rank_score`, `n_observations`, `n_excluded_nan`.

### 2. Método de quantil para IQR

Escolhido `statistics.quantiles(data, n=4, method='inclusive')` (Python ≥ 3.10).
**Motivo**: interpolação linear nos dados ordenados (tipo Tukey/inclusive), amplamente
adotado em análise exploratória. Fórmula: posição do k-ésimo quartil = k/(n-1) × (N-1),
onde N = tamanho da amostra. IQR retorna `NaN` se `n_observations < 2` (IQR
indefinido para observação única).

### 3. `failure_rate` reutiliza `EvaluationResult.is_failure`

Não reimplemente o limiar — delega para `r.is_failure(threshold)`, que retorna `False`
para NaN por design (NaN < threshold = False em Python). Denominador = `n_observations`
(apenas não-NaN), conforme ADR-007.

### 4. `critical_failure_rate` — denominador exclui `flag=None` (ADR-010)

Linhas não anotadas pela Camada 3 têm `critical_failure_flag = None` e são **excluídas
do denominador**. Retorna `NaN` quando nenhuma linha foi anotada (denominador = 0).
Decisão documentada no docstring do VO e nos testes.

### 5. `win_rate` — comparação cross-config por `question_id`

Para cada `question_id`, o score representativo de uma config é a **média dos
FinalScores válidos** para aquele (config, question_id). Configs sem score válido
recebem 0 wins para essa questão. Empate de k configs: cada recebe `1/k` (tie-splitting
por igualdade exata de float — scores gerados pelo mesmo caminho computacional são
bitwise iguais). `win_rate = Σ wins / n_distinct_questions`.

### 6. Injeção de `RankScoreCalculator`

`AggregationService.__init__` recebe a instância de `RankScoreCalculator` (DI).
Isso mantém o serviço testável e desacoplado da configuração de pesos.

### 7. Ordenação determinística da saída

`aggregate_all` retorna `tuple[ConfigAggregate, ...]` ordenado por
`(base.value, llm.value)`. Garante ordem determinística independente da inserção.

---

## Problemas Encontrados e Soluções

### Ruff C420 — dict comprehension desnecessária

`{k: 0.0 for k in config_keys}` → substituído por `dict.fromkeys(config_keys, 0.0)`.

### Ruff F401 — importação não usada no teste

`ConfigAggregate` importado no teste mas não usado diretamente (a type annotation
estava ausente). Removido da importação.

### Ruff format — reformatação automática

Dois arquivos reformatados: `aggregation.py` e `test_aggregation.py`.

---

## Validação (DoD)

```bash
uv run ruff check .                        # ✅ All checks passed
uv run ruff format --check .               # ✅ 45 files already formatted
uv run mypy --strict src                   # ✅ Success: no issues found in 21 source files
uv run lint-imports                        # ✅ 4 contracts KEPT, 0 broken
uv run pytest --cov=src --cov-fail-under=85 -n auto
# ✅ 397 passed | Cobertura total: 96.96% | aggregation.py: 100% line+branch
```

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| Exclui NaN dos cálculos e reporta `n_excluded_nan` — testado | ✅ |
| `failure_rate` usa `EvaluationResult.is_failure` (sem duplicar limiar) | ✅ |
| `critical_failure_rate` ignora `flag=None` no denominador — testado | ✅ |
| `win_rate` correto entre configs, com empate `1/k` — testado com 2-way e 3-way tie | ✅ |
| Método de quantil para IQR documentado (`method='inclusive'`); golden numérico confere | ✅ |
| Cobertura line+branch ≥ 95% do módulo — obtido **100%** | ✅ |
| `import-linter`: 4 contratos KEPT, 0 broken | ✅ |
| `mypy --strict`: sem erros | ✅ |
| Serviço puro: apenas `math`, `statistics`, `collections` (stdlib) | ✅ |

---

## Golden Dataset (4 casos)

| Caso | Cenário | O que valida |
|------|---------|--------------|
| `case_01_two_configs_clear_winner` | Config A domina todas as 3 questões | win_rate=1.0/0.0, failure_rate, critical_rate |
| `case_02_nan_excluded_single_config` | 1 NaN em 3 resultados | n_excluded_nan=1, denominadores corretos |
| `case_03_win_rate_tie_two_configs` | Empate exato em todas as questões | win_rate=0.5 (1/k com k=2) |
| `case_04_all_nan_single_config` | Todos NaN | n_observations=0, todos agregados NaN |

---

## Observações para Próximas Tarefas

- **TAREFA-009**: `ReportingService` ou `ComparisonService` pode consumir
  `tuple[ConfigAggregate, ...]` diretamente de `AggregationService.aggregate_all`.
- O `threshold` é parâmetro de chamada (não fixado no serviço), pronto para
  receber valor de `EvalConfig` da infra (TAREFA-010 já implementado).
- `win_rate` usa média por (config, question_id) como score representativo quando
  há múltiplas seeds. Esta decisão pode ser revisada se a spec for alterada.
