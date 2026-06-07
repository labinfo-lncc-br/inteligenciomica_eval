# M6_TAREFA-606_B — Auditoria Codex do manual de operação

**Data**: 2026-06-07
**Milestone**: M6 — Qualidade e Segurança
**Épico**: E9 (Operações/Documentação)
**Papel**: code-reviewer
**Escopo auditado**:
- `docs/prompts_m6_tarefa_606_manual.md`
- `docs/dev-log/M6_TAREFA-606_A_emenda-manual-operacao.md`
- `docs/operations_manual.md`
- `scripts/validate_manual.py`
- código entregue nas trilhas M3-309 / M3-310 / M3-311

---

## Veredito

**FAIL parcial / Request changes**

O manual foi atualizado de forma **cirúrgica** e cobre a maior parte do prompt
`docs/prompts_m6_tarefa_606_manual.md`, sobretudo nos temas:

- `--run-id` obrigatório na execução real;
- nova seção de modo `external`;
- documentação de `endpoint_env` por nome;
- ressalva do M5/funil;
- smoke-test do manual com validação de flags.

Apesar disso, a versão final do manual **não ficou totalmente alinhada** com o
código realmente entregue em M3-309/310/311. Há dois desvios materiais e alguns
resíduos textuais.

---

## Resultado item a item contra o prompt 606

### 1. Seção 5 — `run ... --run-id`, `--phase`, `--serial`

**Status:** ✅ Conforme ao prompt e ao código

Evidência no manual:
- `ielm-eval run --config config/experiment_round1.yaml --run-id <run_id>`
  em [docs/operations_manual.md:451](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:451)
- tabela com `--phase`, `--serial` e `--require-verified-determinism`
  em [docs/operations_manual.md:458](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:458)

Evidência no código:
- `--run-id` na CLI em [src/inteligenciomica_eval/cli.py:60](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/cli.py:60)
- `--phase` em [src/inteligenciomica_eval/cli.py:64](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/cli.py:64)
- `--serial` em [src/inteligenciomica_eval/cli.py:78](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/cli.py:78)

Conclusão:
- essa parte ficou correta e aderente ao comportamento real da CLI.

### 2. Subseção de perguntas — `questions:` / multi-área / formato

**Status:** ⚠️ Conforme ao prompt, mas **não conforme à execução real atual**

Evidência no manual:
- subseção em [docs/operations_manual.md:468](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:468)
- exemplo `questions: "config/questions.yaml"` em [docs/operations_manual.md:473](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:473)
- exemplos multi-área com `questions_<area>.yaml`
  em [docs/operations_manual.md:489](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:489)

Evidência no código:
- o schema contém `questions: str | None = None`
  em [src/inteligenciomica_eval/infrastructure/config/schema.py:144](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/config/schema.py:144)
- porém a execução real carrega perguntas a partir de `BENCHMARK_QUESTIONS_PATH`
  ou do arquivo empacotado, sem consumir `cfg.questions`, em
  [src/inteligenciomica_eval/infrastructure/wiring.py:626](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:626)
  e [src/inteligenciomica_eval/infrastructure/config/settings.py:31](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/config/settings.py:31)
- o loader espera **JSONL**, não YAML, em
  [src/inteligenciomica_eval/infrastructure/benchmark/loader.py:11](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/benchmark/loader.py:11)

Impacto:
- o operador pode editar `questions:` no YAML de rodada acreditando que mudou o benchmark;
- a execução real continua lendo outro caminho;
- o exemplo `.yaml` conflita com o formato efetivamente consumido pelo loader (`JSONL`).

Conclusão:
- a seção atende ao texto do prompt 606, mas **não está alinhada ao runtime real**;
- esse é um achado **importante** e suficiente para impedir aprovação imediata.

### 3. Nova seção de modo `external`

**Status:** ✅ Majoritariamente conforme ao prompt e alinhada a M3-311

Evidência no manual:
- abertura da seção em [docs/operations_manual.md:281](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:281)
- `managed` como default em [docs/operations_manual.md:290](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:290)
- `server_mode: external` em [docs/operations_manual.md:312](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:312)
- `endpoint_env` por modelo em [docs/operations_manual.md:318](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:318)
- túneis SSH em [docs/operations_manual.md:335](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:335)
- verificação `/health` e `/healthz` em [docs/operations_manual.md:353](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:353)
- bloco de responsabilidade do operador em [docs/operations_manual.md:364](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:364)
- auditoria de proveniência em [docs/operations_manual.md:403](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:403)

Evidência no código:
- `server_mode` em [src/inteligenciomica_eval/infrastructure/config/schema.py:157](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/config/schema.py:157)
- `endpoint_env` em [src/inteligenciomica_eval/infrastructure/config/model_registry.py:56](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/config/model_registry.py:56)
- probes e `--require-verified-determinism` em
  [src/inteligenciomica_eval/cli.py:86](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/cli.py:86)
  e [src/inteligenciomica_eval/cli.py:170](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/cli.py:170)
- proveniência (`server_mode`, served model IDs, determinismo, `endpoints_provenance`)
  em [src/inteligenciomica_eval/infrastructure/wiring.py:530](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:530)

Conclusão:
- esta foi a parte mais sólida da emenda;
- a seção está substancialmente correta e alinhada à TAREFA-311.

### 4. Seção 2 — env vars de `endpoint_env` por nome

**Status:** ✅ Conforme ao prompt e ao código

Evidência no manual:
- subseção em [docs/operations_manual.md:125](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:125)

Evidência no código:
- validação do nome da env var em
  [src/inteligenciomica_eval/infrastructure/config/schema.py:44](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/config/schema.py:44)

Conclusão:
- o manual documenta corretamente que os YAMLs guardam apenas nomes de variáveis;
- não introduz nova variável global obrigatória.

### 5. Pendências M6 — `--force` e ressalva do funil

**Status:** ✅ Conforme

Evidência:
- `--force` em [docs/operations_manual.md:635](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:635)
- ressalva do nome do funil em [docs/operations_manual.md:718](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:718)

Conclusão:
- a pendência do `funnel` foi endereçada corretamente;
- não foi encontrado uso de `--force-rows`.

### 6. M5 adiado — Seção 9 não preenchida com comandos inexistentes

**Status:** ✅ Conforme

Evidência:
- stub preservado em [docs/operations_manual.md:701](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:701)

Conclusão:
- o manual preserva corretamente a condição de M5 não implementado.

### 7. Não-regeneração — diff cirúrgico

**Status:** ✅ Conforme

Evidência:
- o relatório A e o diff mostram inserções localizadas;
- a estrutura global do manual foi preservada;
- a nova seção foi introduzida como `4-B`, evitando renumeração em cascata.

Conclusão:
- a edição foi de fato cirúrgica.

### 8. Smoke-test do manual

**Status:** ✅ Atendido, com ressalva de robustez

Evidência:
- novo comportamento em [scripts/validate_manual.py](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/scripts/validate_manual.py:1)
- checagem de `--run-id` e `--require-verified-determinism`
  em [scripts/validate_manual.py:183](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/scripts/validate_manual.py:183)
- saída PASS registrada no relatório A:
  [docs/dev-log/M6_TAREFA-606_A_emenda-manual-operacao.md](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/dev-log/M6_TAREFA-606_A_emenda-manual-operacao.md:77)

Ressalva:
- `_check_subcmd()` e `_run_help_output()` usam estratégias diferentes para invocar a CLI,
  em [scripts/validate_manual.py:140](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/scripts/validate_manual.py:140)
  e [scripts/validate_manual.py:162](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/scripts/validate_manual.py:162);
- isso pode gerar falso PASS/FAIL se o entrypoint instalado divergir do código fonte.

Conclusão:
- o smoke-test existe e cobre o exigido pelo prompt;
- a implementação pode ser endurecida, mas isso não invalida o entregável por si só.

### 9. Markdown válido; sem segredos expostos

**Status:** ✅ Conforme

Conclusão:
- não foram expostos segredos nem endpoints reais;
- os exemplos usam valores mascarados ou localhost.

---

## Divergências cirúrgicas

### 1. `questions:` documentado como mecanismo operacional, mas não usado pela execução real

**Gravidade:** IMPORTANTE

Manual:
- [docs/operations_manual.md:470](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:470)

Código:
- [src/inteligenciomica_eval/infrastructure/wiring.py:627](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/wiring.py:627)
- [src/inteligenciomica_eval/infrastructure/config/settings.py:31](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/config/settings.py:31)

Descrição:
- o manual afirma que o benchmark vem de `questions:` no YAML de rodada;
- o runtime real usa `BENCHMARK_QUESTIONS_PATH` ou o arquivo empacotado;
- o campo existe no schema, mas não é consumido no wiring de produção.

Impacto:
- instrução operacional enganosa para troca de benchmark;
- risco de rodada executada com perguntas diferentes das esperadas.

### 2. Exemplo de perguntas usa extensão `.yaml`, mas o loader consome JSONL

**Gravidade:** IMPORTANTE

Manual:
- [docs/operations_manual.md:475](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:475)

Código:
- [src/inteligenciomica_eval/infrastructure/benchmark/loader.py:11](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/benchmark/loader.py:11)

Descrição:
- o texto fala em “arquivo JSONL”, mas os exemplos e nomes de arquivo usam `.yaml`.

Impacto:
- operador pode produzir um YAML inválido para um loader que espera JSONL linha a linha.

### 3. `config/experiment_round1_external.yaml` é tratado como arquivo operacional, mas não existe

**Gravidade:** IMPORTANTE

Manual:
- [docs/operations_manual.md:313](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:313)
- [docs/operations_manual.md:396](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:396)

Repositório:
- `config/experiment_round1.yaml`
- `config/model_registry.yaml`

Descrição:
- a seção `external` fornece um comando pronto com um arquivo que não está versionado.

Impacto:
- copy/paste operacional falha imediatamente;
- a documentação exige derivação manual não explicada.

### 4. Inconsistência interna sobre `VLLM_ENABLE_V1_MULTIPROCESSING`

**Gravidade:** IMPORTANTE

Manual:
- trecho antigo `managed`: [docs/operations_manual.md:234](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:234)
- trecho novo `external`: [docs/operations_manual.md:377](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:377)

Código e arquitetura:
- [src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py:17](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/src/inteligenciomica_eval/infrastructure/adapters/vllm_server_manager.py:17)
- [docs/arquitetura_detalhada_validacao_inteligenciomica.md:466](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/arquitetura_detalhada_validacao_inteligenciomica.md:466)

Descrição:
- na seção antiga de subida manual do juiz, o manual ainda mostra
  `VLLM_ENABLE_V1_MULTIPROCESSING=1`;
- a nova seção `external` e o código exigem `=0` para o juiz determinístico.

Impacto:
- o manual contém duas instruções conflitantes para o mesmo regime do juiz.

### 5. Resíduo textual: “Quando o full run estiver implementado”

**Gravidade:** SUGESTÃO

Manual:
- [docs/operations_manual.md:521](/prj/prjatrv/lgonzaga/DVLP/inteligenciomica_eval/docs/operations_manual.md:521)

Descrição:
- a frase é remanescente da era pré-TAREFA-310;
- contradiz a própria Seção 5, que já documenta o full run real.

Impacto:
- baixa gravidade, mas reduz consistência editorial.

---

## Alinhamento com M3-309 / M3-310 / M3-311

### M3-309 / M3-310

**Alinhado:**
- `--run-id` obrigatório;
- `--phase`;
- `--serial`;
- resumabilidade por `row_id`.

**Não alinhado:**
- a documentação operacional de `questions:` como fonte efetiva do benchmark.

### M3-311

**Alinhado:**
- `server_mode='external'`;
- `endpoint_env` por modelo;
- `--require-verified-determinism`;
- colunas/estrutura de proveniência;
- `managed` como default preservado.

Conclusão:
- a parte de modo `external` está coerente com a trilha M3-311;
- a parte de perguntas segue o prompt 606, mas não o wiring real hoje mergeado.

---

## Recomendação final

**Request changes**

### Motivos objetivos

- o manual passou a instruir o operador a usar `questions:` como fonte do benchmark,
  mas a execução real não usa esse campo;
- o manual usa nomes de arquivos `.yaml` para uma carga que é `JSONL`;
- a seção `external` referencia um arquivo de exemplo que não existe no repositório;
- persiste uma contradição interna sobre `VLLM_ENABLE_V1_MULTIPROCESSING` no juiz.

### Ações mínimas para aprovação

1. Corrigir a documentação de perguntas para refletir o mecanismo real atualmente usado,
   ou corrigir o código para efetivamente consumir `cfg.questions`.
2. Unificar o formato/nome dos arquivos de perguntas com o loader real (`JSONL`).
3. Versionar um arquivo real para `external` ou reescrever o trecho para derivação a
   partir de `config/experiment_round1.yaml`.
4. Corrigir a Seção 4 antiga para `VLLM_ENABLE_V1_MULTIPROCESSING=0` no juiz.
5. Remover o resíduo “Quando o full run estiver implementado”.

---

## Fechamento

O entregável da TAREFA-606 ficou **bom na parte de `external` e de flags CLI**, e a edição
foi de fato **cirúrgica**. O problema é de **consistência entre documentação e runtime**,
não de abrangência do diff. Por isso a avaliação final é:

**Prompt 606:** atendido em grande parte  
**Código M3-309/310/311:** alinhamento parcial  
**Decisão de review:** `FAIL parcial / Request changes`
