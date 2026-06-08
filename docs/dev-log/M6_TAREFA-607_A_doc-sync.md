# M6_TAREFA-607_A — Doc-sync: arquitetura v1.2 + visão v1.1

**Data**: 2026-06-08
**Milestone**: M6 — Hardening, validação e documentação final
**Épico**: E9 (docs)
**Skill**: system-architect
**Prioridade / Tamanho**: P1 / M

---

## Objetivo

Sincronizar a arquitetura detalhada (v1.1 → v1.2) e a visão de alto nível (v1.0 → v1.1) com o
as-built de TAREFA-309/310/311/606 e o gate 312 (commit `86d18e6`). DOCS-ONLY.

---

## Arquivos Criados / Modificados

| Arquivo | Operação | Descrição |
|---------|----------|-----------|
| `docs/arquitetura_detalhada_validacao_inteligenciomica.md` | Modificado | v1.1 → v1.2 (10 edições) |
| `docs/visao_alto_nivel_validacao_inteligenciomica.md` | Modificado | v1.0 → v1.1 (3 edições) |

Nenhum arquivo em `src/`, `tests/`, `config/` ou `scripts/` foi tocado.

---

## Edições Aplicadas

### A. Arquitetura (v1.1 → v1.2)

**A.1 — Cabeçalho e Changelog v1.2**
- Versão: `1.1` → `1.2`
- Data: `22 de maio de 2026` → `8 de junho de 2026`
- Adicionado bloco `Changelog v1.2 (08/06/2026)` resumindo: mecanismo de perguntas via
  `RoundConfig.questions` (TAREFA-313); CLI `run` completo (`--run-id`, `--phase`, `--serial`);
  modo `external` + proveniência verificada (ADR-014, TAREFA-311); 3 colunas novas no schema
  43→46 (já em §§4.3/5.3 via gate 312 — não duplicadas); gate TAREFA-312 (PASS); ADR-013/014
  no catálogo; seções §7.2/§12/§14/§15 expandidas.

**A.2 — RNF1 (reprodutibilidade)**
- Adicionada nuance: em `managed`, determinismo do juiz é **garantido** pelo lançamento; em
  `external`, é **responsabilidade do operador**, apenas **verificado por sonda** (`ADR-014`).

**A.3 — Catálogo de ADRs (§6)**
- Adicionado **ADR-013** (funil da Rodada 2, M5 adiado; referência
  `docs/adr/ADR-013-round2-funnel.md`).
- Adicionado **ADR-014** (managed vs external; proveniência verificada por sonda;
  `determinism_verified=False` default; 3 probes; `--require-verified-determinism`;
  referências ADR-003/004/008/012 e `operations_manual.md` Seção 4-B;
  referência `docs/adr/ADR-014-server-mode-external.md`).

**A.4 — §7.2.1 Modo external (nova subseção)**
- Diagrama textual: cliente x86 ↔ túnel SSH ↔ GH200 (vLLM gen1/gen2/judge + Qdrant).
- Tabela comparativa managed vs external (ciclo de vida, determinismo, `determinism_verified`,
  fixação de GPU, endpoints).
- Cross-ref a `docs/operations_manual.md` Seção 4-B.

**A.5 — §12.4 Reprodutibilidade no modo external (nova subseção)**
- Tabela de 3 probes: `probe_served_model`, `probe_vllm_version`, `probe_judge_determinism`.
- Semântica de `determinism_verified=False` por default.
- `endpoints_provenance` no run report.
- Exemplo de `--require-verified-determinism`.

**A.6 — §14.6 M3 (reconciliação da tabela)**
- Adicionadas 5 linhas: TAREFA-308 (annotation workflow), 309 (wiring+CLI run+BenchmarkLoader),
  310 (gate E2E), 311 (external+probes), 312 (gate de integração PASS).
- Texto go/no-go atualizado com "(as-built)" e menção ao modo external.

**A.7 — §14.9 M6 (tabela)**
- Adicionadas 2 linhas: TAREFA-606 (manual emenda external) e TAREFA-607 (este doc-sync).

**A.8 — §15.7 Orquestração automática**
- Adicionada tabela dos 8 subcomandos reais.
- Flags incorretas removidas: `--phase generation`, `--phase judging`, `--gpu-layout`.
- Adicionado `--run-id` (obrigatório) e tabela de flags de `ielm-eval run`.
- Cross-ref a `docs/operations_manual.md` Seção 4-B.

**A.9 — §15.8 Fluxo completo**
- Removidas linhas com `--phase generation` e `--phase judging` (não existem na CLI).
- Passo 1 agora usa `ielm-eval run --run-id <run_id>` (único comando; internamente orquestra
  geração + julgamento). Comentários inline para `--phase A/B`, `--serial`,
  `--require-verified-determinism`.
- Passo de julgamento separado removido (era artefato da v1.0 com premissa de CLI inexistente).

**A.10 — §15.9 Rodada 2**
- Adicionada nota explícita: `--stage retrieval-funnel` e `--stage full` **ainda não existem**
  na CLI; chegam com M5 (ADR-013).
- Comandos comentados (com prefixo `# [M5 FUTURO]`) para não induzir execução prematura.

### B. Visão (v1.0 → v1.1)

**B.8 — Cabeçalho e Changelog v1.1**
- Versão: `1.0` → `1.1`
- Data: `21 de maio de 2026` → `8 de junho de 2026`
- Adicionado bloco `Changelog v1.1 (08/06/2026)` resumindo topologias e proveniência verificada.

**B.9 — §9.4 (nova subseção após §9.3)**
- Parágrafo sobre managed vs external (tom alto nível; cross-ref ADR-014 e Seção 4-B).
- Responsabilidade de reprodutibilidade compartilhada no modo external.
- `determinism_verified=False` por default; `--require-verified-determinism` para publicação.

**B.10 — Nota sobre os três campos no dataset**
- `server_mode`, `served_model_id` e `determinism_verified` descritos no §9.4 como verificados
  por sonda, não apenas declarados.

---

## Decisões Técnicas

- **Não duplicação de §§4.3/5.3**: confirmado que ambas as seções já contêm as 3 colunas de
  proveniência desde o gate TAREFA-312 — nenhuma edição feita nessas seções.
- **ADR-013 ≠ ADR-014**: ADR-013 é o funil M5 (arquivo existente); ADR-014 é external mode.
  Ordem preservada sem inversão.
- **8 subcomandos reais**: `version`, `run`, `annotate`, `analyze`, `report`, `status`,
  `show-config`, `validate-judge`. `compute-metrics` não existe (use case interno);
  `run-round2` não existe (M5 futuro).
- **`--phase A|B|both`**: não existe `--phase generation` nem `--phase judging` na CLI real.
  Corrigidos em §15.7 e §15.8.

---

## Validação (DoD)

### git diff --name-only

```
docs/arquitetura_detalhada_validacao_inteligenciomica.md
docs/visao_alto_nivel_validacao_inteligenciomica.md
```

Nenhum `.py`, `.yaml`, teste ou config tocado — DOCS-ONLY confirmado.

### Critérios de Aceitação

- [x] Arquitetura em v1.2 com Changelog v1.2
- [x] ADR-013 (stub funil M5) e ADR-014 (external mode) presentes em §6
- [x] §7.2.1 com subseção external (start/stop no-op; managed default; diagrama ASCII)
- [x] §12.4 com reprodutibilidade external (3 probes; `determinism_verified=False` default)
- [x] RNF1 com nuance managed (garantido) / external (verificado, não garantido)
- [x] §14.6 reconciliada com TAREFA-308/309/310/311/312
- [x] §14.9 cita TAREFA-606 e TAREFA-607
- [x] §15 com 8 subcomandos reais; `run --run-id` obrigatório; sem `--phase generation/judging`
- [x] §15.9 marca `--stage retrieval-funnel` como M5 futuro (comandos comentados)
- [x] Visão em v1.1 com Changelog v1.1
- [x] §9.4 com parágrafo de topologias + `server_mode`/`served_model_id`/`determinism_verified`
- [x] `git diff --name-only` somente sob `docs/` (verificado)
- [x] §§4.3/5.3 NÃO duplicadas/alteradas (confirmado antes de editar)

---

## Observações para Próximas Tarefas

- **M5**: quando iniciado, remover os comentários `# [M5 FUTURO]` de §15.9 e implementar
  `--stage retrieval-funnel`/`--stage full` na CLI.
- **CLAUDE.md §13**: a nota sobre `mask_url` descrevendo `scheme://host:port/***` está
  desatualizada (pós-TAREFA-314 é `scheme://host:port`). Não alterado aqui (DOCS-ONLY sobre
  arquitetura/visão), mas vale corrigir em próxima tarefa de manutenção do CLAUDE.md.
