from __future__ import annotations

from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
)
from inteligenciomica_eval.domain.services.aggregation import ConfigAggregate
from inteligenciomica_eval.domain.value_objects import (
    BaseId,
    DeterminismRegime,
    FinalScore,
    LLMId,
    MetricVector,
    RankScore,
    RowId,
    Seed,
)

_NAN = float("nan")

_DEFAULT_RUN_ID = "run-test"
_DEFAULT_QUESTION_ID = "q01"
_DEFAULT_PHASE = "A"
_DEFAULT_BASE = "IDx_400k"
_DEFAULT_LLM = "llama3-8b"
_DEFAULT_SEED = 42


def make_row_id(
    *,
    run_id: str = _DEFAULT_RUN_ID,
    phase: str = _DEFAULT_PHASE,
    base: str = _DEFAULT_BASE,
    llm: str = _DEFAULT_LLM,
    seed: int = _DEFAULT_SEED,
    question_id: str = _DEFAULT_QUESTION_ID,
) -> RowId:
    """Build a deterministic RowId from its components.

    Args:
        run_id: run identifier.
        phase: experiment phase.
        base: knowledge-base identifier.
        llm: LLM identifier.
        seed: reproducibility seed.
        question_id: question identifier.

    Returns:
        RowId with a SHA-256 digest computed from the given components.
    """
    return RowId.from_cell(
        run_id=run_id,
        phase=phase,
        base=base,
        llm=llm,
        seed=seed,
        question_id=question_id,
    )


def make_question(
    *,
    question_id: str = _DEFAULT_QUESTION_ID,
    text: str = "O que é RAG?",
    ground_truth: str = "Retrieval-Augmented Generation.",
) -> Question:
    """Build a valid Question with sensible defaults.

    Args:
        question_id: unique identifier (non-empty).
        text: question text (non-empty).
        ground_truth: reference answer (non-empty).

    Returns:
        Validated Question instance.
    """
    return Question(question_id=question_id, text=text, ground_truth=ground_truth)


def make_generated_answer(
    *,
    row_id: RowId | None = None,
    question: Question | None = None,
    question_id: str = _DEFAULT_QUESTION_ID,
    base: str = _DEFAULT_BASE,
    llm: str = _DEFAULT_LLM,
    seed: int = _DEFAULT_SEED,
    phase: str = _DEFAULT_PHASE,
    generated_answer: str = "RAG combina recuperação com geração.",
    retrieved_chunk_ids: tuple[str, ...] = ("c1",),
    retrieved_chunks_text: tuple[str, ...] = ("Texto do chunk 1.",),
    retrieval_scores: tuple[float, ...] = (0.9,),
) -> GeneratedAnswer:
    """Build a valid GeneratedAnswer with sensible defaults.

    Args:
        row_id: deterministic row identifier; derived from other fields if None.
        question: Question instance; a default one is used if None.
        base: knowledge-base identifier string (must be a valid BaseId value).
        llm: LLM identifier string (non-empty, no spaces).
        seed: non-negative reproducibility seed.
        phase: experiment phase (``"A"`` or ``"B"``).
        generated_answer: generated response text.
        retrieved_chunk_ids: tuple of chunk IDs from retrieval.
        retrieved_chunks_text: tuple of chunk texts from retrieval.
        retrieval_scores: tuple of retrieval similarity scores.

    Returns:
        Validated GeneratedAnswer instance.
    """
    q = question or make_question(question_id=question_id)
    rid = row_id or make_row_id(
        phase=phase,
        base=base,
        llm=llm,
        seed=seed,
        question_id=q.question_id,
    )
    return GeneratedAnswer(
        row_id=rid,
        question=q,
        base=BaseId(base),
        llm=LLMId(llm),
        seed=Seed(seed),
        phase=phase,
        generated_answer=generated_answer,
        retrieved_chunk_ids=retrieved_chunk_ids,
        retrieved_chunks_text=retrieved_chunks_text,
        retrieval_scores=retrieval_scores,
    )


def make_metric_vector(
    *,
    answer_correctness: float = 0.80,
    answer_similarity: float = 0.75,
    faithfulness: float = 0.90,
    context_precision: float = 0.85,
    context_recall: float = 0.70,
    answer_relevancy: float = 0.88,
    bertscore_f1: float = 0.82,
    rubric_biomed_score: float = 4.0,
) -> MetricVector:
    """Build a MetricVector with sensible defaults (all fields can be overridden).

    Args:
        answer_correctness: factual accuracy score.
        answer_similarity: semantic similarity score.
        faithfulness: faithfulness to retrieved context score.
        context_precision: retrieval precision score.
        context_recall: retrieval recall score.
        answer_relevancy: answer relevancy score.
        bertscore_f1: BERTScore F1.
        rubric_biomed_score: biomedical rubric score from LLM judge.

    Returns:
        MetricVector instance; any field may be ``float('nan')``.
    """
    return MetricVector(
        answer_correctness=answer_correctness,
        answer_similarity=answer_similarity,
        faithfulness=faithfulness,
        context_precision=context_precision,
        context_recall=context_recall,
        answer_relevancy=answer_relevancy,
        bertscore_f1=bertscore_f1,
        rubric_biomed_score=rubric_biomed_score,
    )


def make_evaluation_result(
    *,
    answer: GeneratedAnswer | None = None,
    metrics: MetricVector | None = None,
    final_score: float = 0.80,
    determinism_regime: DeterminismRegime = DeterminismRegime.JUDGE,
    critical_failure_flag: int | None = None,
    critical_failure_note: str | None = None,
) -> EvaluationResult:
    """Build a valid EvaluationResult with sensible defaults.

    Args:
        answer: GeneratedAnswer instance; a default one is used if None.
        metrics: MetricVector instance; canonical defaults used if None.
        final_score: aggregated final score in ``[0.0, 1.0]`` or NaN.
        determinism_regime: judge or generator determinism regime.
        critical_failure_flag: ``0``, ``1``, or ``None`` (not yet annotated).
        critical_failure_note: optional annotation justification.

    Returns:
        Validated EvaluationResult instance.
    """
    return EvaluationResult(
        answer=answer or make_generated_answer(),
        metrics=metrics or make_metric_vector(),
        final_score=FinalScore(final_score),
        determinism_regime=determinism_regime,
        critical_failure_flag=critical_failure_flag,
        critical_failure_note=critical_failure_note,
    )


def make_config_aggregate(
    *,
    base: str = _DEFAULT_BASE,
    llm: str = _DEFAULT_LLM,
    mean_score: float = 0.78,
    median_score: float = 0.80,
    min_score: float = 0.55,
    iqr: float = 0.12,
    failure_rate: float = 0.10,
    critical_failure_rate: float = 0.05,
    win_rate: float = 0.60,
    rank_score: float = 0.72,
    n_observations: int = 13,
    n_excluded_nan: int = 0,
) -> ConfigAggregate:
    """Build a valid ConfigAggregate with sensible defaults.

    Args:
        base: knowledge-base identifier string.
        llm: LLM identifier string.
        mean_score: mean of valid FinalScores.
        median_score: median of valid FinalScores.
        min_score: minimum of valid FinalScores.
        iqr: interquartile range of valid FinalScores.
        failure_rate: fraction of observations below the failure threshold.
        critical_failure_rate: fraction of annotated observations flagged critical.
        win_rate: fraction of questions where this config wins.
        rank_score: composite ranking score.
        n_observations: number of valid (non-NaN) observations.
        n_excluded_nan: number of observations excluded due to NaN FinalScore.

    Returns:
        Validated ConfigAggregate instance.
    """
    return ConfigAggregate(
        base=BaseId(base),
        llm=LLMId(llm),
        mean_score=mean_score,
        median_score=median_score,
        min_score=min_score,
        iqr=iqr,
        failure_rate=failure_rate,
        critical_failure_rate=critical_failure_rate,
        win_rate=win_rate,
        rank_score=RankScore(rank_score),
        n_observations=n_observations,
        n_excluded_nan=n_excluded_nan,
    )
