# M2_TAREFA-022_A — Contrato `batch_invariant` + `DeterminismRegime.JUDGE` ponta-a-ponta

**Data**: 2026-05-29
**Milestone**: M2 — Avaliação automática (Camadas 1+2, juiz determinístico)
**Épico**: E2
**Skill**: python-engineer, test-engineer
**Prioridade / Tamanho**: P0 / S
**Referência arquitetural**: TAREFA-201 (§14.5) · ADR-003, ADR-009 · §4.3, §5.3

## Objetivo

Fechar o contrato §4.3: garantir que o campo `batch_invariant: bool` do schema
§5.3 recebe `True` para toda linha julgada pelo juiz determinístico (Prometheus-2)
e que `DeterminismRegime.JUDGE` flui do adapter (TAREFA-016) até o `EvaluationResult`
persistido no Parquet. Entrega principal: testes de contrato (5 cenários) + checklist
de alinhamento para o auditor.

## Arquivos Criados / Modificados

### Criados
- `tests/contract/__init__.py` — novo pacote de testes de contrato (cross-layer).
- `tests/contract/test_batch_invariant_contract.py` — 8 testes cobrindo os 5 cenários.
- `tests/contract/BATCH_INVARIANT_CHECKLIST.md` — checklist arquivo:linha + decisões.

### Modificados
- `src/inteligenciomica_eval/domain/entities.py` — adicionada property derivada
  `EvaluationResult.batch_invariant -> bool` (linha 166).
- `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py` — adicionado
  atributo de instância `determinism_regime = DeterminismRegime.JUDGE` (linha 87) +
  doc no docstring da classe.
- `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py` — `to_row`
  passa a usar `result.batch_invariant` (fonte única; mesmo valor de antes, linha 205).
- `pyproject.toml` — registrado o marker `contract` (necessário por `--strict-markers`).

## Decisões Técnicas

1. **`batch_invariant` é property derivada, não campo independente.** O invariante
   §4.3 (`JUDGE ⟺ batch_invariant=True`) é garantido **por construção**: não há
   atributo separado nem setter, logo a inconsistência é *irrepresentável*. Foi a
   resolução escolhida para o cenário (d) do Prompt A — **sem** exceção de runtime e
   **sem** WARNING no writer, pois ambos seriam código morto (a inconsistência não
   pode ser instanciada). Decisão documentada inline na property e no checklist.

2. **Atributo `determinism_regime` no adapter (não herança).** Exposto como atributo
   de instância simples para que o `ComputeMetricsUseCase` (TAREFA-026) descubra o
   regime via duck-typing, sem acoplar a uma hierarquia de classes (item 1a).

3. **Auditoria de M1 — item 1c já estava OK.** O schema pyarrow já continha
   `pa.field("batch_invariant", pa.bool_(), nullable=False)` desde M0/TAREFA-009;
   nenhuma correção necessária ali. As lacunas eram apenas (1a) e (1b).

4. **Refatoração de `to_row` sem mudança de comportamento.** Antes calculava o
   booleano inline; agora delega à property — valor idêntico, só a fonte de verdade
   foi unificada. M1 não é afetado.

## Problemas Encontrados e Soluções

- **Import das factories.** `from tests.factories...` falha (`ModuleNotFoundError`):
  o projeto coloca `tests/` no `sys.path` via conftest, então o padrão correto é
  `from factories.factories import ...` (alinhado com os testes existentes).
- **Exceção ao tentar mutar a property.** Em frozen dataclass + slots + property,
  `result.batch_invariant = X` levanta `TypeError` (não `AttributeError`) por
  particularidade do `__setattr__` gerado. O teste passou a (a) verificar que o
  descriptor é `property` com `fset is None` e (b) aceitar `(AttributeError, TypeError)`
  — robusto entre versões de Python.
- **isort/format.** Ruff reorganizou o grupo de import local e reformatou o arquivo de
  teste; aplicado via `ruff check --fix` + `ruff format`.

## Validação (DoD §14.2)

```
ruff check .              → All checks passed!
ruff format --check .     → 86 files already formatted
mypy --strict src         → Success: no issues found in 30 source files
lint-imports              → 4 kept, 0 broken
pytest (full, -n 4)       → 705 passed, 11 skipped — 96.76% cobertura
pytest tests/contract/    → 8 passed
```

Cobertura pós-tarefa: `entities.py` 100%, `prometheus_judge.py` 100%,
`parquet_storage.py` 93%.

## Critérios de Aceitação (TAREFA-022)

- [x] 5 cenários de contrato passam em `pytest tests/contract/` (8 testes, a–e).
- [x] `BATCH_INVARIANT_CHECKLIST.md` sem itens marcados como "⚠ ausente".
- [x] `batch_invariant=True` confirmado num round-trip Parquet **real** (não mockado) —
  cenário (c), coluna lida via `ParquetFile.read()`.
- [x] `DeterminismRegime.GENERATOR` → `batch_invariant=False` round-trip — cenário (e).
- [x] import-linter OK; mypy --strict OK; DoD §14.2 OK.

## Observações para Próximas Tarefas

- **TAREFA-026 (`ComputeMetricsUseCase`)**: o Prompt A da 026 chama
  `writer.update_metrics(row_id=..., metrics=..., final_score=..., regime=DeterminismRegime.JUDGE)`,
  mas a assinatura atual do `ResultWriterPort.update_metrics` é
  `(row_id, metrics)` — **sem** `final_score` nem `regime`. Será necessário evoluir o
  port e os adapters (`ParquetStorage`, `InMemoryResultWriter`) na TAREFA-026 para
  aceitar e persistir `final_score` + `regime`. A property `batch_invariant` já está
  pronta para refletir o regime gravado.
- O atributo `determinism_regime` do `PrometheusJudgeAdapter` é o ponto de descoberta
  do regime pelo use case (Nota M2 item 3). O `PrometheusRubricJudgeAdapter` da
  TAREFA-024 deve expor o mesmo atributo.
- Marker `contract` disponível para futuras tarefas de invariantes cross-layer.
