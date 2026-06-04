# M3_TAREFA-310_E — Reauditoria de amplitude e robustez

**Data:** 2026-06-04  
**Tarefa:** TAREFA-310 — E2E gate M3  
**Escopo auditado:** estado atual do código + relatórios do desenvolvedor ciclos C e D  
**Resultado:** **FAIL**

## Objetivo

Rever se os ciclos C/D fecharam os achados anteriores e se a implementação E2E ficou
ampla e robusta o suficiente para cumprir o Prompt B de `docs/prompts_m3_tarefa_310.md`.

## Achados

### 🛑 [Fixture] `tests/e2e/test_m3_full_cycle.py:397`

O contrato de perguntas reais continua coberto só parcialmente. A fixture `questions_stub`
usa `load_questions(Path(str(resource)))[:2]`, mas o path é montado diretamente para o
arquivo empacotado `questions_rf1.jsonl`, sem passar pelo `round_config` nem por um campo
`questions` configurável da rodada.

**Impacto:** o teste prova que o loader abre um arquivo real, mas **não** prova o contrato
pedido no prompt: `questions_stub = load_questions(Path(round_config_stub.questions))[:2]`
nem a integração do E2E com um caminho de perguntas configurado pela rodada.

**Evidências:**
- [tests/e2e/test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:397)
- [src/inteligenciomica_eval/infrastructure/config/schema.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/config/schema.py:131)

### ⚠️ [Storage API] `tests/e2e/test_m3_full_cycle.py:463`

A checagem de schema continua saindo da API pública do storage e lendo Parquet por
atributo privado (`_base_dir`) + `pyarrow.parquet.ParquetFile`.

**Impacto:** isso reduz robustez do teste E2E. A suíte fica acoplada ao layout físico
interno do adapter, não apenas ao contrato exposto pelo sistema.

**Evidências:**
- [tests/e2e/test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:463)
- [tests/e2e/test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:499)

### ⚠️ [Golden] `tests/e2e/test_m3_full_cycle.py:493`

O golden ainda não valida `rank_scores_by_config` como pedido. O arquivo contém as 6
chaves, mas todas com `null`, e o cenário principal só verifica que todos os rank scores
calculados no relatório são `NaN`.

**Impacto:** a parte do prompt que pede “inclui também o RankScore esperado por
`{base, llm}`” continua sem cobertura material. O teste não confronta o dicionário
`rank_scores_by_config` do golden contra resultados reais por configuração.

**Evidências:**
- [tests/golden/e2e_m3_expected.json](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/golden/e2e_m3_expected.json:26)
- [tests/e2e/test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:493)
- [tests/e2e/test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:621)

## Correções confirmadas

- O cenário RNF7 agora cobre `KeyboardInterrupt` originado no gerador, sem `pytest.raises`,
  com persistência parcial e `stop()` chamado para os servidores ativos.
- `RunExperimentUseCase._run()` passou a capturar `KeyboardInterrupt` e devolver relatório
  parcial em shutdown gracioso.

**Evidências:**
- [tests/e2e/test_m3_full_cycle.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/tests/e2e/test_m3_full_cycle.py:690)
- [src/inteligenciomica_eval/application/use_cases/run_experiment.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/application/use_cases/run_experiment.py:314)

## Validação executada

```text
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -m e2e tests/e2e/test_m3_full_cycle.py -v --timeout=30
→ 5 passed in 0.94s

UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
→ All checks passed!

UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src
→ Success: no issues found in 57 source files

UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports
→ Contracts: 4 kept, 0 broken.
```

## Sumário

Os ciclos C/D resolveram bem o gap de shutdown e melhoraram a aderência ao RNF7. Ainda
assim, o gate E2E permanece com escopo menor que o pedido no prompt em três frentes:
configuração real das perguntas pela rodada, dependência de internals do storage para
schema e ausência de validação material do `rank_scores_by_config` do golden.

**Recomendação:** `Request changes`
