# M6_TAREFA-604_A — Manual de operação final

**Data**: 2026-06-03
**Milestone**: M6 — Hardening, validação do juiz e documentação final
**Épico**: E9
**Skill**: python-engineer
**Prioridade / Tamanho**: P0 / M

---

## Objetivo

Produzir o manual de operação final (`docs/operations_manual.md`) com todos os
comandos validados por execução real durante M0–M4, substituindo qualquer placeholder
por valores reais ou por marcadores `[PENDENTE: <motivo>]` explícitos. Entregar também
o smoke-test `scripts/validate_manual.py` e atualizar o `README.md`.

---

## Arquivos Criados / Modificados

| Arquivo | Ação |
|---------|------|
| `docs/operations_manual.md` | Criado — manual de operação com 11 seções |
| `scripts/validate_manual.py` | Criado — smoke-test que valida subcomandos CLI do manual |
| `README.md` | Atualizado — seção "Operação" linkando para o manual |

---

## Decisões Técnicas

### 1. Parser de fenced code blocks (estado de máquina)

A abordagem inicial de usar `re.REGEX` para extrair blocos ```bash``` falhou porque o
padrão de fechamento ` ``` ` era reutilizado como abertura de um novo bloco sem
especificador de linguagem. Solução: substituir o regex por um parser de estado
linha-a-linha (`_extract_blocks`) que rastreia:
- se está dentro de um bloco aberto;
- se o heading corrente está marcado como PENDENTE.

### 2. Supressão de seções PENDENTE

Ao encontrar um heading com `[PENDENTE: ...]`, o parser ativa `suppressed_level` com
o nível do heading. O modo é desativado ao encontrar o próximo heading de mesmo nível
ou superior que não seja PENDENTE. Isso garante que a Seção 9 (M5 adiado) não
contribua subcomandos para validação.

### 3. Verificação de subcomandos via entry point

`_check_subcmd` tenta primeiro via `python -m inteligenciomica_eval.cli <subcmd> --help`
e, em seguida, via o entry point instalado no venv (`ielm-eval`). Isso garante que
o script funciona mesmo em ambientes onde o entry point não está no PATH.

### 4. `compute-metrics` inexistente na CLI

A spec do Prompt A menciona `ielm-eval compute-metrics --run-id <id> --force` na
Seção 11 (Troubleshooting). Este subcomando **não existe** na CLI atual (M0–M4).
Para evitar que o smoke-test falhe, o item de troubleshooting correspondente foi
escrito como **texto em tabela** (sem bloco de código bash), com marcador explícito
`[PENDENTE: subcomando compute-metrics não implementado]`.

### 5. `run` sem `--dry-run`

O subcomando `run --config ...` (sem `--dry-run`) existe na CLI e é verificado pelo
smoke-test via `ielm-eval run --help`. A implementação do orçuestrador de ondas está
completa (M3), mas o full run requer hardware GH200 com modelos carregados. A Seção 5
documenta o comportamento esperado e marca a execução completa como
`[PENDENTE: hardware GH200]`.

### 6. Valores REAIS vs. PENDENTE

Todos os valores confirmados durante M0–M4 foram usados diretamente:
- Versão do pacote: `0.1.0`
- Coleções Qdrant: `IDx_400k`, `ID_230K`
- Porta Qdrant padrão: 6333
- Modelos: roster canônico do `model_registry.yaml`
- Pesos de scoring: do `experiment_round1.yaml`
- Variáveis de ambiente: `VLLM_GENERATOR_URL`, `VLLM_JUDGE_URL`, `QDRANT_URL`
- Diretório de dados: `config/data/round-1/`
- Diretório de relatórios: `reports/`

Valores que dependem de medições na bancada (Premissa P1.1 — footprint de VRAM por
modelo) estão marcados como `[PENDENTE: P1.1]`.

---

## Problemas Encontrados e Soluções

| Problema | Solução |
|----------|---------|
| Parser regex reutilizava ` ``` ` de fechamento como abertura | Reescrito como parser de estado linha-a-linha |
| `compute-metrics` inexistente na CLI | Item de troubleshooting escrito como tabela texto sem bloco bash |
| ruff T201 em `print()` | Substituído por `sys.stdout.write()` |
| ruff N806 (`_OPEN_RE`, `_CLOSE_RE` dentro de função) | Renomeado para `open_re`, `close_re` |
| **[Ciclo B]** Parser capturava conteúdo de blocos `yaml` (fechamento ` ``` ` reinterpretado como abertura de bloco vazio) | Parser rastreia TODOS os tipos de fence; só captura conteúdo de blocos `bash`/`sh`/`shell`/vazio |
| **[Ciclo B]** Seção 5 documentava `ielm-eval run --config` sem `--dry-run` como executável hoje | Seção 5 agora marca a execução completa como `[PENDENTE: CLI full run — TAREFA-310]`; o bloco do comando fica dentro de um blockquote (não capturado pelo smoke-test) |
| **[Ciclo B]** Layout Parquet incorreto (`round-1/A/<run_id>_...parquet`) | Corrigido para o layout Hive real: `round_id=round-1/experiment_phase=A/base=.../llm=.../<row_id_hex>.parquet` |
| **[Ciclo B]** Smoke-test não validava sintaxe de blocos `curl` | Adicionada função `_curl_errors_in_block` que valida URL `http://localhost:<porta>/...` sem conexão real |

---

## Validação (DoD)

```
uv run ruff check .                              → All checks passed
uv run ruff format --check .                     → 153 files already formatted
uv run mypy --strict src                         → Success: no issues found
uv run lint-imports                              → Contracts: 4 kept, 0 broken
uv run pytest --cov=src --cov-fail-under=85 -n 4 → 1159 passed, 90.43% coverage
python scripts/validate_manual.py               → PASS (7 subcomandos OK; 0 erros curl)
```

---

## Critérios de Aceitação

| Critério | Status |
|----------|--------|
| `docs/operations_manual.md` presente com 11 seções | ✅ |
| Sem placeholders `<a-definir>` fora de seções PENDENTE | ✅ |
| Seção 9 marcada `[PENDENTE: M5 não implementado]` sem `ielm-eval` executável | ✅ |
| Seção 5: `ielm-eval run` sem `--dry-run` marcado como `[PENDENTE: TAREFA-310]` | ✅ (corrigido ciclo B) |
| Layout Parquet correto (Hive `round_id=.../experiment_phase=.../base=.../llm=.../`) | ✅ (corrigido ciclo B) |
| `python scripts/validate_manual.py` retorna PASS | ✅ 7 subcomandos OK; 0 erros curl |
| Smoke-test valida sintaxe de URLs `curl http://localhost:...` sem conexão | ✅ (adicionado ciclo B) |
| Nenhum segredo no arquivo | ✅ |
| README.md linkado | ✅ |
| Gates de lint/mypy/import-linter/cobertura verdes | ✅ |

---

## Observações para Próximas Tarefas

- **TAREFA-605** (security review): o manual pode ser insumo para o checklist
  `docs/security_review.md` — especialmente as seções sobre variáveis de ambiente
  (ADR-008) e ausência de credenciais hardcoded.
- **M5** (Rodada 2): quando implementado, substituir a Seção 9 stub com comandos
  reais verificados via `ielm-eval funnel --help`; remover o marcador PENDENTE;
  adicionar `funnel` e o subcomando da fase top-N ao `_OPEN_RE` do smoke-test
  (ou simplesmente re-rodar `validate_manual.py` — o parser detecta automaticamente).
- **Premissa P1.1**: ao medir o footprint real de VRAM dos geradores, atualizar
  `config/model_registry.yaml` e os valores `[PENDENTE: P1.1]` no manual.
