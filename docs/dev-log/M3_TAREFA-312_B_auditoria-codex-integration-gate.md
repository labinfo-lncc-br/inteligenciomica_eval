# M3_TAREFA-312_B — Auditoria Codex do gate de integração 309/310/311/606

**Data**: 2026-06-07
**Milestone**: M3 — Gate transversal (integração 309/310/311 + coerência com 606)
**Épico**: E3 (transversal)
**Skill**: code-reviewer, test-engineer
**Prioridade / Tamanho**: P0 / M

## Objetivo

Auditar de forma independente a execução da TAREFA-312 a partir do prompt
`docs/prompts_m3_tarefa_312_integration_gate.md`, do relatório
`docs/dev-log/M3_TAREFA-312_A_integration-gate-completude.md` e do commit
`37e7314`.

## Escopo auditado

- Diff do commit `37e7314`
- Prompt M3/TAREFA-312
- Relatório da Parte A
- Código e documentação tocados pela tarefa
- Reprodução local dos gates e testes-chave do gate

## Comandos reproduzidos

### Gates estáticos

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
All checks passed!
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .
Would reformat: src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py
Would reformat: tests/unit/infrastructure/test_provenance_columns.py
2 files would be reformatted, 168 files already formatted
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src
Success: no issues found in 60 source files
```

```text
$ uv run lint-imports
Contracts: 4 kept, 0 broken.
```

### CLI / smoke-test / dry-run

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run ielm-eval --help
Commands:
  version
  run
  annotate
  analyze
  report
  status
  show-config
  validate-judge
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run ielm-eval run --help
Flags presentes:
  --config
  --run-id
  --phase
  --dry-run
  --serial
  --require-verified-determinism
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/validate_manual.py
PASS — todos os subcomandos e flags validados existem na CLI.
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run ielm-eval run --config config/experiment_round1.yaml --run-id smoke --dry-run
Dry-run plan — round-1
Perguntas carregadas: 3
Config valid — dry-run complete.
```

### Testes-chave

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/test_provenance_columns.py -q
28 passed in 0.15s
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/e2e/test_m3_full_cycle.py -v --timeout=30
5 passed in 0.82s
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/e2e/test_full_pipeline_m4.py tests/unit/test_cli_m4_subcommands.py -q
13 passed, 1 skipped in 1.94s
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/test_external_server_manager.py -q
18 passed in 0.17s
```

```text
$ UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/cli/test_run_external.py -q
5 passed in 0.22s
```

## Divergências encontradas

### 1. FAIL nos gates estáticos declarados como verdes

**Gravidade**: BLOQUEADOR

O relatório da Parte A afirma `ruff format --check .` verde, mas a reprodução local
falhou. O próprio formatter indica diffs pendentes nos dois arquivos alterados pela
tarefa:

- `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py`
- `tests/unit/infrastructure/test_provenance_columns.py`

Diferenças reportadas pelo `ruff format --diff`:

- quebra de linha da compreensão/lista e do dict `defaults` em
  `parquet_storage.py`
- assinatura multiline de `test_from_row_defaults_when_columns_absent()` em
  `test_provenance_columns.py`

Isso invalida o item “gates verdes” do relatório e o critério de aceitação do prompt.

### 2. Doc↔código ainda incoerentes em `determinism_verified`

**Gravidade**: BLOQUEADOR

O commit corrige a ausência das 3 colunas na arquitetura, mas a semântica
documentada para `determinism_verified` continua divergente do código executável:

- A arquitetura agora afirma que `determinism_verified` é `False` por default e
  “nunca `True` sem prova”:
  `docs/arquitetura_detalhada_validacao_inteligenciomica.md:264`
  e `:435`
- O domínio continua com default `True`:
  `src/inteligenciomica_eval/domain/entities.py:153`
- O reader de Parquet legado continua defaultando `True` e ainda registra esse
  default no warning:
  `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:307`
  e `:320`
- O teste de retrocompatibilidade consolida esse comportamento como esperado:
  `tests/unit/infrastructure/test_provenance_columns.py:290`
- A dataclass interna do wiring também mantém default `True`:
  `src/inteligenciomica_eval/infrastructure/wiring.py:126`

Impacto:

- a superfície H (“coerência doc↔código”) não está realmente verde;
- a superfície F (“determinismo não verificável → false explícito; nunca True por
  default”) não está satisfeita para linhas legadas e defaults de entidade;
- o relatório A marca H1 como totalmente corrigido, mas isso não se sustenta.

## Verificações que passaram

- `ruff check .`: verde
- `mypy --strict src`: verde
- `lint-imports`: verde
- CLI preserva os subcomandos reais (`version`, `run`, `annotate`, `analyze`,
  `report`, `status`, `show-config`, `validate-judge`)
- `ielm-eval run --help` expõe `--run-id`, `--phase`, `--serial`, `--dry-run`,
  `--require-verified-determinism`
- `config/experiment_round1.yaml` e `config/model_registry.yaml` parseiam
- dry-run managed sai com exit 0 e imprime `Perguntas carregadas: 3`
- smoke-test do manual passa
- `tests/unit/infrastructure/test_provenance_columns.py`: verde
- `tests/e2e/test_m3_full_cycle.py`: 5 passed em < 30 s
- suíte M4 reproduzida: verde
- testes external reproduzidos parcialmente: `test_external_server_manager.py`
  e `test_run_external.py` verdes
- golden E2E M3 contém as 3 colunas novas
- não há imports de `tests.fakes` no topo de módulos de produção

## Veredito

**FAIL**

### Tabela de divergências

| Superfície | Critério | Arquivo:linha | Gravidade |
|-----------|----------|---------------|-----------|
| A — gates estáticos | `ruff format --check .` deve estar verde | `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:301`, `tests/unit/infrastructure/test_provenance_columns.py:278` | BLOQUEADOR |
| F / H — proveniência e doc↔código | `determinism_verified` não verificável deve ser `False`; docs e código devem coincidir | `docs/arquitetura_detalhada_validacao_inteligenciomica.md:264`, `docs/arquitetura_detalhada_validacao_inteligenciomica.md:435`, `src/inteligenciomica_eval/domain/entities.py:153`, `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:307`, `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:320`, `tests/unit/infrastructure/test_provenance_columns.py:290` | BLOQUEADOR |

## Conclusão

O gate 312 **não está pronto para aprovação** no estado do commit `37e7314`.
Embora os testes-chave de CLI, dry-run, M3 E2E, M4 e smoke-test do manual estejam
verdes, há dois bloqueadores remanescentes:

1. o relatório declara `ruff format --check` verde, mas o repositório não está formatado;
2. a correção de doc↔código da proveniência ficou incompleta: a documentação passou a
   prometer `determinism_verified=False` por default, enquanto o código continua
   materializando `True` em caminhos sem prova.

**Recomendação**: `Request changes`.
