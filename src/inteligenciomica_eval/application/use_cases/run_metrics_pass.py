"""RunMetricsPassUseCase — Passada 2 da arquitetura de 3 passadas (ADR-004).

Computa métricas RAGAS (Camada 1) e BERTScore para cada linha da Passada 1,
persistindo MetricVector + FinalScore via writer.update_metrics (ADR-009).

NaN-propagation (ADR-007): MetricComputationError após max_metric_retries tentativas
retorna MetricVector all-NaN + FinalScore(NaN) e persiste (linha excluída na
agregação por NaN). rubric_biomed_score permanece NaN — preenchido pela Passada 3
(RunJudgePassUseCase, TAREFA-306).

Desvio consciente em relação à spec (TAREFA-305):
``config: MetricsPassConfig`` (dataclass de aplicação) em vez de ``RoundConfig``
(infrastructure). A camada application NÃO pode importar infrastructure
(import-linter Contract 2/4). Os campos necessários — batch_size,
max_metric_retries, log_progress_every — não existem em RoundConfig; são
parâmetros de orquestração injetados pelo caller (TAREFA-309/310).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import structlog

from inteligenciomica_eval.domain.entities import EvaluationResult
from inteligenciomica_eval.domain.errors import MetricComputationError
from inteligenciomica_eval.domain.ports import (
    DeterministicMetricPort,
    EvaluationSample,
    Layer1Metrics,
    MetricSuitePort,
    ResultReaderPort,
    ResultWriterPort,
)
from inteligenciomica_eval.domain.services.final_score import FinalScoreCalculator
from inteligenciomica_eval.domain.value_objects import (
    DeterminismRegime,
    MetricVector,
)

_log = structlog.get_logger(__name__)

_NAN = float("nan")
_ALL_NAN_LAYER1 = Layer1Metrics(
    answer_correctness=_NAN,
    answer_similarity=_NAN,
    faithfulness=_NAN,
    context_precision=_NAN,
    context_recall=_NAN,
    answer_relevancy=_NAN,
)


@dataclass(frozen=True, slots=True)
class MetricsPassConfig:
    """Configuração da Passada 2 de métricas (ADR-004).

    Args:
        batch_size: tamanho do lote enviado ao MetricSuitePort via score_batch.
        max_metric_retries: tentativas máximas por lote em MetricComputationError
            antes de aceitar MetricVector all-NaN (ADR-007).
        log_progress_every: frequência de log de progresso (linhas avaliadas).
    """

    batch_size: int = 10
    max_metric_retries: int = 3
    log_progress_every: int = 10


@dataclass(frozen=True, slots=True)
class MetricsPassReport:
    """Relatório de execução da Passada 2 de métricas (ADR-004).

    Args:
        run_id: identificador da rodada.
        round_id: identificador do round no armazenamento.
        n_evaluated: linhas persistidas com FinalScore não-NaN.
        n_skipped: linhas puladas por idempotência (answer_correctness já não-NaN).
        n_skipped_missing_generation: linhas sem geração (generated_answer vazio).
        n_nan: linhas avaliadas cujo FinalScore ficou NaN (métrica NaN ou retries
            esgotados — ADR-007). rubric_biomed_score=NaN sempre nesta passada,
            logo n_nan == n_eligible quando score_calc usa rubric_biomed_score com
            peso > 0; o orquestrador deve injetar um score_calc compatível.
        n_errors: erros inesperados (não MetricComputationError).
        duration_s: duração total da passada em segundos.
    """

    run_id: str
    round_id: str
    n_evaluated: int
    n_skipped: int
    n_skipped_missing_generation: int
    n_nan: int
    n_errors: int
    duration_s: float


class RunMetricsPassUseCase:
    """Passada 2 da arquitetura de 3 passadas (ADR-004): computa e persiste métricas.

    Carrega linhas geradas pela Passada 1 via reader, computa métricas RAGAS e
    BERTScore em lotes, e persiste MetricVector + FinalScore via
    writer.update_metrics com regime GENERATOR.

    Args:
        metric_suite: port de métricas RAGAS (Camada 1) — async, usa score_batch.
        deterministic: port de métricas determinísticas (BERTScore) — síncrono.
        score_calc: serviço de domínio de FinalScore ponderado (TAREFA-006).
        writer: port de persistência (update_metrics para linhas existentes).
        reader: port de leitura (carrega linhas da Passada 1 por round_id).
        config: parâmetros da passada — batch_size, retries, progresso.
    """

    def __init__(
        self,
        *,
        metric_suite: MetricSuitePort,
        deterministic: DeterministicMetricPort,
        score_calc: FinalScoreCalculator,
        writer: ResultWriterPort,
        reader: ResultReaderPort,
        config: MetricsPassConfig | None = None,
    ) -> None:
        self._metric_suite = metric_suite
        self._deterministic = deterministic
        self._score_calc = score_calc
        self._writer = writer
        self._reader = reader
        self._config = config if config is not None else MetricsPassConfig()

    async def execute(
        self,
        *,
        run_id: str,
        round_id: str,
        phase: str | None = None,
    ) -> MetricsPassReport:
        """Executa a passada de métricas para todas as linhas elegíveis.

        Args:
            run_id: identificador da rodada (proveniência, logging).
            round_id: identificador do round no armazenamento (filtro reader).
            phase: fase do experimento (``"A"`` ou ``"B"``); ``None`` processa ambas.

        Returns:
            :class:`MetricsPassReport` com totais de avaliação, skips e erros.
        """
        t_start = time.monotonic()
        n_evaluated = 0
        n_skipped = 0
        n_skipped_missing_generation = 0
        n_nan = 0
        n_errors = 0
        evaluated_count = 0

        frame = self._reader.load(round_id=round_id, phase=phase)
        results = list(frame.results)

        eligible: list[EvaluationResult] = []
        for result in results:
            if not math.isnan(result.metrics.answer_correctness):
                n_skipped += 1
                continue
            if not result.answer.generated_answer:
                n_skipped_missing_generation += 1
                _log.warning(
                    "metrics_skipped_missing_generation",
                    run_id=run_id,
                    round_id=round_id,
                    row_id=result.answer.row_id.value,
                    question_id=result.answer.question.question_id,
                )
                continue
            eligible.append(result)

        _log.info(
            "metrics_pass_started",
            run_id=run_id,
            round_id=round_id,
            n_eligible=len(eligible),
            n_skipped=n_skipped,
            n_skipped_missing_generation=n_skipped_missing_generation,
        )

        batch_size = self._config.batch_size
        for i in range(0, len(eligible), batch_size):
            batch = eligible[i : i + batch_size]
            samples = [self._make_sample(r) for r in batch]
            layer1_list = await self._process_batch(samples)

            for result, layer1 in zip(batch, layer1_list, strict=False):
                try:
                    aux = self._deterministic.score(
                        answer=result.answer.generated_answer,
                        ground_truth=result.answer.question.ground_truth,
                    )
                    metric_vec = MetricVector(
                        answer_correctness=layer1.answer_correctness,
                        answer_similarity=layer1.answer_similarity,
                        faithfulness=layer1.faithfulness,
                        context_precision=layer1.context_precision,
                        context_recall=layer1.context_recall,
                        answer_relevancy=layer1.answer_relevancy,
                        bertscore_f1=aux.bertscore_f1,
                        rubric_biomed_score=_NAN,
                    )
                    final_score = self._score_calc.compute(metric_vec)
                    self._writer.update_metrics(
                        result.answer.row_id,
                        metrics=metric_vec,
                        final_score=final_score,
                        regime=DeterminismRegime.GENERATOR,
                    )
                    if math.isnan(final_score.value):
                        n_nan += 1
                    else:
                        n_evaluated += 1
                except Exception as exc:
                    n_errors += 1
                    _log.error(
                        "metrics_unexpected_error",
                        run_id=run_id,
                        round_id=round_id,
                        row_id=result.answer.row_id.value,
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )

                evaluated_count += 1
                if evaluated_count % self._config.log_progress_every == 0:
                    _log.info(
                        "metrics_progress",
                        run_id=run_id,
                        round_id=round_id,
                        evaluated_count=evaluated_count,
                        n_evaluated=n_evaluated,
                        n_nan=n_nan,
                        n_errors=n_errors,
                    )

        duration_s = time.monotonic() - t_start
        _log.info(
            "metrics_pass_completed",
            run_id=run_id,
            round_id=round_id,
            n_evaluated=n_evaluated,
            n_skipped=n_skipped,
            n_skipped_missing_generation=n_skipped_missing_generation,
            n_nan=n_nan,
            n_errors=n_errors,
            duration_s=round(duration_s, 3),
        )
        return MetricsPassReport(
            run_id=run_id,
            round_id=round_id,
            n_evaluated=n_evaluated,
            n_skipped=n_skipped,
            n_skipped_missing_generation=n_skipped_missing_generation,
            n_nan=n_nan,
            n_errors=n_errors,
            duration_s=duration_s,
        )

    @staticmethod
    def _make_sample(result: EvaluationResult) -> EvaluationSample:
        """Constrói EvaluationSample a partir de um EvaluationResult da Passada 1."""
        return EvaluationSample(
            question_id=result.answer.question.question_id,
            question=result.answer.question.text,
            ground_truth=result.answer.question.ground_truth,
            generated_answer=result.answer.generated_answer,
            contexts=result.answer.retrieved_chunks_text,
        )

    async def _process_batch(
        self,
        samples: list[EvaluationSample],
    ) -> list[Layer1Metrics]:
        """Chama score_batch com retry em MetricComputationError (ADR-007).

        Retenta o lote completo até max_metric_retries vezes; ao esgotar,
        retorna MetricVector all-NaN para cada amostra do lote (ADR-007:
        NaN é estado legítimo — não descarta a linha).

        Args:
            samples: amostras a avaliar em batch.

        Returns:
            Lista de :class:`Layer1Metrics` — all-NaN se retries esgotados.
        """
        for attempt in range(1, self._config.max_metric_retries + 1):
            try:
                return await self._metric_suite.score_batch(samples)
            except MetricComputationError as exc:
                is_last = attempt == self._config.max_metric_retries
                _log.warning(
                    "metric_batch_error",
                    attempt=attempt,
                    max_retries=self._config.max_metric_retries,
                    action="fail" if is_last else "retry",
                    batch_size=len(samples),
                    error=str(exc),
                )
                if is_last:
                    return [_ALL_NAN_LAYER1] * len(samples)
        return [_ALL_NAN_LAYER1] * len(samples)  # satisfaz o type-checker
