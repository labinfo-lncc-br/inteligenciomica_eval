# M1_TAREFA-016_B — Correção: EvaluationSample.question_id (PR retroativo)

**Data**: 2026-05-28
**Milestone**: M1 — Adapters de Infraestrutura
**Épico**: E2 — Adapters de Avaliação
**Skill**: python-engineer
**Prioridade / Tamanho**: P0 / S

---

## Origem da Correção

Durante a execução de TAREFA-016-A, o arquivo de prompts utilizado foi
`prompts_m1_tarefas_013_021.md` (original, referenciado no `CLAUDE.md`). Porém o
arquivo correto e vigente é `prompts_m1_tarefas_013_021_corrigido.md` (versão 1.1,
auditado em 26/05/2026).

A diferença crítica identificada: a versão corrigida contém a **Nota M1 item 11**
(correção I6 da auditoria), que exige:

> `EvaluationSample.question_id: str` — extensão obrigatória de DTO, com PR retroativo
> em `domain/ports.py` **antes** de TAREFA-016. O campo `question_id` é obrigatório
> no schema §5.3, portanto sua ausência era uma lacuna de proveniência.

A implementação de TAREFA-016-A entregou o adapter funcionalmente correto, mas sem
esse campo no DTO nem no logging.

---

## Objetivo

Aplicar o PR retroativo da Nota M1 item 11:

1. Adicionar `question_id: str` como primeiro campo de `EvaluationSample` em `domain/ports.py`.
2. Incluir `question_id=sample.question_id` nos dois eventos de log do `PrometheusJudgeAdapter`.
3. Atualizar todas as instanciações de `EvaluationSample` nos testes e no harness e2e.
4. Corrigir `CLAUDE.md`: referência ao arquivo de prompts corrigido + estado das tarefas.

---

## Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/inteligenciomica_eval/domain/ports.py` | `EvaluationSample`: adicionado `question_id: str` como primeiro campo (com docstring) |
| `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py` | Logs `prometheus_judge_completed` e `prometheus_judge_nan` incluem `question_id=sample.question_id` |
| `tests/unit/infrastructure/adapters/test_prometheus_judge.py` | `_SAMPLE`: adicionado `question_id="q_resist_antibioticos"` |
| `tests/unit/fakes/test_fakes_satisfy_ports.py` | `_SAMPLE`: adicionado `question_id="q_rag_001"` |
| `tests/unit/domain/test_ports_contract.py` | Dois construtores: `question_id="q_rag_001"` e `"q_rag_002"`; asserção `s.question_id == "q_rag_001"` adicionada |
| `tests/e2e/_harness.py` | `EvaluationSample(question_id=answer.question.question_id, ...)` |
| `CLAUDE.md` | Referência ao arquivo de prompts corrigida; status TAREFA-015/016 atualizado; cobertura atualizada; seções de design adicionadas |

---

## Decisões Técnicas

### `question_id` como primeiro campo do dataclass

`EvaluationSample` é um `dataclass(frozen=True, slots=True)`. A ordem dos campos
define a assinatura do construtor posicional. `question_id` foi colocado **primeiro**
por ser o identificador — convenção natural do schema §5.3 onde o ID sempre precede
os dados. Todos os construtores existentes eram keyword-only nos testes (usando `=`),
portanto a inserção não causa ambiguidade posicional.

### `answer.question.question_id` no harness e2e

A entidade `Question` em `domain/entities.py` já possui `question_id: str` (campo
obrigatório, com validação de não-vazio). O harness e2e usa `answer.question.question_id`
para preencher `EvaluationSample.question_id` — zero delta semântico, apenas
propagação explícita do campo que já existia na entidade.

### CLAUDE.md — arquivo de prompts

A referência `prompts_m1_tarefas_013_021.md` no `CLAUDE.md` apontava para um arquivo
que não existe mais no disco. Corrigida para `prompts_m1_tarefas_013_021_corrigido.md`
com nota da versão e data da auditoria.

---

## Validação (DoD)

| Gate | Resultado | Detalhe |
|------|-----------|---------|
| `ruff check .` | ✅ PASS | 0 erros |
| `ruff format --check .` | ✅ PASS | 74 arquivos sem alteração de formato |
| `mypy --strict src/` | ✅ PASS | 26 arquivos, zero issues |
| `lint-imports` | ✅ PASS | 4 contratos mantidos |
| `pytest --cov --cov-fail-under=85` | ✅ PASS | **620 passed, 7 skipped — 96.66%** |
| `prometheus_judge.py` cobertura | ✅ PASS | **100%** (mantida após inclusão de `question_id` no log) |

---

## Observações para Próximas Tarefas

- **TAREFA-017 (RAGASLayer1Adapter)**: ao instanciar `EvaluationSample` nos testes,
  incluir `question_id` obrigatoriamente.
- **TAREFA-020 (AnnotationReaderAdapter)**: o `RowId` referenciado por anotações é
  derivado do hash dos campos da linha — verificar se `question_id` deve participar
  do cálculo do `RowId` (consultar §5.3 do documento de arquitetura).
- **Fakes `FakeMetricSuite` e `FakeRubricJudge`**: recebem `EvaluationSample` em
  `score()` mas não usam `question_id` internamente — sem alteração necessária nos
  fakes neste momento.
