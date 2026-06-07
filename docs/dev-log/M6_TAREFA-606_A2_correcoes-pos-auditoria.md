# M6_TAREFA-606_A2 — Correções pós-auditoria Codex (ciclo B→A)

**Data**: 2026-06-07
**Milestone**: M6 — Qualidade e Segurança
**Épico**: E9 (Operações/Documentação)
**Skill**: python-engineer
**Ciclo**: A2 (correções após Prompt B — relatório da auditoria Codex em
`M6_TAREFA-606_B_auditoria-codex-manual.md`)

---

## Veredito da auditoria

**FAIL parcial** — 2 bloqueadores (desalinhamento runtime), 1 aviso operacional,
1 texto residual, 1 sugestão de robustez no tooling.

---

## Correções aplicadas

### C1 — `VLLM_ENABLE_V1_MULTIPROCESSING=1` → `=0` na Seção 4

**Achado**: A Seção 4 (subida manual do juiz em modo managed) ainda tinha
`VLLM_ENABLE_V1_MULTIPROCESSING=1`, enquanto o regime correto é `=0` (ADR-003).
A nova Seção 4-B já estava correta; o manual ficou internamente contraditório.

**Arquivo**: `docs/operations_manual.md:234`  
**Correção**: `VLLM_ENABLE_V1_MULTIPROCESSING=1` → `VLLM_ENABLE_V1_MULTIPROCESSING=0`

### C2 — Subseção de perguntas: documentar `BENCHMARK_QUESTIONS_PATH` (runtime real)

**Achado**: O manual documentava `questions: "config/questions.yaml"` (campo do schema)
como mecanismo de configuração, mas o runtime lê de `settings.BENCHMARK_QUESTIONS_PATH`
(`wiring.py:627`). O campo `questions:` existe no schema mas **não está conectado ao
loader**. O formato também era incorreto (`.yaml` em vez de `.jsonl`).

**Arquivo**: `docs/operations_manual.md` (subseção "De onde vêm as perguntas")  
**Correção**:
- Documentada `BENCHMARK_QUESTIONS_PATH` como mecanismo real de configuração
- Formato corrigido para JSONL (confirmado por `loader.py:11` e arquivo empacotado)
- Adicionada nota explícita: "o campo `questions:` existe no schema do YAML de rodada
  mas **não está conectado ao loader** na versão atual"
- Exemplos de multi-área agora usam `export BENCHMARK_QUESTIONS_PATH=...` por execução

### C3 — `experiment_round1_external.yaml` → usar o YAML existente

**Achado**: A Seção 4-B referenciava `config/experiment_round1_external.yaml` como
artefato real, mas só existe `config/experiment_round1.yaml`. Instrução operacional
incompleta para uso direto.

**Arquivo**: `docs/operations_manual.md` (Seção 4-B, bloco de configuração e execução)  
**Correção**:
- "Configuração do YAML de rodada" agora instrui a **adicionar** `server_mode: external`
  ao YAML existente (`config/experiment_round1.yaml`) em vez de referenciar arquivo
  inexistente
- Bloco "Executando em modo external" corrigido para usar
  `--config config/experiment_round1.yaml`

### C4 — Remoção de texto residual "Quando o full run estiver implementado..."

**Achado**: Subseção "Retomando uma execução interrompida" ainda tinha o blockquote
"Quando o full run estiver implementado, basta re-executar o mesmo comando..." — resíduo
do texto anterior que contradiz a Seção 5 atualizada.

**Arquivo**: `docs/operations_manual.md:532`  
**Correção**: blockquote removido. A instrução de retomada por `row_id` ficou completa
sem o texto condicional.

### C5 — Unificação de estratégia de invocação da CLI no smoke-test

**Achado (sugestão)**: `_check_subcmd` e `_run_help_output` usavam estratégias diferentes
para localizar o entry point (`-m` vs. entry point instalado), gerando risco de
falso PASS/FAIL se o entrypoint divergisse do código fonte.

**Arquivo**: `scripts/validate_manual.py`  
**Correção**:
- Extraída função `_cli_argv(subcmd, *args)` que centraliza a lógica: prefere
  o entry point instalado (`ielm` no venv/bin), cai de volta em `-m` se ausente
- `_check_subcmd` simplificado para usar `_cli_argv`
- `_run_help_output` já usava a mesma lógica; agora delega para `_cli_argv`

---

## Validação pós-correção

### Smoke-test

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

### Suíte de testes

```
1240 passed, 16 warnings in 23.45s
```

---

## Conformidade final com critérios de aceitação

| Critério | Ciclo A | Ciclo A2 |
|----------|---------|----------|
| Seção 5 com `run ... --run-id`; `--phase`/`--serial` | ✅ | ✅ |
| Perguntas: mecanismo real (`BENCHMARK_QUESTIONS_PATH`) | ❌ schema incorreto | ✅ env var documentada |
| Seção 4-B: modo `external` completo | ✅ | ✅ `managed` default explícito |
| Bloco responsabilidade operador (flags ADR-003) | ✅ | ✅ |
| `VLLM_ENABLE_V1_MULTIPROCESSING` consistente | ❌ =1 na Seção 4 | ✅ =0 em ambas |
| `experiment_round1_external.yaml` inexistente | ❌ referenciado como real | ✅ instrução de edição do YAML existente |
| Texto residual "full run estiver implementado" | ❌ presente | ✅ removido |
| Smoke-test estratégia unificada | ⚠️ duas estratégias | ✅ `_cli_argv` centralizado |
| Seção 2: endpoint_env por NOME; sem novo global | ✅ | ✅ |
| Pendência I4 (`--force-rows`): confirmado ausente | ✅ | ✅ |
| Ressalva `funnel` na Seção 9 | ✅ | ✅ |
| Smoke-test PASS | ✅ | ✅ |
| 1240 testes unit PASS | ✅ | ✅ |
