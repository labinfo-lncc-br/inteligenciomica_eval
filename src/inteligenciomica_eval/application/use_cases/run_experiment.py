"""RunExperimentUseCase — Orquestrador top-level do ciclo completo A+B (ADR-004).

Ordena e executa as 3 passadas: geração (por onda de modelo) → métricas → juiz →
agregação. Graceful shutdown via flag ``_shutdown_requested`` (RNF7): SIGTERM/SIGINT
sinaliza a flag; o loop de ondas completa a onda corrente e para; servidores ativos
são encerrados em bloco ``finally``.

Desvios conscientes em relação à spec (TAREFA-307):
1. ``config: ExperimentConfigView`` (Protocol local, ADR-001) em vez de ``RoundConfig``
   (Pydantic/infrastructure) — import-linter Contract 2/4 proíbe infrastructure na
   camada application. ``ExperimentConfigView`` é satisfeito estruturalmente pelo
   ``RoundConfig`` + campos extras montados pelo wiring (TAREFA-309).
2. ``execute`` recebe ``questions: Sequence[Question]`` explicitamente — não há port de
   dataset na arquitetura; o orquestrador (TAREFA-309) carrega as perguntas do benchmark
   e as passa como argumento (mesmo padrão de ``RunGenerationPassUseCase``, TAREFA-304).
3. ``retriever: RetrieverPort`` injetado no ``__init__`` para construir
   ``canonical_contexts`` do Experimento B antes da Passada 1 (spec §1b —
   "retriever injetado").
4. ``generator_factory: GeneratorFactory`` injetado para criar um ``GeneratorPort``
   por onda apontando para o servidor ativo. ``gen_pass_uc._generator`` é substituído
   via atribuição direta antes de cada onda — única forma de trocar o gerador sem
   criar nova instância de ``RunGenerationPassUseCase`` por onda nem expor todos os
   seus sub-componentes no construtor de ``RunExperimentUseCase``.
"""

from __future__ import annotations

import asyncio
import signal
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

import structlog

from inteligenciomica_eval.application.services.wave_scheduler import (
    Wave,
    WavePlan,
    WaveSchedulerService,
)
from inteligenciomica_eval.application.use_cases.run_generation_pass import (
    RunGenerationPassUseCase,
)
from inteligenciomica_eval.application.use_cases.run_judge_pass import (
    JudgePassReport,
    RunJudgePassUseCase,
)
from inteligenciomica_eval.application.use_cases.run_metrics_pass import (
    RunMetricsPassUseCase,
)
from inteligenciomica_eval.domain.entities import Question
from inteligenciomica_eval.domain.errors import ServerStartTimeoutError
from inteligenciomica_eval.domain.ports import (
    Chunk,
    GeneratorFactory,
    ModelSpec,
    ResultReaderPort,
    ResultWriterPort,
    RetrieverPort,
    ServerHandle,
    VLLMServerManagerPort,
)
from inteligenciomica_eval.domain.services.aggregation import (
    AggregationService,
    ConfigAggregate,
)
from inteligenciomica_eval.domain.services.rank_score import (
    RankScoreCalculator,
    RankScoreInputs,
)
from inteligenciomica_eval.domain.value_objects import BaseId, ModelWaveSpec, RankScore

_log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Vista estrutural da configuração (ADR-001 — application NÃO importa infrastructure)
# ---------------------------------------------------------------------------


class ExperimentConfigView(Protocol):
    """Vista estrutural mínima da configuração de rodada para RunExperimentUseCase.

    Satisfeita estruturalmente por um adaptador do ``RoundConfig`` + campos extras
    montados pelo wiring (TAREFA-309). A camada ``application`` NÃO importa
    ``RoundConfig`` (Pydantic/infrastructure — import-linter Contract 2/4); depende
    desta abstração por duck-typing (ADR-001, inversão de dependência).

    Campos de proveniência (TAREFA-311, ADR-014):
    - ``server_mode``: ``"managed"`` ou ``"external"``.
    - ``config_hash``: SHA-256 canônico da config (primeiros 8 hex).
    - ``endpoints_provenance``: dict com dados de proveniência por endpoint.
    """

    phases: list[str]
    bases: list[str]
    seeds: list[int]
    llms: list[str]
    temperature: float
    round_id: str
    startup_timeout_s: int
    failure_threshold: float
    top_k: int
    canonical_context_base: str
    canonical_top_k: int
    model_registry: tuple[ModelWaveSpec, ...]
    model_spec_map: dict[str, ModelSpec]
    server_mode: str
    config_hash: str
    endpoints_provenance: dict[str, object]


# ---------------------------------------------------------------------------
# ExperimentReport — saída do orquestrador
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExperimentReport:
    """Relatório consolidado de uma execução completa A+B (ADR-004, §14.6).

    Args:
        run_id: identificador da rodada.
        config_hash: primeiros 8 hex do SHA-256 canônico da config (proveniência).
        wave_plan: plano de ondas calculado antes da execução.
        n_generated: total de linhas geradas com sucesso pela Passada 1.
        n_evaluated: total de linhas avaliadas pelo RAGAS na Passada 2.
        n_judged: total de linhas julgadas pela rubrica biomédica na Passada 3.
        n_cells_total: total de células planejadas (``wave_plan.total_cells``).
        aggregates: tupla de :class:`~inteligenciomica_eval.domain.services.aggregation.ConfigAggregate`
            por configuração ``{base, llm}``, ordenada por ``(base, llm)``.
        rank_scores: tupla de :class:`~inteligenciomica_eval.domain.value_objects.RankScore`
            na mesma ordem de ``aggregates``.
        duration_s: duração total do experimento em segundos (wall clock).
        failed_waves: índices de ondas onde ``ServerStartTimeoutError`` ocorreu.
    """

    run_id: str
    config_hash: str
    wave_plan: WavePlan
    n_generated: int
    n_evaluated: int
    n_judged: int
    n_cells_total: int
    aggregates: tuple[ConfigAggregate, ...]
    rank_scores: tuple[RankScore, ...]
    duration_s: float
    failed_waves: tuple[int, ...]
    endpoints_provenance: dict[str, object]


# ---------------------------------------------------------------------------
# RunExperimentUseCase
# ---------------------------------------------------------------------------


class RunExperimentUseCase:
    """Orquestrador top-level do ciclo de avaliação A+B (ADR-004, §3.4).

    Executa as 3 passadas em ordem: geração (por onda de modelo) → métricas → juiz →
    agrega resultados e computa ranking. Suporta graceful shutdown (RNF7) via flag
    ``_shutdown_requested`` sinalizada por SIGTERM/SIGINT.

    Args:
        wave_scheduler: serviço de planejamento de ondas por GPU (ADR-012).
        server_manager: port de ciclo de vida dos servidores vLLM.
        gen_pass_uc: use case de geração (Passada 1); ``_generator`` é substituído
            por onda via atribuição direta com o adapter apontando para o servidor ativo.
        metrics_pass_uc: use case de métricas RAGAS (Passada 2).
        judge_pass_uc: use case de rubrica biomédica (Passada 3).
        aggregation_service: serviço de domínio para agregação cross-config.
        rank_calc: calculadora de RankScore (§7.3).
        writer: port de persistência de resultados (mantido por DI uniforme).
        reader: port de leitura de resultados.
        config: vista estrutural da configuração de rodada.
        retriever: port de retrieval vetorial; usado para construir
            ``canonical_contexts`` do Experimento B antes da Passada 1.
        generator_factory: factory que instancia :class:`~inteligenciomica_eval.domain.ports.GeneratorPort`
            por URL de servidor (Nota M3 item 5).
    """

    def __init__(
        self,
        *,
        wave_scheduler: WaveSchedulerService,
        server_manager: VLLMServerManagerPort,
        gen_pass_uc: RunGenerationPassUseCase,
        metrics_pass_uc: RunMetricsPassUseCase,
        judge_pass_uc: RunJudgePassUseCase,
        aggregation_service: AggregationService,
        rank_calc: RankScoreCalculator,
        writer: ResultWriterPort,
        reader: ResultReaderPort,
        config: ExperimentConfigView,
        retriever: RetrieverPort,
        generator_factory: GeneratorFactory,
    ) -> None:
        self._wave_scheduler = wave_scheduler
        self._server_manager = server_manager
        self._gen_pass_uc = gen_pass_uc
        self._metrics_pass_uc = metrics_pass_uc
        self._judge_pass_uc = judge_pass_uc
        self._aggregation_service = aggregation_service
        self._rank_calc = rank_calc
        self._writer = writer
        self._reader = reader
        self._config = config
        self._retriever = retriever
        self._generator_factory = generator_factory
        self._shutdown_requested = False

    async def execute(
        self,
        *,
        run_id: str,
        questions: Sequence[Question],
        progress_callback: Callable[[str], None] | None = None,
    ) -> ExperimentReport:
        """Executa o ciclo completo de avaliação A+B.

        Fluxo: plano de ondas → canonical_contexts (Exp. B) → Passada 1 por onda →
        Passada 2 → Passada 3 (juiz) → agregação. O ``_shutdown_requested`` interrompe
        o loop de ondas entre iterações: a onda corrente é completada; servidores
        ativos são encerrados em ``finally`` antes de sair.

        Args:
            run_id: identificador da rodada (proveniência, ADR-009).
            questions: perguntas do benchmark (RF1: 13 perguntas curadas).
            progress_callback: callback opcional invocado com mensagens de progresso.

        Returns:
            :class:`ExperimentReport` com totais, aggregates e rank_scores.
            Se shutdown solicitado antes da conclusão, ``n_evaluated`` e ``n_judged``
            são 0 e ``aggregates``/``rank_scores`` são tuplas vazias.
        """
        t_start = time.monotonic()
        self._shutdown_requested = False
        _handlers_registered = self._register_signals()
        try:
            return await self._run(
                run_id=run_id,
                questions=questions,
                progress_callback=progress_callback,
                t_start=t_start,
            )
        finally:
            if _handlers_registered:
                self._unregister_signals()

    # ------------------------------------------------------------------
    # Implementação principal
    # ------------------------------------------------------------------

    async def _run(
        self,
        *,
        run_id: str,
        questions: Sequence[Question],
        progress_callback: Callable[[str], None] | None,
        t_start: float,
    ) -> ExperimentReport:
        config_hash = self._config.config_hash[:8]

        # 1a. Plano de ondas.
        wave_plan = self._wave_scheduler.plan(self._config.model_registry, self._config)
        _log.info(
            "experiment_started",
            run_id=run_id,
            round_id=self._config.round_id,
            config_hash=config_hash,
            n_waves=len(wave_plan.waves),
            total_cells=wave_plan.total_cells,
        )
        _notify(progress_callback, "experiment_started")

        # 1b. Canonical contexts para Experimento B (antes da Passada 1).
        canonical_contexts: dict[str, list[Chunk]] | None = None
        if "B" in self._config.phases:
            canonical_contexts = await self._build_canonical_contexts(questions)
            _notify(progress_callback, "canonical_contexts_built")

        # 2. Passada de geração — um servidor por modelo, sequencial.
        n_generated = 0
        failed_wave_set: set[int] = set()
        active_handle: ServerHandle | None = None

        try:
            for wave in wave_plan.waves:
                if self._shutdown_requested:
                    _log.info(
                        "shutdown_between_waves",
                        run_id=run_id,
                        next_wave_index=wave.wave_index,
                    )
                    break

                for model_name in wave.models:
                    model_spec = self._config.model_spec_map[model_name]
                    try:
                        active_handle = await self._server_manager.start(model_spec)
                        await self._server_manager.wait_healthy(
                            active_handle, self._config.startup_timeout_s
                        )
                    except ServerStartTimeoutError:
                        _log.error(
                            "generator_start_timeout",
                            run_id=run_id,
                            wave_index=wave.wave_index,
                            model=model_name,
                        )
                        failed_wave_set.add(wave.wave_index)
                        active_handle = None
                        continue

                    try:
                        # Injetar gerador apontando para o servidor ativo (desvio 4).
                        self._gen_pass_uc._generator = self._generator_factory(
                            active_handle.url
                        )
                        single_plan = _single_model_wave_plan(
                            wave, model_name, model_spec.gpu_index
                        )
                        gen_report = await self._gen_pass_uc.execute(
                            run_id=run_id,
                            wave_plan=single_plan,
                            questions=questions,
                            canonical_contexts=canonical_contexts,
                        )
                        n_generated += gen_report.n_generated
                        _log.info(
                            "generation_model_done",
                            run_id=run_id,
                            wave_index=wave.wave_index,
                            model=model_name,
                            n_generated=gen_report.n_generated,
                        )
                        _notify(progress_callback, f"generation:{model_name}")
                    except KeyboardInterrupt:
                        # RNF7: SIGINT durante geração → shutdown gracioso (sem propagação).
                        self._shutdown_requested = True
                        _log.warning(
                            "generation_interrupted_by_signal",
                            run_id=run_id,
                            wave_index=wave.wave_index,
                            model=model_name,
                        )
                    finally:
                        await self._server_manager.stop(active_handle)
                        active_handle = None

                    if self._shutdown_requested:
                        break

        finally:
            # Limpeza de servidor ativo em saídas inesperadas (exceção, SIGKILL).
            if active_handle is not None:
                await self._server_manager.stop(active_handle)
                active_handle = None

        # Shutdown solicitado durante geração: devolver relatório parcial.
        if self._shutdown_requested:
            duration_s = time.monotonic() - t_start
            _log.warning(
                "experiment_aborted_on_shutdown",
                run_id=run_id,
                n_generated=n_generated,
                n_failed_waves=len(failed_wave_set),
                duration_s=round(duration_s, 3),
            )
            return ExperimentReport(
                run_id=run_id,
                config_hash=config_hash,
                wave_plan=wave_plan,
                n_generated=n_generated,
                n_evaluated=0,
                n_judged=0,
                n_cells_total=wave_plan.total_cells,
                aggregates=(),
                rank_scores=(),
                duration_s=duration_s,
                failed_waves=tuple(sorted(failed_wave_set)),
                endpoints_provenance=dict(self._config.endpoints_provenance),
            )

        # 3. Passada de métricas (única, após toda geração).
        _log.info("metrics_pass_started", run_id=run_id)
        _notify(progress_callback, "metrics_pass_started")
        metrics_report = await self._metrics_pass_uc.execute(
            run_id=run_id, round_id=self._config.round_id
        )
        _log.info(
            "metrics_pass_done",
            run_id=run_id,
            n_evaluated=metrics_report.n_evaluated,
        )
        _notify(progress_callback, "metrics_pass_done")

        # 4. Passada do juiz — servidor dedicado, após toda geração.
        judge_report = await self._run_judge_pass(
            run_id=run_id, progress_callback=progress_callback
        )

        # 5. Agregação final.
        _log.info("aggregation_started", run_id=run_id)
        frame = self._reader.load(round_id=self._config.round_id)
        aggregates = self._aggregation_service.aggregate_all(
            list(frame.results), threshold=self._config.failure_threshold
        )
        rank_scores = tuple(
            self._rank_calc.compute(
                RankScoreInputs(
                    median_score=agg.median_score,
                    failure_rate=agg.failure_rate,
                    win_rate=agg.win_rate,
                    critical_failure_rate=agg.critical_failure_rate,
                )
            )
            for agg in aggregates
        )

        duration_s = time.monotonic() - t_start
        _log.info(
            "experiment_completed",
            run_id=run_id,
            duration_s=round(duration_s, 3),
            n_generated=n_generated,
            n_evaluated=metrics_report.n_evaluated,
            n_judged=judge_report.n_judged,
            n_configs=len(aggregates),
            n_failed_waves=len(failed_wave_set),
        )
        _notify(progress_callback, "experiment_completed")

        return ExperimentReport(
            run_id=run_id,
            config_hash=config_hash,
            wave_plan=wave_plan,
            n_generated=n_generated,
            n_evaluated=metrics_report.n_evaluated,
            n_judged=judge_report.n_judged,
            n_cells_total=wave_plan.total_cells,
            aggregates=aggregates,
            rank_scores=rank_scores,
            duration_s=duration_s,
            failed_waves=tuple(sorted(failed_wave_set)),
            endpoints_provenance=dict(self._config.endpoints_provenance),
        )

    async def _run_judge_pass(
        self,
        *,
        run_id: str,
        progress_callback: Callable[[str], None] | None,
    ) -> JudgePassReport:
        """Inicia servidor juiz, executa a Passada 3 e para o servidor (ADR-003)."""
        judge_spec = self._find_judge_spec()
        _log.info(
            "judge_pass_started",
            run_id=run_id,
            judge_model=judge_spec.model,
        )
        _notify(progress_callback, "judge_pass_started")

        judge_handle = await self._server_manager.start(judge_spec)
        await self._server_manager.wait_healthy(
            judge_handle, self._config.startup_timeout_s
        )
        try:
            judge_report = await self._judge_pass_uc.execute(
                run_id=run_id, round_id=self._config.round_id
            )
        finally:
            await self._server_manager.stop(judge_handle)

        _log.info(
            "judge_pass_done",
            run_id=run_id,
            n_judged=judge_report.n_judged,
        )
        _notify(progress_callback, "judge_pass_done")
        return judge_report

    def _find_judge_spec(self) -> ModelSpec:
        """Localiza o ModelSpec do juiz pelo flag ``is_judge`` no model_registry."""
        for wave_spec in self._config.model_registry:
            if wave_spec.is_judge:
                judge_name = wave_spec.name
                if judge_name not in self._config.model_spec_map:
                    raise RuntimeError(
                        f"Judge model '{judge_name}' not found in model_spec_map. "
                        "Wiring error: model_spec_map must include all models in "
                        "model_registry (generators + judge)."
                    )
                return self._config.model_spec_map[judge_name]
        raise RuntimeError(
            "No judge model found in model_registry (is_judge=True). "
            "Wiring error: registry must include the Prometheus judge model."
        )

    async def _build_canonical_contexts(
        self,
        questions: Sequence[Question],
    ) -> dict[str, list[Chunk]]:
        """Constrói canonical_contexts para o Experimento B via retriever injetado."""
        result: dict[str, list[Chunk]] = {}
        base = BaseId(self._config.canonical_context_base)
        for question in questions:
            retrieval = await self._retriever.search(
                base=base,
                question=question.text,
                top_k=self._config.canonical_top_k,
            )
            result[question.question_id] = list(retrieval.chunks)
        _log.info(
            "canonical_contexts_built",
            n_questions=len(result),
            base=self._config.canonical_context_base,
            top_k=self._config.canonical_top_k,
        )
        return result

    def _register_signals(self) -> bool:
        """Registra handlers SIGTERM/SIGINT para graceful shutdown (RNF7).

        Returns:
            ``True`` se registrado com sucesso; ``False`` se fora da main thread
            ou se o loop não suportar sinais (ex.: Windows, threads secondárias).
        """
        try:
            loop = asyncio.get_running_loop()

            def _on_sigterm() -> None:
                self._shutdown_requested = True
                _log.warning(
                    "sigterm_received",
                    action="graceful_shutdown_requested",
                )

            def _on_sigint() -> None:
                self._shutdown_requested = True
                _log.warning(
                    "sigint_received",
                    action="graceful_shutdown_requested",
                )

            loop.add_signal_handler(signal.SIGTERM, _on_sigterm)
            loop.add_signal_handler(signal.SIGINT, _on_sigint)
            return True
        except (ValueError, NotImplementedError, OSError):
            return False

    def _unregister_signals(self) -> None:
        """Remove os handlers de sinal registrados pelo execute."""
        try:
            loop = asyncio.get_running_loop()
            loop.remove_signal_handler(signal.SIGTERM)
            loop.remove_signal_handler(signal.SIGINT)
        except (ValueError, NotImplementedError, OSError):
            pass


# ---------------------------------------------------------------------------
# Helpers de módulo
# ---------------------------------------------------------------------------


def _single_model_wave_plan(
    wave: Wave,
    model_name: str,
    gpu_index: int,
) -> WavePlan:
    """Cria WavePlan com um único modelo para a onda especificada.

    Usado para passar ao ``RunGenerationPassUseCase.execute`` apenas o modelo
    cujo servidor está ativo nesta iteração — evita que o use case tente processar
    modelos de outras ondas com o mesmo servidor.

    Args:
        wave: onda original (wave_index preservado para logging).
        model_name: nome do modelo a incluir no plano.
        gpu_index: GPU atribuída ao modelo (ADR-012).

    Returns:
        :class:`WavePlan` com uma única :class:`Wave` e um único modelo.
    """
    single = Wave(
        wave_index=wave.wave_index,
        models=(model_name,),
        gpu_indices=(gpu_index,),
        vram_required_gb=0.0,
        cells_in_wave=0,
    )
    return WavePlan(waves=(single,), total_cells=0, estimated_vram_peak_gb=0.0)


def _notify(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        callback(message)
