# M0_TAREFA-007_A — RankScoreCalculator

**Data**: 2026-05-23
**Milestone**: M0 — Bootstrap e Domínio Core
**Épico**: E0
**Skill**: ml-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Implementar o serviço de domínio `RankScoreCalculator` em
`src/inteligenciomica_eval/domain/services/rank_score.py`, que computa o RankScore
executivo de uma configuração de modelo segundo a fórmula §7.3 do documento-base:

```
RankScore = 0.50*MedianScore + 0.20*(1 - FailureRate) + 0.15*WinRate
          - 0.15*CriticalFailureRate
```

---

## Arquivos Criados / Modificados

| Arquivo | Ação |
|---------|------|
| `src/inteligenciomica_eval/domain/services/rank_score.py` | Criado |
| `src/inteligenciomica_eval/domain/services/__init__.py` | Modificado — expõe `RankScoreCalculator`, `RankScoreInputs`, `RANK_DEFAULT_WEIGHTS` |
| `tests/unit/domain/services/test_rank_score.py` | Criado |
| `tests/golden/rank_score_cases.json` | Criado |

---

## Decisões Técnicas

### 1. DTO `RankScoreInputs` (frozen dataclass)

Escolhido sobre a alternativa de 4 keyword args por clareza de intenção e
facilidade de serialização futura. Os 4 campos (`median_score`, `failure_rate`,
`win_rate`, `critical_failure_rate`) aceitam `NaN` para sinalizar métrica
não computável (ADR-007).

### 2. Sem restrição de soma == 1.0 nos pesos

A validação de pesos no `FinalScoreCalculator` exige `|sum - 1.0| < tolerância`
porque todos os 6 termos são aditivos e o resultado deve permanecer em `[0,1]`.
O `RankScoreCalculator` tem semântica diferente:

- Um dos 4 termos é **subtrativo** (`- w_p * critical_failure_rate`).
- Um dos termos usa transformação `(1 - failure_rate)`.
- O resultado pode ser **negativo** legitimamente (sinal clínico §7.3).

Portanto, exigir `sum == 1` seria semanticamente errado. A restrição adotada é:
cada peso deve ser um `float` finito e `>= 0`.

### 3. Reutilização de `WeightsDoNotSumToOneError`

A especificação proíbe criar novas exceções sem necessidade. A exceção existente
é reutilizada para o caso de peso inválido (negativo/NaN/inf), documentada via
docstring como "aqui a semântica é 'peso inválido', não 'soma errada'".

### 4. Fallback para `DEFAULT_WEIGHTS` em chaves ausentes

O construtor aceita mapeamentos parciais. O método `compute` usa
`self._weights.get(key, DEFAULT_WEIGHTS[key])` para qualquer chave não
fornecida, permitindo overrides seletivos sem especificar os 4 pesos.

### 5. Sem clamp no RankScore

A especificação §7.3 afirma explicitamente que o `RankScore` pode ser negativo.
O VO `RankScore` (TAREFA-003) já aceita valores negativos finitos. Nenhum clamp
ou normalização é aplicado após o cálculo.

---

## Problemas Encontrados e Soluções

### P1 — Ruff RUF002/RUF003: MINUS SIGN ambíguo

Docstrings e comentários usavam o caractere Unicode `−` (U+2212, MINUS SIGN)
copiado do enunciado. Substituído pelo ASCII `-` (U+002D, HYPHEN-MINUS).

### P2 — Ruff B007: variável de loop não usada

A validação de valores usava `for key, val in weights.items():` mas `key` não
era referenciado. Renomeado para `_key` conforme convenção Ruff.

### P3 — `test_construction_stores_defensive_copy` falhando

O teste verificava que `result.value == 0.50` com `failure_rate=0.0`,
`win_rate=0.0`, `critical_failure_rate=0.0`. Mas o `compute` usa defaults para
as chaves não fornecidas; com `failure_rate=0.0`, o termo `one_minus_failure`
(default 0.20) contribui com `0.20*(1-0.0) = 0.20`, totalizando 0.70, não 0.50.

Solução: usar `failure_rate=1.0` para zerar o termo `one_minus_failure`, isolando
o termo `median`. O expected correto passa a ser `0.50 * 1.0 = 0.50`.

### P4 — Caminho de cobertura errado

O flag `--cov=src/...` não é interpretado como módulo quando o `src` não está no
`PYTHONPATH` da forma esperada pelo coverage. Usar `--cov=inteligenciomica_eval`
(módulo) ou simplesmente `--cov=src` para cobrir todo o pacote.

---

## Validação (DoD)

```
uv run ruff check .                          ✅ 0 errors
uv run ruff format --check .                 ✅ já formatado
uv run mypy --strict src                     ✅ 0 issues
uv run lint-imports                          ✅ 4 contratos KEPT
uv run pytest --cov=src --cov-fail-under=85  ✅ 291 passed, 95.95% coverage
```

Cobertura do módulo `rank_score.py`: **100% lines + 100% branches**.

---

## Critérios de Aceitação — Verificação

| Critério | Resultado |
|----------|-----------|
| CriticalFailureRate alta produz RankScore negativo (sem clamp) | ✅ `case_02` (−0.15), `case_05` (−0.065), `test_compute_worst_config_is_negative`, `test_compute_high_critical_failure_is_negative` |
| Golden ≥ 5 casos com expected calculado independentemente | ✅ 7 casos (2 negativos, 2 NaN, 3 positivos) |
| Bordas: config perfeita ⇒ 0.85; config péssima ⇒ −0.15; NaN ⇒ NaN | ✅ `case_01`, `case_02`, `case_06`, `case_07` |
| Cobertura line+branch ≥ 95% | ✅ 100% |
| Property-based monotonicidade CriticalFailureRate | ✅ `test_hypothesis_increasing_critical_never_increases_rank_score` (400 exemplos) |
| Property-based monotonicidade MedianScore | ✅ `test_hypothesis_increasing_median_never_decreases_rank_score` (400 exemplos) |

---

## Observações para Próximas Tarefas

- O `RankScoreInputs` é um DTO de domínio puro. Futuros serviços de agregação
  (ex.: comparação entre configurações) constroem `RankScoreInputs` a partir de
  coleções de `EvaluationResult` — ponto de extensão natural na camada
  `application/`.
- A constante `RANK_DEFAULT_WEIGHTS` foi exposta no `__init__.py` do pacote de
  serviços sob alias para evitar colisão com `DEFAULT_WEIGHTS` do `FinalScore`.
  Se o número de serviços crescer, considerar sub-namespaces ou imports diretos
  dos módulos ao invés do `__init__`.
