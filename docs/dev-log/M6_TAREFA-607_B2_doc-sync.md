# M6_TAREFA-607_B2 — Re-auditoria do doc-sync (ciclo B2)

**Data**: 2026-06-08
**Commit auditado**: `c04e166`
**Resultado**: **FAIL**

---

## Foco da re-auditoria

Revalidar o achado B1 da auditoria anterior: referências residuais ao subcomando
inexistente `serve` na arquitetura, comparando o documento com a CLI real.

---

## Evidências objetivas

### `git diff --name-only`

```text
docs/arquitetura_detalhada_validacao_inteligenciomica.md
docs/dev-log/M6_TAREFA-607_A2_doc-sync.md
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

---

## Divergência remanescente

| Seção/arquivo | Critério | Gravidade | Observação |
|---|---|---|---|
| `docs/arquitetura_detalhada_validacao_inteligenciomica.md:738` | Coerência doc↔CLI real | IMPORTANTE | A árvore do pacote ainda descreve `cli.py` como `Typer: run/analyze/report/annotate/serve`, mas `serve` não existe no `ielm-eval --help`. |

---

## O que foi corrigido corretamente

- O diagrama C4 não lista mais `serve/`; agora usa `status/`.
- A tabela de stack em §7.1 foi alinhada para os subcomandos reais.
- O texto da topologia §7.2 agora fala apenas em `run`.

---

## Conclusão

O ciclo A2 resolveu 3 das 4 ocorrências apontadas, mas ainda resta uma referência a
`serve` como subcomando na árvore do pacote. Como a §15 e o `--help` real afirmam que
a CLI tem exatamente 8 subcomandos sem `serve`, a documentação ainda permanece
internamente inconsistente.

Próximo passo: corrigir a linha da árvore de código (`cli.py`) e reenviar para B3.
