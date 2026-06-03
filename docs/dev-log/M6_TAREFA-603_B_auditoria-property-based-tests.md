# M6_TAREFA-603_B_auditoria-property-based-tests

Data: 2026-06-03
Prompt-base: `docs/m6_tarefas_603.md`
Resultado: **FAIL**

## Resumo

A suíte nova de property-based tests foi adicionada e os 15 testes passam com
`pytest -m property` em 3.52s no recorte auditado. O marcador `property` foi
registrado em `pyproject.toml`, os quatro arquivos de teste existem e os
targets 1, 2 e partes relevantes do 4 estão cobertos.

Apesar disso, a tarefa **não passa** porque há uma divergência material no
Target 3 e uma cobertura incompleta no Target 4. O teste de `config_hash` não
exercita `config_hash()` de produção; ele valida apenas uma reimplementação
local do algoritmo. Além disso, o roundtrip de `ParquetStorage` não compara
todos os campos persistidos do `EvaluationResult`.

## Divergências

| Critério | Arquivo:linha | Gravidade |
|---|---|---|
| O Target 3 deveria validar o alvo real `config_hash(config: RoundConfig) -> str`, mas os testes exercitam apenas o helper local `_canonical_dict_hash`. Isso reduz o teste a uma verificação de consistência da cópia local e não detecta drift entre a implementação real e a duplicada no teste. | `tests/unit/infrastructure/config/test_config_hash_property.py:31`, `src/inteligenciomica_eval/infrastructure/config/provenance.py:13` | **BLOQUEADOR** |
| O roundtrip do Target 4 não compara o `EvaluationResult` completo. `_result_eq()` ignora `retrieved_chunk_ids`, `retrieved_chunks_text`, `retrieval_scores`, `critical_failure_flag` e `critical_failure_note`, embora esses campos sejam serializados no Parquet e reconstruídos em `from_row()`. Uma regressão nessas colunas não seria detectada por `test_parquet_roundtrip`. | `tests/unit/infrastructure/adapters/test_parquet_roundtrip_property.py:99`, `src/inteligenciomica_eval/domain/entities.py:56`, `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:241` | **IMPORTANTE** |

## Evidências positivas

- O marcador `property` foi registrado em `pyproject.toml` em `pyproject.toml:180`.
- Os quatro arquivos da tarefa existem:
  - `tests/unit/infrastructure/adapters/test_prometheus_parser_property.py`
  - `tests/unit/domain/test_metric_vector_property.py`
  - `tests/unit/infrastructure/config/test_config_hash_property.py`
  - `tests/unit/infrastructure/adapters/test_parquet_roundtrip_property.py`
- Todas as funções dos arquivos novos estão decoradas com `@pytest.mark.property`.
- O Target 1 cobre `@given(st.text())` e `@settings(max_examples=200)` em `tests/unit/infrastructure/adapters/test_prometheus_parser_property.py:72`.
- O Target 2 inclui casos com `NaN` e roundtrip NaN-safe em `tests/unit/domain/test_metric_vector_property.py:62` e `:87`.
- O Target 3 testa explicitamente sensibilidade e canonicidade por ordem reversa e permutação arbitrária, ainda que sobre o helper local, em `tests/unit/infrastructure/config/test_config_hash_property.py:104`, `:128` e `:138`.
- O Target 4 cobre `@settings(database=None)` e idempotência por `row_id` em `tests/unit/infrastructure/adapters/test_parquet_roundtrip_property.py:130`, `:161` e `:191`.
- Os testes novos são independentes de GPU/rede e não usam `@pytest.mark.integration`.

## Validação executada

- `uv run pytest tests/unit/infrastructure/config/test_config_hash_property.py tests/unit/infrastructure/adapters/test_prometheus_parser_property.py tests/unit/domain/test_metric_vector_property.py tests/unit/infrastructure/adapters/test_parquet_roundtrip_property.py -m property` → `15 passed in 3.52s`
- Inspeção direta dos arquivos alterados e dos módulos alvo:
  - `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py`
  - `src/inteligenciomica_eval/domain/value_objects.py`
  - `src/inteligenciomica_eval/infrastructure/config/provenance.py`
  - `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py`

## Recomendação

**Request changes**.

Correção mínima esperada:
1. Reescrever o Target 3 para exercitar `config_hash()` de produção sobre instâncias reais de `RoundConfig`, mantendo as propriedades de estabilidade, sensibilidade e canonicidade.
2. Ampliar `_result_eq()` ou equivalente no Target 4 para comparar todos os campos persistidos no Parquet, incluindo `retrieved_chunk_ids`, `retrieved_chunks_text`, `retrieval_scores`, `critical_failure_flag` e `critical_failure_note`.
