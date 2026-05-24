# M0_TAREFA-005_B — Auditoria de Ports como Protocol

**Data**: 2026-05-23
**Milestone**: M0 — Bootstrap e Domínio Core
**Épico**: E0
**Skill**: code-reviewer
**Prioridade / Tamanho**: P0 / S

---

## Objetivo

Auditar a implementação da TAREFA-005 contra `docs/arquitetura_detalhada_validacao_inteligenciomica.md` §5.1/§5.2, ADR-001, ADR-011, a nota operacional sobre `ResultFrame` e o DoD §14.2, sem reescrever o código.

---

## Arquivos Inspecionados

| Arquivo | Papel na auditoria |
|---|---|
| `src/inteligenciomica_eval/domain/ports.py` | Implementação auditada |
| `tests/unit/domain/test_ports_contract.py` | Prova de compatibilidade estrutural |
| `docs/arquitetura_detalhada_validacao_inteligenciomica.md` | Fonte das assinaturas e DoD |
| `.importlinter` | Contratos de dependência da arquitetura |
| `CLAUDE.md` | Padrão de relatório |

---

## Veredito

**PASS**

Não encontrei divergências bloqueadoras. Os 11 ports da §5.1 estão presentes em `src/inteligenciomica_eval/domain/ports.py` e as assinaturas batem com o documento em nome do método, parâmetros, presença de `*` keyword-only e tipo de retorno. O módulo usa `typing.Protocol`, mantém o domínio puro e os testes de contrato demonstram compatibilidade estrutural via `@runtime_checkable`.

---

## Verificação Item a Item

| Critério | Status | Evidência |
|---|---|---|
| 1. Os 11 ports da §5.1 estão presentes com assinaturas idênticas | ✅ | Arquitetura `docs/arquitetura_detalhada_validacao_inteligenciomica.md:287-350`; implementação `src/inteligenciomica_eval/domain/ports.py:260-553` |
| 2. Ports são `typing.Protocol` e `@runtime_checkable` onde útil | ✅ | `src/inteligenciomica_eval/domain/ports.py:5`, `:260`, `:287`, `:318`, `:337`, `:357`, `:378`, `:397`, `:433`, `:453`, `:498`, `:517` |
| 3. DTOs auxiliares são dataclasses frozen puras; `ResultFrame` é wrapper de `tuple[EvaluationResult, ...]` sem pandas/polars/pyarrow | ✅ | DTOs em `src/inteligenciomica_eval/domain/ports.py:22-251`; `ResultFrame` em `:240-251`; imports do módulo em `:1-13` |
| 4. Não há `Any` solto; `# type: ignore` apenas justificado; `mypy --strict src` limpo | ✅ | `rg` sem `Any`; único ignore em teste de imutabilidade `tests/unit/domain/test_ports_contract.py:282`; `uv run mypy --strict src` → `Success: no issues found in 15 source files` |
| 5. `import-linter`: domain não importa infra nem libs de I/O canônicas | ✅ | Contrato em `.importlinter:8-29`; imports de `ports.py` em `src/inteligenciomica_eval/domain/ports.py:1-13`; `uv run lint-imports` → `4 kept, 0 broken` |
| 6. Teste de contrato prova compatibilidade estrutural de stub com cada Protocol | ✅ | Stubs em `tests/unit/domain/test_ports_contract.py:124-214`; `isinstance` por Protocol em `:222-256`; `uv run pytest tests/unit/domain/test_ports_contract.py -q` → `37 passed` |
| 7. DoD §14.2: `from __future__ import annotations` e docstrings em todos os Protocols/DTOs | ✅ | DoD em `docs/arquitetura_detalhada_validacao_inteligenciomica.md:911-914`; `from __future__ import annotations` em `src/inteligenciomica_eval/domain/ports.py:1` e `tests/unit/domain/test_ports_contract.py:10`; docstrings em todos os DTOs/Protocols auditados |

---

## Comparação das 11 Assinaturas da §5.1

| Port | Assinatura da arquitetura | Implementação | Resultado |
|---|---|---|---|
| `RetrieverPort.search` | `search(self, *, base: BaseId, question: str, top_k: int) -> RetrievalResult` | `src/inteligenciomica_eval/domain/ports.py:267-273` | ✅ |
| `GeneratorPort.generate` | `generate(self, *, llm: LLMId, question: str, contexts: Sequence[Chunk], seed: int, temperature: float) -> GenerationOutput` | `src/inteligenciomica_eval/domain/ports.py:294-302` | ✅ |
| `MetricSuitePort.score` | `score(self, sample: EvaluationSample) -> Layer1Metrics` | `src/inteligenciomica_eval/domain/ports.py:325` | ✅ |
| `RubricJudgePort.score` | `score(self, sample: EvaluationSample) -> RubricResult` | `src/inteligenciomica_eval/domain/ports.py:344` | ✅ |
| `DeterministicMetricPort.score` | `score(self, *, answer: str, ground_truth: str) -> AuxMetrics` | `src/inteligenciomica_eval/domain/ports.py:365` | ✅ |
| `GoldChunkReaderPort.gold_for` | `gold_for(self, question_id: str) -> list[str]` | `src/inteligenciomica_eval/domain/ports.py:385` | ✅ |
| `ResultWriterPort.append` | `append(self, result: EvaluationResult) -> None` | `src/inteligenciomica_eval/domain/ports.py:404` | ✅ |
| `ResultWriterPort.update_metrics` | `update_metrics(self, row_id: RowId, metrics: MetricVector) -> None` | `src/inteligenciomica_eval/domain/ports.py:412` | ✅ |
| `ResultWriterPort.exists` | `exists(self, row_id: RowId) -> bool` | `src/inteligenciomica_eval/domain/ports.py:421` | ✅ |
| `ResultReaderPort.load` | `load(self, *, round_id: str, phase: str | None = None) -> ResultFrame` | `src/inteligenciomica_eval/domain/ports.py:440` | ✅ |
| `StatsPort.wilcoxon_paired` | `wilcoxon_paired(self, frame: ResultFrame, metric: str) -> WilcoxonReport` | `src/inteligenciomica_eval/domain/ports.py:461` | ✅ |
| `StatsPort.friedman_nemenyi` | `friedman_nemenyi(self, frame: ResultFrame, metric: str) -> FriedmanReport` | `src/inteligenciomica_eval/domain/ports.py:473` | ✅ |
| `StatsPort.mixed_linear_model` | `mixed_linear_model(self, frame: ResultFrame, formula: str) -> MLMReport` | `src/inteligenciomica_eval/domain/ports.py:485` | ✅ |
| `AnnotationReaderPort.read` | `read(self, run_id: str) -> list[CriticalAnnotation]` | `src/inteligenciomica_eval/domain/ports.py:505` | ✅ |
| `VLLMServerManagerPort.start` | `start(self, model: ModelSpec) -> ServerHandle` | `src/inteligenciomica_eval/domain/ports.py:524` | ✅ |
| `VLLMServerManagerPort.wait_healthy` | `wait_healthy(self, handle: ServerHandle, timeout_s: int) -> None` | `src/inteligenciomica_eval/domain/ports.py:535` | ✅ |
| `VLLMServerManagerPort.stop` | `stop(self, handle: ServerHandle) -> None` | `src/inteligenciomica_eval/domain/ports.py:547` | ✅ |

**Assinaturas que NÃO batem com a §5.1**: nenhuma.

---

## Tabela de Divergências

Nenhuma divergência encontrada.

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| Nenhuma | — | — |

---

## Validação Executada

```bash
uv run mypy --strict src
uv run lint-imports
uv run pytest tests/unit/domain/test_ports_contract.py -q
```

Resultados observados nesta auditoria:

- `uv run mypy --strict src` → `Success: no issues found in 15 source files`
- `uv run lint-imports` → `Contracts: 4 kept, 0 broken`
- `uv run pytest tests/unit/domain/test_ports_contract.py -q` → `37 passed in 0.13s`

---

## Observações

- O único `# type: ignore` encontrado está em `tests/unit/domain/test_ports_contract.py:282` para forçar uma atribuição inválida e comprovar imutabilidade da dataclass; o uso é justificado.
- `FriedmanReport` e `MLMReport` são `@dataclass(frozen=True)` puras, mas carregam `dict[str, float]` internamente mutável (`src/inteligenciomica_eval/domain/ports.py:153-192`). Isso não viola os critérios desta auditoria, porém limita a imutabilidade profunda.
