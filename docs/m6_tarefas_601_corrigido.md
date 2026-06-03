# Prompt M6 — TAREFA-601 (Mutation testing em `domain/services`)

**Milestone:** M6 — Hardening, validação do juiz e documentação final
**Documento de referência:** `arquitetura_detalhada_validacao_inteligenciomica.md` (v1.1)
**Continuação de:** `prompts_m4_tarefas_401_409_corrigido.md` — M4 mergeado e verde; **M5 (Rodada 2) adiado**
**Formato:** **Prompt A (implementação — Claude Code)** + **Prompt B (verificação — ChatGPT Codex)**, conforme seção 16 do documento de arquitetura.
**Épico coberto:** E9 — Hardening + validação do juiz (Cohen's κ) + docs finais.

> Pressupõe que **M0–M4 (TAREFA-001..409) já estão mergeados e verdes**: domínio puro,
> todos os adapters, orquestração GH200, Rodada 1 avaliada e persistida, decisão executiva
> M4 emitida (incluindo a análise estatística — Wilcoxon, Friedman + Nemenyi, modelo linear
> misto e correção múltipla). **O M5 (Rodada 2 — funil OFAT de variação de chunking/embedding)
> foi deliberadamente adiado**: o subsistema opera sobre a Rodada 1 (variação **base × LLM**,
> com chunking e embedding fixos no baseline). A variação de chunking/embedding entrará numa
> rodada futura, reentrando limpa — depende apenas do gate de M4 + curadoria de chunks-ouro
> (Premissa P5) e **não exige nenhuma alteração no M6**. As convenções da "Nota de
> operacionalização" dos arquivos M0–M2 **continuam valendo integralmente** (lista canônica
> de libs proibidas em `domain`/`application`; `import-linter`; `ResultFrame` como wrapper;
> DoD §14.2).

---

## Protocolo de desenvolvimento em pares (Claude Code ↔ ChatGPT Codex)

Estamos desenvolvendo o **inteligenciômica-eval**, executando prompts organizados por marcos
(milestones). Cada marco reúne vários prompts, e **cada prompt é sempre dividido em duas
partes**: a **Parte A — implementação**, executada pelo **Claude Code**, e a **Parte B —
revisão e auditoria**, executada pelo **ChatGPT Codex**. Cada prompt tem o seu próprio
arquivo; como agora executaremos a **TAREFA-601**, os prompts (Parte A e Parte B) estão em
`docs/m6_tarefas_601.md`.

**Toda execução gera obrigatoriamente um relatório** do que foi feito e dos resultados
obtidos. O processo é **iterativo**: implementação (A) → revisão/auditoria (B) → correção e
recodificação (A) → nova revisão/auditoria (B), repetindo até que **Claude Code e ChatGPT
Codex concordem** que não há mais falhas e a tarefa seja **aprovada (PASS) por ambos**.

O avanço para a próxima tarefa **nunca é automático**: ocorre somente com a **minha
autorização explícita** e após o `add` / `commit` / `push` no GitHub.

O **`CLAUDE.pm`** contém a padronização de como escrever os relatórios e gravá-los em
`docs/dev-log/`. O `CLAUDE.pm` **deve ser mantido atualizado** com os padrões e as decisões
que impactam a continuidade do desenvolvimento.

> **Início desta tarefa:** execute primeiro a **Parte A (Claude Code)** abaixo e produza o
> relatório de implementação. A **Parte B (ChatGPT Codex)** roda em seguida, a partir da
> resposta do desenvolvedor (relatório + diff do PR da Parte A). Itere A↔B até PASS mútuo.

---

## Nota de operacionalização de M6 (decisões que estes prompts fixam)

Seis pontos que 601–605 precisam fixar para Code e Codex não divergirem (vetáveis
pela equipe):

1. **Mutation testing roda fora do CI normal, mas é gate do M6.** O `mutmut` é lento
   (pode levar minutos sobre `domain/services`); por isso roda como step **manual** no
   gate do milestone, não no CI de cada PR. A prova de gate é um artefato
   `tests/mutation/mutation_report.txt` (resultado de `mutmut results`) commitado no PR
   da TAREFA-601. O CI verifica a *existência e validade* do artefato (score ≥ 80%
   parseado do arquivo), não re-executa o `mutmut`. A configuração `[tool.mutmut]` em
   `pyproject.toml` e os paths corretos são parte da entrega.

2. **Cohen's κ usa limiar de binarização configurável via YAML.** Para calcular κ entre
   o juiz LLM (score contínuo [0,1]) e o anotador humano (`critical_failure_flag ∈ {0,1}`),
   o score contínuo do juiz é binarizado: `judge_binary = 1 if rubric_biomed_score < threshold
   else 0` (juiz concorda com falha crítica quando atribui score baixo). O `threshold`
   padrão é `0.50` mas é configurável no YAML de análise para permitir sensibilidade vs.
   especificidade. A TAREFA-602 entrega tanto o módulo de cálculo quanto o relatório
   gerado sobre os dados reais de M4 (Parquet + anotação humana). O juiz ser determinístico
   (`VLLM_BATCH_INVARIANT=1`) é o que torna a comparação válida: um juiz não-determinístico
   invalidaria a comparação porque o score poderia flutuar entre o momento da execução e
   o da validação (`visao_alto_nivel §9.5` — mitigação de viés do juiz).

3. **Property-based tests da TAREFA-603 são independentes de GPU/rede.** Todos os alvo
   do `hypothesis` são funções puras ou adapters mockados: parser do juiz Prometheus
   (entrada: strings arbitrárias), roundtrip Parquet em `tmp_path`, `config_hash` de
   dicts arbitrários. Nenhum teste da 603 requer container ou serviço externo — devem
   rodar no CI de CPU junto com os testes unitários normais. Os testes usam o marcador
   `@pytest.mark.property` (registrado em `pyproject.toml` nesta tarefa).

4. **A TAREFA-605 é uma _revisão_ de segurança, não uma auditoria de segurança formal.**
   Ela produz um checklist verificável (`docs/security_review.md`) com evidências de
   execução (saída de `git-secrets` ou `truffleHog`, resultado do teste de chunk
   malicioso). O PR da 605 fecha o milestone M6 e é o go/no-go final do subsistema.

5. **`scikit-learn` (sklearn) é tratado como biblioteca de infraestrutura de ML**, sujeita
   às mesmas restrições de camada das demais libs de análise. Fica **proibida em `domain`
   e `application`** — mesma regra das libs da lista canônica de M0. Estender a lista
   canônica do `.importlinter` (regras 1 e 2) incluindo `sklearn`. O adapter sklearn fica
   em `infrastructure/stats/`. Esta decisão é vetável pela equipe antes de M6 iniciar.

6. **O M5 (Rodada 2 — funil OFAT) está adiado; o M6 não depende dele.** Nenhum código de
   produção de M6 importa módulos de M5. Os únicos pontos de contato foram neutralizados
   nesta versão: (a) **TAREFA-601** **não inclui** `funnel.py` (FunnelSelector, criado em
   M5) nos `paths_to_mutate` — quando o M5 for implementado, reincluí-lo como alvo opcional
   de mutação; (b) **TAREFA-604** mantém a **Seção 9 (Rodada 2)** do manual como
   `[PENDENTE: M5 não implementado]`, **sem blocos `ielm-eval` executáveis**, para que
   `scripts/validate_manual.py` não tente validar subcomandos (`funnel`/`round2`) ainda
   inexistentes na CLI. Esta decisão é vetável pela equipe e deve ser revertida quando o
   M5 entrar.

---

## TAREFA-601 — Mutation testing em `domain/services`

**Épico:** E9 · **Skill:** test-engineer · **Prioridade:** P1 · **Tamanho:** M
**Dependências:** TAREFA-006 (`FinalScoreCalculator`), TAREFA-007 (`RankScoreCalculator`),
TAREFA-008 (`AggregationService`) — todos de M0 · **ADRs:** nenhum específico
**Camadas:** testes (não altera código de produção; pode adicionar testes ao existente)

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §14.9 TAREFA-601).
Skills ativos: test-engineer §12 (mutation testing), python-clean-architecture §1.
M0–M4 já mergeados (M5 adiado). Esta tarefa NÃO altera código de produção, COM UMA
exceção autorizada de escopo mínimo (ver item 6 — DECISÃO DE ARQUITETURA, tolerância de
pesos): fora dela, apenas adiciona configuração de mutation testing e, se necessário,
fortalece os testes unitários existentes para sobreviventes críticos.

TAREFA: TAREFA-601 — Configurar e executar mutation testing sobre
`src/inteligenciomica_eval/domain/services/` (módulos `final_score.py`,
`rank_score.py`, `aggregation.py`).
Meta: mutation score ≥ 80% nos serviços de scoring e ranking.

NOTA M5 ADIADO: o módulo `funnel.py` (FunnelSelector) é criado em M5 (TAREFA-503) e
ainda NÃO existe. Por isso NÃO é incluído em `paths_to_mutate` nesta versão. Quando o
M5 for implementado, reincluir `funnel.py` como alvo opcional de mutação (mesma meta
de score nos serviços de scoring/ranking do funil).

ESPECIFICAÇÃO:

1. CONFIGURAÇÃO `[tool.mutmut]` em `pyproject.toml`:
   - `paths_to_mutate = "src/inteligenciomica_eval/domain/services/"`
   - `tests_dir = "tests/unit/domain/services/"`
   - `runner = "python -m pytest tests/unit/domain/services/ -x -q --no-header"`
   - `use_coverage = false`  ← mutmut mais estável sem coverage integrado
   - Documente a decisão de rodar fora do CI (motivo: lentidão) no próprio comentário
     do `pyproject.toml`.

2. SCRIPT DE GATE `scripts/mutation_gate.py` (ou Makefile target `make mutation`):
   - Executa `mutmut run` via subprocess.
   - Extrai da saída de `mutmut results` (ou do arquivo `.mutmut-cache`): número total de
     mutantes gerados, número de sobreviventes, número de mortos, mutation score (%).
   - Falha com exit code 1 se mutation score < 80%.
   - Grava o relatório legível em `tests/mutation/mutation_report.txt` com:
     - Data/hora de execução
     - Versão do mutmut (`mutmut --version`)
     - Total de mutantes / mortos / sobreviventes / score (%)
     - Lista dos sobreviventes (arquivo:linha:tipo de mutação) — extraída de
       `mutmut show <id>` para cada sobrevivente
   - O `tests/mutation/mutation_report.txt` deve ser commitado no PR como evidência de gate.

3. CI STEP (`.github/workflows/ci.yml`) — adicionar step `mutation-gate`:
   - Roda apenas na branch `main` (ou via `workflow_dispatch`) — NÃO em cada PR.
   - Step: `python scripts/mutation_gate.py`
   - Falha se mutation score < 80%.
   - Persiste `tests/mutation/mutation_report.txt` como artefato do GitHub Actions.

4. TESTES DE REFORÇO (se sobreviventes críticos forem encontrados):
   - Para cada mutante sobrevivente em `final_score.py` ou `rank_score.py`, adicionar
     ou fortalecer um caso de teste unitário que o mate (asserting on the EXACT value
     changed by the mutation, not just ">= 0.5").
   - Para `aggregation.py`, mutações típicas perigosas: `+` → `-` nas somas de contagem
     de NaN, `<` → `<=` no limiar de failure_rate, `len(results)` → `len(results) - 1`.
     Adicionar testes que distingam esses casos.
   - NUNCA enfraquecer um teste para fazer um mutante "morrer" artificialmente.

5. ESPECIFICAÇÃO DE SOBREVIVENTES ACEITÁVEIS (documentar no relatório):
   - Mutações em `__repr__`, `__str__`, docstrings: ACEITÁVEL sobreviver.
   - Mutações em guard clauses que já são cobertas por testes de exceção: ACEITÁVEL.
   - Mutações em linhas de logging (não afetam lógica): ACEITÁVEL.
   - Mutações que alteram a FÓRMULA (pesos, operadores aritméticos, comparações de
     limiar): INACEITÁVEL sobreviver — são os alvos primários.
   - **Mutantes equivalentes PROVADOS**: sobrevivente para o qual existe um argumento
     formal de que NENHUMA entrada o distingue do original (ex.: alcançabilidade em
     ponto-flutuante) é ACEITÁVEL — desde que a prova seja registrada no
     `mutation_report.txt` (id do mutante, arquivo:linha, e o argumento). Equivalência
     meramente PRESUMIDA, sem prova, é INACEITÁVEL. Esta cláusula NÃO se aplica ao
     mutmut_12 (que é MORTO via item 6); existe para os casos genuinamente inmatáveis que
     surgirão em `aggregation.py` agora e em `funnel.py` quando o M5 entrar.

6. DECISÃO DE ARQUITETURA — tolerância de pesos exatamente representável (resolve mutmut_12):
   O mutante `>` → `>=` em `abs(total - 1.0) > _WEIGHTS_TOLERANCE` é, com
   `_WEIGHTS_TOLERANCE = 1e-9`, um MUTANTE EQUIVALENTE: nenhum `total` (soma de pesos float
   próxima de 1.0) satisfaz `abs(total - 1.0) == 1e-9`. Perto de 1.0, a subtração é exata
   (lema de Sterbenz) e cai na grade de múltiplos de 2^-52 (faixa [1,2)) ou 2^-53 (faixa
   [0.5,1)); o double mais próximo de 1e-9 não pertence a essa grade, então a fronteira
   `==` é INALCANÇÁVEL e `>`/`>=` são indistinguíveis para qualquer entrada.
   RESOLUÇÃO (escopo mínimo, AUTORIZADA pelo arquiteto) — uma única alteração de produção:
       # em src/inteligenciomica_eval/domain/services/final_score.py
       _WEIGHTS_TOLERANCE: float = 2 ** -30   # ≈ 9.3132e-10; dyadic exato → fronteira
                                              # de aceitação/rejeição determinística e testável
   Justificativa: 2^-30 é exatamente representável; existe `total = 1.0 + 2**-30`
   (representável, pois 2^-30 = 2^22·2^-52 ≫ ULP em 1.0) tal que
   `abs(total - 1.0) == _WEIGHTS_TOLERANCE`, tornando a fronteira OBSERVÁVEL. A escolha é,
   por si só, melhor engenharia de ponto-flutuante (tolerância com semântica de fronteira
   bem-definida); a morte do mutmut_12 é consequência, não o objetivo isolado. Impacto
   comportamental em produção: nulo na prática — a banda [0.931e-9, 1e-9] onde o resultado
   mudaria é inalcançável por qualquer vetor de pesos realista.
   TESTE DE FRONTEIRA (mata mutmut_12) — em `tests/unit/domain/services/test_final_score.py`:
   construir um vetor de pesos cuja soma seja EXATAMENTE `1.0 + 2**-30` e assertar que a
   validação ACEITA (operador `>` → False); o mutante `>=` REJEITARIA, sendo morto.
   Comentar: `# mata mutmut_12: fronteira de tolerância observável (2**-30)`.
   ESTA É A ÚNICA mudança de produção permitida nesta tarefa; tudo o mais permanece em
   testes/config.

ENTREGÁVEL:
- `pyproject.toml` — seção `[tool.mutmut]` adicionada
- `scripts/mutation_gate.py` — script de gate com saída estruturada
- `.github/workflows/ci.yml` — step `mutation-gate` adicionado (roda em main/dispatch)
- `src/inteligenciomica_eval/domain/services/final_score.py` — ÚNICA mudança de produção:
  `_WEIGHTS_TOLERANCE` de `1e-9` para `2 ** -30`, com o comentário de justificativa (item 6)
- `tests/unit/domain/services/test_final_score.py` — teste de fronteira que mata mutmut_12
- `tests/mutation/mutation_report.txt` — relatório gerado pela execução REAL do mutmut
  sobre o código de produção (evidência do gate); deve registrar mutmut_12 como MORTO
- `tests/unit/domain/services/` — demais arquivos de teste reforçados para sobreviventes
  críticos (se houver), com comentário `# reforçado: mata mutante <id> em <arquivo>:<linha>`

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings em `mutation_gate.py`.
- `ruff`, `mypy --strict`, `import-linter` verdes (nenhum import novo de third-party
  em `domain`).
- O relatório commitado DEVE mostrar score ≥ 80%. Se a primeira execução ficar abaixo,
  fortalecer os testes antes de commitar.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-601):
- `mutmut run` (ou `python scripts/mutation_gate.py`) completa sem erro de configuração.
- `tests/mutation/mutation_report.txt` mostra mutation score > 80% nos módulos
  `final_score.py`, `rank_score.py`, `aggregation.py`.
- `funnel.py` NÃO está em `paths_to_mutate` (M5 adiado) — sem erro de path inexistente.
- Sobreviventes documentados são todos em linhas aceitáveis (repr/logging/guards) OU
  mutantes equivalentes com PROVA formal no relatório.
- Nenhum sobrevivente NÃO-DOCUMENTADO na lógica aritmética de score/ranking.
- mutmut_12 (`>`→`>=` em `abs(total-1.0) > _WEIGHTS_TOLERANCE`) está MORTO via `2**-30` +
  teste de fronteira — NÃO documentado como equivalente.
- A alteração de `final_score.py` é a única mudança de produção e tem comentário justificando 2^-30.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-601 + arquitetura §14.9 + skill test-engineer §12
(mutation testing) + `tests/mutation/mutation_report.txt` commitado no PR +
relatório de implementação do desenvolvedor (Parte A).

VERIFIQUE, item a item, citando arquivo:linha:
1. `[tool.mutmut]` em `pyproject.toml` aponta para
   `src/inteligenciomica_eval/domain/services/` e para `tests/unit/domain/services/`?
   Runner usa `pytest -x` (para no primeiro teste que passa, evitando falsos
   sobreviventes por timeout)? `funnel.py` NÃO consta de `paths_to_mutate` (M5 adiado)?
2. `mutation_report.txt` está presente e parsável? Contém: data, versão do mutmut,
   total de mutantes, mortos, sobreviventes, score (%)? Score ≥ 80%?
3. Sobreviventes em linha aritmética/comparação de `final_score.py`, `rank_score.py` ou
   `aggregation.py` (operadores `+`, `-`, `*`, `/`, `<`, `>`, `<=`, `>=`):
   - SEM prova de equivalência anexada → BLOQUEADOR (FAIL); reportar arquivo:linha:tipo.
   - COM prova formal de mutante equivalente registrada no `mutation_report.txt`
     (argumento de alcançabilidade, ex.: ponto-flutuante) → ACEITÁVEL: auditar a VALIDADE
     da prova, NÃO exigir a morte do mutante.
   Verificar especificamente o **mutmut_12** (`>`→`>=` em `abs(total-1.0) > _WEIGHTS_TOLERANCE`):
   deve estar MORTO via `_WEIGHTS_TOLERANCE = 2**-30` + teste de fronteira (item 6 do
   Prompt A), e NÃO documentado como equivalente. Confirmar que a alteração em
   `src/.../final_score.py` é a ÚNICA mudança de produção e traz comentário justificando 2^-30.
4. Testes de reforço (se adicionados): cada novo teste referencia o mutante que mata
   (comentário `# reforçado: ...`)? Os asserts são específicos (valor exato), não apenas
   `>= 0`?
5. CI step `mutation-gate` existe e está configurado para rodar apenas em `main` ou
   `workflow_dispatch`? NÃO em cada PR (protege tempo de CI)?
6. `scripts/mutation_gate.py`: exit code 1 quando score < 80%? Artefato
   `tests/mutation/mutation_report.txt` gerado corretamente?
7. Nenhum código de produção alterado (apenas `pyproject.toml`, scripts, testes e
   o artefato de relatório)?
8. DoD §14.2: type hints em `mutation_gate.py`; ruff/mypy verdes; import-linter OK?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Se houver sobreviventes NÃO-DOCUMENTADOS em lógica aritmética de scoring: FAIL automático
(BLOQUEADOR). Sobreviventes equivalentes com prova formal válida no relatório são
ACEITÁVEIS. Confirme que mutmut_12 consta como MORTO.
Cite o mutation score exato lido do `mutation_report.txt`.
~~~
