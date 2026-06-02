from __future__ import annotations

import json
import math
import random
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import structlog
import typer
from rich.console import Console

if TYPE_CHECKING:
    from inteligenciomica_eval.application.services.wave_scheduler import WavePlan
    from inteligenciomica_eval.application.use_cases.annotation_workflow import (
        AnnotationWorkflowUseCase,
    )
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
_log = structlog.get_logger(__name__)


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


@app.command()
def annotate(
    config: Annotated[
        Path, typer.Option("--config", help="Path to round config YAML.")
    ],
    run_id: Annotated[str, typer.Option("--run-id", help="Run identifier.")],
    data_dir: Annotated[
        Path | None,
        typer.Option("--data-dir", help="Parquet storage base directory (M3 mode)."),
    ] = None,
    # M4 — export / ingest flags (ADR-010, §14.7 TAREFA-401/402)
    export_path: Annotated[
        Path | None,
        typer.Option(
            "--export",
            help="Export prioritized responses to JSONL for offline expert review.",
        ),
    ] = None,
    ingest_path: Annotated[
        Path | None,
        typer.Option(
            "--ingest",
            help="Ingest expert-annotated JSONL back into Parquet (TAREFA-402).",
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force/--no-force",
            help="Re-ingest rows already annotated (overwrites existing flag).",
        ),
    ] = False,
    threshold: Annotated[
        float,
        typer.Option(
            "--threshold",
            help="Export responses with final_score below this threshold (or NaN).",
        ),
    ] = 0.70,
    max_items: Annotated[
        int | None,
        typer.Option("--max-items", help="Maximum number of items to export."),
    ] = None,
    sort_by: Annotated[
        str,
        typer.Option(
            "--sort-by",
            help="Sort order for export: finalscore (asc), rubric (asc), random (seed=42).",
        ),
    ] = "finalscore",
    # M3 — interactive / batch CSV annotation (existing)
    csv_path: Annotated[
        Path | None,
        typer.Option(
            "--csv",
            help="CSV file with columns {row_id, flag, note} for batch annotation "
            "(non-interactive). Required columns: row_id, flag. Optional: note.",
        ),
    ] = None,
    max_to_review: Annotated[
        int | None,
        typer.Option("--max", help="Maximum items to show in the review queue."),
    ] = None,
    score_threshold: Annotated[
        float,
        typer.Option(
            "--score-threshold",
            help="Queue items with final_score below this threshold (M3 mode).",
        ),
    ] = 0.6,
    rubric_threshold: Annotated[
        float,
        typer.Option(
            "--rubric-threshold",
            help="Queue items with rubric_biomed_score below this threshold (M3 mode).",
        ),
    ] = 0.5,
) -> None:
    """Manage human annotation for biomedical critical-failure review (Camada 3).

    **M4 export mode** (``--export PATH``): exports prioritized responses to a
    JSONL file that the biomedical specialist edits offline.  Responses with
    ``final_score < threshold`` or NaN are selected and sorted by ``--sort-by``.

    **M4 ingest mode** (``--ingest PATH``): ingests the expert-annotated JSONL
    back into Parquet — implemented in TAREFA-402.

    ``--export`` and ``--ingest`` are mutually exclusive.

    **M3 interactive mode** (default): displays each item from the review queue
    and prompts for 0 (no critical error), 1 (critical error), s (skip) or q (quit).

    **M3 non-interactive mode** (``--csv path``): reads a CSV file with columns
    {row_id, flag, note} and persists annotations in batch without prompts.
    """
    # Mutual exclusivity guard (ADR-010, TAREFA-401 §6)
    if export_path is not None and ingest_path is not None:
        raise typer.BadParameter(
            "Flags mutuamente exclusivas: use --export OU --ingest, não ambas.",
            param_hint="'--export'/'--ingest'",
        )

    # ------------------------------------------------------------------ M4 export
    if export_path is not None:
        try:
            _run_export_annotate(
                config=config,
                run_id=run_id,
                export_path=export_path,
                threshold=threshold,
                max_items=max_items,
                sort_by=sort_by,
            )
        except KeyboardInterrupt:
            _log.info("export_annotate_interrupted", run_id=run_id)
            _err_console.print("\n[yellow]Interrupted.[/yellow]")
            raise typer.Exit(130) from None
        return

    # ------------------------------------------------------------------ M4 ingest
    if ingest_path is not None:
        try:
            _run_ingest_annotate(
                config=config,
                run_id=run_id,
                ingest_path=ingest_path,
                force=force,
            )
        except KeyboardInterrupt:
            _log.info("ingest_annotate_interrupted", run_id=run_id)
            _err_console.print("\n[yellow]Interrupted.[/yellow]")
            raise typer.Exit(130) from None
        return

    # ------------------------------------------------------------------ M3 mode
    if data_dir is None:
        _err_console.print(
            "[red]--data-dir é obrigatório no modo interativo/CSV (M3).[/red]"
        )
        raise typer.Exit(1)

    from inteligenciomica_eval.application.use_cases.annotation_workflow import (
        AnnotationConfig,
        AnnotationWorkflowUseCase,
    )
    from inteligenciomica_eval.domain.errors import ConfigValidationError
    from inteligenciomica_eval.infrastructure.config.schema import load_round_config
    from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
        ParquetStorage,
    )

    try:
        cfg = load_round_config(config)
    except FileNotFoundError as exc:
        _err_console.print(f"[red]File not found:[/red] {exc}")
        raise typer.Exit(1) from exc
    except ConfigValidationError as exc:
        _err_console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(1) from exc

    annotation_cfg = AnnotationConfig(
        round_id=cfg.round_id,
        score_threshold=score_threshold,
        rubric_threshold=rubric_threshold,
        max_to_review=max_to_review,
    )

    storage = ParquetStorage(base_dir=data_dir, run_id=run_id, round_id=cfg.round_id)
    uc = AnnotationWorkflowUseCase(
        reader=storage, writer=storage, config=annotation_cfg
    )

    if csv_path is not None:
        _run_batch_annotate(uc, run_id=run_id, csv_path=csv_path)
    else:
        _run_interactive_annotate(uc, run_id=run_id)


def _run_export_annotate(
    *,
    config: Path,
    run_id: str,
    export_path: Path,
    threshold: float,
    max_items: int | None,
    sort_by: str,
) -> None:
    """Export prioritized evaluation results to a JSONL file for offline review.

    Reads all EvaluationResult for the round from Parquet via the annotation reader,
    filters by ``final_score < threshold OR NaN``, sorts according to ``sort_by``,
    applies ``max_items``, serialises each result as a JSON line, and writes to
    ``export_path``.  The parent directory is created if it does not exist.

    Args:
        config: path to the round config YAML (derives round_id and data_dir).
        run_id: run identifier (used for logging and summary display).
        export_path: destination JSONL file path.
        threshold: score cut-off — items below this value (or NaN) are exported.
        max_items: maximum number of exported items; ``None`` = no limit.
        sort_by: ordering for exported items — ``"finalscore"`` (asc, NaN first),
            ``"rubric"`` (asc, NaN first), or ``"random"`` (seed=42).
    """
    from inteligenciomica_eval.domain.errors import ConfigValidationError
    from inteligenciomica_eval.infrastructure.config.schema import load_round_config
    from inteligenciomica_eval.infrastructure.factories import build_annotation_reader

    _valid_sort_by = {"finalscore", "rubric", "random"}
    if sort_by not in _valid_sort_by:
        _err_console.print(
            f"[red]--sort-by inválido:[/red] {sort_by!r}. "
            "Escolha: finalscore | rubric | random."
        )
        raise typer.Exit(1)

    try:
        cfg = load_round_config(config)
    except FileNotFoundError as exc:
        _err_console.print(f"[red]File not found:[/red] {exc}")
        raise typer.Exit(1) from exc
    except ConfigValidationError as exc:
        _err_console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(1) from exc

    from inteligenciomica_eval.domain.errors import StorageError

    try:
        reader = build_annotation_reader(config)
        frame = reader.load(round_id=cfg.round_id, phase=None, run_id=run_id)
    except StorageError as exc:
        _err_console.print(f"[red]Storage error:[/red] {exc}")
        raise typer.Exit(1) from exc

    total = len(frame.results)

    # Stratify: final_score < threshold OR NaN
    candidates = [
        r
        for r in frame.results
        if math.isnan(r.final_score.value) or r.final_score.value < threshold
    ]

    # Sort
    if sort_by == "finalscore":
        candidates.sort(
            key=lambda r: (
                (0, 0.0)
                if math.isnan(r.final_score.value)
                else (1, float(r.final_score.value))
            )
        )
    elif sort_by == "rubric":
        candidates.sort(
            key=lambda r: (
                (0, 0.0)
                if math.isnan(r.metrics.rubric_biomed_score)
                else (1, float(r.metrics.rubric_biomed_score))
            )
        )
    else:  # random
        rng = random.Random(42)
        rng.shuffle(candidates)

    # Apply max_items limit
    if max_items is not None:
        candidates = candidates[:max_items]

    # Serialise to JSONL — NaN → null (JSON-compliant, §5.3 convention)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for r in candidates:
        fs = r.final_score.value
        rb = r.metrics.rubric_biomed_score
        entry: dict[str, object] = {
            "row_id": r.answer.row_id.value,
            "question_id": r.answer.question.question_id,
            "question": r.answer.question.text,
            "generated_answer": r.answer.generated_answer,
            "ground_truth": r.answer.question.ground_truth,
            "final_score": None if math.isnan(fs) else round(float(fs), 6),
            "rubric_biomed_score": None if math.isnan(rb) else round(float(rb), 6),
            "rubric_feedback": "",
            "critical_failure_flag": None,
            "critical_failure_note": r.critical_failure_note or "",
        }
        lines.append(json.dumps(entry, ensure_ascii=False))

    export_path.write_text("\n".join(lines), encoding="utf-8")

    # Summary breakdown by final_score bucket (based on all results, not just exported)
    n_below_half = sum(
        1
        for r in frame.results
        if not math.isnan(r.final_score.value) and r.final_score.value < 0.5
    )
    n_half_to_07 = sum(
        1
        for r in frame.results
        if not math.isnan(r.final_score.value) and 0.5 <= r.final_score.value < 0.7
    )
    n_above_07 = sum(
        1
        for r in frame.results
        if not math.isnan(r.final_score.value) and r.final_score.value >= 0.7
    )

    from rich.panel import Panel

    _console.print(
        Panel(
            f"Run:             [bold]{run_id}[/bold]\n"
            f"Round:           [bold]{cfg.round_id}[/bold]\n"
            f"Total no Parquet:[bold]{total}[/bold]\n"
            f"Exportados:      [bold]{len(candidates)}[/bold]"
            f" (threshold={threshold})\n\n"
            f"[bold]Breakdown por final_score:[/bold]\n"
            f"  < 0.5 :  {n_below_half}\n"
            f"  0.5-0.7: {n_half_to_07}\n"
            f"  ≥ 0.7 :  {n_above_07}",
            title="annotate --export",
        )
    )
    _console.print(f"[green]Exportado para:[/green] {export_path}")


def _run_ingest_annotate(
    *,
    config: Path,
    run_id: str,
    ingest_path: Path,
    force: bool,
) -> None:
    """Ingere anotações humanas de um JSONL para o Parquet (TAREFA-402, ADR-010).

    Args:
        config: caminho para o YAML de configuração da rodada.
        run_id: identificador do run.
        ingest_path: caminho do JSONL editado pelo especialista.
        force: se ``True``, sobrescreve anotações já existentes.
    """
    from rich.table import Table

    from inteligenciomica_eval.application.use_cases.ingest_annotation import (
        IngestAnnotationInput,
        IngestHumanAnnotationUseCase,
    )
    from inteligenciomica_eval.domain.errors import ConfigValidationError, StorageError
    from inteligenciomica_eval.infrastructure.factories import build_annotation_writer

    if not ingest_path.exists():
        _err_console.print(f"[red]Arquivo não encontrado:[/red] {ingest_path}")
        raise typer.Exit(1)

    try:
        writer = build_annotation_writer(config, run_id=run_id)
    except FileNotFoundError as exc:
        _err_console.print(f"[red]Config não encontrado:[/red] {exc}")
        raise typer.Exit(1) from exc
    except ConfigValidationError as exc:
        _err_console.print(f"[red]Configuração inválida:[/red] {exc}")
        raise typer.Exit(1) from exc

    try:
        uc = IngestHumanAnnotationUseCase(writer=writer)
        result = uc.execute(
            IngestAnnotationInput(
                annotations_path=ingest_path,
                run_id=run_id,
                force=force,
            )
        )
    except StorageError as exc:
        _err_console.print(f"[red]Storage error:[/red] {exc}")
        raise typer.Exit(1) from exc

    table = Table(title="annotate --ingest")
    table.add_column("Categoria", style="bold")
    table.add_column("Contagem", justify="right")
    table.add_row("[green]Ingeridas[/green]", str(result.n_ingested))
    table.add_row("[yellow]Puladas (já anotadas)[/yellow]", str(result.n_skipped))
    table.add_row("[red]Inválidas (flag ∉ {0,1,null})[/red]", str(result.n_invalid))
    table.add_row("[red]row_id não encontrado[/red]", str(result.n_missing_row_id))
    _console.print(table)


def _run_batch_annotate(
    uc: AnnotationWorkflowUseCase,
    *,
    run_id: str,
    csv_path: Path,
) -> None:
    """Processa anotações em lote a partir de um arquivo CSV."""
    from inteligenciomica_eval.domain.errors import StorageError

    try:
        csv_content = csv_path.read_text(encoding="utf-8")
        summary = uc.batch_annotate_from_csv(csv_content)
    except (FileNotFoundError, StorageError) as exc:
        _err_console.print(f"[red]CSV error:[/red] {exc}")
        raise typer.Exit(1) from exc

    _console.print(
        f"\n[green]Batch annotation complete[/green] — "
        f"{summary.n_annotated} annotated, {summary.n_errors} errors."
    )


def _run_interactive_annotate(
    uc: AnnotationWorkflowUseCase,
    *,
    run_id: str,
) -> None:
    """Loop interativo de anotação com Rich."""
    import math

    from rich.panel import Panel
    from rich.table import Table

    from inteligenciomica_eval.domain.errors import StorageError

    queue = uc.get_review_queue(run_id=run_id)
    if not queue:
        _console.print("[green]Review queue is empty — nothing to annotate.[/green]")
        return

    _console.print(f"\n[bold]Review queue:[/bold] {len(queue)} items\n")
    table = Table()
    table.add_column("question_id")
    table.add_column("llm")
    table.add_column("base")
    table.add_column("seed", justify="right")
    table.add_column("final_score", justify="right")
    table.add_column("rubric_score", justify="right")
    table.add_column("answer (first 200 chars)")
    for r in queue:
        ans = r.answer
        fs = r.final_score.value
        rb = r.metrics.rubric_biomed_score
        table.add_row(
            ans.question.question_id,
            ans.llm.value,
            ans.base.value,
            str(ans.seed.value),
            "NaN" if math.isnan(fs) else f"{fs:.3f}",
            "NaN" if math.isnan(rb) else f"{rb:.3f}",
            ans.generated_answer[:200],
        )
    _console.print(table)

    n_annotated = 0
    n_skipped = 0
    for item in queue:
        ans = item.answer
        _console.print(
            Panel(
                f"[bold]Question:[/bold] {ans.question.text}\n\n"
                f"[bold]Answer:[/bold] {ans.generated_answer}\n\n"
                f"[dim]Ground truth:[/dim] {ans.question.ground_truth}",
                title=f"{ans.question.question_id} | {ans.llm.value} | seed={ans.seed.value}",
            )
        )
        raw = (
            typer.prompt(
                "[0] No critical error / [1] Critical biomedical error / [s] Skip / [q] Quit",
                default="s",
            )
            .strip()
            .lower()
        )
        if raw == "q":
            break
        if raw == "s":
            n_skipped += 1
            continue
        if raw not in ("0", "1"):
            _err_console.print("[yellow]Unknown option — skipping.[/yellow]")
            n_skipped += 1
            continue
        flag = int(raw)
        note = ""
        if flag == 1:
            note = typer.prompt("Note (optional — press Enter to skip)", default="")
        try:
            uc.annotate(row_id=ans.row_id, flag=flag, note=note)
            n_annotated += 1
            _console.print(
                f"[green]✓ Annotated as {'critical' if flag == 1 else 'ok'}[/green]"
            )
        except StorageError as exc:
            _err_console.print(f"[red]Storage error:[/red] {exc}")

    n_pending = len(queue) - n_annotated - n_skipped
    _console.print(
        f"\n[bold]Session summary:[/bold] "
        f"{n_annotated} annotated, {n_skipped} skipped, {n_pending} pending."
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
