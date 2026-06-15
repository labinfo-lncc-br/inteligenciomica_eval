# M3_TAREFA-317_A — Resolução do served_model_id + smoke run external

**Data**: 2026-06-15
**Milestone**: M3 — Orquestração das 4 GPUs
**Épico**: E3/E4 (orquestração + proveniência)
**Skill**: backend-engineer, python-engineer, test-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

1. **FIX** — corrigir a resolução do nome do modelo na `_VLLMGeneratorFactory` para usar o `served_model_id` sondado (probe) antes de cair no layout por porta (ADR-012) ou no fallback `"model"`.
2. **Comando `smoke`** — entregar `ielm-eval smoke --config <yaml> [--llm <name>] [--question-id <id>]` que valida 1 modelo × 1 pergunta × 1 seed ponta a ponta sem gravar no dataset de produção.
3. **Manual** — atualizar seção G1 (Seção 5, antes de "Execução completa") com o comando real e leitura do diagnóstico.

---

## Arquivos Criados / Modificados

| Arquivo | Tipo | Descrição |
|---------|------|-----------|
| `src/inteligenciomica_eval/infrastructure/wiring.py` | modificado | FIX factory + `served_model_by_url` + `DIContainer.endpoints_provenance` |
| `src/inteligenciomica_eval/cli.py` | modificado | subcomando `smoke` |
| `docs/operations_manual.md` | modificado | Seção 5 — G1 smoke run |
| `tests/unit/infrastructure/test_vllm_generator_factory.py` | criado | 7 testes de regressão da factory |
| `tests/unit/test_cli_smoke_command.py` | criado | 12 testes do comando smoke |

---

## Decisões Técnicas

### 1. FIX — `_VLLMGeneratorFactory` (wiring.py:218)

**Antes (TAREFA-316):**
```python
port = int(url.split(":")[2].split("/")[0])
model = self._port_to_model.get(port, "model")
```

**Depois (TAREFA-317):**
```python
# Precedência: (a) served_probe > (b) port_layout > (c) fallback
served = self._served_model_by_url.get(url, "")
if served:
    model = served
    _resolution = "served_probe"
else:
    try:
        port = int(url.split(":")[2].split("/")[0])
        if port in self._port_to_model:
            model = self._port_to_model[port]
            _resolution = "port_layout"
        else:
            model = "model"
            _resolution = "fallback"
    except (IndexError, ValueError):
        model = "model"
        _resolution = "fallback"
_log.debug("generator_model_resolved", url_masked=mask_url(url), model=model, resolution=_resolution)
```

**Parâmetro adicionado ao `__init__`:** `served_model_by_url: dict[str, str] | None = None`

**`build_container` — montagem de `served_model_by_url`:**
```python
# External: _gen_urls tem URLs distintas → served_model_id confiável.
# Managed: _gen_urls é degenerado (mesma URL) → probes falham antes dos servidores
#   subirem → dict vazio → factory cai no layout de porta (ADR-012).
served_model_by_url = {
    url: _gen_served_ids[name]
    for name, url in _gen_urls.items()
    if _gen_served_ids.get(name)
}
generator_factory = _VLLMGeneratorFactory(
    port_to_model, ..., served_model_by_url=served_model_by_url
)
```

### 2. `DIContainer.endpoints_provenance`

Campo adicionado ao `DIContainer` com `default_factory=dict`. Permite que o comando `smoke` acesse os probes já executados em `build_container` sem re-executar probes (requisito "reaproveitar proveniência existente"). `build_fake_container` usa o default `{}`.

### 3. `ParquetStorage` — `run_id` no construtor

Descoberto durante testes: `ParquetStorage.append` usa `self._provenance.run_id` (fixado no construtor), não um parâmetro. O smoke passa `run_id=smoke_run_id` ao construtor para que `load(run_id=smoke_run_id)` filtre corretamente os resultados temporários.

### 4. Comando `smoke`

- Usa `asyncio.run()` para cada uma das 3 passadas.
- `_smoke_cfg = SimpleNamespace(...)` satisfaz `RunConfigView` por duck-typing.
- `TemporaryDirectory(prefix="ielm_smoke_")` — storage isolado, limpado ao final.
- `resolved_model_name = getattr(smoke_generator, "_model", "unknown")` — acessa o nome resolvido pela factory sem quebrar fakes.
- Exit code 0 apenas quando `gen_status == "ok" AND not math.isnan(judge_score)`.
- Log estruturado `smoke_diagnostic` com todos os campos de diagnóstico.

---

## Problemas Encontrados e Soluções

| Problema | Causa | Solução |
|----------|-------|---------|
| `gen_status = "empty"` nos testes mesmo com geração bem-sucedida | `ParquetStorage` armazena `run_id` fixado no construtor; `load(run_id=smoke_run_id)` não encontrava as linhas escritas sem `run_id`. | Passar `run_id=smoke_run_id` ao construtor do `temp_storage`. |
| `mypy --strict` em `dict(ep_prov.get(...))` | `endpoints_provenance` é `dict[str, object]` → `.get(key)` retorna `object` → `dict(object)` falha no mypy. | Função auxiliar `_as_dict(v: object) -> dict[str, object]` com `isinstance` check. |
| `RUF002` no docstring do smoke | `×` (MULTIPLICATION SIGN) em docstring. | Trocado por `x` (ASCII). |

---

## Validação (DoD)

### Gates executados

```
$ uv run ruff check src/ tests/unit/infrastructure/test_vllm_generator_factory.py tests/unit/test_cli_smoke_command.py
All checks passed!

$ uv run ruff format --check .
176 files already formatted

$ uv run mypy --strict src/
Success: no issues found in 61 source files

$ uv run lint-imports
Contracts: 4 kept, 0 broken.

$ uv run pytest tests/unit/infrastructure/test_vllm_generator_factory.py tests/unit/test_cli_smoke_command.py -v --timeout=60
19 passed in 1.00s

$ uv run pytest -m "not integration" --cov=src --cov-report=term-missing --cov-fail-under=85 -n 4 --timeout=120 -q
1337 passed, 6 skipped, 21 warnings
Required test coverage of 85% reached. Total coverage: 88.93%
```

### Testes de regressão (falharam contra o código anterior à TAREFA-317)

| Cenário | Resultado |
|---------|-----------|
| URL de túnel `http://localhost:8010/v1` COM `served_model_by_url` | `PASS` → retorna `served_model_id` (NÃO `"model"`) |
| URL managed `http://localhost:8001/v1` SEM `served_model_by_url` | `PASS` → retorna nome do registry (port_layout) |
| URL desconhecida sem served | `PASS` → retorna `"model"` (fallback) |
| `served_probe` tem prioridade sobre `port_layout` | `PASS` |
| `served_model_by_url` com string vazia → cai para port_layout | `PASS` |

### Testes do comando `smoke`

| Cenário | Resultado |
|---------|-----------|
| Fakes saudáveis → EXIT 0 | `PASS` |
| Gerador retorna texto vazio (simula 404) → EXIT 1 | `PASS` |
| Juiz retorna NaN → EXIT 1 | `PASS` |
| Smoke não cria `data/` (usa temp) | `PASS` |
| `--llm` inválido → EXIT 1 | `PASS` |
| `--llm` válido funciona | `PASS` |
| `smoke` aparece no `--help` | `PASS` |
| `smoke --help` EXIT 0 | `PASS` |

---

## Critérios de Aceitação

- [x] `_VLLMGeneratorFactory` usa `served_model_by_url` como precedência máxima
- [x] `port_to_model` (ADR-012) preservado como fallback para modo managed
- [x] `"model"` é último recurso quando ambos falham
- [x] Log usa `mask_url(url)` — sem URL crua
- [x] `build_container` monta `served_model_by_url` de `_gen_served_ids` / `_gen_urls`
- [x] Comentário explica por que managed não regride
- [x] `DIContainer.endpoints_provenance` exposto ao `smoke`
- [x] `smoke` usa storage TEMPORÁRIO (não grava em `data/`)
- [x] `smoke` imprime diagnóstico: server_mode, served_model_id, nome enviado (WARN se `"model"`), status geração, score juiz, embeddings, determinism_verified
- [x] Exit code 0 somente se geração ok E score não-NaN
- [x] Manual Seção 5 — G1 smoke atualizado com comando real
- [x] `mypy --strict`, `ruff`, `lint-imports` verdes
- [x] Cobertura ≥ 85% (alcançado: 88.93%)

---

## Observações para Próximas Tarefas

- O `resolved_model_name` exibido no diagnóstico é `"unknown"` para fakes (FakeGenerator não tem `_model`); em produção com `VLLMGeneratorAdapter`, retorna o nome real.
- Em modo `managed`, `served_model_by_url` tende a ser vazio (servidores não subiram durante probes) → a factory cai no `port_layout` como esperado.
- O campo `DIContainer.endpoints_provenance` pode ser útil para outros subcomandos no futuro (ex.: `status` com diagnóstico de endpoint).
- TAREFA-608 (doc-sync do 316) continua paralela a esta — sem dependência.
