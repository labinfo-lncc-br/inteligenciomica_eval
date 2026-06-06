# M6_TAREFA-606_A — Emenda do manual de operação

**Data**: 2026-06-05
**Milestone**: M6 — Qualidade e Segurança
**Épico**: E9 (Operações/Documentação)
**Skill**: python-engineer
**Prioridade / Tamanho**: P1 / M

---

## Objetivo

Aplicar edições cirúrgicas em `docs/operations_manual.md` (gerado na TAREFA-604) para:

1. Documentar `--run-id` como obrigatório na execução real (TAREFA-309/310 mergeadas).
2. Adicionar subseção "De onde vêm as perguntas" (`config/questions.yaml`, multi-área).
3. Adicionar nova Seção 4-B: modo `external` (ADR-014 / TAREFA-311).
4. Documentar `endpoint_env` em Seção 2 (sem novas env vars globais obrigatórias).
5. Aplicar pendência I4 do audit M6 (verificada: `--force-rows` não estava presente).
6. Adicionar ressalva sobre nome do subcomando `funnel` em Seção 9 (M5 adiado).
7. Atualizar `scripts/validate_manual.py` com validação de flags obrigatórias.

---

## Arquivos Criados / Modificados

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `docs/operations_manual.md` | Modificado (diff cirúrgico) | 5 blocos editados; nova Seção 4-B inserida |
| `scripts/validate_manual.py` | Modificado | Adicionada validação de flags `--run-id` e `--require-verified-determinism` |
| `docs/dev-log/M6_TAREFA-606_A_emenda-manual-operacao.md` | Criado | Este relatório |

---

## Decisões Técnicas

### 1. Nova seção como "Seção 4-B" (não renumerando)

Inserida entre Seção 4 e Seção 5 como `## Seção 4-B` para não renumerar as seções
existentes (7 → 11 continuam inalteradas). Edição cirúrgica conforme spec.

### 2. `--force-rows` (I4 da auditoria 604-B)

O audit 604-B já reportou `✅ Não há uso da flag inexistente`. Confirmado por grep:
nenhuma ocorrência de `--force-rows` no manual. A pendência I4 estava resolvida.
A TAREFA-606 manteve o `--force` correto em Seção 7 sem alteração.

### 3. Smoke-test: verificação de flags vs. subcomandos

O `validate_manual.py` existente verificava apenas subcomandos (`run`, `annotate` etc.)
via `ielm-eval <subcmd> --help`. Adicionado:
- `_run_help_output(subcmd)` — captura saída de `ielm-eval run --help`
- `_check_run_flags()` — verifica presença de `--run-id` e `--require-verified-determinism`
- Seção 3 de output no `main()`

### 4. Bloco de responsabilidade do operador

O bloco destacado na Seção 4-B usa blockquote Markdown com `⚠` para garantir que o
texto seja visualmente distinto. Inclui as quatro flags obrigatórias do juiz (ADR-003):
`VLLM_BATCH_INVARIANT=1`, `VLLM_ENABLE_V1_MULTIPROCESSING=0`, `temperature=0`,
`tensor_parallel_size=1`.

### 5. ADR-013 vs. ADR-014

O prompt 606 menciona "ADR-013" mas o ADR do modo external é o ADR-014
(`ADR-014-server-mode-external.md`). ADR-013 é o funil da Rodada 2. O manual usa
ADR-014 corretamente.

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| `endpoint_env` está em `JudgeConfig` (não em `ModelEntry` diretamente) | Verificado via `grep -rn endpoint_env src/` — `JudgeConfig` tem o campo; o manual documenta o padrão de nomes genérico adequado para ambos juiz e geradores |
| `questions:` no schema é `str | None` (não é um campo "yaml" nomeado) | Lido em `schema.py:146` — confirmado como `questions: str | None = None`; formato JSONL confirmado via leitura do arquivo empacotado `questions_rf1.jsonl` |

---

## Validação (DoD)

### Smoke-test do manual

```
uv run python scripts/validate_manual.py

Subcomandos ielm-eval:
  ielm-eval version              OK
  ielm-eval run                  OK
  ielm-eval status               OK
  ielm-eval annotate             OK
  ielm-eval analyze              OK
  ielm-eval report               OK
  ielm-eval validate-judge       OK

Flags obrigatórias em `ielm-eval run --help`:
  --run-id                                 OK
  --require-verified-determinism           OK

PASS — todos os subcomandos e flags validados existem na CLI.
```

### Saída de `ielm-eval run --help`

```
 Usage: ielm-eval run [OPTIONS]

 Run an evaluation round.

 Use ``--dry-run`` to validate the config and inspect the planned cell matrix
 and GPU/wave map without making any calls to vLLM, Qdrant, or other external
 services. Use ``--serial`` to preview the conservative one-wave-per-model
 layout.
 ``--run-id`` is required for real execution (identifies this run in the
 Parquet storage). Ignored in ``--dry-run`` mode.

 Em ``server_mode='external'`` (ADR-014), probes de proveniência são executados
 automaticamente antes do ciclo e exibidos em um Rich Panel. Use
 ``--require-verified-determinism`` para falhar se o juiz não for determinístico.

╭─ Options ────────────────────────────────────────────────────────────────────╮
│ *  --config                 PATH  Path to round config YAML. [required]     │
│    --run-id                 TEXT  Run identifier (required for real          │
│                                   execution).                                │
│    --phase                  TEXT  Phases to execute: A | B | both.          │
│                                   [default: both]                            │
│    --dry-run / --no-dry-run       Validate config without touching GPU or   │
│                                   network. [default: no-dry-run]             │
│    --serial / --concurrent        Serialize generators (one wave per        │
│                                   model). [default: concurrent]              │
│    --require-verified-...         Em server_mode='external', falha (exit 1) │
│                                   se o probe de determinismo retornar False. │
│    --help                         Show this message and exit.                │
╰──────────────────────────────────────────────────────────────────────────────╯
```

### Suíte de testes

```
1240 passed, 17 warnings in 22.92s
```

(E2E e integração excluídos — requerem E2E_ENABLED e Docker respectivamente.)

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| Seção 5 mostra `run ... --run-id`; `--phase`/`--serial` documentados | ✅ |
| Subseção de perguntas presente (multi-área, formato JSONL, gold_chunks M5) | ✅ |
| Seção 4-B: modo `external` com topologia, `server_mode`, `endpoint_env` | ✅ |
| Bloco de responsabilidade do operador com flags do juiz (ADR-003) | ✅ |
| Auditoria de proveniência (colunas Parquet + `endpoints_provenance` + flag CLI) | ✅ |
| `managed` é o default e inalterado — explicitado | ✅ |
| Seção 2: env vars por `endpoint_env` por NOME; sem novo obrigatório global | ✅ |
| Pendência I4 (`--force-rows`): confirmado ausente — sem alteração necessária | ✅ |
| Ressalva `funnel` na Seção 9 (verificar nome quando M5 sair) | ✅ |
| Seção 9 NÃO preenchida com comandos inexistentes (mantém stub) | ✅ |
| Smoke-test PASS (todos subcomandos + flags `--run-id` e `--require-verified-determinism`) | ✅ |
| Markdown válido; sem endpoints/segredos expostos | ✅ |
| Diff cirúrgico — seções inalteradas preservadas | ✅ |

---

## Observações para Próximas Tarefas

- A Seção 9 (Rodada 2 / M5) continua stub — quando M5 for implementado, confirmar
  o nome real do subcomando via `ielm-eval --help` antes de documentar.
- O arquivo `config/questions.yaml` referenciado na Seção 5 não existe no repo — é
  responsabilidade do especialista biomédico criar antes da Rodada 1 de produção
  (P4, conforme `questions_rf1.jsonl` com 3 placeholders).
- Pendência P1.1 (medição de VRAM GH200) ainda registrada nas Seções 1 e 3 — permanece
  como stub até medição real na bancada.
