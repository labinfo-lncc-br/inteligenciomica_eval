# M0_TAREFA-010_A — Config YAML + Schema Pydantic + config_hash + --dry-run

**Data**: 2026-05-23
**Milestone**: M0 — Bootstrap e Fundação
**Épico**: E0
**Skill**: python-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Implementar o subsistema de carga e validação de configuração de rodada:

- Modelos Pydantic v2 para o YAML de rodada (§12.1)
- `pydantic-settings` para resolução de endpoints/segredos via env vars (ADR-008)
- `config_hash` SHA-256 canônico para proveniência (§12.2)
- Comando CLI `ielm-eval run --dry-run` que valida e imprime o plano sem tocar GPU/rede

---

## Arquivos Criados / Modificados

| Ação | Arquivo |
|------|---------|
| Criado | `src/inteligenciomica_eval/infrastructure/config/schema.py` |
| Criado | `src/inteligenciomica_eval/infrastructure/config/settings.py` |
| Criado | `src/inteligenciomica_eval/infrastructure/config/provenance.py` |
| Modificado | `src/inteligenciomica_eval/infrastructure/config/__init__.py` |
| Modificado | `src/inteligenciomica_eval/cli.py` |
| Criado | `config/experiment_round1.yaml` |
| Criado | `tests/unit/config/__init__.py` |
| Criado | `tests/unit/config/test_schema.py` |
| Criado | `tests/unit/config/test_provenance.py` |
| Criado | `tests/unit/cli/__init__.py` |
| Criado | `tests/unit/cli/test_dry_run.py` |
| Modificado | `tests/unit/test_imports.py` |
| Modificado | `pyproject.toml` (+ `pyyaml>=6.0`, `types-PyYAML>=6.0` dev) |
| Modificado | `.importlinter` (adicionado `yaml` a contratos 1 e 2) |

---

## Decisões Técnicas

### 1. `batch_invariant=False` → ERRO (não warning)

**Decisão**: `ConfigValidationError` ao carregar config, não log de warning.

**Justificativa**: ADR-003 exige que o juiz seja determinístico. Com `batch_invariant=False`
o runtime de LLM pode reordenar batches, produzindo scores diferentes para o mesmo input
entre execuções. Como um juiz não-determinístico invalida toda a pipeline de avaliação,
falhar fast na carga é mais seguro do que deixar uma rodada contaminada chegar ao armazenamento.

### 2. Estratégia de normalização do `config_hash`

O hash SHA-256 é calculado sobre JSON canônico:

```
json.dumps(config.model_dump(mode='json'), sort_keys=True, ensure_ascii=True, separators=(',', ':'))
```

- `model_dump(mode='json')`: converte nested models para tipos JSON-nativos
- `sort_keys=True`: garante ordenação estável de chaves em todos os níveis de aninhamento
- `ensure_ascii=True`: elimina variação de encoding entre plataformas
- `separators=(',', ':')`: remove espaços opcionais (bytes estritamente canônicos)

Hash sensível à ordem de keys em dicts de usuário? **Não**: `sort_keys=True` resolve recursivamente.

### 3. Versões de pacotes em M0 (vllm, ragas)

Em M0 esses pacotes não estão instalados no ambiente de desenvolvimento. Resolução:

1. `importlib.metadata.version(pkg)` — autoritativo se instalado
2. Env var `{PKG_NAME}_VERSION` — para ambientes onde o pacote existe em runtime
3. `"unknown"` — placeholder inócuo para dry-run e CI

### 4. Nomes de env vars no YAML

O YAML armazena apenas o **nome** da env var (ex.: `endpoint_env: VLLM_JUDGE_URL`).
`resolve_endpoint(env_var_name)` faz o lookup em `os.environ`. `RuntimeSettings`
(pydantic-settings) resolve os 3 endpoints canônicos quando instanciada. Nenhum valor
de segredo entra no YAML versionado (ADR-008).

### 5. B008 (typer.Option em default) → Annotated

O ruff B008 proíbe chamadas de função em defaults de parâmetros. Migrado para estilo
`Annotated[Type, typer.Option(...)]`, que é a abordagem recomendada no Typer 0.12+.

### 6. types-PyYAML como dev dep

`mypy --strict` não aceita `import yaml` sem stubs tipados. Adicionado
`types-PyYAML>=6.0` ao grupo dev. `pyyaml>=6.0` foi adicionado às deps de runtime.
`yaml` foi adicionado à lista `forbidden_modules` dos contratos 1 e 2 do import-linter
(conforme CLAUDE.md §3 — libs de I/O proibidas em `domain` e `application`).

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| `mypy --strict` rejeita `import yaml` sem stubs | `uv add --dev types-PyYAML>=6.0` |
| ruff B008 no `typer.Option` como default | Migrado para `Annotated[T, typer.Option(...)]` |
| ruff RUF001 com `×` (sinal de multiplicação) em f-strings | Substituído por `x` ASCII |
| ruff UP017 `timezone.utc` em provenance.py | Auto-corrigido para `datetime.UTC` (Python 3.11+) |
| `model_validator(mode="after")` no loc do erro seria `scoring` e não `scoring.weights` | Convertido para `@field_validator("weights")` para ter loc preciso |

---

## Validação (DoD)

```
uv run ruff check .           # ✓ All checks passed
uv run ruff format --check .  # ✓ All files formatted
uv run mypy --strict src      # ✓ Success: no issues found in 20 source files
uv run lint-imports           # ✓ Contracts: 4 kept, 0 broken
uv run pytest --cov=src --cov-report=term-missing --cov-fail-under=85 -n auto
                               # ✓ 342 passed, coverage 96.33%
uv run ielm-eval run --dry-run --config config/experiment_round1.yaml
                               # ✓ Imprime plano + config_hash, sem tocar rede
```

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| YAML inválido (base desconhecida) → `ConfigValidationError` com `field="bases"` | ✓ |
| Pesos que não somam 1.0 → `ConfigValidationError` com `"weights"` em field | ✓ |
| `failure_threshold` fora de [0,1] → `ConfigValidationError` | ✓ |
| `batch_invariant=False` → `ConfigValidationError` com `"batch_invariant"` em field | ✓ |
| `config_hash` estável (mesmo config → mesmo hash) | ✓ |
| `config_hash` sensível (mudar 1 campo → hash diferente) | ✓ |
| `ielm-eval run --dry-run --config config/experiment_round1.yaml` imprime plano e hash | ✓ |
| Dry-run não faz chamadas de rede (test passa sem stubs) | ✓ |
| Endpoints vêm de env; nenhum segredo no YAML | ✓ |

---

## Observações para Próximas Tarefas

- **TAREFA-301**: adicionar `gpu_layout` ao model registry schema; extender `schema.py` se necessário
- **TAREFA-303**: substituir o placeholder "GPU/wave map: see TAREFA-303" pelo mapa real no dry-run output
- **TAREFA-009**: `ProvenanceInfo` está pronto para ser injetado em linhas de resultado
- O campo `retrieval.embedding_model` e `chunk_strategy` estão como `"<a-definir>"` no YAML de exemplo; definir em TAREFA-301
- A lógica de contagem de células usa `<Q>` como placeholder; será resolvida quando o repositório de questões estiver disponível
