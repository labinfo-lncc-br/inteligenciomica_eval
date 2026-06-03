# Prompt M6 — TAREFA-604 (Manual de operação final — `docs/operations_manual.md`)

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
arquivo; como agora executaremos a **TAREFA-604**, os prompts (Parte A e Parte B) estão em
`docs/m6_tarefas_604.md`.

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

## TAREFA-604 — Manual de operação final (`docs/operations_manual.md`)

**Épico:** E9 · **Skill:** python-engineer · **Prioridade:** P0 · **Tamanho:** M
**Dependências:** **M0–M4 concluídos (M5 adiado)** — o manual documenta comandos validados
por execução real · **ADRs:** ADR-003, ADR-004, ADR-008, ADR-012 ·
**Camadas:** docs (não altera código de produção)

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §15, §14.9
TAREFA-604). Skill ativo: python-engineer. M0–M4 concluídos (M5 adiado). Esta tarefa
versiona a seção 15 do documento de arquitetura em `docs/operations_manual.md`,
substituindo os placeholders `<a-definir>` por valores REAIS confirmados durante M0–M4,
e adiciona um smoke-test de validação do manual.

IMPORTANTE — M5 ADIADO: a Seção 9 (Rodada 2 — funil de retrieval) documenta comandos que
só existem após o M5 (TAREFA-501..507). Como o M5 foi adiado, a Seção 9 é mantida como
STUB marcado `[PENDENTE: M5 não implementado]`, SEM blocos `ielm-eval` executáveis. O
smoke-test (`scripts/validate_manual.py`) deve IGNORAR blocos sob seções marcadas
`[PENDENTE: ...]` — não há subcomando a validar enquanto o M5 não entrar.

TAREFA: TAREFA-604 — Produzir o manual de operação final em `docs/operations_manual.md`
com todos os comandos validados por execução real no ambiente GH200.

ESPECIFICAÇÃO DO CONTEÚDO (`docs/operations_manual.md`):

O manual deve cobrir as seções abaixo. **Todos os valores de versão, paths e
parâmetros devem ser os REAIS confirmados durante M0–M4** (não placeholders).

### Seção 1: Pré-requisitos da máquina
- Driver NVIDIA e versão CUDA confirmados (`nvidia-smi` output de referência)
- Versão do vLLM instalada (`vllm.__version__`) e confirmação de suporte a
  `VLLM_BATCH_INVARIANT` (como verificar — comando exato)
- Qdrant: versão, porta, coleções existentes (`IDx_400k`, `ID_230K`)
- Python: versão mínima, `uv` instalado

### Seção 2: Setup do ambiente (reprodutível)
- Sequência completa: clone → `uv sync --frozen` → `uv run ielm-eval --help`
- Variáveis de ambiente obrigatórias (sem valores reais — apenas os NOMES e o que
  cada uma controla): VLLM_GENERATOR_URL, VLLM_JUDGE_URL, QDRANT_URL, e eventuais
  tokens descobertos durante M1–M3
- Como verificar que o ambiente está pronto: `ielm-eval run --dry-run --config
  config/experiment_round1.yaml` deve imprimir plano e config_hash sem erro

### Seção 3: O `model_registry.yaml` — configuração de serving
- Explicação do campo `gpu_layout`, `generators` e `judge`
- Regra de ouro: GPU 3 → juiz (residente), GPUs 0–2 → geradores em 2 ondas (ADR-012)
- Como adicionar um novo modelo gerador (5 passos)
- Como verificar `tensor_parallel_size` necessário por modelo (footprint check)

### Seção 4: Subindo o ambiente vLLM (antes do `run`)
- Comando de serving (verificar nome exato implementado em M3 com `ielm-eval --help`,
  ex.: `ielm-eval serve --config config/model_registry.yaml` ou equivalente)
- Como confirmar que o juiz está determinístico:
  `curl http://localhost:8001/v1/models` + enviar a MESMA prompt duas vezes e conferir
  que o score é idêntico (comando/script exato)
- Como confirmar que o Qdrant está acessível: `curl http://localhost:6333/healthz`

### Seção 5: Executando a Rodada 1 (Experimentos A e B)
- Comando completo de execução: `ielm-eval run --config config/experiment_round1.yaml`
- Como monitorar progresso (logs estruturados; onde fica o run report)
- Como retomar uma execução interrompida (resumabilidade por `row_id`, ADR-009):
  basta re-executar o mesmo comando — linhas existentes são puladas
- Onde ficam os Parquets gerados (path e estrutura de diretórios)
- Como verificar integridade: `ielm-eval run --dry-run` + inspecionar run report

### Seção 6: Troca de ondas de geradores (M3 GH200)
- O orquestrador `VLLMServerManager` gerencia ondas automaticamente — o operador NÃO
  precisa fazer isso manualmente
- Como verificar qual modelo está em cada GPU em cada onda (run report / log)
- Sinal de que uma troca de onda falhou e como resolver (processo vLLM morreu)

### Seção 7: Anotação humana (Camada 3)
- `ielm-eval annotate --run-id <run_id> [--threshold 0.70]` — exporta CSV priorizado
- Formato do CSV de entrada do especialista (colunas obrigatórias: `row_id`,
  `critical_failure_flag`)
- `ielm-eval annotate --run-id <run_id> --ingest annotation.csv` — merge
  idempotente pelo `row_id` (ADR-009)

### Seção 8: Análise e relatório (M4)
- `ielm-eval analyze --run-id <run_id> --tests all`
- `ielm-eval report --run-id <run_id> --format html`
- Onde ficam os outputs (HTML, figuras, run report de análise)

### Seção 9: Rodada 2 — funil de retrieval (M5)  `[PENDENTE: M5 não implementado]`
> **Esta seção é um STUB.** O M5 (Rodada 2 — funil OFAT de chunking/embedding) foi
> deliberadamente adiado; os subcomandos da CLI correspondentes (`funnel` e a fase top-N
> da Rodada 2) **ainda não existem**. Por isso esta seção **NÃO contém blocos `ielm-eval`
> executáveis** — o smoke-test (`scripts/validate_manual.py`) não tem subcomando a validar
> aqui (blocos sob seção `[PENDENTE: ...]` são ignorados).
>
> Quando o M5 for implementado (TAREFA-501..507), esta seção deverá documentar — em prosa
> e com os blocos de comando REAIS confirmados via `ielm-eval --help`:
> - como configurar as variantes de chunking (fase 2a) e embedding (fase 2b) nos YAMLs
>   `config/experiment_round2a.yaml` / `config/experiment_round2b.yaml`;
> - o funil barato de retrieval puro (estágio 1, sem LLM) que ranqueia as configurações
>   por `precision@k`, `recall@k`, `MRR`, `nDCG@k` contra os chunks-ouro;
> - a execução da fase cara (estágio 2, com LLM e juiz) apenas nas top-N configurações
>   selecionadas pelo funil.
>
> **Pré-requisito do M5:** curadoria de chunks-ouro (Premissa P5) entregue. Até lá, o
> subsistema opera sobre a Rodada 1 (variação base × LLM).

### Seção 10: Validação do juiz (M6)
- `ielm-eval validate-judge --run-id <run_id> --round-id A --threshold 0.50 --report docs/judge_validation_report.md`
- Interpretação do κ: o que esperar, o que fazer se κ < 0.40

### Seção 11: Troubleshooting
Tabela com os problemas mais comuns encontrados durante M0–M4 e soluções:
- vLLM não sobe em tempo (`ServerStartTimeoutError`) → checar GPU memory, matar processos
  órfãos: `fuser -k 8000/tcp 8001/tcp`
- `VLLM_BATCH_INVARIANT` não reconhecido → checar versão do vLLM
- Parquet corrompido → deletar partição e re-executar (resumabilidade por `row_id`
  garante consistência — ADR-009)
- Muitos NaN no juiz (taxa > 5%) → checar prompt template, recomputar métricas com
  `ielm-eval compute-metrics --run-id <id> --force` (recomputar toda a rodada)
- `import-linter` falha em nova dependência → revisar a camada antes de adicionar

SMOKE-TEST DO MANUAL (script `scripts/validate_manual.py`):
- Percorre o manual em Markdown, extrai todos os blocos de código shell (```bash```).
- IGNORA blocos de código que estejam sob uma seção cujo cabeçalho contém o marcador
  `[PENDENTE: ...]` (ex.: a Seção 9 enquanto o M5 não for implementado) — não há
  subcomando a validar nessas seções.
- Para cada bloco restante que começa com `ielm-eval`, verifica que o subcomando existe
  na CLI (`ielm-eval <subcmd> --help` não retorna erro). Roda em CPU, sem GPU/rede.
- Para blocos com `curl http://localhost:...`, apenas verifica que o comando está
  sintaticamente correto (não tenta conectar).
- Saída: PASS se todos os `ielm-eval` subcomandos (fora de seções PENDENTE) existem;
  FAIL com lista dos faltantes.

ENTREGÁVEL:
- `docs/operations_manual.md` — manual completo com valores REAIS (sem placeholders
  `<a-definir>`; a Seção 9 é o único stub permitido, marcado `[PENDENTE: M5 não
  implementado]`; se algum outro valor ainda não foi confirmado, marcá-lo explicitamente
  com `[PENDENTE: <motivo>]`)
- `scripts/validate_manual.py` — smoke-test do manual (com o guard de seções PENDENTE)
- Atualização do `README.md`: seção "Operação" linkando para o manual

RESTRIÇÕES:
- O manual NÃO deve conter segredos, tokens ou credenciais reais.
- Todos os comandos `ielm-eval` mencionados FORA de seções PENDENTE devem existir na CLI
  (verificado pelo smoke-test).
- `scripts/validate_manual.py` deve passar sem erro.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-604):
- `docs/operations_manual.md` presente com as 11 seções; sem placeholders `<a-definir>`.
  Seção 9 presente como stub `[PENDENTE: M5 não implementado]`, sem `ielm-eval` executável.
- `python scripts/validate_manual.py` retorna PASS (ignora a Seção 9 PENDENTE).
- Nenhum segredo no arquivo.
- README.md linkado.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-604 + arquitetura §15 (todas as subseções) + ADR-008
(segredos via env) + ADR-012 (alocação de GPUs) + "Nota de operacionalização M6" item 6
(M5 adiado) + relatório de implementação do desenvolvedor (Parte A).

VERIFIQUE, item a item, citando arquivo:linha (ou número de seção do manual):
1. As 11 seções obrigatórias estão presentes no manual?
2. Há placeholders `<a-definir>` ou `<placeholder>` sem justificativa? (BLOQUEADOR se
   for em comandos de execução; WARNING se for em versões ainda não confirmadas marcadas
   como `[PENDENTE: <motivo>]`)
3. Segredos: o manual NÃO contém tokens, senhas ou URLs com credenciais embutidas?
   Endpoints aparecem apenas como `http://localhost:<porta>` ou referências a variáveis
   de ambiente?
4. Regra de ouro GPU (seção 3/4): juiz na GPU 3, geradores nas GPUs 0–2 em 2 ondas
   (ADR-012) está correto e consistente com o `model_registry.yaml` de exemplo?
5. Retomada de execução (seção 5): explicação de resumabilidade por `row_id` está
   correta (ADR-009 — mesmo comando, linhas existentes puladas)?
6. Seção 7 (anotação humana): comando de ingestão usa `--ingest` (não `--ingest-file`
   ou outro nome diferente do especificado em TAREFA-402)?
7. Seção 11 (Troubleshooting): usa `--force` (não `--force-rows`) para recomputar
   métricas? (BLOQUEADOR se usar `--force-rows` — flag inexistente)
8. Seção 9 (Rodada 2 / M5 ADIADO): está marcada como `[PENDENTE: M5 não implementado]`
   e NÃO contém blocos `ielm-eval` executáveis? (BLOQUEADOR se houver `ielm-eval funnel`
   ou `round2` executável — o subcomando não existe e o smoke-test falharia.) O
   `scripts/validate_manual.py` IGNORA blocos sob seções `[PENDENTE: ...]`?
9. `scripts/validate_manual.py`:
   - Extrai blocos `bash` com `ielm-eval`? Testa via `--help`?
   - Implementa o guard que pula blocos sob seções `[PENDENTE: ...]`?
   - Retorna PASS sem erro para o manual gerado?
   - Roda em CPU sem GPU/rede?
10. README.md foi atualizado com link para o manual?

SAÍDA: PASS/FAIL + tabela de divergências (critério | seção/arquivo:linha | gravidade).
Execute `python scripts/validate_manual.py` e cite o resultado.
Se houver comandos `ielm-eval` no manual (fora de seções PENDENTE) que o smoke-test
reporte como inexistentes: BLOQUEADOR.
~~~
