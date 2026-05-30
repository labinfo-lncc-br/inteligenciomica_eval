from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console

if TYPE_CHECKING:
    from inteligenciomica_eval.application.services.wave_scheduler import WavePlan
    from inteligenciomica_eval.domain.value_objects import ModelWaveSpec
    from inteligenciomica_eval.infrastructure.config.model_registry import (
        ModelRegistryConfig,
    )

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
    serial: Annotated[
        bool,
        typer.Option(
            "--serial/--concurrent",
            help="Serialize generators (one wave per model). Against ADR-012; "
            "for debugging or single-GPU hardware. Default: concurrent waves.",
        ),
    ] = False,
) -> None:
    """Run an evaluation round.

    Use ``--dry-run`` to validate the config and inspect the planned cell matrix
    and GPU/wave map without making any calls to vLLM, Qdrant, or other external
    services. Use ``--serial`` to preview the conservative one-wave-per-model layout.
    """
    # Lazy imports keep CLI startup fast and avoid circular-import issues.
    from inteligenciomica_eval.application.services.wave_scheduler import (
        WaveSchedulerService,
    )
    from inteligenciomica_eval.domain.errors import (
        ConfigValidationError,
        ModelNotInRegistryError,
    )
    from inteligenciomica_eval.infrastructure.config.model_registry import (
        load_model_registry,
        to_wave_spec,
    )
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

    # --- GPU/wave map (TAREFA-303) — needs the registry referenced by the round ---
    registry_path = config.parent / cfg.model_registry_path
    try:
        registry = load_model_registry(registry_path)
    except FileNotFoundError:
        _console.print(
            f"\n[dim]Model registry not found at {registry_path} — wave map skipped.[/dim]"
        )
    else:
        specs = tuple(to_wave_spec(entry) for entry in registry.models)
        scheduler = WaveSchedulerService(
            allow_concurrent_models=not serial, n_questions=n_questions
        )
        try:
            plan = scheduler.plan(specs, cfg)
        except ModelNotInRegistryError as exc:
            _err_console.print(f"[red]Wave plan error:[/red] {exc}")
            raise typer.Exit(1) from exc
        _print_wave_map(plan, specs, registry, serial=serial)

    _console.print("\n[green]Config valid — dry-run complete.[/green]")


def _print_wave_map(
    plan: WavePlan,
    specs: tuple[ModelWaveSpec, ...],
    registry: ModelRegistryConfig,
    *,
    serial: bool,
) -> None:
    """Render the wave map table plus serial / VRAM-capacity warnings (TAREFA-303)."""
    from rich.panel import Panel
    from rich.table import Table

    table = Table(title="GPU / wave map (ADR-012)")
    table.add_column("Wave", justify="right")
    table.add_column("Models")
    table.add_column("GPUs")
    table.add_column("VRAM req. (GB)", justify="right")
    table.add_column("Cells", justify="right")
    for wave in plan.waves:
        table.add_row(
            str(wave.wave_index),
            ", ".join(wave.models),
            ", ".join(str(gpu) for gpu in wave.gpu_indices),
            f"{wave.vram_required_gb:.1f}",
            str(wave.cells_in_wave),
        )
    _console.print()
    _console.print(table)
    _console.print(
        f"Total cells per pass: {plan.total_cells} · across 3 passes "
        f"(generation + metrics + judge): {plan.total_cells * 3}"
    )
    _console.print(
        f"Estimated VRAM peak (concurrent): {plan.estimated_vram_peak_gb:.1f} GB"
    )

    if serial:
        _console.print(
            Panel(
                "Serial mode (--serial): one wave per model. This goes AGAINST ADR-012 "
                "(concurrent waves) and is intended for debugging or single-GPU hardware.",
                title="ADR-012 warning",
                style="yellow",
            )
        )

    slots = {slot.gpu_index: slot for slot in registry.gpu_slots}
    spec_by_name = {spec.name: spec for spec in specs}
    over = [
        f"{name} needs {spec_by_name[name].vram_gb_awq:.1f} GB but GPU {gpu} "
        f"has {slots[gpu].available_gb:.1f} GB available"
        for wave in plan.waves
        for name, gpu in zip(wave.models, wave.gpu_indices, strict=True)
        if gpu in slots and spec_by_name[name].vram_gb_awq > slots[gpu].available_gb
    ]
    if over:
        _console.print(
            Panel("\n".join(over), title="VRAM capacity warning", style="yellow")
        )


def main() -> None:
    """CLI entry point wrapper with explicit KeyboardInterrupt handling."""
    try:
        app()
    except KeyboardInterrupt:
        _err_console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    main()
