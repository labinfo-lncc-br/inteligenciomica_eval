# inteligenciomica-eval

Subsistema de Validação InteligenciÔmica.

## Milestones

| Milestone | Descrição | Status |
|-----------|-----------|--------|
| M0 (001–012) | Fundação do Domínio (VOs, entidades, ports, serviços) | ✅ |
| M1 (013–021) | Adapters de Infraestrutura (Qdrant, vLLM, RAGAS, BERTScore) | ✅ |
| M2 (022–028) | Pipeline de Métricas (Camadas 1+2, gate de integração M2) | ✅ |
| M3 (301–311) | Orquestração das 4 GPUs + ExternalVLLMServerManager + probes de proveniência | ✅ |
| M4 (401–409) | Decisão executiva (Anotação · Agregação · Estatística · Relatório) | ✅ |
| M6 (601–605) | Qualidade e Segurança (mutation testing, Cohen's κ, property-based, manual) | ✅ |
| M5 (501–5xx) | Rodada 2 (OFAT) + Funil de dois estágios | 🔜 |

## Quickstart

```bash
git clone <repo-url>
cd inteligenciomica_eval

# Install dependencies (creates .venv automatically)
uv sync --frozen

# Verify the CLI works
uv run ielm-eval --help
uv run ielm-eval version
```

## Rodada 1 — Modos de execução (M3)

```bash
# Modo managed: ielm-eval gerencia os processos vLLM localmente
ielm-eval run --config round_config.yaml

# Modo external: vLLM já está rodando (cluster LNCC / deploy dedicado)
# Configurar server_mode: external + endpoint_env por modelo no YAML
ielm-eval run --config round_config.yaml --require-verified-determinism
```

## Decisão executiva (M4)

Após executar a Rodada 1 com `ielm-eval run --config round_config.yaml`, use os
comandos de M4 para análise e relatório:

```bash
# Analisar resultados estatisticamente (Wilcoxon, Friedman+Nemenyi, MLM)
ielm-eval analyze --run-id <run> --tests all

# Gerar relatório HTML executivo com plots e ranking de configurações
ielm-eval report  --run-id <run> --output-dir reports/

# Ver status resumido de um run (sem carregar config completo)
ielm-eval status  --run-id <run>

# Exportar respostas para anotação humana offline (Camada 3 — ADR-010)
ielm-eval annotate --config round_config.yaml --run-id <run> \
    --export export_review.jsonl --threshold 0.75

# Ingerir anotações do especialista de volta ao Parquet
ielm-eval annotate --config round_config.yaml --run-id <run> \
    --ingest export_review_editado.jsonl
```

## Operação

Para instruções detalhadas de instalação, configuração de GPUs, execução de rodadas,
anotação humana, análise estatística e troubleshooting, consulte o
**[Manual de Operação](docs/operations_manual.md)**.

## Development

```bash
# Install with dev dependencies
uv sync --frozen

# Install pre-commit hooks
uv run pre-commit install

# Run linting
uv run ruff check .
uv run ruff format --check .

# Run type checking
uv run mypy --strict src

# Check import architecture contracts
uv run lint-imports

# Run tests with coverage (gate de 85%)
uv run pytest --cov=src --cov-report=term-missing -n 4

# Run E2E gate M4 (requer E2E_ENABLED=1, < 90s CPU)
E2E_ENABLED=1 uv run pytest -m e2e tests/e2e/test_full_pipeline_m4.py -v
```

## Project Layout

```
src/inteligenciomica_eval/
├── domain/          # Pure business rules — no I/O, no frameworks
│   └── services/
├── application/     # Use cases orchestrating domain
│   ├── aggregate_results.py      # AggregateResultsUseCase (M4)
│   ├── statistical_analysis.py   # StatisticalAnalysisUseCase (M4)
│   └── use_cases/
├── infrastructure/  # Adapters, repositories, config, prompts
│   ├── adapters/
│   │   ├── external_vllm_server_manager.py  # ExternalVLLMServerManager (M3-311)
│   │   ├── html_report.py                   # HTMLReportAdapter (M4)
│   │   └── stats_adapters.py                # Wilcoxon/Friedman/MLM (M4)
│   ├── config/
│   ├── prompts/
│   ├── provenance/
│   │   └── endpoint_probe.py     # probe_served_model/vllm_version/judge_determinism (M3-311)
│   └── repositories/
├── visualization/   # MatplotlibVisualizationAdapter (M4 — 6 plots canônicos)
└── cli.py           # Typer CLI: run, annotate, analyze, report, status, show-config

tests/
├── unit/            # Fast, no I/O (70–80%)
├── integration/     # Real adapters (15–25%)
├── e2e/             # Full-stack flows (5%)
│   ├── test_m3_full_cycle.py     # Gate E2E M3 ciclo completo (TAREFA-310/311)
│   └── test_full_pipeline_m4.py  # Gate E2E M4 (TAREFA-409)
├── fakes/           # In-memory port implementations
├── factories/       # Test data builders
├── fixtures/        # JSON/JSONL de referência
└── golden/          # Golden datasets para ML/RAG
```
