# M1_TAREFA-015_A — PromptRegistry e Templates Jinja2

**Data**: 2026-05-27
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E2 — Adapters de Avaliação
**Skill**: python-engineer, rag-engineer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Implementar o `PromptRegistry` e os templates Jinja2 da rubrica biomédica
(`biomed_rubric.j2`) e de system prompt RAGAS (`ragas_system.j2`) conforme §11.2 do
documento de arquitetura e a especificação da TAREFA-015 do Prompt A.

---

## Arquivos Criados / Modificados

| Arquivo | Tipo | Mudança |
|---|---|---|
| `pyproject.toml` | modificado | Adicionada dependência `jinja2>=3.0` ao grupo `dependencies` (runtime) |
| `uv.lock` | modificado | `jinja2==3.1.6` + `markupsafe==3.0.3` adicionados |
| `src/inteligenciomica_eval/infrastructure/prompts/registry.py` | criado | `PromptRegistry` + `get_default_registry()` |
| `src/inteligenciomica_eval/infrastructure/prompts/biomed_rubric.j2` | criado | Template da rubrica biomédica (6 critérios, few-shot, saída JSON) |
| `src/inteligenciomica_eval/infrastructure/prompts/ragas_system.j2` | criado | System prompt mínimo para chamadas RAGAS (M1) |
| `tests/unit/infrastructure/prompts/__init__.py` | criado | Módulo de testes de prompts |
| `tests/unit/infrastructure/prompts/test_prompt_registry.py` | criado | 17 testes unitários |

---

## Decisões Técnicas

### 1. `jinja2.PackageLoader` em src/ layout com instalação editável

`jinja2.PackageLoader("inteligenciomica_eval", "infrastructure/prompts")` foi escolhido
conforme especificação. Em instalação editável (`uv sync`), o `importlib.resources`
localiza corretamente os arquivos `.j2` no diretório fonte (`src/`). Verificado
experimentalmente: `PromptRegistry()` carrega `biomed_rubric.j2` sem erros.

`autoescape=False` e `keep_trailing_newline=True` garantem que os templates de prompt
não sofram escaping HTML acidental e preservem quebra de linha final.

### 2. `prompt_version` com cascata de fallback

```
git describe --tags --dirty (returncode 0 e stdout não vazio)
    → usa saída do git

else → PROMPT_VERSION (variável de ambiente)
    → usa env var

else → structlog.warning + "unversioned"
```

O fallback em cascata permite que CI sem histórico git completo (shallow clone) use
`PROMPT_VERSION` configurada na pipeline.

### 3. `get_default_registry()` com `functools.cache`

`functools.cache` (Python 3.9+) garante que o ambiente Jinja2 e o subprocess `git
describe` sejam executados uma única vez por processo. Os testes criam `PromptRegistry()`
diretamente (nunca via `get_default_registry()`) para evitar interferência de estado
cacheado entre testes.

### 4. Template `biomed_rubric.j2` — estrutura

O template está estruturado em três seções XML-like para facilitar parsing pelo LLM:

- `<INSTRUÇÕES>` — papel do juiz + 6 critérios enumerados + instrução de saída JSON
- `<EXEMPLOS>` — 2 exemplos few-shot (score 1.0 e score 0.2) sobre biomedicina genérica
- `<AVALIAÇÃO>` — bloco de entrada com os placeholders Jinja2:
  `{{ question }}`, `{{ ground_truth }}`, `{{ generated_answer }}`,
  `{% for ctx in contexts %}...{% endfor %}`

Os 6 critérios (em maiúsculas para facilitar substring matching nos testes):
1. CORREÇÃO FACTUAL
2. COMPLETUDE
3. AUSÊNCIA DE CONTRADIÇÕES
4. AUSÊNCIA DE ALUCINAÇÃO
5. RESSALVAS NECESSÁRIAS
6. PERTINÊNCIA BIOMÉDICA

### 5. Saída JSON estritamente solicitada

O template instrui o juiz a retornar exclusivamente:
`{"score": <float 0.0-1.0>, "feedback": "<string>"}` — sem markdown, sem texto extra.
Isso é crítico para o parsing do `PrometheusJudgeAdapter` (TAREFA-016).

### 6. Few-shot sem PII

Os dois exemplos do few-shot usam perguntas biomédicas genéricas (mecanismos de
resistência a antibióticos e reconhecimento antigênico) sem nenhum dado de paciente,
identificador, dosagem real de caso clínico ou dado pessoal.

---

## Validação (DoD)

```
uv run ruff check src/inteligenciomica_eval/infrastructure/prompts/registry.py
    → All checks passed!
uv run ruff format --check .
    → 1 arquivo reformatado (teste), depois All checks passed!
uv run mypy --strict src
    → Success: no issues found in 25 source files
uv run lint-imports
    → Contracts: 4 kept, 0 broken
uv run pytest tests/unit/infrastructure/prompts/test_prompt_registry.py -v
    → 17 passed in 0.21s
uv run pytest --cov=src --cov-fail-under=85 -n auto -q
    → 597 passed, 7 skipped — 96.48%
registry.py cobertura: 94% (linha 57 = branch do warning structlog — não testado)
```

A linha 57 (`_log.warning(...)`) não é testada diretamente — só é atingida quando
git falha E PROMPT_VERSION não está definida, mas o teste `test_prompt_version_fallback_unversioned_when_git_fails`
cobre o comportamento observable (`"unversioned"`). Para 100% seria necessário capturar
logs structlog, o que foge do escopo desta tarefa.

---

## Critérios de Aceitação

| Critério | Status |
|---|---|
| `render_biomed_rubric` inclui `question`, `ground_truth`, `generated_answer` | ✅ |
| Template contém os 6 critérios da §5.2 (substring matching) | ✅ |
| Template solicita JSON com campos `"score"` e `"feedback"` | ✅ |
| `prompt_version` é string não-vazia em qualquer ambiente | ✅ |
| Fallback `"unversioned"` quando git ausente (subprocess mock) | ✅ |
| Fallback via `PROMPT_VERSION` env var quando git falha | ✅ |
| `get_default_registry()` retorna `PromptRegistry` e é cacheado (`is`) | ✅ |
| `mypy --strict`, `ruff`, `lint-imports` passam | ✅ |
| Suite completa verde: 597 passed, 96.48% cobertura | ✅ |

---

## Observações para Próximas Tarefas

- **TAREFA-016 (PrometheusJudgeAdapter)**: deve receber `PromptRegistry` via injeção de
  dependência no construtor; chamar `registry.render_biomed_rubric(...)` para construir o
  prompt; parsear a saída JSON `{"score": ..., "feedback": ...}` com política NaN-or-retry
  (ADR-007). O campo `prompt_version` deve ser incluído no logging estruturado.
- **TAREFA-015 futura**: quando `ragas_system.j2` precisar de variáveis, adicionar
  parâmetros a um novo método `render_ragas_system(...)` no `PromptRegistry`.
- **Alterações de template**: qualquer mudança em `biomed_rubric.j2` deve ser commitada
  com mensagem explícita — o `prompt_version` rastreia exatamente qual versão foi usada
  em cada linha do Parquet.
