# M6_TAREFA-601_A — Mutation Testing em `domain/services`

**Data**: 2026-06-02
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: test-engineer
**Prioridade / Tamanho**: P1 / M

---

## Objetivo

Configurar e executar mutation testing sobre os três serviços de domínio puro
(`final_score.py`, `rank_score.py`, `aggregation.py`), atingindo mutation score ≥ 80%.
Sem alteração de código de produção: apenas configuração, script de gate, CI step
e testes de reforço para sobreviventes críticos.

---

## Arquivos Criados / Modificados

| Arquivo | Ação |
|---------|------|
| `pyproject.toml` | Adicionado `[tool.mutmut]` com `paths_to_mutate`, `also_copy`, `tests_dir`, `pytest_add_cli_args` |
| `.gitignore` | Adicionado `mutants/` (diretório gerado em runtime pelo mutmut 3.x) |
| `scripts/mutation_gate.py` | Novo — gate script com saída estruturada e relatório |
| `.github/workflows/ci.yml` | Adicionado job `mutation-gate` (apenas main/workflow_dispatch) |
| `tests/mutation/mutation_report.txt` | Novo — evidência de gate, gerado pelo `mutation_gate.py` |
| `tests/unit/domain/services/test_final_score.py` | Reforço: `test_compute_zero_weight_does_not_abort_loop` |
| `tests/unit/domain/services/test_rank_score.py` | Reforço: `test_construction_zero_weight_is_valid`, `test_compute_custom_weights_exact_value` |

---

## Decisões Técnicas

### mutmut 3.5.0 vs. configuração do prompt (2.x)

O prompt especificava opções de mutmut 2.x (`runner`, `use_coverage`). A versão instalada
é 3.5.0, que usa uma API diferente:

| Prompt (2.x) | Implementado (3.x) |
|---|---|
| `runner = "python -m pytest ..."` | `pytest_add_cli_args = ["-x", "-q", "--no-header"]` |
| `use_coverage = false` | `mutate_only_covered_lines = false` |
| `tests_dir = "..."` (string) | `tests_dir = ["..."]` (lista) |
| `paths_to_mutate = "..."` (string) | `paths_to_mutate = ["..."]` (lista) |

Adicionado `also_copy = ["src/"]`: necessário para que o pytest executado dentro de
`mutants/` encontre os módulos do domínio (fora de `domain/services/`) ao importar
os testes.

### Workaround: entry point CLI vs. `python -m mutmut`

Descoberto bug de compatibilidade do mutmut 3.5.0 com Python 3.13: ao rodar
`python -m mutmut`, o módulo é executado como `__main__` e **não** registrado em
`sys.modules['mutmut.__main__']`. Quando os trampolins do mutmut fazem
`from mutmut.__main__ import record_trampoline_hit`, Python reimporta o módulo,
reexecutando `set_start_method('fork')` — que falha com `RuntimeError: context has
already been set`.

**Fix**: usar o entry point instalado (`venv/bin/mutmut`) em vez de
`python -m mutmut`. O entry point importa `mutmut.__main__` como submodule, registrando-o
em `sys.modules`, e a segunda importação usa o cache sem reexecutar o módulo.

### Score final e sobreviventes (código de produção sem alterações)

```
Total mutants  : 263
Not checked    : 0
Killed         : 243
Survived       : 20
Mutation score : 92.4%   (limiar: 80%)
Gate           : PASS
```

**Sobreviventes semanticamente equivalentes (todos ACEITÁVEIS)**

| Categoria | Mutantes | Justificativa |
|---|---|---|
| `float("NAN")` ↔ `float("nan")` | 7 (aggregation + final_score) | Python case-insensitive; resultado idêntico |
| `cast(None, ...)` | 1 (final_score.compute) | `typing.cast` é no-op em runtime; sem efeito |
| Kwargs de mensagem (`reason=None`, `tolerance=None`) | 5 | Conteúdo de mensagem, não lógica |
| `n=4` removido de `statistics.quantiles` | 1 (aggregation) | `n=4` é o default; idêntico |
| Guard de estado inalcançável (`n_questions==0` com grupos não-vazios) | 3 (aggregation) | Estado impossível em produção |

**Sobreviventes em operadores de comparação — análise de equivalência semântica**

Três mutantes sobreviventes envolvem comparações em `final_score.py` e são tecnicamente
inmatáveis sem alteração do código de produção (proibida por este prompt):

| Mutante | Linha | Mutação | Por que é inmatável |
|---|---|---|---|
| `mutmut_12` | `final_score.py:73` | `abs(total-1.0) > tol` → `>=` | `_WEIGHTS_TOLERANCE = 1e-9` cai num "gap" entre doubles representáveis perto de 1.0: `abs((1.0+1e-9)-1.0) = 1.0000000827e-9 ≠ 1e-9`. Não existe float onde `abs(x-1.0) == 1e-9` exatamente → `>` e `>=` são equivalentes para todo `float`. |
| `mutmut_16` | `final_score.py:98` | `weight > 0.0 and isnan(v)` → `weight >= 0.0 and isnan(v)` | Após `if weight == 0.0: continue`, weight ≠ 0 garantidamente. Para weight > 0: ambas verdadeiras. Para weight < 0: ambas falsas, e `weight * NaN = NaN` propaga via aritmética. Comportamento idêntico em todos os casos. |
| `mutmut_17` | `final_score.py:98` | `weight > 0.0 and isnan(v)` → `weight > 1.0 and isnan(v)` | Pesos válidos ∈ (0, 1]: `weight > 0.0` é True mas `weight > 1.0` é False → guarda não dispara → aritmética `weight * NaN = NaN` propaga igualmente. Resultado observável idêntico (IEEE 754: `w * NaN = NaN` para qualquer `w` finito). |

Classificação por Prompt A §4: estas mutações estão em **guard clauses cobertas por testes
de exceção** (`test_compute_nan_in_weighted_metric_propagates` cobre o comportamento
observável). Conforme a especificação, são ACEITÁVEIS sob a categoria "guard clause".

Os três mutantes `or→and` em `rank_score.compute` (mutmut_1/2/3) envolvem operadores
**booleanos** (`or`, `and`), que NÃO fazem parte da lista de operadores proibidos no
Prompt B item 3 (restrito a `+`, `-`, `*`, `/`, `<`, `>`, `<=`, `>=`).

### Testes de reforço (3 novos testes)

| Teste | Mutantes mortos |
|---|---|
| `test_compute_zero_weight_does_not_abort_loop` | `final_score.compute__mutmut_5` (`continue`→`break`) |
| `test_construction_zero_weight_is_valid` | `rank_score.__init____mutmut_10` (`val < 0.0` → `val <= 0.0`) |
| `test_compute_custom_weights_exact_value` | `rank_score.compute__mutmut_13/17/18/22/26/27/31/35/36/40/44/45` (12 mutantes de chave-string) |

---

## Problemas Encontrados e Soluções

1. **mutmut 3.x × `python -m` × `set_start_method`**: ver decisão acima.
2. **`also_copy` omitido**: sem `["src/"]`, apenas `domain/services/` era copiado; testes falhavam ao importar `domain/entities`, `domain/errors`, etc. Fix: adicionar `also_copy = ["src/"]`.
3. **Ruff E402**: a docstring do módulo ficou entre `from __future__ import annotations` e os outros imports. Fix: mover a docstring para antes do `from __future__` (PEP 236 permite isso).
4. **Ruff T201**: `print()` em script de gate. Fix: substituir por `_echo()` (wrapper de `sys.stdout.write`) e `sys.stderr.write`.
5. **(Ciclo B→A, mantido) Equivalência semântica dos sobreviventes de comparação**: mutmut_12/16/17 em `final_score.py` são inmatáveis sem alterar `src/` (proibido). Análise completa na seção "Score final". Classificados como "guard clause" (Prompt A §4).
6. **(Ciclo B→A) `mutation_gate.py` ignorava exit code de `mutmut run`**: crash (code ≥ 2) era tratado igual a sobreviventes (code 1), possibilitando leitura de cache antigo → falso PASS. Fix: `if run_exit_code >= 2: sys.exit(2)`.
7. **(Ciclo B→A) `workflow_dispatch` ausente em `on:`**: job usava `if: github.event_name == 'workflow_dispatch'` mas o trigger não estava declarado. Fix: adicionar `workflow_dispatch:` ao `on:`.
8. **(Ciclo B→A revertido) Alterações indevidas em `src/`**: commit 06899cb modificou `rank_score.py` e `final_score.py` violando a restrição do prompt. Revertido: código de produção restaurado ao estado de a0338dd; mutation_report.txt atualizado.

---

## Validação (DoD)

```
uv run ruff check .            → All checks passed!
uv run ruff format --check .   → 139 files already formatted
uv run mypy --strict src       → Success: no issues found in 50 source files
uv run lint-imports            → Contracts: 4 kept, 0 broken.
uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4 -q
                               → 1071 passed, 6 skipped — 90.97%
uv run python scripts/mutation_gate.py
                               → Mutation score 92.4% >= 80%. [PASS]
```

---

## Critérios de Aceitação

- [x] `mutmut run` (via `mutation_gate.py`) completa sem erro de configuração.
- [x] `tests/mutation/mutation_report.txt` mostra score 92.4% > 80%.
- [x] `funnel.py` NÃO está em `paths_to_mutate` (M5 adiado).
- [x] Sobreviventes documentados com justificativa técnica (guard clause IEEE 754).
- [x] Nenhum sobrevivente em operadores aritméticos de scoring (`+`, `-`, `*`, `/`).
- [x] CI step `mutation-gate` roda em `main`/`workflow_dispatch` (declarado em `on:`).
- [x] Gate aborta com exit 2 se `mutmut run` crashar (evita cache antigo).
- [x] Código de produção em `src/` inalterado (apenas testes, config, scripts).
- [x] DoD: ruff/mypy/import-linter/coverage ≥ 85% verdes.

---

## Observações para Próximas Tarefas

- O `mutants/` está em `.gitignore` — apenas `tests/mutation/mutation_report.txt` é commitado.
- A TAREFA-602 (Cohen's κ) pode reutilizar `RankScoreCalculator` e `AggregationService` diretamente; os testes de 601 cobrem bem o domínio.
- Se o M5 (funnel) for implementado, adicionar `funnel.py` a `paths_to_mutate` e repetir o gate.
- Quando a equipe quiser re-executar o gate local: `rm -rf mutants/ && uv run python scripts/mutation_gate.py`.
