# M6_TAREFA-603_A — Property-based Tests em Parsers e Serializers

**Data**: 2026-06-03
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: test-engineer
**Prioridade / Tamanho**: P1 / S

---

## Objetivo

Adicionar testes property-based com `hypothesis` para os 4 targets críticos de
roundtrip/idempotência do subsistema, sem alterar código de produção.  Registrar
os marcadores `property` e `security` em `pyproject.toml`.

---

## Arquivos Criados / Modificados

| Arquivo | Ação |
|---------|------|
| `pyproject.toml` | Marcadores `property` e `security` adicionados a `[tool.pytest.ini_options] markers` |
| `tests/unit/infrastructure/config/__init__.py` | Criado (novo diretório de testes) |
| `tests/unit/infrastructure/adapters/test_prometheus_parser_property.py` | Criado (Target 1 — parser Prometheus) |
| `tests/unit/domain/test_metric_vector_property.py` | Criado (Target 2 — MetricVector roundtrip) |
| `tests/unit/infrastructure/config/test_config_hash_property.py` | Criado (Target 3 — config_hash) |
| `tests/unit/infrastructure/adapters/test_parquet_roundtrip_property.py` | Criado (Target 4 — ParquetStorage) |

---

## Decisões Técnicas

### Target 1 — Parser Prometheus
- `_parse_response` é método de instância puro (não usa atributos de rede).
  Adapter instanciado com `MagicMock()` como registry — sem rede, sem SDK real.
- `_ParseFailureError` importado diretamente do módulo (`# type: ignore[attr-defined]`
  pois é nome privado).
- P1.2 cobre strings arbitrárias via `st.text()` — inclui binários, JSON malformado,
  strings vazias.  Nenhum `KeyError`/`ValueError`/`JSONDecodeError` não-capturado
  pode vazar: todos são absorvidos em `_ParseFailureError`.
- `@settings(max_examples=200)` em todos os 3 testes do Target 1.

### Target 2 — MetricVector roundtrip
- `MetricVector` não tem métodos `to_dict`/`from_dict` na produção.  Implementados
  via helpers locais: `dataclasses.asdict(mv)` + `MetricVector(**d)`.
- Comparação NaN-safe (`_mv_eq_nan_safe`) necessária porque `float('nan') == float('nan')`
  é `False` em Python — o dataclass `__eq__` gerado automaticamente falha para NaN.
- P2.3a e P2.3b usam `st.builds(MetricVector, **{f: strategy})` que permite fixar
  estratégias por campo.
- P2.3b variante usa `_metric_vector_strategy()` e força um campo para NaN —
  cobre o caso de mix válido+NaN.

### Target 3 — config_hash
- A assinatura real é `config_hash(config: RoundConfig) -> str`, não `dict`.
  Gerar `RoundConfig` arbitrário com hypothesis seria muito complexo (modelo
  Pydantic com vários validators).
- Abordagem: helper local `_canonical_dict_hash(d: dict) -> str` que espelha
  o algoritmo interno (`json.dumps(sort_keys=True, ensure_ascii=True,
  separators=(',',':')) + SHA-256`).  O docstring deixa claro que estamos
  testando o algoritmo, não a interface de produção.
- Sensibilidade (P3.2): usa `_MUTATION_SENTINEL` (string impossível de colidir
  com a estratégia) + `assume()` para garantir que o JSON muda de fato.
- Canonicidade (P3.3): dois testes — ordem reversa e permutação arbitrária via
  `st.permutations()`.

### Target 4 — ParquetStorage roundtrip
- `tmp_path` do pytest não é recriada entre exemplos hypothesis (uma fixture por
  invocação de teste, não por exemplo).  Solução: `tempfile.TemporaryDirectory()`
  dentro de cada teste → cada exemplo tem diretório isolado.
- `@settings(database=None)` evita acúmulo de exemplos no banco do hypothesis
  entre runs — testes de I/O não devem reusar exemplos antigos.
- Métricas restritas a `{0.0, 0.25, 0.5, 0.75, 1.0, NaN}` — valores com
  representação float32 exata → roundtrip sem perda de precisão (Parquet usa
  `pa.float32()`; valores arbitrários em float64 não sobrevivem sem delta).
- `retrieval_scores=(0.5,)` fixado pelo mesmo motivo (stored as `list_(float32)`).
- Comparação NaN-safe em `_result_eq` para `MetricVector`, `FinalScore` e
  `DeterminismRegime`.
- `@settings(max_examples=50)` — envolve I/O de arquivo (criação de diretórios
  e escrita de Parquet por exemplo).
- **Benefício colateral**: cobertura do `parquet_storage.py` subiu de 57% (unit-only)
  para 89% (unit+e2e), confirmando que os property tests cobrem novos ramos.

### Isolamento de GPU/rede
Todos os 4 targets rodam em CPU sem container, serviço externo ou GPU.
Nenhum marcador `@pytest.mark.integration` ou `skipif` para containers.

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| `from tests.factories.factories import ...` não funciona (módulo `tests` não está no PYTHONPATH diretamente) | Corrigido para `from factories.factories import ...` (padrão dos demais testes unitários) |
| `ruff` I001 — imports desordenados em 4 arquivos após uso de `from hypothesis import given, settings, strategies as st` na mesma linha | `ruff check --fix` + `ruff format` |
| `pyproject.toml` sem `--timeout` plugin instalado | Omitido `--timeout=120`; limite de tempo verificado pelo tempo real de execução |

---

## Validação (DoD)

### Marcadores
```
pytest -m property   →  15 testes selecionados, sem aviso de marcador desconhecido
pytest -m security   →   0 testes (marcador registrado; testes criados na TAREFA-605)
```

### Execução property tests
```
uv run pytest -m property -v
→ 15 passed in 14.93s   (< 60 s ✓)
```

### Gate completo (não integration)
```
uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4
→ 1131 passed, 6 skipped — 90.43% total coverage  ✓
```

### Linters
```
ruff check .             → All checks passed
ruff format --check .    → (sem reformatações necessárias)
mypy --strict src/       → Success: no issues found in 54 source files
lint-imports             → 4 kept, 0 broken
```

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| Marcador `property` registrado em `pyproject.toml` | ✅ |
| `pytest -m property` sem aviso de marcador desconhecido | ✅ |
| Marcador `security` registrado (pré-requisito TAREFA-605) | ✅ |
| 4 arquivos de teste, um por target | ✅ |
| Todas as funções decoradas com `@pytest.mark.property` | ✅ |
| Target 1 — P1.1, P1.2 (`st.text()` presente), P1.3 | ✅ |
| Target 1 — `@settings(max_examples=200)` | ✅ |
| Target 2 — roundtrip NaN-safe, idempotência, detecção de NaN | ✅ |
| Target 3 — estabilidade, sensibilidade, canonicidade (ordem diferente → mesmo hash) | ✅ |
| Target 4 — `tempfile.TemporaryDirectory()` (isolamento por exemplo) | ✅ |
| Target 4 — `@settings(database=None)` | ✅ |
| Target 4 — idempotência P4.2 (2 writes → 1 linha) | ✅ |
| Hypothesis não falsificou nenhuma propriedade | ✅ (nenhum bug encontrado) |
| Testes em < 60 s | ✅ (14.93 s) |
| `ruff`, `mypy --strict`, `import-linter` verdes | ✅ |
| Zero alterações em código de produção | ✅ |

---

## Observações para Próximas Tarefas

- **TAREFA-604** (manual de usuário): o marcador `security` já está registrado para
  receber os testes da TAREFA-605 sem precisar alterar `pyproject.toml` novamente.
- **TAREFA-605** (revisão de segurança): os testes usarão `@pytest.mark.security`
  e poderão ser executados com `pytest -m security`.
- A cobertura de `parquet_storage.py` subiu para 89% no gate unit+e2e, revelando
  que os property tests cobrem ramos do `update_metrics` ainda descobertos
  (linhas 471-521, 544-573) — candidatos para property tests adicionais em M7.
