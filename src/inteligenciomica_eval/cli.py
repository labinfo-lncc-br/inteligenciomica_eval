from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(
    name="ielm-eval",
    help="InteligenciÔmica Evaluation CLI.",
    add_completion=False,
    no_args_is_help=True,
)
_console = Console()
_err_console = Console(stderr=True)


@app.callback()
def _main() -> None:
    """InteligenciÔmica Evaluation CLI."""


@app.command()
def version() -> None:
    """Print the installed package version."""
    try:
        pkg_version = _pkg_version("inteligenciomica-eval")
    except PackageNotFoundError:
        pkg_version = "unknown"
    _console.print(f"inteligenciomica-eval {pkg_version}")


@app.command()
def run(
    config: Annotated[
        Path, typer.Option("--config", help="Path to round config YAML.")
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run/--no-dry-run",
            help="Validate config and print plan without touching GPU or network.",
        ),
    ] = False,
) -> None:
    """Run an evaluation round.

    Use ``--dry-run`` to validate the config and inspect the planned cell matrix
    without making any calls to vLLM, Qdrant, or other external services.
    """
    # Lazy imports keep CLI startup fast and avoid circular-import issues.
    from inteligenciomica_eval.domain.errors import ConfigValidationError
    from inteligenciomica_eval.infrastructure.config.provenance import config_hash
    from inteligenciomica_eval.infrastructure.config.schema import load_round_config
    from inteligenciomica_eval.infrastructure.config.settings import (
        RuntimeSettings,
        mask_endpoint,
        resolve_endpoint,
    )

    try:
        cfg = load_round_config(config)
    except FileNotFoundError as exc:
        _err_console.print(f"[red]File not found:[/red] {exc}")
        raise typer.Exit(1) from exc
    except ConfigValidationError as exc:
        _err_console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(1) from exc

    if not dry_run:
        _err_console.print(
            "[yellow]Full run not yet implemented. Use --dry-run to validate the config.[/yellow]"
        )
        raise typer.Exit(1)

    # --- Dry-run: print plan, never call vLLM / Qdrant ---
    # RF1 fixes 13 questions per evaluation round (§P4: curated and versioned pre-M1).
    n_questions = 13

    cfg_hash = config_hash(cfg)
    settings = RuntimeSettings()

    n_bases = len(cfg.bases)
    n_llms = len(cfg.llms)
    n_seeds = len(cfg.seeds)

    _console.print(f"\n[bold]Dry-run plan — {cfg.round_id}[/bold]")
    _console.print(f"config_hash  : {cfg_hash}")
    _console.print(f"phases       : {cfg.phases}")

    _console.print(f"\n[bold]Cell counts (N_questions = {n_questions}):[/bold]")
    if "A" in cfg.phases:
        cells_a = n_bases * n_llms * n_seeds * n_questions
        _console.print(
            f"  Phase A  : {n_bases} base(s) x {n_llms} LLM(s) x {n_seeds} seed(s)"
            f" x {n_questions} questions = {cells_a} cells"
        )
    if "B" in cfg.phases:
        cells_b = n_llms * n_seeds * n_questions
        _console.print(
            f"  Phase B  : {n_llms} LLM(s) x {n_seeds} seed(s)"
            f" x {n_questions} questions = {cells_b} cells"
        )

    _console.print("\n[bold]Resolved endpoints (credentials masked):[/bold]")
    _console.print(
        f"  VLLM_GENERATOR_URL : {mask_endpoint(settings.VLLM_GENERATOR_URL)}"
    )
    judge_url = resolve_endpoint(cfg.judge.endpoint_env)
    _console.print(f"  {cfg.judge.endpoint_env} (judge) : {mask_endpoint(judge_url)}")
    _console.print(f"  QDRANT_URL         : {mask_endpoint(settings.QDRANT_URL)}")

    _console.print("\n[dim]GPU/wave map: placeholder — see TAREFA-303.[/dim]")
    _console.print("\n[green]Config valid — dry-run complete.[/green]")


def main() -> None:
    """CLI entry point wrapper with explicit KeyboardInterrupt handling."""
    try:
        app()
    except KeyboardInterrupt:
        _err_console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    main()
