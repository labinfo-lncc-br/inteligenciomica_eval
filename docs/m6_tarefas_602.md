# Prompt M6 — TAREFA-602 (Validação amostral humana do juiz — Cohen's κ)

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
arquivo; como agora executaremos a **TAREFA-602**, os prompts (Parte A e Parte B) estão em
`docs/m6_tarefas_602.md`.

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

## TAREFA-602 — Validação amostral humana do juiz (Cohen's κ)

**Épico:** E9 · **Skill:** ml-engineer · **Prioridade:** P0 · **Tamanho:** M
**Dependências:** TAREFA-009 (`ParquetStorage`), TAREFA-401/402 (anotação humana da
Camada 3, M4) · **ADRs:** ADR-003 (determinismo do juiz — condição de validade do κ),
ADR-007 (NaN/falhas do juiz) · **Camadas:** domain (port + exceção), infrastructure/adapters
(adapter do relatório), infrastructure/stats (CohenKappaAdapter),
infrastructure/prompts (template), application (use case)

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1,
visao_alto_nivel §9.5 (mitigação de viés do juiz), §14.9 TAREFA-602).
Skills ativos: ml-engineer, python-engineer, python-clean-architecture.
M0–M4 concluídos (M5 adiado): Parquet com `rubric_biomed_score` e `critical_failure_flag`
(Camada 3) persistido. A validade científica do cálculo de κ depende do juiz ser
determinístico (ADR-003): o mesmo `row_id` sempre produz o mesmo `rubric_biomed_score`.

TAREFA: TAREFA-602 — Implementar o módulo de validação amostral do juiz com cálculo de
Cohen's κ e geração de relatório `docs/judge_validation_report.md`.

ESPECIFICAÇÃO:

1. EXTENSÃO DE `domain/errors.py` — nova exceção de domínio:
   ```python
   class InsufficientAnnotationError(EvaluationError):
       """Levantada quando a amostra anotada é menor que o mínimo configurado."""
   ```
   Adicionar à hierarquia existente (TAREFA-002).

2. EXTENSÃO DE `domain/ports.py` — novo port (delta de contrato, vetável pela equipe):
   ```python
   class KappaCalculatorPort(Protocol):
       """Calcula a concordância entre dois rótulos binários (Cohen's κ)."""
       def compute(
           self,
           y_true: Sequence[int],
           y_pred: Sequence[int],
       ) -> float: ...
   ```
   Adicionar a `domain/ports.py` com `@runtime_checkable`. Documentar com docstring
   que é extensão de M6 não prevista em §5.1 original.

3. MÓDULO `src/inteligenciomica_eval/infrastructure/stats/cohen_kappa_adapter.py`:
   ```python
   class CohenKappaAdapter:
       """Implementa KappaCalculatorPort usando sklearn.metrics."""
       def compute(self, y_true: Sequence[int], y_pred: Sequence[int]) -> float:
           from sklearn.metrics import cohen_kappa_score
           return float(cohen_kappa_score(y_true, y_pred))
   ```
   `sklearn` fica APENAS nesta camada (Nota de operacionalização M6, item 5).

4. MÓDULO `src/inteligenciomica_eval/application/judge_validation.py`:
   ```python
   @dataclass(frozen=True)
   class JudgeValidationConfig:
       binarization_threshold: float = 0.50  # score < threshold → judge_binary=1 (falha)
       min_sample_size: int = 10             # levanta InsufficientAnnotationError se menor

   @dataclass(frozen=True)
   class JudgeValidationResult:
       n_total: int              # linhas no Parquet para o run_id/round_id
       n_annotated: int          # linhas com critical_failure_flag não-nulo
       n_valid: int              # linhas com rubric_biomed_score não-NaN E flag não-nulo
       n_excluded_nan: int       # = n_annotated - n_valid (excluídas por NaN do juiz)
       cohen_kappa: float
       kappa_interpretation: Literal[
           "fraca", "razoável", "moderada", "substancial", "quase-perfeita"
       ]
       confusion_matrix: dict[str, int]  # {"TP": n, "TN": n, "FP": n, "FN": n}
       binarization_threshold: float
       judge_model: str          # lido do Parquet (deve ser único — avisar se divergir)
       batch_invariant_confirmed: bool  # todos os registros têm batch_invariant=True?

   class JudgeValidationUseCase:
       def __init__(
           self,
           reader: ResultReaderPort,
           kappa_calculator: KappaCalculatorPort,
           config: JudgeValidationConfig,
       ) -> None: ...
       def run(self, run_id: str, round_id: str) -> JudgeValidationResult: ...
   ```
   - Lógica de binarização:
     `judge_binary = 1 if rubric_biomed_score < binarization_threshold else 0`
     (score baixo do juiz → concorda que é falha crítica)
   - Interpretação de κ (escala de Landis & Koch, 5 categorias):
     - κ < 0.20 → `"fraca"`
     - 0.20 ≤ κ < 0.40 → `"razoável"`
     - 0.40 ≤ κ < 0.60 → `"moderada"`
     - 0.60 ≤ κ < 0.80 → `"substancial"`
     - κ ≥ 0.80 → `"quase-perfeita"`
   - Logar WARNING estruturado se `n_excluded_nan > 0` (linhas com anotação mas sem
     `rubric_biomed_score` — NaN do juiz).
   - Logar WARNING se `batch_invariant_confirmed = False` (juiz pode não ser determinístico
     — invalida a comparação; reportar como aviso crítico no relatório).
   - Levanta `InsufficientAnnotationError` se `n_valid < config.min_sample_size`.
   - **NÃO recebe `report_path`** — retorna apenas `JudgeValidationResult` puro.
     A CLI controla onde o relatório é gravado (responsabilidade de apresentação).

5. ADAPTER DE RELATÓRIO `src/inteligenciomica_eval/infrastructure/adapters/judge_validation_report_adapter.py`:
   - `generate_report(result: JudgeValidationResult, path: Path) -> None`
   - Usa template Jinja2 em `infrastructure/prompts/judge_validation_report.j2`
     (via `PromptRegistry` — padrão estabelecido em M2).
   - Produz `docs/judge_validation_report.md` em Markdown com:
     - Data de geração + `run_id` + `round_id`
     - Modelo do juiz (`judge_model`) + confirmação de determinismo (`batch_invariant_confirmed`)
     - Threshold de binarização utilizado
     - Tamanhos amostrais: `n_total`, `n_annotated`, `n_valid`, `n_excluded_nan`
     - **Cohen's κ = <valor> (<`kappa_interpretation`>)**
     - Matriz de confusão (tabela Markdown 2×2: Juiz×Humano)
     - Seção de interpretação com 5 ramos (alinhados com `kappa_interpretation`):
       - κ ≥ 0.80: "quase-perfeita — concordância excelente com o avaliador humano."
       - 0.60 ≤ κ < 0.80: "substancial — suporte forte ao uso como métrica de avaliação."
       - 0.40 ≤ κ < 0.60: "moderada — usar com cautela; análise manual de discordâncias recomendada."
       - 0.20 ≤ κ < 0.40: "razoável — concordância limitada; revisão do prompt de rubrica recomendada."
       - κ < 0.20: "fraca — concordância próxima do acaso; considerar troca de juiz antes de próximas rodadas."
     - Tabela das primeiras 20 discordâncias (row_id, rubric_biomed_score, judge_binary,
       critical_failure_flag) para inspeção manual.

6. INTEGRAÇÃO NA CLI (`cli.py`) — comando `validate-judge`:
   ```
   ielm-eval validate-judge \
     --run-id round_1_20260601 \
     --round-id A \
     --threshold 0.50 \
     --report docs/judge_validation_report.md
   ```
   - Carrega config de env.
   - Instancia `JudgeValidationUseCase` (via factory) e chama `.run(run_id, round_id)`.
   - Chama `JudgeValidationReportAdapter.generate_report(result, path=report_path)`.
   - Imprime resumo na stdout: κ, interpretação, n_valid, n_excluded_nan, threshold.

7. TESTES:
   - `tests/unit/application/test_judge_validation.py`:
     - Golden com dataset sintético: 20 linhas, 10 com flag=1 (humano), juiz binarizado
       conforme threshold. Calcular κ esperado manualmente (citar o cálculo no comentário
       do teste). Verificar κ ± 1e-9.
     - `n_excluded_nan` correto (= n_annotated - n_valid).
     - Caso: `n_valid < min_sample_size` → `InsufficientAnnotationError`.
     - Caso: todas as linhas com `rubric_biomed_score = NaN` → `n_valid=0`, `n_excluded_nan=n_annotated`,
       levanta `InsufficientAnnotationError` (pois n_valid=0 < min_sample_size=10).
     - Caso: `batch_invariant = False` em alguma linha → `batch_invariant_confirmed=False`
       no resultado + WARNING logado.
     - Matriz de confusão correta para o golden (TP/TN/FP/FN conferidos manualmente).
     - `kappa_interpretation` retorna valor correto do `Literal` para o κ calculado.
   - `tests/unit/infrastructure/adapters/test_judge_validation_report.py`:
     - Relatório gerado contém κ, interpretação, threshold, n_valid, n_excluded_nan.
     - Arquivo de relatório é Markdown válido (começa com `#`, contém tabela).
     - Todos os 5 ramos de interpretação são cobertos (mock com κ em cada faixa).
   - `tests/unit/infrastructure/stats/test_cohen_kappa_adapter.py`:
     - `CohenKappaAdapter.compute([0,1,0,1], [0,1,0,0])` → valor esperado ± 1e-9
       (computar manualmente e citar no teste).
     - Concordância perfeita → κ = 1.0.

ENTREGÁVEL:
- Extensão de `src/inteligenciomica_eval/domain/errors.py`
  (`InsufficientAnnotationError`)
- Extensão de `src/inteligenciomica_eval/domain/ports.py`
  (`KappaCalculatorPort` — delta de contrato M6, documentado)
- `src/inteligenciomica_eval/infrastructure/stats/cohen_kappa_adapter.py`
  (`CohenKappaAdapter`)
- `src/inteligenciomica_eval/application/judge_validation.py`
  (`JudgeValidationConfig`, `JudgeValidationResult`, `JudgeValidationUseCase`)
- `src/inteligenciomica_eval/infrastructure/adapters/judge_validation_report_adapter.py`
- `src/inteligenciomica_eval/infrastructure/prompts/judge_validation_report.j2`
  (template Jinja2)
- Atualização de `cli.py` com o comando `validate-judge`
- `tests/unit/application/test_judge_validation.py`
- `tests/unit/infrastructure/adapters/test_judge_validation_report.py`
- `tests/unit/infrastructure/stats/test_cohen_kappa_adapter.py`
- `docs/judge_validation_report.md` — gerado pela execução REAL sobre os dados de M4
  (evidência do gate do milestone)

RESTRIÇÕES (DoD §14.2):
- `sklearn` APENAS em `infrastructure/stats/` (Nota de operacionalização M6, item 5);
  `import-linter` deve rejeitar `sklearn` em `domain`/`application` após extensão da lista.
- `JudgeValidationUseCase` **não** recebe `report_path` — retorna resultado puro.
- `from __future__ import annotations`; type hints; docstrings Google style.
- `mypy --strict`; `import-linter` OK; cobertura ≥ 90% no use case.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-602):
- κ calculado e reportado sobre os dados REAIS de M4 em `docs/judge_validation_report.md`.
- Determinismo do juiz confirmado (`batch_invariant_confirmed=True`) — ou WARNING claro.
- `n_excluded_nan` presente no resultado e no relatório.
- `kappa_interpretation` é `Literal` com os 5 valores de Landis & Koch.
- Relatório com 5 ramos de interpretação alinhados com a escala.
- Matriz de confusão presente e conferida.
- `ielm-eval validate-judge --help` funciona.
- Testes unitários passam com golden calculado manualmente.
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-602 + arquitetura visao_alto_nivel §9.5 + §14.9 +
ADR-003 (determinismo do juiz) + ADR-007 (NaN) + "Nota de operacionalização M6" item 5
(sklearn restrito a infrastructure/) + `docs/judge_validation_report.md` gerado +
relatório de implementação do desenvolvedor (Parte A).

VERIFIQUE, item a item, citando arquivo:linha:
1. DOMÍNIO:
   - `InsufficientAnnotationError` declarada em `domain/errors.py` na hierarquia correta?
   - `KappaCalculatorPort` declarado em `domain/ports.py` como `@runtime_checkable Protocol`
     com método `compute(y_true, y_pred) -> float`? Documentado como delta de contrato M6?
2. CAMADAS:
   - `CohenKappaAdapter` em `infrastructure/stats/` — NÃO em `application/` ou `domain/`?
   - `import sklearn` ocorre APENAS em `infrastructure/stats/cohen_kappa_adapter.py`?
     `import-linter` atualizado para incluir `sklearn` na lista proibida de `domain` e
     `application`?
3. USE CASE:
   - `JudgeValidationUseCase` recebe `KappaCalculatorPort` via injeção — NÃO instancia
     `CohenKappaAdapter` internamente?
   - `JudgeValidationConfig` NÃO contém `report_path`?
   - `.run()` retorna `JudgeValidationResult` puro — sem efeito colateral de arquivo?
   - `n_excluded_nan: int` presente em `JudgeValidationResult` (= n_annotated - n_valid)?
4. BINARIZAÇÃO:
   - `judge_binary = 1 if rubric_biomed_score < threshold else 0`?
     (score baixo → concordância com flag=1 do humano — semântica correta)?
   - Linhas com `rubric_biomed_score = NaN` excluídas do cálculo de κ?
     Contadas em `n_excluded_nan`?
5. INTERPRETAÇÃO:
   - `kappa_interpretation` é `Literal["fraca","razoável","moderada","substancial","quase-perfeita"]`?
   - Os 5 limiares de Landis & Koch implementados corretamente (<0.20, 0.20–0.40,
     0.40–0.60, 0.60–0.80, ≥0.80)?
6. RELATÓRIO (`docs/judge_validation_report.md`):
   - Presente no PR? Contém κ numérico + interpretação?
   - Contém `n_excluded_nan` explícito?
   - Contém matriz de confusão 2×2?
   - Contém tabela de discordâncias (pelo menos cabeçalho)?
   - Template em `infrastructure/prompts/judge_validation_report.j2` (não inline no .py)?
   - Adapter em `infrastructure/adapters/judge_validation_report_adapter.py` (não em
     `infrastructure/report/` — diretório inexistente em §8)?
7. TESTES:
   - Golden com κ calculado manualmente e citado no comentário?
   - `InsufficientAnnotationError` quando `n_valid < min_sample_size`?
   - `batch_invariant_confirmed=False` gera WARNING?
8. DoD §14.2: type hints; docstrings; mypy --strict; import-linter (sklearn APENAS em
   infrastructure/stats/)?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Cite o κ reportado em `docs/judge_validation_report.md` e a interpretação correspondente
na escala de 5 categorias.
~~~
