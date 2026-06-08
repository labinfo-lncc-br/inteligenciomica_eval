# M6_TAREFA-607_B — Auditoria do doc-sync (arquitetura v1.2 / visão v1.1)

**Data**: 2026-06-08
**Commit auditado**: `faaf1aa`
**Resultado**: **FAIL**

---

## Escopo auditado

- `docs/arquitetura_detalhada_validacao_inteligenciomica.md`
- `docs/visao_alto_nivel_validacao_inteligenciomica.md`
- `docs/operations_manual.md`
- `docs/adr/ADR-013-round2-funnel.md`
- `docs/adr/ADR-014-server-mode-external.md`
- `docs/dev-log/M6_TAREFA-607_A_doc-sync.md`
- `uv run ielm-eval --help`
- `uv run ielm-eval run --help`
- schema real em `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py`

---

## Evidências objetivas

### `git diff --name-only`

```text
docs/arquitetura_detalhada_validacao_inteligenciomica.md
docs/dev-log/M6_TAREFA-607_A_doc-sync.md
docs/visao_alto_nivel_validacao_inteligenciomica.md
```

### `ielm-eval --help`

```text
Commands:
  version
  run
  annotate
  analyze
  report
  status
  show-config
  validate-judge
```

### `ielm-eval run --help`

```text
Options:
  --config
  --run-id
  --phase
  --dry-run / --no-dry-run
  --serial / --concurrent
  --require-verified-determinism / --no-require-verified-determinism
```

### Schema real

- `EVAL_SCHEMA` contém **46 colunas**.
- As colunas `server_mode`, `served_model_id` e `determinism_verified` existem no storage real.

---

## Divergências

| Seção/arquivo | Critério | Gravidade | Observação |
|---|---|---|---|
| `docs/arquitetura_detalhada_validacao_inteligenciomica.md:138` | §15 e arquitetura devem refletir a CLI real | IMPORTANTE | O diagrama de containers ainda lista `serve/` dentro da CLI, mas `ielm-eval --help` expõe apenas 8 subcomandos e `serve` não existe. |
| `docs/arquitetura_detalhada_validacao_inteligenciomica.md:602` | CLI real sem subcomandos inexistentes | IMPORTANTE | A tabela de stack ainda descreve `typer` como CLI `run/analyze/report/annotate/serve`. |
| `docs/arquitetura_detalhada_validacao_inteligenciomica.md:646` | Coerência doc↔código | IMPORTANTE | O texto afirma que o `serve/run` da CLI orquestra o ciclo de vida. O as-built atual só expõe `run`. |
| `docs/arquitetura_detalhada_validacao_inteligenciomica.md:738` | Estrutura de código/CLI real | IMPORTANTE | A árvore do pacote ainda documenta `cli.py` como `run/analyze/report/annotate/serve`. |

---

## Validação dos demais critérios

- DOCS-ONLY: **OK**
- Versões bumpadas (`arquitetura 1.2`, `visão 1.1`): **OK**
- Changelogs presentes: **OK**
- ADR-013 e ADR-014 não foram trocados: **OK**
- §§4.3/5.3 não foram duplicadas e seguem coerentes com o schema real: **OK**
- §7.2.1 external presente: **OK**
- §12.4 external presente com `determinism_verified=False` por default e `--require-verified-determinism`: **OK**
- RNF1 com nuance managed vs external: **OK**
- §14.6 reconciliada com 308/309/310/311/312: **OK**
- §14.9 cita 606/607: **OK**
- §15.7 lista os 8 subcomandos reais: **OK**
- §15.8 usa `run --run-id` e remove fluxo fictício generation/judging: **OK**
- §15.9 marca M5 futuro sem vender subcomando atual: **OK**
- Visão §9.4 mantém tom alto nível e registra `server_mode` / `served_model_id` / `determinism_verified`: **OK**

---

## Conclusão

O núcleo da TAREFA-607 foi implementado corretamente, mas a arquitetura v1.2 ainda
mantém referências a um subcomando inexistente (`serve`) em quatro pontos fora de §15.
Isso deixa o documento internamente contraditório: §15 afirma corretamente que a CLI tem
8 subcomandos, enquanto outras seções ainda documentam um non-existent command.

Recomendação: corrigir as quatro ocorrências de `serve` na arquitetura e reenviar para
re-auditoria B2.
