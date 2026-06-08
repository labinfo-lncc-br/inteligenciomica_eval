# Auditoria Completa — inteligenciomica-eval

**Data:** 2026-06-07  
**Escopo:** código de produção, testes, documentação em `docs/`, prompts e relatórios em `docs/dev-log/`  
**Método:** revisão estrutural com foco em correção, arquitetura, testes, operabilidade, segurança de observabilidade e consistência doc↔código  
**Skills utilizados:** `code-reviewer`, `test-engineer`, `system-architect`

---

## 1. Resumo executivo

O repositório está em um estado **tecnicamente sólido no núcleo executável**:

- `ruff check .` verde
- `ruff format --check .` verde
- `mypy --strict src` verde
- `lint-imports` verde
- smoke do manual verde
- amostras relevantes de unit/e2e verdes
- separação `domain` / `application` / `infrastructure` preservada

O principal problema atual **não está no miolo da arquitetura**, mas em três frentes:

1. **observabilidade segura incompleta** em parte da infraestrutura;
2. **operabilidade/documentação inconsistente** em torno de benchmark/questions e modo `external`;
3. **drift entre código, ADRs, prompts e relatórios** que volta a induzir auditorias e execuções futuras ao erro.

Em termos práticos: o projeto roda, testa e está relativamente bem estruturado, mas a superfície documental e operacional ainda produz informação incorreta ou parcialmente obsoleta em pontos críticos.

---

## 2. Metodologia e evidências

### 2.1 Arquivos-base lidos

Superfícies principais inspecionadas:

- `src/inteligenciomica_eval/cli.py`
- `src/inteligenciomica_eval/domain/entities.py`
- `src/inteligenciomica_eval/infrastructure/wiring.py`
- `src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py`
- `src/inteligenciomica_eval/infrastructure/config/schema.py`
- `src/inteligenciomica_eval/infrastructure/config/settings.py`
- `src/inteligenciomica_eval/infrastructure/config/model_registry.py`
- `src/inteligenciomica_eval/infrastructure/benchmark/loader.py`
- `src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py`
- `src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py`
- `docs/operations_manual.md`
- `docs/security_review.md`
- `docs/arquitetura_detalhada_validacao_inteligenciomica.md`
- `docs/adr/ADR-014-server-mode-external.md`
- prompts M3/M6 relevantes
- relatórios recentes em `docs/dev-log/`

### 2.2 Comandos reproduzidos

Foram reproduzidos os seguintes checks:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run ruff check .
UV_CACHE_DIR=/tmp/uv-cache uv run ruff format --check .
UV_CACHE_DIR=/tmp/uv-cache uv run mypy --strict src
UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/test_endpoint_probe.py tests/unit/cli/test_dry_run.py -q
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/unit/infrastructure/test_wiring_external.py tests/unit/infrastructure/test_provenance_columns.py -q
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/e2e/test_m3_full_cycle.py tests/e2e/test_full_pipeline_m4.py -q --timeout=30
UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/validate_manual.py
```

### 2.3 Resultado dos checks

- `ruff check .`: **PASS**
- `ruff format --check .`: **PASS**
- `mypy --strict src`: **PASS**
- `lint-imports`: **PASS**
- `tests/unit/infrastructure/test_endpoint_probe.py` + `tests/unit/cli/test_dry_run.py`: **30 passed**
- `tests/e2e/test_m3_full_cycle.py` + `tests/e2e/test_full_pipeline_m4.py`: **5 passed, 1 skipped**
- `scripts/validate_manual.py`: **PASS**

Conclusão importante: **os achados abaixo não decorrem de um repositório quebrado**, e sim de inconsistências reais entre superfícies que hoje continuam “verdes” nos gates.

---

## 3. Achados priorizados

## 3.1 Bloqueadores

### B1. Logs de probes ainda expõem URLs cruas

**Categoria:** Segurança / Observabilidade  
**Prioridade:** Bloqueador  
**Arquivos:**

- [src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py:46)
- [docs/security_review.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/security_review.md:160)

**Evidência**

As funções de probe seguem registrando `url` em claro:

- `probe_served_model_ok` / `probe_served_model_empty` / `probe_served_model_failed`  
  [46-51](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py:46)
- `probe_vllm_version_unavailable` / `probe_vllm_version_failed`  
  [114-117](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py:114)
- `probe_judge_determinism_ok` / `probe_judge_determinism_failed`  
  [156-164](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/provenance/endpoint_probe.py:156)

Isso contradiz a narrativa de hardening já consolidada em `docs/security_review.md`, que trata mascaramento de endpoints como entrega concluída, e contradiz também o padrão já adotado em `external_vllm_server_manager.py` e em partes do `wiring`.

**Impacto**

- Se o endpoint remoto vier em formato com credenciais, elas podem aparecer em logs.
- O projeto passa a ter política de mascaramento **parcial**, o que é mais perigoso que ausência explícita de política.
- A documentação de segurança fica factualmente incorreta.

**Recomendação**

- Extrair/compartilhar um helper de mascaramento entre probes e adapters.
- Garantir que nenhum evento de log da infraestrutura emita endpoint cru.
- Adicionar testes explícitos de logging/masking para probes, não só para adapters.

---

### B2. ADR-014 continua contradizendo o comportamento real do sistema

**Categoria:** Documentação normativa / Arquitetura  
**Prioridade:** Bloqueador  
**Arquivos:**

- [docs/adr/ADR-014-server-mode-external.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/adr/ADR-014-server-mode-external.md:60)
- [src/inteligenciomica_eval/domain/entities.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/domain/entities.py:153)
- [src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:147)
- [src/inteligenciomica_eval/infrastructure/wiring.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:126)
- [docs/arquitetura_detalhada_validacao_inteligenciomica.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/arquitetura_detalhada_validacao_inteligenciomica.md:264)

**Evidência**

A ADR ainda afirma:

- `determinism_verified: bool = True` por default  
  [63](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/adr/ADR-014-server-mode-external.md:63)

Mas o sistema executável foi corrigido para:

- `EvaluationResult.determinism_verified = False` por default  
  [153](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/domain/entities.py:153)
- `RowProvenance.determinism_verified = False`  
  [147](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/repositories/parquet_storage.py:147)
- fallback legado de `from_row()` também em `False`
- `_ExperimentConfig.judge_determinism_verified = False`  
  [126](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:126)

Além disso, a arquitetura detalhada já foi atualizada com a regra “nunca `True` sem prova”.

**Impacto**

- A ADR deixa de ser fonte confiável da decisão.
- Auditorias futuras podem reabrir uma discussão já resolvida.
- O projeto fica com duas normas concorrentes: a ADR e o código.

**Recomendação**

- Atualizar a ADR-014 imediatamente para refletir o as-built.
- Fazer varredura de todas as superfícies normativas derivadas da ADR.

---

## 3.2 Importantes

### I1. `BENCHMARK_QUESTIONS_PATH` relativo é resolvido contra `cwd`, não contra o YAML

**Categoria:** Correção / Operabilidade  
**Prioridade:** Importante  
**Arquivos:**

- [src/inteligenciomica_eval/infrastructure/wiring.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:627)
- [src/inteligenciomica_eval/cli.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/cli.py:162)

**Evidência**

`model_registry_path` é resolvido com base em `config.parent`, mas o benchmark override não:

- `questions_path = Path(questions_path_str)`  
  [627-631](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:627)

Isso cria uma semântica operacional inconsistente:

- `model_registry_path` é relativo ao YAML;
- `BENCHMARK_QUESTIONS_PATH` relativo é, na prática, relativo ao diretório de execução.

**Impacto**

- o comando funciona em um diretório e falha em outro;
- troubleshooting operacional fica desnecessariamente difícil;
- o manual induz o uso de caminhos relativos sem explicar a semântica real.

**Recomendação**

- escolher explicitamente a convenção;
- idealmente, tratar paths relativos de benchmark do mesmo modo que `model_registry_path`;
- se não for corrigido no código, documentar isso de forma inequívoca.

---

### I2. `RoundConfig.questions` permanece como campo morto de configuração

**Categoria:** Configuração / Contrato  
**Prioridade:** Importante  
**Arquivos:**

- [src/inteligenciomica_eval/infrastructure/config/schema.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/config/schema.py:146)
- [src/inteligenciomica_eval/infrastructure/wiring.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:627)
- [docs/operations_manual.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:509)

**Evidência**

O schema ainda aceita:

- `questions: str | None = None`  
  [146](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/config/schema.py:146)

Mas o runtime real usa apenas `BENCHMARK_QUESTIONS_PATH` ou o arquivo empacotado.

O manual até documenta corretamente que o campo **não está wired**, mas o mero fato do campo continuar no schema sem uso prático mantém a ambiguidade viva.

**Impacto**

- reforça drift entre schema e comportamento;
- incentiva documentação errada em tarefas futuras;
- torna o contrato YAML mais permissivo do que o runtime.

**Recomendação**

- remover o campo do schema, se ele não faz parte do contrato real;
- ou ligá-lo ao runtime de forma canônica;
- evitar manter “configuração fantasma” por longos ciclos.

---

### I3. O manual segue com exemplos de arquivos de benchmark que não existem

**Categoria:** Operação / Documentação  
**Prioridade:** Importante  
**Arquivos:**

- [docs/operations_manual.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:472)
- [config](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/config)

**Evidência**

O manual sugere:

- `config/questions.jsonl`  
  [481](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:481)
- `config/questions_resistencia.jsonl`  
  [501](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:501)
- `config/questions_sepse.jsonl`  
  [505](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:505)

Mas `config/` contém somente:

- `experiment_round1.yaml`
- `model_registry.yaml`

**Impacto**

- copy/paste operacional falha;
- o smoke-test do manual dá PASS sem cobrir a utilidade real dos exemplos;
- o operador fica sem artefato versionado para seguir o procedimento.

**Recomendação**

- versionar arquivos exemplo reais;
- ou reescrever o manual para deixar explícito que são arquivos a serem criados pelo operador;
- ampliar a validação do manual para detectar referências locais inexistentes.

---

### I4. O manual fala em 13 perguntas empacotadas, mas o repositório entrega 3 placeholders

**Categoria:** Operação / Acurácia documental  
**Prioridade:** Importante  
**Arquivos:**

- [docs/operations_manual.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:476)
- [questions_rf1.jsonl](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/benchmark/questions_rf1.jsonl:1)

**Evidência**

O manual diz:

- arquivo empacotado com “13 perguntas RF1”  
  [476-477](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:476)

O arquivo real contém:

- 1 linha `_comment`
- 3 perguntas placeholder

**Impacto**

- expectativa operacional errada;
- percepção artificial de prontidão do benchmark;
- risco de alguém assumir que a base curada está pronta para produção.

**Recomendação**

- tornar o manual preciso sobre o estado atual;
- ou fechar a lacuna entregando de fato o benchmark completo.

---

### I5. `config/model_registry.yaml` canônico ainda não está pronto para `external`

**Categoria:** Operação / Configuração  
**Prioridade:** Importante  
**Arquivos:**

- [config/model_registry.yaml](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/config/model_registry.yaml:68)
- [docs/operations_manual.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:323)

**Evidência**

O código e a documentação pedem `endpoint_env` por modelo em `external`, mas o registry versionado das entradas reais não traz `endpoint_env` em nenhum modelo do roster canônico ([68-130](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/config/model_registry.yaml:68)).

**Impacto**

- `external` depende de mutação manual do registry canônico;
- a configuração versionada representa de fato só o cenário `managed`;
- a trilha operacional do manual fica parcialmente hipotética.

**Recomendação**

- decidir se o registry canônico deve ser dual-mode;
- ou versionar um segundo arquivo de registry para `external`;
- ou deixar explícito na documentação que `external` exige derivação local do registry.

---

### I6. O smoke-test do manual é útil, mas ainda superficial para a criticidade do documento

**Categoria:** Tooling / QA de documentação  
**Prioridade:** Importante  
**Arquivos:**

- [scripts/validate_manual.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/scripts/validate_manual.py:1)

**Evidência**

Hoje o script valida:

- subcomandos existentes;
- flags em `run --help`;
- sintaxe básica de `curl localhost`.

Ele **não valida**:

- referências a arquivos locais existentes;
- coerência de claims como “13 perguntas”;
- exemplos de paths em `BENCHMARK_QUESTIONS_PATH`;
- coerência entre trechos do manual e o estado do repositório.

**Impacto**

- o manual pode continuar “verde” mesmo com instruções operacionais erradas;
- regressões documentais práticas escapam facilmente.

**Recomendação**

- adicionar checagem opcional de arquivos referenciados em blocos shell;
- validar exemplos locais conhecidos do manual;
- incluir asserts básicos sobre claims críticas do documento.

---

## 3.3 Sugestões

### S1. Prompts M3/M6 permanecem como fonte ativa de drift

**Categoria:** Processo / Governança documental  
**Arquivos:**

- [docs/prompts_m3_tarefa_311.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/prompts_m3_tarefa_311.md:14)
- [docs/prompts_m6_tarefa_606_manual.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/prompts_m6_tarefa_606_manual.md:5)
- [docs/prompts_m3_tarefa_312_integration_gate.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/prompts_m3_tarefa_312_integration_gate.md:17)

**Evidência**

Os prompts ainda carregam instruções obsoletas:

- `external` referenciado como ADR-013 em vez de ADR-014;
- `config/questions.yaml` e `questions:` como mecanismo canônico;
- parse obrigatório de `config/questions.yaml` no gate 312.

**Impacto**

- novas rodadas A/B tendem a reintroduzir hipóteses erradas;
- revisões podem reprovar código correto por comparar contra prompt obsoleto.

**Sugestão**

- manter uma disciplina explícita de “prompt sync” quando o as-built divergir da intenção original;
- reduzir o número de prompts que continuam descrevendo estados intermediários já abandonados.

---

### S2. `docs/dev-log/` é valioso, mas hoje também consolida estados antigos sem índice de validade

**Categoria:** Manutenibilidade / Processo  
**Evidência**

O histórico em `docs/dev-log/` é rico, mas várias conclusões antigas seguem localizáveis sem um marcador explícito de que foram substituídas por ciclos posteriores.

**Impacto**

- leitura retroativa fica mais cara;
- auditorias pontuais exigem reconstruir a cadeia inteira manualmente.

**Sugestão**

- criar convenção simples no cabeçalho: `status: superseded | current | historical`;
- ou manter um índice por tarefa apontando o último relatório válido.

---

### S3. `PrometheusJudgeAdapter` ainda loga conteúdo bruto de falha de parsing

**Categoria:** Segurança / Observabilidade  
**Arquivos:**

- [src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py:156)

**Evidência**

O adapter registra `raw_content` truncado em falhas de parsing:

- [156-164](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py:156)
- [203-214](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/prometheus_judge.py:203)

Isso pode ser aceitável em ambiente de depuração, mas entra em tensão com o princípio geral do projeto de não vazar payloads textuais completos ou semiestruturados em log.

**Sugestão**

- revisar se esse conteúdo bruto é realmente necessário;
- considerar hash, snippet ainda menor ou logging condicionado por nível/flag de debug.

---

## 4. Análise por superfície

## 4.1 Código de produção

### O que está bom

- arquitetura limpa preservada;
- `domain` sem contaminação indevida por infraestrutura;
- wiring suficientemente explícito e auditável;
- fluxo `managed` / `external` está bem separado;
- correção recente de `determinism_verified=False` por default foi bem aplicada.

### Onde o código ainda pede atenção

- segurança de logs em probes;
- semântica de resolução de path para benchmark;
- permanência de `questions` como campo morto de schema;
- alguns pontos de observabilidade expõem mais payload do que o resto do projeto aparenta desejar.

---

## 4.2 Testes

### O que está bom

- boa cobertura de superfícies críticas da trilha M3/M4;
- testes de `external` estão fortes;
- smoke do manual existe e já foi útil;
- `import-linter` está efetivamente protegendo arquitetura.

### Lacunas observadas

- não há teste cobrindo mascaramento de URLs em `endpoint_probe.py`;
- não há teste falhando se o manual citar arquivos locais inexistentes;
- a suíte não protege a consistência entre ADRs/manuais e defaults semânticos do código;
- alguns testes e prompts ainda preservam linguagem de estados antigos, mesmo quando o comportamento já mudou.

---

## 4.3 Documentação em `docs/`

### O que está bom

- `operations_manual.md` melhorou claramente nas últimas tarefas;
- `arquitetura_detalhada_validacao_inteligenciomica.md` está mais alinhada ao código do que os prompts antigos;
- `security_review.md` fornece boa trilha de decisão.

### Onde a documentação falha

- ADR-014 ainda está semanticamente errada;
- manual continua com exemplos de arquivos inexistentes;
- manual superestima o estado do benchmark empacotado;
- documentação normativa e documentação operacional nem sempre falam a mesma língua.

---

## 4.4 Prompts e `docs/dev-log/`

### O que está bom

- o projeto deixou evidência abundante de implementação e auditoria;
- há histórico claro de ciclos A/B/A2/B2;
- várias inconsistências reais foram capturadas por auditorias anteriores.

### Onde há problema

- prompts antigos continuam vivos como se fossem canônicos;
- alguns relatórios já reconhecem drift, mas esse drift não foi totalmente eliminado da base documental;
- falta um mecanismo simples de “estado vigente” por tarefa.

---

## 5. Conclusão geral

O **inteligenciomica-eval** está em um estágio bom de engenharia no núcleo do sistema. O código principal não passa a impressão de projeto improvisado: há arquitetura disciplinada, tipagem forte, testes relevantes e preocupação real com reprodutibilidade, proveniência e operação.

O problema remanescente é de **acabamento crítico nas bordas**:

- parte da observabilidade ainda não honra a política de mascaramento;
- a trilha benchmark/questions segue sofrendo com contrato mal definido;
- o modo `external` está implementado, mas sua documentação/configuração canônica ainda não está completamente “fechada”;
- prompts, ADRs e manual ainda não convergiram totalmente para um único as-built.

Em resumo:

- **estado do código executável:** bom;
- **estado da governança documental e operacional:** razoável, mas ainda inconsistente;
- **próximo ganho de qualidade:** não é reescrever arquitetura, e sim eliminar drift residual entre runtime, config versionada, ADRs, manual e prompts.

---

## 6. Recomendações objetivas de próxima rodada

Ordem sugerida:

1. Corrigir mascaramento de URLs em `endpoint_probe.py` e cobrir com testes.
2. Corrigir ADR-014 para refletir `determinism_verified=False` por default.
3. Definir o contrato real de benchmark:
   - ou `BENCHMARK_QUESTIONS_PATH` é o mecanismo oficial;
   - ou `RoundConfig.questions` volta a ser a fonte canônica;
   - mas não manter os dois em conflito.
4. Resolver a semântica de path relativo de benchmark.
5. Corrigir o manual para:
   - não afirmar 13 perguntas empacotadas enquanto houver 3 placeholders;
   - não citar arquivos inexistentes como se fossem versionados.
6. Atualizar prompts M3/M6 obsoletos para o as-built atual.
7. Ampliar `scripts/validate_manual.py` para checagens operacionais mínimas de artefatos locais.

---

## 7. Veredito final

**Veredito técnico geral:** `PASS COM RESSALVAS IMPORTANTES`

O projeto **não está quebrado** e a base de código é boa. Mas ainda há problemas suficientes em documentação normativa, operabilidade e observabilidade para justificar uma rodada adicional de saneamento antes de considerar o sistema plenamente consistente como produto de engenharia.
