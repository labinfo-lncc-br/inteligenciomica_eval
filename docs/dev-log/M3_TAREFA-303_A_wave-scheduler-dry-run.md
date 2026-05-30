# M3_TAREFA-303_A — WaveSchedulerService + extensão do CLI `--dry-run`

**Data**: 2026-05-30
**Milestone**: M3 — Orquestração experimental
**Épico**: E3
**Skill**: backend-engineer
**Prioridade / Tamanho**: P0 / S

## Objetivo

Implementar o `WaveSchedulerService` (serviço de aplicação **puro**) que planeja as ondas de
geração por ADR-012 (3+2 geradores concorrentes; juiz à parte) e estender `ielm-eval run
--dry-run` (TAREFA-010) para exibir o mapa de ondas (tabela Rich) + avisos.

## Arquivos Criados / Modificados

| Arquivo | Mudança |
|---------|---------|
| `src/.../application/services/__init__.py` | **Novo** (pacote). |
| `src/.../application/services/wave_scheduler.py` | **Novo**: `WaveSchedulerService`, DTOs `Wave`/`WavePlan`, Protocol `RoundConfigView`. |
| `src/.../infrastructure/config/model_registry.py` | **+`to_wave_spec(entry) -> ModelWaveSpec`** (extração canônica ModelEntry→VO; reusada pela 309). Aditivo. |
| `src/.../cli.py` | Extensão `--dry-run`: carrega registry, planeja ondas, renderiza tabela + avisos; nova flag `--serial/--concurrent`; helper `_print_wave_map`. |
| `tests/unit/application/services/__init__.py` | **Novo**. |
| `tests/unit/application/services/test_wave_scheduler.py` | **Novo**: 16 testes (3+2, serial, ModelNotInRegistryError, juiz excluído, golden de cells, VRAM/peak, determinismo, frozen DTOs). |
| `tests/unit/cli/test_dry_run.py` | +`TestDryRunWaveMap` (tabela, serial, capacidade, modelo desconhecido) + skip de registry ausente. |

## Decisões Técnicas

1. **`round_config: RoundConfigView` (Protocol estrutural), NÃO `RoundConfig`.** A spec pede
   `plan(model_specs, round_config: RoundConfig)`, mas `RoundConfig` é **infrastructure** e a
   camada `application` não pode importá-lo (import-linter Contract 2/4; mesmo padrão do
   `ComputeMetricsConfig` de M2). Definido um Protocol `RoundConfigView` (em application) com
   `phases/bases/llms/seeds`, que o `RoundConfig` Pydantic satisfaz por **duck-typing**
   (inversão de dependência, ADR-001). Honra a intenção da assinatura sem acoplar camadas.
2. **Divisão da verificação de VRAM.** A spec lista, na lógica do scheduler, "verificar que
   `sum(vram_awq da onda) ≤ sum(available_gb)`". Mas o scheduler é **puro** e só recebe
   `ModelWaveSpec` + `RoundConfigView` — **nenhum** carrega a capacidade da GPU (`GPUSlot` é
   infrastructure). Decisão: o **scheduler** computa a *demanda* (`vram_required_gb` por onda);
   o **CLI dry-run** (que tem `GPUSlot`) faz o *aviso de capacidade* ("se algum modelo excede o
   `available_gb` da sua GPU" — critério literal da spec). Mantém o scheduler puro.
3. **GPUs de geração `(0,1,2)` e reatribuição dinâmica.** O `gpu_index` do `ModelWaveSpec` é
   nominal (comentário do YAML da 301); o scheduler **reatribui** as GPUs de geração por onda.
   `generation_gpu_indices=(0,1,2)` é parâmetro do construtor (default ADR-012); o tamanho
   define o empacotamento (3 por onda concorrente).
4. **`n_questions` como parâmetro do construtor (default 13/RF1).** `RoundConfig` não carrega o
   nº de perguntas e a assinatura de `plan()` é fixa; o scheduler recebe `n_questions` (o CLI
   passa o mesmo 13 que já usava). Testes injetam valores pequenos para golden determinístico.
5. **Flag `--serial/--concurrent` no CLI.** A spec menciona o aviso para
   `allow_concurrent_models=False` mas não um toggle de CLI; expô-lo é a forma natural de
   alcançar/testar o modo serial. Default concorrente (ADR-012).
6. **Registry ausente → skip gracioso** no dry-run (notice `[dim]`, exit 0): mantém o dry-run
   útil para validação de config sem registry e não quebra fixtures existentes. Registry
   presente + `llm` ausente nele → `ModelNotInRegistryError` → exit 1 (inconsistência real).
7. **`.importlinter` NÃO precisou de mudança**: os contratos usam pacotes-raiz
   (`inteligenciomica_eval.application`), que já cobrem `application/services/` (e cobrirão
   `application/use_cases/` em 304+). `lint-imports` permaneceu 4/0.

## Problemas Encontrados e Soluções

- **RUF002** (caracteres ambíguos `×`/`–` em docstrings): trocados por `x`/`-` (acentos do
  português preservados).
- **Aviso de capacidade era inalcançável com GPUs homogêneas**: como o registry valida cada
  modelo contra o `available_gb` da sua GPU *nominal*, e as GPUs de geração têm capacidade
  igual no layout ADR-012, a reatribuição nunca estoura. O teste usa um registry
  **heterogêneo** (GPU 1 menor) onde um modelo grande reatribuído a ela estoura — cenário real
  que o dry-run deve sinalizar.

## Validação (DoD §14.2)

```text
ruff check . / format --check   -> All checks passed! / 104 files
mypy --strict src               -> Success: no issues found in 37 source files
lint-imports                    -> Contracts: 4 kept, 0 broken
pytest --cov -n 4 --cov-fail-under=85
  -> 813 passed, 15 skipped — coverage 97.49%
  -> wave_scheduler.py: 67 stmts, 0 missed = 100%
  -> cli.py: 96% (faltantes 39-40 = except do `version`, e ramos de fase ausente — PRÉ-EXISTENTES)
```

## Critérios de Aceitação (tabela TAREFA-303)

| Critério | Estado | Evidência (teste) |
|----------|--------|-------------------|
| `allow_concurrent_models=True` (default): 3 onda 1, 2 onda 2 | ✅ | `test_concurrent_three_then_two` |
| `allow_concurrent_models=False`: uma onda por modelo (contra-ADR-012) | ✅ | `test_serial_one_wave_per_model` (+ docstring/Panel) |
| LLM ausente em model_specs → `ModelNotInRegistryError` | ✅ | `test_missing_llm_raises_model_not_in_registry` |
| Juiz NUNCA nas ondas de geração | ✅ | `test_judge_never_in_generation_waves`, `test_judge_excluded_even_if_listed_in_llms` |
| `cells_in_wave` correto (golden) | ✅ | `test_cells_in_wave_golden_phase_a`/`_a_and_b`, `test_phase_b_ignores_base_count` |
| `WaveSchedulerService` NÃO importa infrastructure | ✅ | `lint-imports` 4/0 (Protocol estrutural) |
| `ielm-eval run --dry-run` exibe tabela com coluna GPUs; sem rede | ✅ | `TestDryRunWaveMap.*` (mock-free, sem stubs de rede) |

## Reforço pós-auditoria 303-B (2026-05-30)

A auditoria do Codex (`docs/dev-log/M3_TAREFA-303_B_auditoria-wave-scheduler-dry-run.md`)
retornou **PASS**, com um risco residual pequeno (não-bloqueador): o aviso de capacidade de
VRAM no CLI estava coberto pelo fluxo, mas sem asserção dedicada ao **texto** do Panel.

Endereçado (mudança só-de-teste) em
`tests/unit/cli/test_dry_run.py::TestDryRunWaveMap::test_capacity_warning_when_reassigned_gpu_too_small`:
além do título (`"capacity"`), agora afirma o conteúdo da mensagem de estouro — `"needs"`,
`"available"` (palavras que só ocorrem nessa mensagem e sobrevivem ao wrapping do Rich por
serem palavras inteiras) e o nome do modelo reatribuído (`"gen-b"`). Regates verdes:
ruff/format limpos, mypy 37 files, lint-imports 4/0, `pytest --cov -n 4` → `813 passed,
15 skipped`, cobertura 97.49%, `wave_scheduler.py` 100%.

## Observações para Próximas Tarefas

- **Desvios conscientes a sinalizar ao Codex (Prompt B)**: (1) `round_config` tipado como
  Protocol estrutural `RoundConfigView` (application não importa `RoundConfig`); (2) verificação
  de VRAM dividida (scheduler=demanda, CLI=aviso de capacidade, pois `GPUSlot` é infra); (3)
  flag `--serial` e `n_questions` no construtor; (4) `to_wave_spec` adicionado ao
  `model_registry.py` (aditivo, arquivo da 301).
- **TAREFA-304+** (use cases): usar `application/use_cases/` (auto-coberto pelo import-linter);
  o `WavePlan`/`Wave` desta tarefa são o contrato de entrada do `RunGenerationPassUseCase`.
- **TAREFA-309 (wiring)**: reusar `to_wave_spec` para alimentar o `WaveSchedulerService` a
  partir do `ModelRegistryConfig`.
