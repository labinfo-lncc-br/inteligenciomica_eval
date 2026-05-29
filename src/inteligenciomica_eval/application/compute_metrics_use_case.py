"""ComputeMetricsUseCase — passada de julgamento (§5.4, camada application).

Orquestra a "passada 2" do fluxo §3.4: lê as linhas geradas (passada 1), avalia
cada uma pelas Camadas 1 (RAGAS), 1-aux (BERTScore/ROUGE) e 2 (rubrica biomédica),
agrega o ``FinalScore`` e persiste o resultado de forma idempotente (ADR-009).

Padrão clean-architecture (python-clean-architecture §2): o use case **orquestra
ports** injetados por DI, **não** duplica lógica de domínio (o cálculo do score é do
:class:`FinalScoreCalculator`) e **não** importa ``infrastructure`` — apenas
``domain`` (entidades, ports, serviços, value objects) e ``structlog``.

Contratos canônicos dos ports (Nota M2 item 1):

* ``metric_suite.score(sample) -> Layer1Metrics`` — **async** (rede ao vllm-judge).
* ``rubric_judge.score(sample) -> RubricResult`` — **async** (rede ao vllm-judge).
* ``aux_metrics.score(*, answer, ground_truth) -> AuxMetrics`` — **síncrono** (CPU).

``metric_suite`` e ``rubric_judge`` chegam **já envolvidos** pelo
``RetryableMetricAdapter`` (TAREFA-027, Nota M2 item 4): falha total de I/O vira
NaN-sentinel após esgotar o retry, nunca propaga ``MetricComputationError`` aqui.
``aux_metrics`` é determinístico e não usa decorator de retry.

Idempotência (ADR-009): no domínio ``FinalScore`` nunca é ``None`` — a ausência de
score ("ainda não computado", Parquet NULL) é representada por ``NaN`` (ponte
NULL⟷NaN do ``ParquetStorage``). Portanto uma linha é processada quando
``force=True`` **ou** ``math.isnan(final_score.value)``; linhas com score real são
puladas. Uma linha que resultou em NaN-sentinel (ADR-007) será reprocessada num run
futuro — é "incompleta", não "concluída".

Concorrência: **M2 é serial** — uma linha por vez (``await`` sequencial), em ordem
determinística por ``row_id``. O paralelismo via ``asyncio.gather`` é deliberadamente
adiado para M3; **não** antecipar aqui.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import structlog

from inteligenciomica_eval.domain.entities import EvaluationResult
from inteligenciomica_eval.domain.ports import (
    DeterministicMetricPort,
    EvaluationSample,
    MetricSuitePort,
    ResultReaderPort,
    ResultWriterPort,
    RubricJudgePort,
)
from inteligenciomica_eval.domain.services.final_score import FinalScoreCalculator
from inteligenciomica_eval.domain.value_objects import DeterminismRegime, MetricVector

_log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ComputeMetricsInput:
    """Entrada do :class:`ComputeMetricsUseCase`.

    Args:
        run_id: identificador do run de avaliação (proveniência/log).
        round_id: rodada a carregar do armazenamento.
        phase: fase do experimento (``"A"``/``"B"``); ``None`` = todas as fases.
        force: reprocessa linhas com ``final_score`` já preenchido (não-NaN).
    """

    run_id: str
    round_id: str
    phase: str | None = None
    force: bool = False


@dataclass(frozen=True)
class ComputeMetricsReport:
    """Sumário do resultado da passada de julgamento.

    Args:
        run_id: identificador do run processado.
        n_processed: linhas pontuadas com ``final_score`` não-NaN.
        n_skipped: linhas puladas por já terem ``final_score`` (idempotência).
        n_nan_excluded: linhas persistidas com ``final_score`` NaN (ADR-007).
        n_failed_terminal: linhas com exceção inesperada após o retry (bug de adapter).
        failed_row_ids: ``row_id`` (hex) das linhas com falha terminal.
    """

    run_id: str
    n_processed: int
    n_skipped: int
    n_nan_excluded: int
    n_failed_terminal: int
    failed_row_ids: tuple[str, ...]


@dataclass(frozen=True)
class ComputeMetricsConfig:
    """Configuração operacional do use case (frozen dataclass — sem Pydantic).

    Args:
        log_progress_every: emite um log de progresso a cada N linhas processadas.
        failure_threshold: fração de falhas terminais acima da qual o summary final
            emite WARNING (sanity check operacional; não aborta o loop).
    """

    log_progress_every: int = 10
    failure_threshold: float = 0.70


class ComputeMetricsUseCase:
    """Executa a passada de julgamento sobre uma rodada (§5.4).

    Args:
        reader: porta de leitura das linhas tidy (``ResultReaderPort``).
        writer: porta de escrita idempotente (``ResultWriterPort``).
        metric_suite: Camada 1 RAGAS — **já** com ``RetryableMetricAdapter``.
        rubric_judge: Camada 2 rubrica — **já** com ``RetryableMetricAdapter``.
        aux_metrics: Camada 1-aux determinística (BERTScore/ROUGE) — sem retry.
        score_calculator: serviço de domínio do ``FinalScore`` ponderado (§7.1).
        config: :class:`ComputeMetricsConfig`.
    """

    def __init__(
        self,
        *,
        reader: ResultReaderPort,
        writer: ResultWriterPort,
        metric_suite: MetricSuitePort,
        rubric_judge: RubricJudgePort,
        aux_metrics: DeterministicMetricPort,
        score_calculator: FinalScoreCalculator,
        config: ComputeMetricsConfig,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._metric_suite = metric_suite
        self._rubric_judge = rubric_judge
        self._aux_metrics = aux_metrics
        self._score_calculator = score_calculator
        self._config = config

    async def execute(self, inp: ComputeMetricsInput) -> ComputeMetricsReport:
        """Avalia e persiste as linhas pendentes de uma rodada (§5.4).

        Args:
            inp: parâmetros do run (rodada, fase, force).

        Returns:
            :class:`ComputeMetricsReport` com as contagens da passada.
        """
        frame = self._reader.load(round_id=inp.round_id, phase=inp.phase)

        to_process = [r for r in frame.results if self._needs_processing(r, inp.force)]
        n_skipped = len(frame.results) - len(to_process)
        # Ordem determinística (§5.4): processa por row_id crescente.
        to_process.sort(key=lambda r: r.answer.row_id.value)

        _log.info(
            "compute_metrics_started",
            run_id=inp.run_id,
            round_id=inp.round_id,
            phase=inp.phase,
            n_total=len(frame.results),
            n_to_process=len(to_process),
            n_skipped=n_skipped,
            force=inp.force,
        )

        n_processed = 0
        n_nan_excluded = 0
        failed_row_ids: list[str] = []

        for idx, result in enumerate(to_process, start=1):
            row_id_hex = result.answer.row_id.value
            try:
                final_score_is_nan = await self._score_and_persist(result)
            except Exception as exc:  # bug de adapter escapou do decorator de retry
                failed_row_ids.append(row_id_hex)
                _log.error(
                    "compute_metrics_row_failed",
                    run_id=inp.run_id,
                    row_id=row_id_hex[:12],
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                continue  # não aborta o run — segue para a próxima linha

            if final_score_is_nan:
                n_nan_excluded += 1
            else:
                n_processed += 1

            if idx % self._config.log_progress_every == 0:
                _log.info(
                    "compute_metrics_progress",
                    run_id=inp.run_id,
                    done=idx,
                    total=len(to_process),
                )

        report = ComputeMetricsReport(
            run_id=inp.run_id,
            n_processed=n_processed,
            n_skipped=n_skipped,
            n_nan_excluded=n_nan_excluded,
            n_failed_terminal=len(failed_row_ids),
            failed_row_ids=tuple(failed_row_ids),
        )
        self._log_summary(report, n_to_process=len(to_process))
        return report

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    @staticmethod
    def _needs_processing(result: EvaluationResult, force: bool) -> bool:
        """Decide se a linha deve ser (re)processada (ADR-009).

        ``force`` reprocessa sempre; caso contrário, processa apenas linhas sem
        ``final_score`` real (NaN = "ainda não computado", ponte NULL⟷NaN).
        """
        return force or math.isnan(result.final_score.value)

    async def _score_and_persist(self, result: EvaluationResult) -> bool:
        """Avalia uma linha pelas três camadas, agrega e persiste.

        Args:
            result: linha a avaliar.

        Returns:
            ``True`` se o ``final_score`` agregado é NaN (linha NaN-excluded).
        """
        answer = result.answer
        sample = EvaluationSample(
            question_id=answer.question.question_id,
            question=answer.question.text,
            ground_truth=answer.question.ground_truth,
            generated_answer=answer.generated_answer,
            contexts=answer.retrieved_chunks_text,
        )

        layer1 = await self._metric_suite.score(sample)
        rubric = await self._rubric_judge.score(sample)
        aux = self._aux_metrics.score(
            answer=answer.generated_answer,
            ground_truth=answer.question.ground_truth,
        )

        metrics = MetricVector(
            answer_correctness=layer1.answer_correctness,
            answer_similarity=layer1.answer_similarity,
            faithfulness=layer1.faithfulness,
            context_precision=layer1.context_precision,
            context_recall=layer1.context_recall,
            answer_relevancy=layer1.answer_relevancy,
            bertscore_f1=aux.bertscore_f1,
            rubric_biomed_score=rubric.score,
        )
        final_score = self._score_calculator.compute(metrics)

        # with_metrics fixa regime=JUDGE → batch_invariant=True (§4.3, TAREFA-022).
        updated = result.with_metrics(metrics, final_score, DeterminismRegime.JUDGE)
        self._writer.update_metrics(
            row_id=answer.row_id,
            metrics=updated.metrics,
            final_score=updated.final_score,
            regime=updated.determinism_regime,
        )

        nan_fields = metrics.nan_fields()
        is_nan = math.isnan(final_score.value)
        _log.info(
            "compute_metrics_row_done",
            row_id=answer.row_id.value[:12],
            question_id=answer.question.question_id,
            final_score_nan=is_nan,
            nan_fields=list(nan_fields),
        )
        return is_nan

    def _log_summary(self, report: ComputeMetricsReport, *, n_to_process: int) -> None:
        """Emite o log de summary final; WARNING se a taxa de falha terminal exceder."""
        failure_rate = report.n_failed_terminal / n_to_process if n_to_process else 0.0
        _log.info(
            "compute_metrics_finished",
            run_id=report.run_id,
            n_processed=report.n_processed,
            n_skipped=report.n_skipped,
            n_nan_excluded=report.n_nan_excluded,
            n_failed_terminal=report.n_failed_terminal,
        )
        if failure_rate > self._config.failure_threshold:
            _log.warning(
                "compute_metrics_high_failure_rate",
                run_id=report.run_id,
                failure_rate=failure_rate,
                threshold=self._config.failure_threshold,
            )
