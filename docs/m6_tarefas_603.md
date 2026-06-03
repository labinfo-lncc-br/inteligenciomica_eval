# Prompt M6 — TAREFA-603 (Property-based tests em parsers e serializers)

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
arquivo; como agora executaremos a **TAREFA-603**, os prompts (Parte A e Parte B) estão em
`docs/m6_tarefas_603.md`.

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

## TAREFA-603 — Property-based tests em parsers e serializers

**Épico:** E9 · **Skill:** test-engineer · **Prioridade:** P1 · **Tamanho:** S
**Dependências:** TAREFA-009 (`ParquetStorage`), TAREFA-010 (config/`config_hash`),
TAREFA-020 (`PrometheusJudgeAdapter`/parser de rubrica — M2), TAREFA-003 (`MetricVector`) ·
**ADRs:** ADR-009 (idempotência por `row_id`) · **Camadas:** testes (não altera produção)

### Prompt A — Implementação (Claude Code)

~~~text
CONTEXTO: Subsistema de Validação InteligenciÔmica (arquitetura v1.1, §11.1, §14.9
TAREFA-603). Skills ativos: test-engineer §8 (hypothesis/property-based), python-clean-architecture.
M0–M4 já mergeados (M5 adiado). Esta tarefa NÃO altera código de produção; fortalece a
suite de testes com property-based testing sobre os 4 targets críticos de
roundtrip/idempotência.

TAREFA: TAREFA-603 — Adicionar testes property-based com `hypothesis` para parsers e
serializers críticos do subsistema.

SETUP OBRIGATÓRIO — antes de escrever os testes:
- Registrar o marcador `property` em `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  markers = [
    "unit: testes unitários",
    "integration: testes de integração",
    "e2e: testes ponta-a-ponta",
    "property: property-based tests (hypothesis)",  # ← NOVO
    "security: testes de segurança",                # ← necessário para TAREFA-605
  ]
  ```
- Todas as funções de teste desta tarefa devem ser decoradas com `@pytest.mark.property`.

TARGETS E PROPRIEDADES:

### Target 1: Parser de resposta do juiz Prometheus
Arquivo: `tests/unit/infrastructure/adapters/test_prometheus_parser_property.py`
Módulo-alvo: `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py`
— função de parsing de resposta JSON do juiz.

Propriedades a testar:
- P1.1 — `parse(valid_json_with_score_in_range) → RubricScore` (nunca levanta exceção
  para JSON válido com `score ∈ [0.0, 1.0]` e `feedback` como string).
- P1.2 — `parse(arbitrary_string) → NaN ou LLMOutputParseError` (strings arbitrárias
  NUNCA causam exceção não-tratada que vaze para o use case — ou retorna NaN-sentinel
  ou levanta `LLMOutputParseError`, nunca `KeyError`/`ValueError`/`json.JSONDecodeError`
  não-capturado).
- P1.3 — Para JSON válido, `parsed.score ∈ [0.0, 1.0]` sempre.

Estratégias hypothesis:
```python
import pytest
from hypothesis import given, settings, strategies as st

valid_score = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
valid_feedback = st.text(min_size=1, max_size=500)
valid_json = st.builds(
    lambda s, f: json.dumps({"score": s, "feedback": f}),
    valid_score, valid_feedback
)
arbitrary_string = st.text()  # inclui strings vazias, JSON malformado, binário

@pytest.mark.property
@given(s=arbitrary_string)
@settings(max_examples=200)
def test_parser_never_raises_uncaught_exception(s): ...
```

### Target 2: Roundtrip de `MetricVector` (serialização/desserialização)
Arquivo: `tests/unit/domain/test_metric_vector_property.py`
Módulo-alvo: `src/inteligenciomica_eval/domain/value_objects.py` — `MetricVector`

Propriedades a testar:
- P2.1 — Roundtrip: `MetricVector.from_dict(mv.to_dict()) == mv` para qualquer
  `MetricVector` com valores em [0, 1] ou NaN.
- P2.2 — Idempotência: `mv.to_dict()` chamado duas vezes retorna dicts iguais
  (não tem estado interno mutável).
- P2.3 — `MetricVector` com todos os valores válidos ([0,1]) → `has_nan() == False`.
  `MetricVector` com pelo menos um `math.nan` → `has_nan() == True`.

Decorar todas com `@pytest.mark.property`.

Estratégias hypothesis:
```python
metric_value = st.one_of(
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    st.just(float("nan"))
)
# gerar dicts com todas as chaves obrigatórias de MetricVector
```

### Target 3: `config_hash` — estabilidade e sensibilidade
Arquivo: `tests/unit/infrastructure/config/test_config_hash_property.py`
Módulo-alvo: `src/inteligenciomica_eval/infrastructure/config/provenance.py` —
`config_hash(config: dict) -> str`

Propriedades a testar:
- P3.1 — **Estabilidade**: `config_hash(c) == config_hash(c)` (duas chamadas com mesmo
  dict → mesmo hash). Testar com dicts com keys em ordem aleatória.
- P3.2 — **Sensibilidade**: `config_hash(c) != config_hash(mutate_one_field(c))`
  para qualquer mutação de um campo de valor (mudar valor de uma key existente).
  Usar `st.dictionaries` com valores `st.text() | st.integers() | st.floats(...)`.
- P3.3 — **Canonicidade**: dois dicts com mesmas keys/valores mas ordem diferente →
  MESMO hash (serialização canônica/ordenada).

Decorar todas com `@pytest.mark.property`.

Estratégias hypothesis:
```python
simple_config = st.dictionaries(
    st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L",))),
    st.one_of(st.text(max_size=50), st.integers(), st.floats(allow_nan=False)),
    min_size=1, max_size=10
)
```

### Target 4: `ParquetStorage` roundtrip por `row_id`
Arquivo: `tests/unit/infrastructure/adapters/test_parquet_roundtrip_property.py`
Módulo-alvo: `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py`

Propriedades a testar:
- P4.1 — Roundtrip: `read(run_id)[row_id] == original_result` após `write(run_id, result)`.
  Usar polyfactory para gerar `EvaluationResult` válido arbitrário.
- P4.2 — Idempotência por `row_id` (ADR-009): `write(run_id, r); write(run_id, r)` →
  `len(read(run_id)) == 1` (não duplica linhas com mesmo `row_id`).
- P4.3 — `exists(run_id, row_id)` retorna `True` após write, `False` antes.

Decorar todas com `@pytest.mark.property`.

Configuração:
- Usar `tmp_path` fixture do pytest (cada teste hypothesis num `tmp_path` separado;
  usar `@settings(database=None)` para evitar acumular exemplos entre runs).

ENTREGÁVEL:
- `pyproject.toml` — marcadores `property` e `security` registrados (se ainda não estiverem)
- `tests/unit/infrastructure/adapters/test_prometheus_parser_property.py`
- `tests/unit/domain/test_metric_vector_property.py`
- `tests/unit/infrastructure/config/test_config_hash_property.py`
- `tests/unit/infrastructure/adapters/test_parquet_roundtrip_property.py`
- Se propriedades revelarem bugs: corrigir o código de produção + adicionar o fix ao PR
  com comentário `# bug encontrado por hypothesis: <descrição>`.

RESTRIÇÕES (DoD §14.2):
- `from __future__ import annotations`; type hints; docstrings nos módulos de teste.
- Todos os testes correm em CPU sem GPU/rede/container.
- `@pytest.mark.property` em todas as funções de teste desta tarefa.
- `@settings(max_examples=200)` como mínimo para os targets 1 e 3; `@settings(max_examples=50)`
  para target 4 (envolve I/O de arquivo).
- `ruff`, `mypy --strict`, `import-linter` verdes.
- `pytest tests/unit/ -m "not e2e and not integration"` verde em CI.

CRITÉRIO DE ACEITAÇÃO (tabela TAREFA-603):
- Marcador `property` registrado em `pyproject.toml`; `pytest -m property` não gera
  aviso de marcador desconhecido.
- Roundtrip e idempotência cobertos para todos os 4 targets.
- Nenhum hypothesis falsifica as propriedades (se falsificar, o bug deve ser corrigido
  ANTES de commitar).
- Testes rodam em < 60 segundos no CI de CPU (verificar com `pytest --timeout=60`).
~~~

### Prompt B — Verificação (ChatGPT Codex)

~~~text
PAPEL: code-reviewer. NÃO reescreva; AUDITE.

ENTRADA: diff do PR da TAREFA-603 + arquitetura §11.1 + ADR-009 + skill test-engineer §8
(property-based) + relatório de implementação do desenvolvedor (Parte A).

VERIFIQUE, item a item, citando arquivo:linha:
1. Marcador `property` registrado em `pyproject.toml` (`[tool.pytest.ini_options] markers`)?
   `pytest -m property` executado sem aviso de marcador desconhecido?
2. Os 4 arquivos de testes estão presentes, um por target?
   Todas as funções decoradas com `@pytest.mark.property`?
3. Target 1 (parser Prometheus):
   - P1.2 presente? Strings arbitrárias nunca propagam exceção não-tratada? O
     `@given(st.text())` está lá?
   - `@settings(max_examples=200)` (ou superior)?
4. Target 2 (MetricVector roundtrip):
   - `from_dict(mv.to_dict()) == mv` testado? Estratégia inclui casos com NaN?
5. Target 3 (config_hash):
   - Propriedade de **canonicidade** (dicts com mesma keys/valores, ordem diferente →
     mesmo hash) testada explicitamente?
   - Propriedade de **sensibilidade** (mutação de 1 campo → hash diferente) testada?
6. Target 4 (Parquet roundtrip):
   - `tmp_path` fixture usada (não deixa arquivos em /tmp permanente)?
   - `@settings(database=None)` presente para evitar acúmulo de exemplos entre runs?
   - Idempotência por `row_id` (P4.2) testada — dois writes com mesmo row_id → 1 linha?
7. Se algum `@example(...)` de falsificação foi adicionado: indica que hypothesis
   encontrou um bug? O fix está no PR de produção e comentado?
8. Todos os testes são independentes de GPU/rede (sem `@pytest.mark.integration` ou
   `skipif` para containers)?
9. `pytest -m property --timeout=60` passa (< 60 segundos)? DoD §14.2 completo?

SAÍDA: PASS/FAIL + tabela de divergências (critério | arquivo:linha | gravidade).
Confirme execução de `pytest -m property` (não `-k property`) e cite o tempo total.
Se alguma propriedade falsificou e o bug NÃO foi corrigido: FAIL automático.
~~~
