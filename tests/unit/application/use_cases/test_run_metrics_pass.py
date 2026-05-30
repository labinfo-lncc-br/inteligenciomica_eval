"""Testes unitários de RunMetricsPassUseCase (TAREFA-305, Passada 2 de métricas)."""

from __future__ import annotations

import math

import pytest
from factories import (
    make_evaluation_result,
    make_generated_answer,
    make_metric_vector,
)
from fakes.storage import (
    InMemoryResultReader,
    InMemoryResultStore,
    InMemoryResultWriter,
)

from inteligenciomica_eval.application.use_cases.run_metrics_pass import (
    MetricsPassConfig,
    MetricsPassReport,
    RunMetricsPassUseCase,
)
from inteligenciomica_eval.domain.errors import MetricComputationError
from inteligenciomica_eval.domain.ports import (
    AuxMetrics,
    EvaluationSample,
    Layer1Metrics,
)
from inteligenciomica_eval.domain.services.final_score import FinalScoreCalculator
from inteligenciomica_eval.domain.value_objects import DeterminismRegime

_NAN = float("nan")

# Pesos sem rubric_biomed_score (peso 0) para que FinalScore possa ser não-NaN
# na Passada 2, onde rubric_biomed_score fica NaN até a Passada 3.
_TEST_WEIGHTS: dict[str, float] = {
    "answer_correctness": 0.50,
    "faithfulness": 0.20,
    "context_recall": 0.10,
    "context_precision": 0.10,
    "answer_relevancy": 0.05,
    "answer_similarity": 0.05,
    "bertscore_f1": 0.00,
    "rubric_biomed_score": 0.00,
}

_DEFAULT_LAYER1 = Layer1Metrics(
    answer_correctness=0.80,
    answer_similarity=0.75,
    faithfulness=0.90,
    context_precision=0.85,
    context_recall=0.70,
    answer_relevancy=0.88,
)

_NAN_LAYER1 = Layer1Metrics(
    answer_correctness=_NAN,
    answer_similarity=_NAN,
    faithfulness=_NAN,
    context_precision=_NAN,
    context_recall=_NAN,
    answer_relevancy=_NAN,
)

# MetricVector com todos os campos NaN — simula resultado da Passada 1.
_NAN_METRICS = make_metric_vector(
    answer_correctness=_NAN,
    answer_similarity=_NAN,
    faithfulness=_NAN,
    context_precision=_NAN,
    context_recall=_NAN,
    answer_relevancy=_NAN,
    bertscore_f1=_NAN,
    rubric_biomed_score=_NAN,
)

_ROUND_ID = "round_305"
_RUN_ID = "run_305"


# ---------------------------------------------------------------------------
# Stubs locais
# ---------------------------------------------------------------------------


class _SpyMetricSuite:
    """MetricSuitePort espião: registra chamadas a score_batch e pode falhar N vezes."""

    def __init__(
        self,
        fixed: Layer1Metrics | None = None,
        *,
        fail_times: int = 0,
    ) -> None:
        self._fixed = fixed if fixed is not None else _DEFAULT_LAYER1
        self._fail_times = fail_times
        self._call_count = 0
        self.score_batch_calls: list[list[EvaluationSample]] = []

    async def score(self, sample: EvaluationSample) -> Layer1Metrics:
        return self._fixed

    async def score_batch(self, samples: list[EvaluationSample]) -> list[Layer1Metrics]:
        self.score_batch_calls.append(list(samples))
        self._call_count += 1
        if self._call_count <= self._fail_times:
            raise MetricComputationError("ragas_layer1", "simulated I/O error")
        return [self._fixed] * len(samples)


class _CountingDeterministicMetric:
    """DeterministicMetricPort que conta chamadas e registra os argumentos."""

    def __init__(self, fixed: AuxMetrics | None = None) -> None:
        self._fixed = fixed or AuxMetrics(bertscore_f1=0.82, rouge_l=0.71)
        self.calls: list[tuple[str, str]] = []

    def score(self, *, answer: str, ground_truth: str) -> AuxMetrics:
        self.calls.append((answer, ground_truth))
        return self._fixed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store_with_results(
    *,
    n_eligible: int = 1,
    n_skipped: int = 0,
    n_missing_gen: int = 0,
    round_id: str = _ROUND_ID,
) -> tuple[InMemoryResultStore, InMemoryResultWriter, InMemoryResultReader]:
    """Cria store pré-populado com linhas de Passada 1 (metrics NaN) e variações."""
    store = InMemoryResultStore()
    writer = InMemoryResultWriter(store, round_id=round_id)
    reader = InMemoryResultReader(store)

    # Linhas elegíveis: metrics NaN, generated_answer preenchido.
    for i in range(n_eligible):
        answer = make_generated_answer(
            question_id=f"q{i:02d}",
            generated_answer=f"Resposta da questão {i}.",
        )
        writer.append(
            make_evaluation_result(
                answer=answer,
                metrics=_NAN_METRICS,
                final_score=_NAN,
                determinism_regime=DeterminismRegime.GENERATOR,
            )
        )

    # Linhas já avaliadas: answer_correctness não-NaN (devem ser puladas).
    for i in range(n_skipped):
        answer = make_generated_answer(question_id=f"qskip{i:02d}")
        writer.append(
            make_evaluation_result(
                answer=answer,
                metrics=make_metric_vector(answer_correctness=0.80),
                determinism_regime=DeterminismRegime.GENERATOR,
            )
        )

    # Linhas sem geração: generated_answer vazio.
    for i in range(n_missing_gen):
        answer = make_generated_answer(
            question_id=f"qmiss{i:02d}",
            generated_answer="",
        )
        writer.append(
            make_evaluation_result(
                answer=answer,
                metrics=_NAN_METRICS,
                final_score=_NAN,
                determinism_regime=DeterminismRegime.GENERATOR,
            )
        )

    return store, writer, reader


def _make_uc(
    *,
    metric_suite: _SpyMetricSuite | None = None,
    deterministic: _CountingDeterministicMetric | None = None,
    config: MetricsPassConfig | None = None,
    store: InMemoryResultStore | None = None,
    round_id: str = _ROUND_ID,
) -> tuple[RunMetricsPassUseCase, InMemoryResultWriter, InMemoryResultReader]:
    if store is None:
        store, _, _ = _make_store_with_results(round_id=round_id)
    writer = InMemoryResultWriter(store, round_id=round_id)
    reader = InMemoryResultReader(store)
    uc = RunMetricsPassUseCase(
        metric_suite=metric_suite or _SpyMetricSuite(),
        deterministic=deterministic or _CountingDeterministicMetric(),
        score_calc=FinalScoreCalculator(_TEST_WEIGHTS),
        writer=writer,
        reader=reader,
        config=config,
    )
    return uc, writer, reader


# ---------------------------------------------------------------------------
# Idempotência
# ---------------------------------------------------------------------------


class TestIdempotency:
    async def test_already_evaluated_row_is_skipped(self) -> None:
        store, _, _ = _make_store_with_results(n_eligible=0, n_skipped=1)
        spy = _SpyMetricSuite()
        uc, _, _ = _make_uc(metric_suite=spy, store=store)
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert report.n_skipped == 1
        assert len(spy.score_batch_calls) == 0

    async def test_eligible_rows_are_not_skipped(self) -> None:
        store, _, _ = _make_store_with_results(n_eligible=2)
        spy = _SpyMetricSuite()
        uc, _, _ = _make_uc(metric_suite=spy, store=store)
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert report.n_skipped == 0
        assert len(spy.score_batch_calls) > 0

    async def test_mixed_rows_counted_correctly(self) -> None:
        store, _, _ = _make_store_with_results(n_eligible=2, n_skipped=3)
        uc, _, _ = _make_uc(store=store)
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert report.n_skipped == 3


# ---------------------------------------------------------------------------
# Geração ausente
# ---------------------------------------------------------------------------


class TestMissingGeneration:
    async def test_empty_generated_answer_counted_separately(self) -> None:
        store, _, _ = _make_store_with_results(n_missing_gen=1)
        uc, _, _ = _make_uc(store=store)
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert report.n_skipped_missing_generation == 1

    async def test_missing_generation_does_not_call_score_batch(self) -> None:
        store, _, _ = _make_store_with_results(n_eligible=0, n_missing_gen=2)
        spy = _SpyMetricSuite()
        uc, _, _ = _make_uc(metric_suite=spy, store=store)
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert len(spy.score_batch_calls) == 0


# ---------------------------------------------------------------------------
# Processamento em lotes
# ---------------------------------------------------------------------------


class TestBatchProcessing:
    async def test_score_batch_called_not_individual_score(self) -> None:
        """score_batch é chamado uma vez para N linhas, não N chamadas a score."""
        store, _, _ = _make_store_with_results(n_eligible=3)
        spy = _SpyMetricSuite()
        uc, _, _ = _make_uc(
            metric_suite=spy,
            store=store,
            config=MetricsPassConfig(batch_size=10),
        )
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        # 3 linhas com batch_size=10 → 1 chamada a score_batch
        assert len(spy.score_batch_calls) == 1
        assert len(spy.score_batch_calls[0]) == 3

    async def test_batch_size_limits_samples_per_call(self) -> None:
        """batch_size=2 com 3 linhas deve gerar 2 chamadas a score_batch."""
        store, _, _ = _make_store_with_results(n_eligible=3)
        spy = _SpyMetricSuite()
        uc, _, _ = _make_uc(
            metric_suite=spy,
            store=store,
            config=MetricsPassConfig(batch_size=2),
        )
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        # ceil(3/2) = 2 chamadas
        assert len(spy.score_batch_calls) == 2
        assert len(spy.score_batch_calls[0]) == 2
        assert len(spy.score_batch_calls[1]) == 1

    async def test_evaluation_sample_fields_correct(self) -> None:
        """EvaluationSample construído com question, ground_truth e generated_answer."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        spy = _SpyMetricSuite()
        uc, _, _ = _make_uc(metric_suite=spy, store=store)
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        sample = spy.score_batch_calls[0][0]
        assert sample.question == "O que é RAG?"
        assert sample.ground_truth == "Retrieval-Augmented Generation."
        assert sample.generated_answer == "Resposta da questão 0."


# ---------------------------------------------------------------------------
# Métricas e persistência
# ---------------------------------------------------------------------------


class TestMetricsAndPersistence:
    async def test_update_metrics_called_with_generator_regime(self) -> None:
        """update_metrics deve usar DeterminismRegime.GENERATOR (não JUDGE)."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        uc, _, reader = _make_uc(store=store)
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        result = next(iter(reader.load(round_id=_ROUND_ID).results))
        assert result.determinism_regime is DeterminismRegime.GENERATOR

    async def test_bertscore_comes_from_deterministic_not_ragas(self) -> None:
        """bertscore_f1 no MetricVector deve ser do DeterministicMetricPort."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        det = _CountingDeterministicMetric(
            fixed=AuxMetrics(bertscore_f1=0.55, rouge_l=0.33)
        )
        uc, _, reader = _make_uc(deterministic=det, store=store)
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        result = next(iter(reader.load(round_id=_ROUND_ID).results))
        assert result.metrics.bertscore_f1 == pytest.approx(0.55)

    async def test_rubric_biomed_score_is_nan_in_passada2(self) -> None:
        """rubric_biomed_score deve ser NaN na Passada 2 (preenchido na Passada 3)."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        uc, _, reader = _make_uc(store=store)
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        result = next(iter(reader.load(round_id=_ROUND_ID).results))
        assert math.isnan(result.metrics.rubric_biomed_score)

    async def test_deterministic_score_called_with_correct_args(self) -> None:
        """deterministic.score deve receber answer e ground_truth corretos."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        det = _CountingDeterministicMetric()
        uc, _, _ = _make_uc(deterministic=det, store=store)
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert len(det.calls) == 1
        answer, ground_truth = det.calls[0]
        assert answer == "Resposta da questão 0."
        assert ground_truth == "Retrieval-Augmented Generation."

    async def test_n_evaluated_incremented_when_final_score_not_nan(self) -> None:
        """n_evaluated conta linhas com FinalScore não-NaN."""
        store, _, _ = _make_store_with_results(n_eligible=2)
        uc, _, _ = _make_uc(store=store)
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert report.n_evaluated == 2
        assert report.n_nan == 0


# ---------------------------------------------------------------------------
# NaN propagation (ADR-007)
# ---------------------------------------------------------------------------


class TestNanPropagation:
    async def test_nan_layer1_metrics_propagate_to_final_score(self) -> None:
        """Quando RAGAS retorna NaN, FinalScore deve ser NaN e n_nan incrementado."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        spy = _SpyMetricSuite(fixed=_NAN_LAYER1)
        # Pesos com answer_correctness>0: NaN em answer_correctness → FinalScore NaN
        weights = {
            "answer_correctness": 0.50,
            "faithfulness": 0.20,
            "context_recall": 0.10,
            "context_precision": 0.10,
            "answer_relevancy": 0.05,
            "answer_similarity": 0.05,
            "bertscore_f1": 0.00,
            "rubric_biomed_score": 0.00,
        }
        uc = RunMetricsPassUseCase(
            metric_suite=spy,
            deterministic=_CountingDeterministicMetric(),
            score_calc=FinalScoreCalculator(weights),
            writer=InMemoryResultWriter(store, round_id=_ROUND_ID),
            reader=InMemoryResultReader(store),
        )
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert report.n_nan == 1
        assert report.n_evaluated == 0
        result = next(
            iter(InMemoryResultReader(store).load(round_id=_ROUND_ID).results)
        )
        assert math.isnan(result.final_score.value)

    async def test_nan_rows_are_persisted_not_discarded(self) -> None:
        """NaN (ADR-007): linhas com FinalScore NaN DEVEM ser persistidas, não descartadas."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        spy = _SpyMetricSuite(fixed=_NAN_LAYER1)
        uc, _, _ = _make_uc(metric_suite=spy, store=store)
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        # update_metrics foi chamado — a linha ainda existe no store
        results = list(InMemoryResultReader(store).load(round_id=_ROUND_ID).results)
        assert len(results) == 1


# ---------------------------------------------------------------------------
# Retry de MetricComputationError (ADR-007)
# ---------------------------------------------------------------------------


class TestMetricErrorRetry:
    async def test_metric_error_retried_up_to_max_times(self) -> None:
        """MetricComputationError deve ser tentada max_metric_retries vezes."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        spy = _SpyMetricSuite(fail_times=3)  # falha 3x = max_metric_retries
        uc, _, _ = _make_uc(
            metric_suite=spy,
            store=store,
            config=MetricsPassConfig(max_metric_retries=3),
        )
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        # 3 falhas + sucesso na 4a → impossível; 3 = max_retries → NaN
        assert report.n_nan == 1
        assert spy._call_count == 3  # tentativas = max_metric_retries

    async def test_metric_error_nan_persisted_after_exhaustion(self) -> None:
        """Após esgotar retries, MetricVector all-NaN deve ser persistido (ADR-007)."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        spy = _SpyMetricSuite(fail_times=99)  # sempre falha
        uc, _, _ = _make_uc(
            metric_suite=spy,
            store=store,
            config=MetricsPassConfig(max_metric_retries=3),
        )
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        results = list(InMemoryResultReader(store).load(round_id=_ROUND_ID).results)
        assert len(results) == 1
        assert math.isnan(results[0].metrics.answer_correctness)

    async def test_metric_error_success_before_exhaustion(self) -> None:
        """Se score_batch tem sucesso antes de esgotar retries, n_evaluated incrementa."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        spy = _SpyMetricSuite(fail_times=1)  # falha 1x, max=3 → sucesso na 2a
        uc, _, _ = _make_uc(
            metric_suite=spy,
            store=store,
            config=MetricsPassConfig(max_metric_retries=3),
        )
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert report.n_evaluated == 1
        assert report.n_nan == 0
        assert spy._call_count == 2  # 1 falha + 1 sucesso

    async def test_metric_error_not_counted_in_n_errors(self) -> None:
        """MetricComputationError é retryável — NÃO vai para n_errors (vai para n_nan)."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        spy = _SpyMetricSuite(fail_times=99)
        uc, _, _ = _make_uc(
            metric_suite=spy,
            store=store,
            config=MetricsPassConfig(max_metric_retries=3),
        )
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert report.n_errors == 0
        assert report.n_nan == 1


# ---------------------------------------------------------------------------
# MetricsPassReport
# ---------------------------------------------------------------------------


class TestMetricsPassReport:
    async def test_report_fields_populated(self) -> None:
        """MetricsPassReport deve ter todos os campos preenchidos corretamente."""
        store, _, _ = _make_store_with_results(
            n_eligible=2, n_skipped=1, n_missing_gen=1
        )
        uc, _, _ = _make_uc(store=store)
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert isinstance(report, MetricsPassReport)
        assert report.run_id == _RUN_ID
        assert report.round_id == _ROUND_ID
        assert report.n_evaluated == 2
        assert report.n_skipped == 1
        assert report.n_skipped_missing_generation == 1
        assert report.n_nan == 0
        assert report.n_errors == 0
        assert report.duration_s >= 0.0

    async def test_report_type_is_frozen_dataclass(self) -> None:
        """MetricsPassReport deve ser um frozen dataclass."""
        import dataclasses

        store, _, _ = _make_store_with_results()
        uc, _, _ = _make_uc(store=store)
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        with pytest.raises(dataclasses.FrozenInstanceError):
            report.n_evaluated = 999  # type: ignore[misc]

    async def test_empty_round_returns_zero_counts(self) -> None:
        """Round sem linhas deve retornar todos os contadores em 0."""
        store, _, _ = _make_store_with_results(n_eligible=0)
        uc, _, _ = _make_uc(store=store)
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert report.n_evaluated == 0
        assert report.n_skipped == 0
        assert report.n_skipped_missing_generation == 0
        assert report.n_nan == 0
        assert report.n_errors == 0
