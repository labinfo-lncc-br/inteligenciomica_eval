# inteligenciomica-eval

Subsistema de Validação InteligenciÔmica.

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

# Run tests with coverage
uv run pytest --cov=src --cov-report=term-missing -n auto
```

## Project Layout

```
src/inteligenciomica_eval/
├── domain/          # Pure business rules — no I/O, no frameworks
│   └── services/
├── application/     # Use cases orchestrating domain
├── infrastructure/  # Adapters, repositories, config, prompts
│   ├── adapters/
│   ├── config/
│   ├── prompts/
│   └── repositories/
├── visualization/   # Output rendering helpers
└── cli.py           # Typer CLI entrypoint

tests/
├── unit/            # Fast, no I/O (70–80%)
├── integration/     # Real adapters (15–25%)
├── e2e/             # Full-stack flows (5%)
├── fakes/           # In-memory port implementations
├── factories/       # Test data builders
└── golden/          # Golden datasets for ML/RAG
```
