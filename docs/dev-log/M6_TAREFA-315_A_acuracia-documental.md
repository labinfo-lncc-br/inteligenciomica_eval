# M6_TAREFA-315_A — Acurácia Documental

**Data**: 2026-06-08
**Milestone**: M3/M6 — Saneamento pós-auditoria completa
**Épico**: E9 (docs)
**Skill**: system-architect, python-engineer
**Prioridade / Tamanho**: P1 / M

---

## Objetivo

Alinhar documentação normativa/operacional ao as-built corrigido pelas TAReFAs 313/314:

- **(B2)** ADR-014: default `determinism_verified = True` contradiz o código (que usa `False`)
- **(I3/I4)** Manual: referências a arquivos inexistentes (`config/questions.jsonl`,
  `config/questions_resistencia.jsonl`, `config/questions_sepse.jsonl`); claim "13 perguntas
  empacotadas" incorreta (são 3 placeholders); nota errada de que `questions:` não está wired
- **(I6)** `validate_manual.py` não detectava arquivos referenciados inexistentes nem claims
  numéricas incorretas

---

## Arquivos Criados / Modificados

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `docs/adr/ADR-014-server-mode-external.md` | Modificado | default `determinism_verified: bool = True` → `False` |
| `docs/operations_manual.md` | Modificado | Seção "De onde vêm as perguntas" + `endpoint_masked` |
| `scripts/validate_manual.py` | Modificado | 3 novas funções + 2 novas verificações em `main()` |
| `tests/unit/test_validate_manual.py` | Criado | 13 testes das novas funções |

---

## Decisões Técnicas

### ADR-014

- Linha 63: `determinism_verified: bool = True` → `False` com nota explicativa do fix da TAREFA-312.
- Único achado B2 na ADR. Sem outros contradições identificadas.

### Manual — seção "De onde vêm as perguntas" (reescrita completa)

1. Precedência explicitada: `BENCHMARK_QUESTIONS_PATH` (env) > `questions:` (YAML canônico,
   TAREFA-313) > `questions_rf1.jsonl` empacotado (fallback).
2. "13 perguntas RF1" → "**3 perguntas placeholder**; as 13 reais a curar pelo especialista
   biomédico antes da Rodada 1 de produção (P4)".
3. Arquivos inexistentes (`config/questions*.jsonl`) removidos dos blocos bash executáveis;
   exemplos de multi-área usam caminhos absolutos (não `config/`) marcados como "a serem
   criados pelo operador — não versionados".
4. Nota obsoleta ("campo `questions:` não está conectado ao loader") removida; substituída
   pela precedência correta (TAREFA-313).

### Manual — `endpoint_masked` (Seção 4-B)

- Exemplo JSON: `"endpoint_masked": "http://localhost:8010/***"` → `"http://localhost:8010"`,
  alinhando ao comportamento real de `mask_url()` pós-TAREFA-314 (que retorna
  `scheme://host:port` sem `/***`).

### `validate_manual.py` — extensões

Quatro novas funções adicionadas (sem quebrar as 3 verificações existentes):

1. **`_local_file_errors_in_block(block, repo_root)`**: varre linhas não-comentário de
   blocos shell, detecta tokens `config/*` (exceto `config/data/`) que não existem no repo.
   Ignora placeholders `<>`, expansões `${}`.

2. **`_count_bundled_questions(repo_root)`**: conta linhas com `question_id` em
   `questions_rf1.jsonl`; retorna -1 se o arquivo não existir (verificação pulada).

3. **`_check_numeric_claims(text, repo_root)`**: detecta padrão `"N perguntas placeholder"`
   no texto do manual e valida contra a contagem real do arquivo empacotado.

4. Constantes: `_REPO_ROOT = Path(__file__).resolve().parent.parent`,
   `_BUNDLED_QUESTIONS`, `_LOCAL_FILE_RE`, `_CLAIM_RE`.

`main()` estendido com verificações 4 e 5; saída de FAIL atualizada.

---

## Validação (DoD)

### Gates de qualidade

```
ruff check .             → All checks passed!
ruff format --check .    → 174 files already formatted
mypy --strict src/       → Success: no issues found in 61 source files
lint-imports             → Contracts: 4 kept, 0 broken
```

### Novos testes — 13 PASSED

```
tests/unit/test_validate_manual.py::TestLocalFileErrors::test_detects_missing_config_jsonl           PASSED
tests/unit/test_validate_manual.py::TestLocalFileErrors::test_detects_missing_questions_resistencia  PASSED
tests/unit/test_validate_manual.py::TestLocalFileErrors::test_ignores_comment_lines                  PASSED
tests/unit/test_validate_manual.py::TestLocalFileErrors::test_passes_existing_config_yaml            PASSED
tests/unit/test_validate_manual.py::TestLocalFileErrors::test_ignores_config_data_output_paths       PASSED
tests/unit/test_validate_manual.py::TestLocalFileErrors::test_ignores_placeholder_angle_brackets     PASSED
tests/unit/test_validate_manual.py::TestCountBundledQuestions::test_counts_three_questions           PASSED
tests/unit/test_validate_manual.py::TestCountBundledQuestions::test_returns_minus_one_for_missing_file PASSED
tests/unit/test_validate_manual.py::TestCountBundledQuestions::test_comment_line_not_counted         PASSED
tests/unit/test_validate_manual.py::TestNumericClaims::test_fails_on_wrong_count_thirteen            PASSED
tests/unit/test_validate_manual.py::TestNumericClaims::test_passes_on_correct_count_three            PASSED
tests/unit/test_validate_manual.py::TestNumericClaims::test_no_errors_on_text_without_claim          PASSED
tests/unit/test_validate_manual.py::TestNumericClaims::test_deduplicates_same_wrong_claim            PASSED
```

**Testes que falhariam contra o manual antigo:**
- `test_detects_missing_config_jsonl` — detecta `config/questions.jsonl` inexistente
- `test_detects_missing_questions_resistencia` — detecta `config/questions_resistencia.jsonl`
- `test_fails_on_wrong_count_thirteen` — detecta "13 perguntas placeholder" vs. 3 reais

### validate_manual.py PASS contra o manual corrigido

```
uv run python scripts/validate_manual.py

Subcomandos ielm-eval:
  ielm-eval version              OK
  ielm-eval run                  OK
  ielm-eval status               OK
  ielm-eval annotate             OK
  ielm-eval analyze              OK
  ielm-eval report               OK
  ielm-eval validate-judge       OK

Flags obrigatórias em `ielm-eval run --help`:
  --run-id                                 OK
  --require-verified-determinism           OK

PASS — todos os subcomandos e flags validados existem na CLI.
```

(verificações 4 e 5 passam sem output — ausência de erros = sem output)

### Suíte completa

```
uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4 -q

1287 passed, 6 skipped, 21 warnings
Total coverage: 89.61% (≥ 85% ✓)
```

### git diff --name-only

```
docs/adr/ADR-014-server-mode-external.md
docs/operations_manual.md
scripts/validate_manual.py
tests/unit/test_validate_manual.py  ← (untracked, new)
```

Nenhum arquivo em `src/` (código de produção) tocado.

---

## Critérios de Aceitação

- [x] ADR-014 `determinism_verified` default corrigido para `False`, coincidindo com o código
- [x] Manual sem referências a arquivos `config/questions*.jsonl` inexistentes em blocos executáveis
- [x] Claim "13 perguntas" removida; texto diz "3 perguntas placeholder"
- [x] Nota obsoleta sobre `questions:` não conectado removida; precedência real documentada
- [x] `endpoint_masked` no exemplo JSON alinhado ao comportamento de `mask_url()` pós-TAREFA-314
- [x] `validate_manual.py` detecta arquivo referenciado inexistente em bloco shell → FAIL
- [x] `validate_manual.py` detecta claim numérica inconsistente → FAIL
- [x] Testes que falhariam contra o manual antigo existem e passam contra o corrigido
- [x] `git diff --name-only` restrito a `docs/` e `scripts/` + `tests/`
- [x] `validate_manual.py PASS` contra o manual corrigido
- [x] Gates verdes; 1287 passed, 89.61%

---

## Observações para Próximas Tarefas

- **TAREFA-607 (doc-sync)**: CLAUDE.md (seção TAREFA-311) ainda descreve `mask_url` retornando
  `scheme://host:port/***` — pós-TAREFA-314 o formato é `scheme://host:port` sem `/***`.
  Corrigir no 607.
- Referência `config/gold_chunks.jsonl` na nota "Rodada 2 (M5)" (manual) aponta para arquivo
  inexistente no repo atual, mas é forward-looking (M5 pendente) e está em blockquote, não em
  bloco shell — não flagrado pelo validador e não necessita correção agora.
