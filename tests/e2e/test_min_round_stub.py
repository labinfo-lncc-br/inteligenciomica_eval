"""E2E test: minimal evaluation round with fakes/stubs in CPU only (TAREFA-012).

Validates the §3.4 main flow end-to-end:
  retrieve → generate → score → persist (ParquetStorage real) → aggregate.

No GPU, no network. All I/O uses a local tmp_path Parquet directory.
Golden values are in tests/golden/e2e_min_round_expected.json.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from fakes.generation import FakeGenerator
from fakes.metrics import (
    FakeDeterministicMetric,
    FakeMetricSuite,
    FakeRubricJudge,
)
from fakes.retrieval import StubRetriever

from e2e._harness import NanCellKey, run_min_round
from inteligenciomica_eval.domain.entities import Question
from inteligenciomica_eval.domain.ports import Chunk, RubricResult
from inteligenciomica_eval.domain.value_objects import BaseId, LLMId
from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
    ParquetStorage,
)

# ---------------------------------------------------------------------------
# Golden file
# ---------------------------------------------------------------------------

_GOLDEN_PATH = Path(__file__).parents[1] / "golden" / "e2e_min_round_expected.json"
_GOLDEN = json.loads(_GOLDEN_PATH.read_text())

# ---------------------------------------------------------------------------
# Scenario constants (must match golden file)
# ---------------------------------------------------------------------------

_RUN_ID: str = _GOLDEN["run_id"]
_ROUND_ID: str = _GOLDEN["round_id"]
_PHASE: str = _GOLDEN["phase"]
_THRESHOLD: float = _GOLDEN["failure_threshold"]
_TOTAL_CELLS: int = _GOLDEN["total_cells"]
_NORMAL_FINAL_SCORE: float = _GOLDEN["normal_final_score"]

_QUESTIONS: list[Question] = [
    Question(
        question_id="q01",
        text="O que é RAG?",
        ground_truth="Retrieval-Augmented Generation.",
    ),
    Question(
        question_id="q02",
        text="O que é embedding?",
        ground_truth="Representação vetorial de texto.",
    ),
]
_BASE_IDS: list[BaseId] = [BaseId("IDx_400k")]
_LLM_IDS: list[LLMId] = [LLMId("llm-alpha"), LLMId("llm-beta")]
_SEEDS: list[int] = [42]

# Cell (IDx_400k, llm-beta, 42, q02) gets all-NaN metrics to exercise ADR-007
_NAN_CELLS: frozenset[NanCellKey] = frozenset(
    {
        (
            _GOLDEN["nan_cell"][0],
            _GOLDEN["nan_cell"][1],
            int(_GOLDEN["nan_cell"][2]),
            _GOLDEN["nan_cell"][3],
        )
    }
)

# Planted chunks per question (deterministic, no Qdrant)
_PLANTED_CHUNKS: dict[str, list[Chunk]] = {
    "O que é RAG?": [
        Chunk(id="c-rag-1", text="RAG combina retrieval com geração.", score=0.95),
        Chunk(id="c-rag-2", text="O retriever busca chunks relevantes.", score=0.88),
    ],
    "O que é embedding?": [
        Chunk(id="c-emb-1", text="Embeddings são vetores densos.", score=0.92),
        Chunk(id="c-emb-2", text="Modelos de embedding mapeiam texto.", score=0.85),
    ],
}

# Rubric score normalized to [0, 1] so FinalScore stays within [0.0, 1.0]
_RUBRIC_SCORE: float = _GOLDEN["normal_metrics"]["rubric_biomed_score"]

# float32 tolerance — Parquet stores metrics as float32; ~7 significant digits
_F32_TOL: float = 1e-4


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def storage(tmp_path: Path) -> ParquetStorage:
    """Real ParquetStorage backed by pytest's tmp_path directory."""
    return ParquetStorage(
        tmp_path / "results",
        run_id=_RUN_ID,
        round_id=_ROUND_ID,
        judge_model="fake-judge",
        embedding_model="fake-embed",
        chunk_strategy="sentence",
        reranker="none",
        top_k=3,
        prompt_version="v0",
        temperature=0.0,
        vllm_version="stub",
        ragas_version="stub",
        config_hash="abc123",
    )


@pytest.fixture()
def retriever() -> StubRetriever:
    return StubRetriever(responses=_PLANTED_CHUNKS)


@pytest.fixture()
def generator() -> FakeGenerator:
    return FakeGenerator()


@pytest.fixture()
def normal_metric_suite() -> FakeMetricSuite:
    return FakeMetricSuite()


@pytest.fixture()
def nan_metric_suite() -> FakeMetricSuite:
    return FakeMetricSuite(inject_nan=True)


@pytest.fixture()
def normal_rubric() -> FakeRubricJudge:
    return FakeRubricJudge(
        fixed=RubricResult(score=_RUBRIC_SCORE, feedback="Canonical rubric feedback.")
    )


@pytest.fixture()
def nan_rubric() -> FakeRubricJudge:
    return FakeRubricJudge(inject_nan=True)


@pytest.fixture()
def aux_metric() -> FakeDeterministicMetric:
    return FakeDeterministicMetric()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(
    storage: ParquetStorage,
    retriever: StubRetriever,
    generator: FakeGenerator,
    normal_metric_suite: FakeMetricSuite,
    nan_metric_suite: FakeMetricSuite,
    normal_rubric: FakeRubricJudge,
    nan_rubric: FakeRubricJudge,
    aux_metric: FakeDeterministicMetric,
) -> tuple[list, tuple]:  # type: ignore[type-arg]
    """Helper: call run_min_round with the shared scenario config."""
    return await run_min_round(
        storage=storage,
        run_id=_RUN_ID,
        round_id=_ROUND_ID,
        questions=_QUESTIONS,
        base_ids=_BASE_IDS,
        llm_ids=_LLM_IDS,
        seeds=_SEEDS,
        phase=_PHASE,
        retriever=retriever,
        generator=generator,
        normal_metric_suite=normal_metric_suite,
        nan_metric_suite=nan_metric_suite,
        normal_rubric=normal_rubric,
        nan_rubric=nan_rubric,
        aux_metric=aux_metric,
        nan_cells=_NAN_CELLS,
        failure_threshold=_THRESHOLD,
    )


# ---------------------------------------------------------------------------
# Test: row count
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_parquet_row_count(
    storage: ParquetStorage,
    retriever: StubRetriever,
    generator: FakeGenerator,
    normal_metric_suite: FakeMetricSuite,
    nan_metric_suite: FakeMetricSuite,
    normal_rubric: FakeRubricJudge,
    nan_rubric: FakeRubricJudge,
    aux_metric: FakeDeterministicMetric,
) -> None:
    """Parquet must hold exactly as many rows as planned cells."""
    results, _ = await _run(
        storage,
        retriever,
        generator,
        normal_metric_suite,
        nan_metric_suite,
        normal_rubric,
        nan_rubric,
        aux_metric,
    )

    frame = storage.load(round_id=_ROUND_ID, phase=_PHASE)
    assert len(frame.results) == _TOTAL_CELLS, (
        f"Expected {_TOTAL_CELLS} rows, got {len(frame.results)}"
    )
    assert len(results) == _TOTAL_CELLS, (
        f"Harness returned {len(results)} newly appended rows (expected {_TOTAL_CELLS})"
    )


# ---------------------------------------------------------------------------
# Test: roundtrip fidelity
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_parquet_roundtrip(
    storage: ParquetStorage,
    retriever: StubRetriever,
    generator: FakeGenerator,
    normal_metric_suite: FakeMetricSuite,
    nan_metric_suite: FakeMetricSuite,
    normal_rubric: FakeRubricJudge,
    nan_rubric: FakeRubricJudge,
    aux_metric: FakeDeterministicMetric,
) -> None:
    """Reloading Parquet must reconstruct EvaluationResults faithfully (§5.3)."""
    results, _ = await _run(
        storage,
        retriever,
        generator,
        normal_metric_suite,
        nan_metric_suite,
        normal_rubric,
        nan_rubric,
        aux_metric,
    )

    frame = storage.load(round_id=_ROUND_ID, phase=_PHASE)
    loaded_by_row_id = {r.answer.row_id.value: r for r in frame.results}

    for original in results:
        row_id_hex = original.answer.row_id.value
        assert row_id_hex in loaded_by_row_id, (
            f"row_id {row_id_hex[:12]}… missing after load"
        )
        loaded = loaded_by_row_id[row_id_hex]

        # Identity fields survive roundtrip exactly
        assert (
            loaded.answer.question.question_id == original.answer.question.question_id
        )
        assert loaded.answer.base.value == original.answer.base.value
        assert loaded.answer.llm.value == original.answer.llm.value
        assert loaded.answer.seed.value == original.answer.seed.value
        assert loaded.answer.phase == original.answer.phase
        assert loaded.answer.generated_answer == original.answer.generated_answer

        # final_score: NaN preserved; finite values within float32 tolerance
        if math.isnan(original.final_score.value):
            assert math.isnan(loaded.final_score.value), (
                "NaN final_score must roundtrip as NaN"
            )
        else:
            assert loaded.final_score.value == pytest.approx(
                original.final_score.value, abs=_F32_TOL
            ), f"final_score mismatch for {row_id_hex[:12]}…"

        # critical_failure_flag preserved
        assert loaded.critical_failure_flag == original.critical_failure_flag


# ---------------------------------------------------------------------------
# Test: golden final_score
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_normal_cells_have_expected_final_score(
    storage: ParquetStorage,
    retriever: StubRetriever,
    generator: FakeGenerator,
    normal_metric_suite: FakeMetricSuite,
    nan_metric_suite: FakeMetricSuite,
    normal_rubric: FakeRubricJudge,
    nan_rubric: FakeRubricJudge,
    aux_metric: FakeDeterministicMetric,
) -> None:
    """Normal cells must produce final_score == golden value (hand-calculated)."""
    results, _ = await _run(
        storage,
        retriever,
        generator,
        normal_metric_suite,
        nan_metric_suite,
        normal_rubric,
        nan_rubric,
        aux_metric,
    )

    nan_key = frozenset(_NAN_CELLS)
    for r in results:
        cell_key: NanCellKey = (
            r.answer.base.value,
            r.answer.llm.value,
            r.answer.seed.value,
            r.answer.question.question_id,
        )
        if cell_key in nan_key:
            assert math.isnan(r.final_score.value), (
                f"NaN cell {cell_key} must have NaN final_score"
            )
        else:
            assert r.final_score.value == pytest.approx(
                _NORMAL_FINAL_SCORE, abs=_F32_TOL
            ), f"final_score mismatch for cell {cell_key}"


# ---------------------------------------------------------------------------
# Test: NaN excluded and counted in n_excluded_nan
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_nan_cell_excluded_from_aggregation_and_counted(
    storage: ParquetStorage,
    retriever: StubRetriever,
    generator: FakeGenerator,
    normal_metric_suite: FakeMetricSuite,
    nan_metric_suite: FakeMetricSuite,
    normal_rubric: FakeRubricJudge,
    nan_rubric: FakeRubricJudge,
    aux_metric: FakeDeterministicMetric,
) -> None:
    """The NaN cell must be excluded from numeric aggregates and counted (ADR-007)."""
    _, aggregates = await _run(
        storage,
        retriever,
        generator,
        normal_metric_suite,
        nan_metric_suite,
        normal_rubric,
        nan_rubric,
        aux_metric,
    )

    # Find the aggregate for the config that contains the NaN cell
    nan_base, nan_llm = _GOLDEN["nan_cell"][0], _GOLDEN["nan_cell"][1]
    nan_config = next(
        agg
        for agg in aggregates
        if agg.base.value == nan_base and agg.llm.value == nan_llm
    )

    assert nan_config.n_excluded_nan == 1, (
        f"Expected 1 excluded NaN row, got {nan_config.n_excluded_nan}"
    )
    assert nan_config.n_observations == 1, (
        f"Expected 1 valid observation (the other question), "
        f"got {nan_config.n_observations}"
    )
    # The NaN cell must not infect the mean/median of the valid cell
    assert not math.isnan(nan_config.mean_score), (
        "mean_score must not be NaN when at least one valid observation exists"
    )


# ---------------------------------------------------------------------------
# Test: idempotency (ADR-009) — running twice does not duplicate rows
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_idempotency_second_run_does_not_duplicate_rows(
    storage: ParquetStorage,
    retriever: StubRetriever,
    normal_metric_suite: FakeMetricSuite,
    nan_metric_suite: FakeMetricSuite,
    normal_rubric: FakeRubricJudge,
    nan_rubric: FakeRubricJudge,
    aux_metric: FakeDeterministicMetric,
) -> None:
    """Re-running with the same run_id must not duplicate Parquet rows (ADR-009)."""
    gen1 = FakeGenerator()
    gen2 = FakeGenerator()

    # First run: writes all cells
    _results1, _ = await run_min_round(
        storage=storage,
        run_id=_RUN_ID,
        round_id=_ROUND_ID,
        questions=_QUESTIONS,
        base_ids=_BASE_IDS,
        llm_ids=_LLM_IDS,
        seeds=_SEEDS,
        phase=_PHASE,
        retriever=retriever,
        generator=gen1,
        normal_metric_suite=normal_metric_suite,
        nan_metric_suite=nan_metric_suite,
        normal_rubric=normal_rubric,
        nan_rubric=nan_rubric,
        aux_metric=aux_metric,
        nan_cells=_NAN_CELLS,
        failure_threshold=_THRESHOLD,
    )

    # Second run: same storage + same run_id → all rows already exist
    results2, _ = await run_min_round(
        storage=storage,
        run_id=_RUN_ID,
        round_id=_ROUND_ID,
        questions=_QUESTIONS,
        base_ids=_BASE_IDS,
        llm_ids=_LLM_IDS,
        seeds=_SEEDS,
        phase=_PHASE,
        retriever=retriever,
        generator=gen2,
        normal_metric_suite=normal_metric_suite,
        nan_metric_suite=nan_metric_suite,
        normal_rubric=normal_rubric,
        nan_rubric=nan_rubric,
        aux_metric=aux_metric,
        nan_cells=_NAN_CELLS,
        failure_threshold=_THRESHOLD,
    )

    # Generator must NOT have been called on the second pass (all rows exist)
    assert len(gen2.calls) == 0, (
        f"Second run made {len(gen2.calls)} generation calls; expected 0 (idempotent)"
    )

    # Storage must still hold exactly the same number of rows
    frame = storage.load(round_id=_ROUND_ID, phase=_PHASE)
    assert len(frame.results) == _TOTAL_CELLS, (
        f"After 2 runs: expected {_TOTAL_CELLS} rows, got {len(frame.results)}"
    )

    # Pass 2 always re-judges NaN cells (final_score stays NaN after judging — idempotent).
    # Normal cells are skipped (non-NaN final_score). So only NaN cells appear in results2.
    assert len(results2) == len(_NAN_CELLS), (
        f"Second run's pass 2 must re-judge only NaN cells; "
        f"expected {len(_NAN_CELLS)}, got {len(results2)}"
    )


# ---------------------------------------------------------------------------
# Test: golden aggregate values (rank_score + numeric aggregates)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_aggregate_golden_values(
    storage: ParquetStorage,
    retriever: StubRetriever,
    generator: FakeGenerator,
    normal_metric_suite: FakeMetricSuite,
    nan_metric_suite: FakeMetricSuite,
    normal_rubric: FakeRubricJudge,
    nan_rubric: FakeRubricJudge,
    aux_metric: FakeDeterministicMetric,
) -> None:
    """Aggregated ConfigAggregates must match golden hand-calculated values."""
    _, aggregates = await _run(
        storage,
        retriever,
        generator,
        normal_metric_suite,
        nan_metric_suite,
        normal_rubric,
        nan_rubric,
        aux_metric,
    )

    agg_by_key = {f"{a.base.value}|{a.llm.value}": a for a in aggregates}

    for golden_cfg in _GOLDEN["configs"]:
        key = f"{golden_cfg['base']}|{golden_cfg['llm']}"
        assert key in agg_by_key, f"Missing aggregate for {key}"
        agg = agg_by_key[key]

        assert agg.n_observations == golden_cfg["n_observations"], (
            f"{key}: n_observations {agg.n_observations} != {golden_cfg['n_observations']}"
        )
        assert agg.n_excluded_nan == golden_cfg["n_excluded_nan"], (
            f"{key}: n_excluded_nan {agg.n_excluded_nan} != {golden_cfg['n_excluded_nan']}"
        )
        assert agg.mean_score == pytest.approx(
            golden_cfg["mean_score"], abs=_F32_TOL
        ), f"{key}: mean_score mismatch"
        assert agg.median_score == pytest.approx(
            golden_cfg["median_score"], abs=_F32_TOL
        ), f"{key}: median_score mismatch"
        assert agg.min_score == pytest.approx(golden_cfg["min_score"], abs=_F32_TOL), (
            f"{key}: min_score mismatch"
        )
        if golden_cfg["iqr"] is None:
            assert math.isnan(agg.iqr), f"{key}: iqr must be NaN"
        else:
            assert agg.iqr == pytest.approx(golden_cfg["iqr"], abs=_F32_TOL), (
                f"{key}: iqr mismatch"
            )
        assert agg.failure_rate == pytest.approx(
            golden_cfg["failure_rate"], abs=_F32_TOL
        ), f"{key}: failure_rate mismatch"
        assert agg.critical_failure_rate == pytest.approx(
            golden_cfg["critical_failure_rate"], abs=_F32_TOL
        ), f"{key}: critical_failure_rate mismatch"
        assert agg.win_rate == pytest.approx(golden_cfg["win_rate"], abs=_F32_TOL), (
            f"{key}: win_rate mismatch"
        )
        assert agg.rank_score.value == pytest.approx(
            golden_cfg["rank_score"], abs=_F32_TOL
        ), f"{key}: rank_score mismatch"


# ---------------------------------------------------------------------------
# Test: no network / GPU calls by construction (structural assertion)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_no_real_ports_used(
    storage: ParquetStorage,
    retriever: StubRetriever,
    generator: FakeGenerator,
    normal_metric_suite: FakeMetricSuite,
    nan_metric_suite: FakeMetricSuite,
    normal_rubric: FakeRubricJudge,
    nan_rubric: FakeRubricJudge,
    aux_metric: FakeDeterministicMetric,
) -> None:
    """All adapters must be fake types (no real network or GPU ports)."""
    assert isinstance(retriever, StubRetriever), "retriever must be a StubRetriever"
    assert isinstance(generator, FakeGenerator), "generator must be a FakeGenerator"
    assert isinstance(normal_metric_suite, FakeMetricSuite)
    assert isinstance(nan_metric_suite, FakeMetricSuite)
    assert isinstance(normal_rubric, FakeRubricJudge)
    assert isinstance(nan_rubric, FakeRubricJudge)
    assert isinstance(aux_metric, FakeDeterministicMetric)

    # Run confirms no exception (would fail if real I/O were attempted)
    await _run(
        storage,
        retriever,
        generator,
        normal_metric_suite,
        nan_metric_suite,
        normal_rubric,
        nan_rubric,
        aux_metric,
    )
