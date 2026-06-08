# M3_TAREFA-314_A — Observabilidade Segura

**Data**: 2026-06-07
**Milestone**: M3 — Orquestração das 4 GPUs (hardening E9)
**Épico**: E9
**Skill**: backend-engineer, security-auditor, test-engineer
**Prioridade / Tamanho**: P0 (B1) / P2 (S3) · S

---

## Objetivo

Fechar o mascaramento parcial de URLs em logs de infraestrutura:

- **B1**: Consolidar os dois `_mask_url` duplicados (`external_vllm_server_manager.py` e
  `wiring.py`) em um helper único (`infrastructure/masking.py`). Mascarar URLs em TODOS
  os eventos de log dos probes de proveniência (`endpoint_probe.py`).
- **S3**: Reduzir exposição de payload do juiz (`prometheus_judge.py`) — substituir
  `raw_content=content[:500]` por `raw_len` + `raw_snippet` (≤ 120 chars).

---

## Arquivos Criados / Modificados

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `src/inteligenciomica_eval/infrastructure/masking.py` | Criado | Helper único `mask_url` + `mask_path` (ponto único de verdade) |
| `src/inteligenciomica_eval/infrastructure/adapters/external_vllm_server_manager.py` | Modificado | Remove `_mask_url` local; importa `mask_url` de `masking` |
| `src/inteligenciomica_eval/infrastructure/wiring.py` | Modificado | Remove `_mask_url` + `_mask_path` locais; importa de `masking` |
| `src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py` | Modificado | Todos os eventos de log usam `mask_url(...)` — 7 ocorrências |
| `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py` | Modificado | `raw_content[:500]` → `raw_len` + `raw_snippet[:120]` (2 eventos) |
| `tests/unit/infrastructure/test_masking.py` | Criado | 10 testes unitários do helper (`TestMaskUrl` + `TestMaskPath`) |
| `tests/unit/infrastructure/test_endpoint_probe.py` | Modificado | Nova classe `TestProbesMaskingUrls` — 4 testes de log (B1) |
| `tests/unit/infrastructure/test_external_server_manager.py` | Modificado | Importa `mask_url` de `masking`; corrige asserção sem `/***` |
| `tests/unit/infrastructure/adapters/test_prometheus_judge.py` | Modificado | Atualiza `test_nan_log_fields`; nova classe `TestPayloadSecurity` (S3) |

---

## Decisões Técnicas

### Helper único de masking (`infrastructure/masking.py`)

Localização escolhida: raiz de `infrastructure/` — acessível a todos os submodulos
sem criar dependências circulares. O helper expõe:

- `mask_url(url: str) -> str` — remove credenciais `user:pass@` e reduz a
  `scheme://host:port` (sem path/query/fragment). Retorna `"***"` se `hostname` for
  `None` (URL malformada como `"not-a-url"` → urlparse retorna scheme="" + hostname=None).
- `mask_path(p: Path) -> str` — retorna `<...>/{filename}` (já existia em `wiring.py`).

**Diferença vs. comportamento anterior**:
- `external_vllm_server_manager._mask_url` retornava `scheme://host:port/***` (com `/***`)
- `wiring._mask_url` retornava `scheme://netloc/***` (com netloc = host+port+auth)
- Novo `mask_url` retorna `scheme://host:port` (sem `/***`, sem auth, sem path)

O campo `/***` é redundante — o fato de não ter path já implica que o path está omitido.

**`settings.mask_endpoint` mantido**:
O `mask_endpoint` em `settings.py` tem comportamento diferente (mantém path, remove
apenas auth; lida com non-URL secrets). É usado para display de settings, não para logs
de infra — mantido como está (uso distinto justificado).

### Probes — mascaramento total (B1)

Todos os 7 eventos de log do `endpoint_probe.py` agora usam `mask_url(...)`:

| Evento | Campo mascarado |
|--------|----------------|
| `probe_served_model_ok` | `url=mask_url(models_url)` |
| `probe_served_model_empty` | `url=mask_url(models_url)` |
| `probe_served_model_failed` | `url=mask_url(models_url)` |
| `probe_vllm_version_unavailable` | `url=mask_url(version_url)` |
| `probe_vllm_version_failed` | `url=mask_url(version_url)` |
| `probe_judge_determinism_ok` | `url=mask_url(completions_url)` |
| `probe_judge_determinism_failed` | `url=mask_url(completions_url)` |

Os campos `source="/version"`, `source="header"`, `source="models_header"` são identificadores
de fonte (sem host) — não são URLs; não exigem mascaramento.

### Payload do juiz — redução de exposição (S3)

Dois eventos de `prometheus_judge.py` tinham `raw_content=content[:500]`:

**`prometheus_judge_parse_failure`** (em `_parse_response`):
```python
# ANTES:
raw_content=content[:500]
# DEPOIS:
raw_len=len(content),
raw_snippet=content[:120],
```

**`prometheus_judge_nan`** (em `score()` após esgotar retries):
```python
# ANTES:
raw_content=str(exc)[:500]
# DEPOIS:
_exc_str = str(exc)
raw_len=len(_exc_str),
raw_snippet=_exc_str[:120],
```

Justificativa: o conteúdo é saída do juiz (não segredo), mas 500 chars de payload
em log é desproporcional para triagem. `raw_len` + `raw_snippet[:120]` é suficiente
para diagnóstico sem despejar o payload.

---

## Problemas Encontrados e Soluções

**`mask_url("")`** (string vazia): `urlparse("")` retorna `hostname=None` → sem o
guard `if not p.hostname: return "***"`, a função retornava `"://None"`. Adicionado
guard logo após o parse.

**Teste de version probe**: o probe `probe_vllm_version` loga `source="/version"` como
identificador de fonte. O teste inicial verificava `"/version"` em todos os valores dos
eventos — falso positivo. Corrigido para verificar `"probehost:9876/version"` (host+path)
que só aparece se a URL crua for logada.

**`test_external_server_manager.py`** importava `_mask_url` do adapter diretamente.
Atualizado para importar `mask_url` de `masking` (com alias `as _mask_url` para
mínima alteração de testes). Asserção `"/***" in masked` removida — o novo helper
não acrescenta `/***`.

---

## Validação (DoD)

### Gates de qualidade

```
ruff check .          → All checks passed!
ruff format --check . → 173 files already formatted
mypy --strict src/    → Success: no issues found in 61 source files
lint-imports          → 4 kept, 0 broken
```

### Suíte de testes

```
uv run pytest -m "not integration" --cov=src --cov-fail-under=85 -n 4 -q

1273 passed, 6 skipped, 20 warnings in 31.45s
TOTAL coverage: 89.61% (≥ 85% ✓)
```

### Testes novos / atualizados

```
tests/unit/infrastructure/test_masking.py::TestMaskUrl::test_strips_path PASSED
tests/unit/infrastructure/test_masking.py::TestMaskUrl::test_strips_credentials PASSED
tests/unit/infrastructure/test_masking.py::TestMaskUrl::test_preserves_port PASSED
tests/unit/infrastructure/test_masking.py::TestMaskUrl::test_no_port_in_url PASSED
tests/unit/infrastructure/test_masking.py::TestMaskUrl::test_malformed_url_returns_sentinel PASSED
tests/unit/infrastructure/test_masking.py::TestMaskUrl::test_returns_string PASSED
tests/unit/infrastructure/test_masking.py::TestMaskUrl::test_strips_query_and_fragment PASSED
tests/unit/infrastructure/test_masking.py::TestMaskPath::test_shows_only_filename PASSED
tests/unit/infrastructure/test_masking.py::TestMaskPath::test_nested_path PASSED
tests/unit/infrastructure/test_masking.py::TestMaskPath::test_simple_filename PASSED
tests/unit/infrastructure/test_endpoint_probe.py::TestProbesMaskingUrls::test_probe_served_model_no_raw_url_in_logs PASSED
tests/unit/infrastructure/test_endpoint_probe.py::TestProbesMaskingUrls::test_probe_served_model_error_no_raw_url_in_logs PASSED
tests/unit/infrastructure/test_endpoint_probe.py::TestProbesMaskingUrls::test_probe_vllm_version_no_raw_url_in_logs PASSED
tests/unit/infrastructure/test_endpoint_probe.py::TestProbesMaskingUrls::test_probe_judge_determinism_no_raw_url_in_logs PASSED
tests/unit/infrastructure/adapters/test_prometheus_judge.py::TestBatchInvariant::test_nan_log_fields PASSED
tests/unit/infrastructure/adapters/test_prometheus_judge.py::TestPayloadSecurity::test_parse_failure_log_no_raw_content_field PASSED
tests/unit/infrastructure/adapters/test_prometheus_judge.py::TestPayloadSecurity::test_nan_log_no_raw_content_field PASSED
```

---

## Critérios de Aceitação

- [x] Um único helper de masking em `infrastructure/masking.py` (duplicatas removidas)
- [x] `_mask_url` em `external_vllm_server_manager.py` e `wiring.py` removidos; importam de `masking`
- [x] Todos os 7 eventos de log de `endpoint_probe.py` usam `mask_url(...)` — zero URL crua
- [x] `prometheus_judge_parse_failure` e `prometheus_judge_nan` logam `raw_len` + `raw_snippet` (≤120)
- [x] `raw_content` removido dos dois eventos (sem payload completo)
- [x] Comportamento preservado nos pontos já mascarados (`external_server_manager`, `wiring`)
- [x] 10 testes unitários do helper de masking (cobrindo credenciais, path-stripping, port, malformados)
- [x] 4 testes de masking de probe (falhavam antes — B1)
- [x] 2 testes de segurança de payload do juiz (falhavam antes — S3)
- [x] Suíte completa ≥ 85%; 1273 passed
- [x] Relatório da Parte A gravado em `docs/dev-log/`

---

## Observações para Próximas Tarefas

- **TAREFA-315** (acurácia documental): o `security_review.md` deve ser atualizado para
  descrever mascaramento **total** (não mais parcial) — pré-requisito para o Prompt B.
- **TAREFA-607** (doc-sync): CLAUDE.md §12 deve refletir TAREFA-314 como CONCLUÍDA;
  §13 deve documentar `infrastructure/masking.py` como ponto único de mascaramento.
- **Regressão `settings.mask_endpoint`**: a função permanece em `settings.py` com
  comportamento diferente (keeppath + handle-non-URL). Não confundir com `masking.mask_url`.
