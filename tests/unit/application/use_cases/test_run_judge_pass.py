"""Testes unitários de RunJudgePassUseCase (TAREFA-306, Passada 3 do juiz)."""

from __future__ import annotations

import dataclasses
import math

import pytest
from factories import (
    make_evaluation_result,
    make_generated_answer,
    make_metric_vector,
    make_row_id,
)
from fakes.storage import (
    InMemoryResultReader,
    InMemoryResultStore,
    InMemoryResultWriter,
)

from inteligenciomica_eval.application.use_cases.run_judge_pass import (
    JudgePassConfig,
    JudgePassReport,
    RunJudgePassUseCase,
)
from inteligenciomica_eval.domain.errors import JudgeUnavailableError
from inteligenciomica_eval.domain.ports import EvaluationSample, RubricResult
from inteligenciomica_eval.domain.services.final_score import FinalScoreCalculator
from inteligenciomica_eval.domain.value_objects import DeterminismRegime

_NAN = float("nan")

# Pesos com rubric_biomed_score=0.15 (Passada 3 deve contribuir ao FinalScore).
# Todos os campos de make_metric_vector padrão estão em [0, 1], portanto
# FinalScore ∈ [0, 1] com estes pesos.
_TEST_WEIGHTS: dict[str, float] = {
    "answer_correctness": 0.35,
    "faithfulness": 0.20,
    "context_recall": 0.10,
    "context_precision": 0.10,
    "answer_relevancy": 0.05,
    "answer_similarity": 0.05,
    "bertscore_f1": 0.00,
    "rubric_biomed_score": 0.15,
}

# Score normalizado [0, 1] para que FinalScore fique válido após ponderação.
_FIXED_RUBRIC = RubricResult(score=0.8, feedback="Canonical rubric for tests.")

# MetricVector após Passada 2: RAGAS preenchido (defaults), rubric=NaN.
_METRICS_PASSADA2 = make_metric_vector(rubric_biomed_score=_NAN)

_ROUND_ID = "round_306"
_RUN_ID = "run_306"


# ---------------------------------------------------------------------------
# Stubs locais
# ---------------------------------------------------------------------------


class _SpyRubricJudge:
    """RubricJudgePort espião: registra chamadas e pode falhar N vezes."""

    def __init__(
        self,
        fixed: RubricResult | None = None,
        *,
        fail_times: int = 0,
    ) -> None:
        self._fixed = fixed if fixed is not None else _FIXED_RUBRIC
        self._fail_times = fail_times
        self._call_count = 0
        self.calls: list[EvaluationSample] = []
        self.call_question_ids: list[str] = []

    async def score(self, sample: EvaluationSample) -> RubricResult:
        self.calls.append(sample)
        self.call_question_ids.append(sample.question_id)
        self._call_count += 1
        if self._call_count <= self._fail_times:
            raise JudgeUnavailableError("spy-judge", "simulated unavailable")
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
    """Cria store pré-populado com linhas de Passada 2 e variações."""
    store = InMemoryResultStore()
    writer = InMemoryResultWriter(store, round_id=round_id)
    reader = InMemoryResultReader(store)

    # Linhas elegíveis: rubric=NaN, generated_answer preenchido.
    for i in range(n_eligible):
        answer = make_generated_answer(
            question_id=f"q{i:02d}",
            generated_answer=f"Resposta da questão {i}.",
        )
        writer.append(
            make_evaluation_result(
                answer=answer,
                metrics=_METRICS_PASSADA2,
                final_score=0.80,
                determinism_regime=DeterminismRegime.GENERATOR,
            )
        )

    # Linhas já julgadas: rubric_biomed_score não-NaN (devem ser puladas).
    for i in range(n_skipped):
        answer = make_generated_answer(question_id=f"qskip{i:02d}")
        writer.append(
            make_evaluation_result(
                answer=answer,
                metrics=make_metric_vector(rubric_biomed_score=0.8),
                determinism_regime=DeterminismRegime.JUDGE,
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
                metrics=_METRICS_PASSADA2,
                final_score=_NAN,
                determinism_regime=DeterminismRegime.GENERATOR,
            )
        )

    return store, writer, reader


def _make_uc(
    *,
    judge: _SpyRubricJudge | None = None,
    config: JudgePassConfig | None = None,
    store: InMemoryResultStore | None = None,
    round_id: str = _ROUND_ID,
) -> tuple[RunJudgePassUseCase, InMemoryResultWriter, InMemoryResultReader]:
    if store is None:
        store, _, _ = _make_store_with_results(round_id=round_id)
    writer = InMemoryResultWriter(store, round_id=round_id)
    reader = InMemoryResultReader(store)
    uc = RunJudgePassUseCase(
        judge=judge or _SpyRubricJudge(),
        writer=writer,
        reader=reader,
        score_calc=FinalScoreCalculator(_TEST_WEIGHTS),
        config=config,
    )
    return uc, writer, reader


# ---------------------------------------------------------------------------
# Idempotência
# ---------------------------------------------------------------------------


class TestIdempotency:
    async def test_already_judged_row_is_skipped(self) -> None:
        store, _, _ = _make_store_with_results(n_eligible=0, n_skipped=1)
        spy = _SpyRubricJudge()
        uc, _, _ = _make_uc(judge=spy, store=store)
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert report.n_skipped == 1
        assert spy._call_count == 0

    async def test_eligible_rows_are_not_skipped(self) -> None:
        store, _, _ = _make_store_with_results(n_eligible=2)
        spy = _SpyRubricJudge()
        uc, _, _ = _make_uc(judge=spy, store=store)
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert report.n_skipped == 0
        assert spy._call_count == 2

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

    async def test_missing_generation_does_not_call_judge(self) -> None:
        store, _, _ = _make_store_with_results(n_eligible=0, n_missing_gen=2)
        spy = _SpyRubricJudge()
        uc, _, _ = _make_uc(judge=spy, store=store)
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert spy._call_count == 0


# ---------------------------------------------------------------------------
# Linhas com FinalScore NaN
# ---------------------------------------------------------------------------


class TestNanFinalScoreRows:
    async def test_nan_final_score_rows_are_processed(self) -> None:
        """Linhas com FinalScore NaN (Passada 2 incompleta) devem ser julgadas (ADR-004)."""
        store = InMemoryResultStore()
        writer = InMemoryResultWriter(store, round_id=_ROUND_ID)
        answer = make_generated_answer(
            question_id="qnan00", generated_answer="Resposta NaN."
        )
        writer.append(
            make_evaluation_result(
                answer=answer,
                metrics=_METRICS_PASSADA2,
                final_score=_NAN,
                determinism_regime=DeterminismRegime.GENERATOR,
            )
        )
        spy = _SpyRubricJudge()
        uc, _, _ = _make_uc(judge=spy, store=store)
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert spy._call_count == 1
        assert report.n_judged == 1


# ---------------------------------------------------------------------------
# Ordem estável
# ---------------------------------------------------------------------------


class TestStableOrdering:
    async def test_judge_called_in_row_id_sorted_order(self) -> None:
        """Juiz deve ser chamado em ordem lexicográfica estável por row_id (ADR-003)."""
        question_ids = ["qZ", "qA", "qM"]
        store = InMemoryResultStore()
        writer = InMemoryResultWriter(store, round_id=_ROUND_ID)
        for qid in question_ids:
            answer = make_generated_answer(
                question_id=qid, generated_answer=f"Resp {qid}."
            )
            writer.append(
                make_evaluation_result(
                    answer=answer,
                    metrics=_METRICS_PASSADA2,
                    final_score=0.80,
                    determinism_regime=DeterminismRegime.GENERATOR,
                )
            )
        spy = _SpyRubricJudge()
        uc, _, _ = _make_uc(judge=spy, store=store)
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)

        # Ordem esperada: question_ids ordenados pelo row_id.value correspondente.
        expected_order = sorted(
            question_ids,
            key=lambda qid: make_row_id(question_id=qid).value,
        )
        assert spy.call_question_ids == expected_order


# ---------------------------------------------------------------------------
# Retry de JudgeUnavailableError (ADR-007)
# ---------------------------------------------------------------------------


class TestJudgeRetry:
    async def test_judge_retried_up_to_max_times(self) -> None:
        """JudgeUnavailableError deve ser tentada max_judge_retries vezes no total."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        spy = _SpyRubricJudge(fail_times=3)  # falha 3x = max_judge_retries → NaN
        uc, _, _ = _make_uc(
            judge=spy,
            store=store,
            config=JudgePassConfig(max_judge_retries=3, retry_backoff_s=0.0),
        )
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert report.n_nan == 1
        assert spy._call_count == 3

    async def test_judge_nan_persisted_after_exhaustion(self) -> None:
        """Após esgotar retries, rubric_biomed_score=NaN deve ser persistido (ADR-007)."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        spy = _SpyRubricJudge(fail_times=99)  # sempre falha
        uc, _, _ = _make_uc(
            judge=spy,
            store=store,
            config=JudgePassConfig(max_judge_retries=3, retry_backoff_s=0.0),
        )
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        results = list(InMemoryResultReader(store).load(round_id=_ROUND_ID).results)
        assert len(results) == 1
        assert math.isnan(results[0].metrics.rubric_biomed_score)

    async def test_judge_success_before_exhaustion(self) -> None:
        """Se o juiz tem sucesso antes de esgotar retries, n_judged deve incrementar."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        spy = _SpyRubricJudge(fail_times=1)  # falha 1x, max=3 → sucesso na 2a tentativa
        uc, _, _ = _make_uc(
            judge=spy,
            store=store,
            config=JudgePassConfig(max_judge_retries=3, retry_backoff_s=0.0),
        )
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert report.n_judged == 1
        assert report.n_nan == 0
        assert spy._call_count == 2  # 1 falha + 1 sucesso


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------


class TestPersistence:
    async def test_update_metrics_called_with_judge_regime(self) -> None:
        """update_metrics deve usar DeterminismRegime.JUDGE (ADR-003)."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        uc, _, reader = _make_uc(store=store)
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        result = next(iter(reader.load(round_id=_ROUND_ID).results))
        assert result.determinism_regime is DeterminismRegime.JUDGE

    async def test_rubric_score_persisted_from_judge(self) -> None:
        """rubric_biomed_score persistido deve ser o valor retornado pelo juiz."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        spy = _SpyRubricJudge(fixed=RubricResult(score=0.75, feedback="test rubric"))
        uc, _, reader = _make_uc(judge=spy, store=store)
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        result = next(iter(reader.load(round_id=_ROUND_ID).results))
        assert result.metrics.rubric_biomed_score == pytest.approx(0.75)

    async def test_final_score_recomputed_after_judging(self) -> None:
        """FinalScore deve ser recalculado com rubric_biomed_score preenchido."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        uc, _, reader = _make_uc(store=store)
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        result = next(iter(reader.load(round_id=_ROUND_ID).results))
        assert not math.isnan(result.final_score.value)

    async def test_evaluation_sample_fields_correct(self) -> None:
        """EvaluationSample construído com question, ground_truth e generated_answer."""
        store, _, _ = _make_store_with_results(n_eligible=1)
        spy = _SpyRubricJudge()
        uc, _, _ = _make_uc(judge=spy, store=store)
        await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        sample = spy.calls[0]
        assert sample.question == "O que é RAG?"
        assert sample.ground_truth == "Retrieval-Augmented Generation."
        assert sample.generated_answer == "Resposta da questão 0."


# ---------------------------------------------------------------------------
# JudgePassReport
# ---------------------------------------------------------------------------


class TestJudgePassReport:
    async def test_report_fields_populated(self) -> None:
        """JudgePassReport deve ter todos os campos preenchidos corretamente."""
        store, _, _ = _make_store_with_results(
            n_eligible=2, n_skipped=1, n_missing_gen=1
        )
        uc, _, _ = _make_uc(store=store)
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert isinstance(report, JudgePassReport)
        assert report.run_id == _RUN_ID
        assert report.round_id == _ROUND_ID
        assert report.n_judged == 2
        assert report.n_skipped == 1
        assert report.n_skipped_missing_generation == 1
        assert report.n_nan == 0
        assert report.duration_s >= 0.0
        assert report.batch_invariant_assumed is True

    async def test_report_is_frozen_dataclass(self) -> None:
        """JudgePassReport deve ser um frozen dataclass."""
        store, _, _ = _make_store_with_results()
        uc, _, _ = _make_uc(store=store)
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        with pytest.raises(dataclasses.FrozenInstanceError):
            report.n_judged = 999  # type: ignore[misc]

    async def test_empty_round_returns_zero_counts(self) -> None:
        """Round sem linhas deve retornar todos os contadores em 0."""
        store, _, _ = _make_store_with_results(n_eligible=0)
        uc, _, _ = _make_uc(store=store)
        report = await uc.execute(run_id=_RUN_ID, round_id=_ROUND_ID)
        assert report.n_judged == 0
        assert report.n_skipped == 0
        assert report.n_skipped_missing_generation == 0
        assert report.n_nan == 0
