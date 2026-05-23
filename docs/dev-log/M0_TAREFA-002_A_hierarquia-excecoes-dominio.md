# M0_TAREFA-002_A — Hierarquia de Exceções de Domínio

**Data**: 2026-05-23
**Milestone**: M0 — Fundação
**Épico**: E0
**Skill**: python-engineer
**Prioridade / Tamanho**: P0 / XS
**Dependências**: TAREFA-001 (bootstrap do repositório)
**ADRs referenciados**: governa ADR-007 a jusante (strategy de exceções)
**Camada**: domain

---

## Objetivo

Criar a hierarquia completa de exceções específicas de domínio em
`src/inteligenciomica_eval/domain/errors.py`, conforme §9 "Estratégia de exceções"
do documento de arquitetura v1.1. Nenhuma dependência externa permitida — módulo de
domínio puro. Acompanhado de suite de testes que valida hierarquia, captura pela base
e preservação de atributos contextuais.

---

## Arquivos Criados / Modificados

### Novos

| Arquivo | Descrição |
|---------|-----------|
| `src/inteligenciomica_eval/domain/errors.py` | 15 classes de exceção em 5 grupos; stdlib apenas |
| `tests/unit/domain/test_errors.py` | 37 testes: hierarquia, captura pela base, atributos |

### Modificados

| Arquivo | Motivo |
|---------|--------|
| `tests/unit/test_imports.py` | Adicionado `import inteligenciomica_eval.domain.errors` para cobrir o novo módulo no check de importação |

---

## Estrutura da Hierarquia

```
InteligenciomicaEvalError(Exception)
│
├── [Domínio / validação]
│   ├── InvalidBaseIdError
│   ├── InvalidLLMIdError
│   ├── ScoreOutOfRangeError
│   └── WeightsDoNotSumToOneError
│
├── [Configuração]
│   ├── ConfigValidationError
│   └── ModelNotInRegistryError
│
├── [Adapters / I/O]
│   ├── RetrievalError
│   ├── GenerationError
│   ├── JudgeUnavailableError
│   ├── LLMOutputParseError
│   ├── MetricComputationError
│   └── StorageError
│
├── [Orquestração de servidores]
│   ├── ServerStartTimeoutError
│   └── ModelSwitchError
│
└── [Estatística]
    └── InsufficientSampleError
```

Todas herdam **diretamente** de `InteligenciomicaEvalError` (sem nível intermediário),
pois a §9 não especifica classes de grupo — herança plana adotada para simplicidade.

---

## Decisões Técnicas

### D1 — Herança plana (sem classes intermediárias de grupo)
A §9 especifica apenas agrupamento por área e herança de `InteligenciomicaEvalError`.
Não há requisito de classes intermediárias como `AdapterError`. Herança plana reduz
indireção e permite captura precisa. Nível intermediário pode ser adicionado no futuro
sem breaking change (isinstance é transitivo).

### D2 — Atributos contextuais tipados em cada subclasse
Cada construtor define atributos de instância (`self.base_id`, `self.score`, etc.)
além da mensagem de texto. O código capturador inspeciona contexto sem fazer parsing
de string. Todos os atributos têm type hint compatível com `mypy --strict`.

### D3 — Construtores passam apenas string para `super().__init__`
`super().__init__(mensagem_formatada)` garante que `str(err)` retorne a mensagem
legível. Mensagens são acionáveis e não vazam segredos — apenas identificadores e
valores que o chamador forneceu.

### D4 — `WeightsDoNotSumToOneError` com parâmetro `tolerance`
Recebe `tolerance: float = 1e-6` para que a mensagem exiba o threshold usado na
validação que gerou o erro. Permite rastreabilidade sem inspecionar código-fonte.

### D5 — Stdlib puro; zero imports externos
O módulo importa apenas `from __future__ import annotations`. Garante que os
contratos import-linter (`domain-forbidden`) continuem passando e que o módulo
seja importável em qualquer ambiente sem dependências extras.

---

## Problemas Encontrados e Soluções

### P1 — `ruff format` reformatou o arquivo na primeira execução
**Sintoma**: `ruff format --check` retornou exit code 1 com "1 file would be reformatted".
**Causa**: Uma f-string concatenada que o ruff quebrou em linha diferente da escrita
original.
**Solução**: `uv run ruff format src/inteligenciomica_eval/domain/errors.py` aplicado;
segunda verificação retornou "2 files already formatted".
**Impacto**: Nenhum — conteúdo lógico não alterado.

---

## Validação (DoD §14.2)

| Check | Comando | Resultado |
|-------|---------|-----------|
| `from __future__ import annotations` | inspeção | ✅ ambos os arquivos |
| type hints | `uv run mypy --strict src/inteligenciomica_eval/domain/errors.py` | ✅ 0 issues |
| ruff lint | `uv run ruff check errors.py test_errors.py` | ✅ All checks passed |
| ruff format | `uv run ruff format --check errors.py test_errors.py` | ✅ (após P1) |
| contratos arq. | `uv run lint-imports` | ✅ 4 KEPT, 0 broken |
| pytest módulo | `uv run pytest tests/unit/domain/test_errors.py -v` | ✅ 37/37 passed |
| pytest suite | `uv run pytest --cov=src --cov-fail-under=85 -n auto` | ✅ 43 passed, 96.5% |
| cobertura módulo | `domain/errors.py` | ✅ 100% (statements + branches) |
| sem imports externos | inspeção + lint-imports | ✅ stdlib only |

---

## Critérios de Aceitação (TAREFA-002)

| Critério | Status |
|----------|--------|
| Todas as 15 classes da §9 presentes | ✅ |
| `issubclass(XxxError, InteligenciomicaEvalError)` para cada subclasse | ✅ 15 testes parametrizados |
| `raise`/`except` pela base captura qualquer subclasse | ✅ `test_except_base_catches_all_subclasses` |
| Pelo menos um teste captura base pegando subclasse de cada grupo | ✅ 5 testes `test_base_catches_*_group` |
| Nenhum import de I/O/infra | ✅ stdlib only, lint-imports KEPT |
| `from __future__ import annotations` | ✅ |
| Docstrings Google-style | ✅ todas as classes públicas |
| type hints em todas as assinaturas | ✅ mypy --strict sem erros |

---

## Observações para Próximas Tarefas

1. **Nível intermediário de hierarquia**: se application/infrastructure precisar capturar
   grupos inteiros (ex: "qualquer erro de adapter"), avaliar classes intermediárias como
   `AdapterError(InteligenciomicaEvalError)` — subclasses existentes passam a herdar do
   intermediário sem breaking change.

2. **`__all__` explícito**: o módulo não declara `__all__`. Se re-exportação via
   `domain/__init__.py` for adotada, adicionar `__all__` com todas as classes.

3. **Uso imediato**: TAREFA-003 em diante pode importar via
   `from inteligenciomica_eval.domain.errors import XxxError` — módulo pronto.
