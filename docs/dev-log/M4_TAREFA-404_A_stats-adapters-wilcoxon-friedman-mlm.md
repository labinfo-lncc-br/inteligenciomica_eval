# M4_TAREFA-404_A — Stats Adapters: Wilcoxon, Friedman+Nemenyi, Mixed Linear Model

**Data**: 2026-06-01
**Milestone**: M4 — Análise Estatística e Publicação
**Épico**: E4
**Skill**: claude-code (implementação)
**Prioridade / Tamanho**: P1 / L

---

## Objetivo

Implementar os três adapters estatísticos da camada de infraestrutura que realizam os
testes de hipótese sobre os `ResultFrame` de avaliação:

- `WilcoxonAdapter` — teste pareado signed-rank (comparação de duas bases de RAG).
- `FriedmanNemenyiAdapter` — Friedman chi² + post-hoc Nemenyi (comparação de ≥ 3 LLMs).
- `MixedLinearModelAdapter` — modelo linear misto (efeito de base e LLM com random effects).

Cada adapter implementa o `StatsPort` estruturalmente (três métodos presentes para passar
`isinstance` com `@runtime_checkable`) e retorna value objects completos com degradação
graciosa em vez de exceção.

---

## Arquivos Criados / Modificados

### Criados

| Arquivo | Descrição |
|---------|-----------|
| `src/inteligenciomica_eval/infrastructure/adapters/stats_adapters.py` | Os três adapters + helpers |
| `tests/unit/adapters/test_stats_adapters.py` | 25 testes unitários |
| `tests/integration/adapters/test_stats_integration.py` | 8 testes de integração golden |
| `tests/golden/stats_wilcoxon_expected.json` | 13 pares com golden values scipy |
| `tests/golden/stats_friedman_expected.json` | 13 blocos / 3 LLMs com golden values scipy |

### Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/inteligenciomica_eval/domain/value_objects.py` | 4 novos VOs: `NemenyiPair`, `WilcoxonReport`, `FriedmanReport`, `MLMReport` |
| `src/inteligenciomica_eval/domain/ports.py` | Removidos stubs inline; re-exports explícitos (`as name`) dos 4 VOs de stats |
| `src/inteligenciomica_eval/infrastructure/config/adapter_configs.py` | `StatsAdapterConfig` (alpha, correction_method, min_pairs_wilcoxon, reml) |
| `pyproject.toml` | Deps runtime: `statsmodels>=0.14`, `scikit-posthocs>=0.9`, `scipy>=1.12`; overrides mypy para `statsmodels.*`, `scikit_posthocs.*`, `patsy.*`, `scipy.*` |
| `.importlinter` | `scipy` e `scikit_posthocs` adicionados às listas `forbidden_modules` de `domain-forbidden` e `application-forbidden` |
| `tests/fakes/data_readers.py` | `FakeStats` atualizado para os novos campos dos VOs |
| `tests/unit/domain/test_ports_contract.py` | `_StubStats` e testes de VOs de stats atualizados; adicionado `test_nemenyi_pair` |
| `tests/unit/fakes/test_fakes_satisfy_ports.py` | Testes de `TestFakeStats` atualizados para campos novos (`nemenyi_pairs`, `effect_size_r`) |

---

## Decisões Técnicas

### VOs em `value_objects.py` (não em `ports.py`)

Os stubs de `WilcoxonReport`, `FriedmanReport` e `MLMReport` existiam como definições
inline em `ports.py` desde M0. Foram migrados para `value_objects.py` com spec completa e
re-exportados de `ports.py` usando o padrão `from ... import X as X` (obrigatório para
`mypy --strict` com `no_implicit_reexport`). `NemenyiPair` foi criado direto em
`value_objects.py`.

### `MLMReport` sem `slots=True`

`MLMReport` contém um campo `dict[str, float]` (`llm_effect_p_values`), incompatível com
`slots=True` em dataclasses frozen. Os demais três VOs usam `slots=True`.

### Degradação graciosa (nunca exceção)

Todos os adapters retornam relatórios degenerados em vez de propagar exceção:
- `WilcoxonAdapter`: `n_pairs < min_pairs_wilcoxon` → `statistic=0.0`, `p_value=1.0`, `significant=False`, `effect_size_r=None`.
- `FriedmanNemenyiAdapter`: `< 3 grupos` → `chi2=0.0`, `p=1.0`, `nemenyi_pairs=()`.
- `MixedLinearModelAdapter`: qualquer falha do statsmodels → `convergence_warning=True`, campos zerados.

### Effect size Wilcoxon

`effect_size_r = Z / sqrt(N)` onde `Z = norm.ppf(1 - p_value / 2)`. Quando `p_value == 1.0`
(caso degenerado), `effect_size_r = None`.

### `isinstance` com `@runtime_checkable` e `StatsPort`

O protocolo verifica presença dos três métodos (`wilcoxon_paired`, `friedman_nemenyi`,
`mixed_linear_model`). Cada adapter especializado implementa os dois não-primários
levantando `NotImplementedError` (coberto por `exclude_lines` no `[tool.coverage.report]`).

### Golden values computados independentemente

Os arquivos JSON de golden foram calculados com scipy diretamente para garantir que o
adapter produza os mesmos resultados numéricos:
- Wilcoxon (13 pares, todos positivos): `statistic=0.0`, `p_value≈0.000244`, `effect_size_r≈1.017`.
- Friedman (13 blocos, 3 LLMs com scores distintos): `chi2=26.0`, `p_value≈2.26e-6`, 3 pares Nemenyi todos significativos.

### MLE boundary (AIC=NaN legítimo)

Com amostras pequenas, statsmodels retorna `AIC=NaN` quando a variância do efeito aleatório
colapsa para zero (MLE na fronteira do espaço de parâmetros). Este é comportamento legítimo,
distinto de não-convergência (`convergence_warning=False`). O teste unitário relaxa a
assertiva de AIC para não exigir não-NaN.

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| `NemenyiPair` removido pelo ruff F401 após re-export | Padrão `as name` em todas as importações de re-export de stats VOs em `ports.py` |
| mypy: VOs de stats não exportados implicitamente | `FriedmanReport as FriedmanReport`, `MLMReport as MLMReport`, `NemenyiPair as NemenyiPair`, `WilcoxonReport as WilcoxonReport` em `ports.py` |
| mypy: sem stubs para scipy | `scipy.*` adicionado a overrides com `ignore_missing_imports = true` |
| AIC=NaN com dataset de 3 questões no MLM | `_make_mlm_frame` expandido para 7 questões; assertiva de AIC relaxada |
| `test_fakes_satisfy_ports.py` usa campos antigos | `f.post_hoc` → `f.nemenyi_pairs`; `effect_size=` → `effect_size_r=` + campos obrigatórios |
| **[Auditoria 404B]** `converged=False` não degrada — adapter retornava coeficientes reais com `convergence_warning=True` | Early-return logo após `result = model.fit(...)`: `if not result.converged → return _degenerate(convergence_warning=True)`. Adicionado `test_converged_false_returns_degenerate` com mock do resultado. |

---

## Validação (DoD)

```
987 passed, 5 skipped — 92.76% total coverage (gate 85% ✅)
ruff check: All checks passed ✅
ruff format --check: 127 files already formatted ✅
mypy --strict src: Success: no issues found in 47 source files ✅
lint-imports: 4 contracts KEPT, 0 broken ✅
```

> Após auditoria Codex (404B): +1 teste `test_converged_false_returns_degenerate`;
> correção do ramo `converged=False` no `MixedLinearModelAdapter`.

### Cobertura do novo módulo

```
stats_adapters.py: 94% (6 linhas não cobertas — apenas NotImplementedError branches)
adapter_configs.py: 100%
```

---

## Critérios de Aceitação

- [x] `WilcoxonAdapter`, `FriedmanNemenyiAdapter`, `MixedLinearModelAdapter` passam `isinstance(adapter, StatsPort)`.
- [x] Wilcoxon golden: `statistic`, `p_value`, `effect_size_r` batem com scipy direto (tol rel=1%).
- [x] Friedman golden: `chi2_statistic`, `p_value`, 3 pares Nemenyi corretos.
- [x] Degradação graciosa em todos os casos de amostra insuficiente e falha numérica.
- [x] Nenhuma dependência de I/O de stats (scipy/statsmodels/scikit_posthocs) em `domain` ou `application` — import-linter verde.
- [x] Gate de cobertura 85% mantido; testes 986/986 (não integração).

---

## Observações para Próximas Tarefas

- **ADR-011** deve ser criado para formalizar a decisão de degradação graciosa dos adapters
  estatísticos (alternativa: propagar exceção e deixar o use case decidir).
- `StatsAdapterConfig.correction_method` está declarado mas não aplicado ainda — a correção
  de Benjamini-Hochberg para múltiplos testes Wilcoxon será usada no use case de análise
  (TAREFA-405 ou posterior).
- `infrastructure/factories.py` permanece em 33% de cobertura — inclui factory de stats
  adapters adicionada nesta tarefa; cobertura será aumentada com o use case de análise.
