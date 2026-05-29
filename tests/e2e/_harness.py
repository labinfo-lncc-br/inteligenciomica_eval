"""Minimal-round E2E test harness (no GPU, no network).

Orchestrates fakes + ParquetStorage + domain services following the §3.4
two-pass flow:

  Pass 1 — Generation:
    retrieve → generate → append(partial row: NaN metrics, NaN final_score)

  Pass 2 — Judging (separate pass, mirrors ComputeMetricsUseCase):
    load rows without final_score → score → update_metrics → re-append
    (last-write-wins to also persist final_score, ADR-009 §5.4)

Designed to be called directly from pytest functions; does NOT anticipate any
M1+ use-case classes — it wires domain services by hand so the E2E validates
each layer independently.
"""

from __future__ import annotations

import math

from fakes.generation import FakeGenerator
from fakes.metrics import FakeDeterministicMetric, FakeMetricSuite, FakeRubricJudge
from fakes.retrieval import StubRetriever

from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
)
from inteligenciomica_eval.domain.ports import EvaluationSample
from inteligenciomica_eval.domain.services.aggregation import (
    AggregationService,
    ConfigAggregate,
)
from inteligenciomica_eval.domain.services.final_score import (
    DEFAULT_WEIGHTS,
    FinalScoreCalculator,
)
from inteligenciomica_eval.domain.services.rank_score import (
    DEFAULT_WEIGHTS as RANK_DEFAULT_WEIGHTS,
)
from inteligenciomica_eval.domain.services.rank_score import (
    RankScoreCalculator,
)
from inteligenciomica_eval.domain.value_objects import (
    BaseId,
    DeterminismRegime,
    FinalScore,
    LLMId,
    MetricVector,
    RowId,
    Seed,
)
from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
    ParquetStorage,
)

# (base_val, llm_val, seed, question_id) — identifies a cell that must get NaN metrics
NanCellKey = tuple[str, str, int, str]

_NAN = float("nan")

# Sentinel MetricVector for partial rows written in pass 1 (all fields NULL in Parquet).
# Allows the judging pass to identify rows that still need scoring via
# ``math.isnan(result.final_score.value)`` (§5.4 contract).
_PARTIAL_METRICS = MetricVector(
    answer_correctness=_NAN,
    answer_similarity=_NAN,
    faithfulness=_NAN,
    context_precision=_NAN,
    context_recall=_NAN,
    answer_relevancy=_NAN,
    bertscore_f1=_NAN,
    rubric_biomed_score=_NAN,
)


async def run_min_round(
    *,
    storage: ParquetStorage,
    run_id: str,
    round_id: str,
    questions: list[Question],
    base_ids: list[BaseId],
    llm_ids: list[LLMId],
    seeds: list[int],
    phase: str,
    retriever: StubRetriever,
    generator: FakeGenerator,
    normal_metric_suite: FakeMetricSuite,
    nan_metric_suite: FakeMetricSuite,
    normal_rubric: FakeRubricJudge,
    nan_rubric: FakeRubricJudge,
    aux_metric: FakeDeterministicMetric,
    nan_cells: frozenset[NanCellKey],
    failure_threshold: float = 0.6,
) -> tuple[list[EvaluationResult], tuple[ConfigAggregate, ...]]:
    """Run one minimal evaluation round with all fakes, no network or GPU.

    Implements the §3.4 two-pass flow:

    **Pass 1 — Generation** (idempotent via ``storage.exists``):
      For each (question x base x llm x seed) cell, if not already persisted:
        1. Retrieve chunks via *retriever*.
        2. Generate a response via *generator*.
        3. Persist a **partial** ``EvaluationResult`` — generated answer filled,
           all metrics and ``final_score`` set to NaN (NULL in Parquet).

    **Pass 2 — Judging** (mirrors ``ComputeMetricsUseCase``, §3.4 step 4):
      For each row whose ``final_score`` is still NaN (not yet judged):
        4. Score with the normal or NaN suite depending on *nan_cells*.
        5. Call ``storage.update_metrics(row_id, metrics)`` — exercises the
           ``ResultWriterPort.update_metrics`` path (§3.4.4d, §5.4).
        6. Re-append the complete ``EvaluationResult`` via ``storage.append``
           (last-write-wins, ADR-009) to also persist ``final_score`` and
           ``critical_failure_flag``, which ``update_metrics`` does not cover.

    Cells in *nan_cells* receive all-NaN Layer1Metrics and NaN rubric score so
    that ``FinalScore`` propagates to NaN (ADR-007).  Because NaN cells retain
    ``final_score = NaN`` after judging, they are re-processed on every call to
    pass 2 — which is idempotent (same NaN output).  Normal cells produce a
    non-NaN ``final_score`` after pass 2 and are skipped on subsequent calls.

    Args:
        storage: ParquetStorage instance backed by a local temp directory.
        run_id: evaluation run identifier embedded in every RowId.
        round_id: round identifier used for partition lookup on load.
        questions: list of Question entities to evaluate.
        base_ids: list of knowledge-base identifiers.
        llm_ids: list of LLM identifiers.
        seeds: list of integer reproducibility seeds.
        phase: experiment phase (``"A"`` or ``"B"``).
        retriever: StubRetriever with planted chunks per question.
        generator: FakeGenerator returning deterministic text.
        normal_metric_suite: FakeMetricSuite returning non-NaN Layer1Metrics.
        nan_metric_suite: FakeMetricSuite returning all-NaN Layer1Metrics.
        normal_rubric: FakeRubricJudge returning a valid (non-NaN) score.
        nan_rubric: FakeRubricJudge returning NaN score (ADR-007 retry exhaustion).
        aux_metric: FakeDeterministicMetric for BERTScore (always non-NaN here).
        nan_cells: frozenset of ``(base_val, llm_val, seed, question_id)`` keys
            that should receive NaN metrics, exercising NaN exclusion in aggregation.
        failure_threshold: ``final_score`` threshold below which a result counts
            as a failure.  Defaults to ``0.6``.

    Returns:
        Tuple of ``(newly_judged_results, config_aggregates)`` where
        ``newly_judged_results`` contains only the complete ``EvaluationResult``
        objects written by pass 2 in this call (rows already judged with a
        non-NaN ``final_score`` are excluded), and ``config_aggregates`` is the
        full aggregation of all rows in storage after both passes.
    """
    calculator = FinalScoreCalculator(DEFAULT_WEIGHTS)
    rank_calculator = RankScoreCalculator(RANK_DEFAULT_WEIGHTS)
    agg_service = AggregationService(rank_calculator)

    # ─── PASS 1: Generation ───────────────────────────────────────────────
    # retrieve → generate → append partial row (NaN metrics, NaN final_score).
    # Idempotent: cells where generated_answer is already stored are skipped.

    for base_id in base_ids:
        for llm_id in llm_ids:
            for seed in seeds:
                for question in questions:
                    row_id = RowId.from_cell(
                        run_id=run_id,
                        phase=phase,
                        base=base_id.value,
                        llm=llm_id.value,
                        seed=seed,
                        question_id=question.question_id,
                    )

                    # Idempotency check: skip if generation already persisted (ADR-009)
                    if storage.exists(row_id):
                        continue

                    retrieval = await retriever.search(
                        base=base_id,
                        question=question.text,
                        top_k=3,
                    )
                    generation = await generator.generate(
                        llm=llm_id,
                        question=question.text,
                        contexts=retrieval.chunks,
                        seed=seed,
                        temperature=0.0,
                    )
                    answer = GeneratedAnswer(
                        row_id=row_id,
                        question=question,
                        base=base_id,
                        llm=llm_id,
                        seed=Seed(seed),
                        phase=phase,
                        generated_answer=generation.text,
                        retrieved_chunk_ids=retrieval.ids,
                        retrieved_chunks_text=tuple(c.text for c in retrieval.chunks),
                        retrieval_scores=retrieval.scores,
                    )
                    # Partial row: metrics and final_score intentionally NaN (NULL in Parquet).
                    # The judging pass (pass 2) will complete them via update_metrics + re-append.
                    partial = EvaluationResult(
                        answer=answer,
                        metrics=_PARTIAL_METRICS,
                        final_score=FinalScore(_NAN),
                        determinism_regime=DeterminismRegime.JUDGE,
                        critical_failure_flag=None,
                        critical_failure_note=None,
                    )
                    storage.append(partial)

    # ─── PASS 2: Judging ──────────────────────────────────────────────────
    # Load all rows. Rows whose final_score is still NaN have not been judged yet.
    # Score → update_metrics (§3.4.4d) → re-append to persist final_score (ADR-009).

    frame = storage.load(round_id=round_id, phase=phase)
    newly_judged: list[EvaluationResult] = []

    for loaded in frame.results:
        # Skip rows already judged with a finite final_score (normal cells after
        # pass 2 has run once).  NaN cells keep final_score=NaN after judging and
        # are re-processed on every call — idempotent because the output is unchanged.
        if not math.isnan(loaded.final_score.value):
            continue

        answer = loaded.answer
        sample = EvaluationSample(
            question_id=answer.question.question_id,
            question=answer.question.text,
            ground_truth=answer.question.ground_truth,
            generated_answer=answer.generated_answer,
            contexts=answer.retrieved_chunks_text,
        )

        cell_key: NanCellKey = (
            answer.base.value,
            answer.llm.value,
            answer.seed.value,
            answer.question.question_id,
        )
        is_nan_cell = cell_key in nan_cells

        if is_nan_cell:
            l1 = await nan_metric_suite.score(sample)
            rubric = await nan_rubric.score(sample)
            flag: int | None = None
        else:
            l1 = await normal_metric_suite.score(sample)
            rubric = await normal_rubric.score(sample)
            # Annotate non-NaN cells so critical_failure_rate is computable
            flag = 0

        aux = aux_metric.score(
            answer=answer.generated_answer,
            ground_truth=answer.question.ground_truth,
        )
        metrics = MetricVector(
            answer_correctness=l1.answer_correctness,
            answer_similarity=l1.answer_similarity,
            faithfulness=l1.faithfulness,
            context_precision=l1.context_precision,
            context_recall=l1.context_recall,
            answer_relevancy=l1.answer_relevancy,
            bertscore_f1=aux.bertscore_f1,
            rubric_biomed_score=rubric.score,
        )
        final_score = calculator.compute(metrics)

        # 2a — update the eight metric columns (exercises ResultWriterPort.update_metrics,
        #      the §3.4.4d / §5.4 contract between generation and judging passes).
        storage.update_metrics(answer.row_id, metrics)

        # 2b — re-append the complete result to also persist final_score and
        #      critical_failure_flag, which update_metrics does not cover.
        #      last-write-wins semantics (ADR-009) ensure no duplication.
        complete = EvaluationResult(
            answer=answer,
            metrics=metrics,
            final_score=final_score,
            determinism_regime=DeterminismRegime.JUDGE,
            critical_failure_flag=flag,
            critical_failure_note=None,
        )
        storage.append(complete)
        newly_judged.append(complete)

    # ─── Aggregate ────────────────────────────────────────────────────────
    frame2 = storage.load(round_id=round_id, phase=phase)
    aggregates = agg_service.aggregate_all(
        frame2.results,
        threshold=failure_threshold,
    )

    return newly_judged, aggregates
