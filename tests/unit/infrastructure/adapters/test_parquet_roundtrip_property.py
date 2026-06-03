"""Property-based tests para ``ParquetStorage`` (roundtrip e idempotência).

Verifica três propriedades sobre ``ParquetStorage.append`` / ``load`` / ``exists``:

P4.1 — Roundtrip: ``load()`` após ``append()`` recupera o resultado original
       (comparação NaN-safe; métricas restritas a valores float32-seguros).
P4.2 — Idempotência por ``row_id`` (ADR-009): dois ``append`` com o mesmo
       resultado → ``load()`` retorna exatamente 1 linha.
P4.3 — ``exists()`` retorna ``False`` antes de qualquer escrita e ``True``
       imediatamente após ``append``.

Todos os testes usam ``tempfile.TemporaryDirectory`` internamente para isolar
cada exemplo do hypothesis — não dependem da fixture ``tmp_path`` do pytest,
que não é recriada entre exemplos hypothesis.
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest
from factories.factories import make_evaluation_result, make_generated_answer
from hypothesis import given, settings
from hypothesis import strategies as st

from inteligenciomica_eval.domain.value_objects import DeterminismRegime, MetricVector
from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
    ParquetStorage,
)

# ---------------------------------------------------------------------------
# Estratégias hypothesis
# ---------------------------------------------------------------------------

# Valores que sobrevivem à conversão float64→float32→float64 sem perda de precisão
_SAFE_METRIC = st.sampled_from([0.0, 0.25, 0.5, 0.75, 1.0, float("nan")])
_SAFE_SCORE = st.sampled_from([0.0, 0.25, 0.5, 0.75, 1.0, float("nan")])

# Seeds e question_ids simples para gerar row_ids distintos
_SEED = st.integers(min_value=0, max_value=999)
_QID = st.from_regex(r"[a-z][a-z0-9]{0,8}", fullmatch=True)


@st.composite
def _evaluation_result(draw: st.DrawFn) -> object:
    """Gera um EvaluationResult com métricas float32-seguras."""
    seed_val: int = draw(_SEED)
    qid: str = draw(_QID)
    metrics = MetricVector(
        answer_correctness=draw(_SAFE_METRIC),
        answer_similarity=draw(_SAFE_METRIC),
        faithfulness=draw(_SAFE_METRIC),
        context_precision=draw(_SAFE_METRIC),
        context_recall=draw(_SAFE_METRIC),
        answer_relevancy=draw(_SAFE_METRIC),
        bertscore_f1=draw(_SAFE_METRIC),
        rubric_biomed_score=draw(_SAFE_METRIC),
    )
    final_score_val: float = draw(_SAFE_SCORE)
    return make_evaluation_result(
        answer=make_generated_answer(
            seed=seed_val,
            question_id=qid,
            retrieval_scores=(0.5,),  # valor float32-seguro fixo
        ),
        metrics=metrics,
        final_score=final_score_val,
        determinism_regime=DeterminismRegime.GENERATOR,
    )


# ---------------------------------------------------------------------------
# Helpers de comparação NaN-safe
# ---------------------------------------------------------------------------


def _feq(a: float, b: float) -> bool:
    """Igualdade float com suporte a NaN."""
    return (math.isnan(a) and math.isnan(b)) or a == b


def _mv_eq(a: MetricVector, b: MetricVector) -> bool:
    """Igualdade NaN-safe entre dois MetricVectors."""
    fields = (
        "answer_correctness",
        "answer_similarity",
        "faithfulness",
        "context_precision",
        "context_recall",
        "answer_relevancy",
        "bertscore_f1",
        "rubric_biomed_score",
    )
    return all(_feq(getattr(a, f), getattr(b, f)) for f in fields)


def _result_eq(original: object, loaded: object) -> bool:
    """Comparação NaN-safe entre dois EvaluationResult após roundtrip Parquet.

    Cobre todos os campos serializados em EVAL_SCHEMA, com NaN-safe apenas onde
    necessário (métricas float32, final_score).  Campos de anotação
    (critical_failure_flag, critical_failure_note) e tuplas de retrieval são
    comparados com igualdade exata.
    """
    from inteligenciomica_eval.domain.entities import EvaluationResult

    assert isinstance(original, EvaluationResult)
    assert isinstance(loaded, EvaluationResult)

    oa, la = original.answer, loaded.answer

    ans_ok = (
        oa.row_id.value == la.row_id.value
        and oa.question.question_id == la.question.question_id
        and oa.question.text == la.question.text
        and oa.question.ground_truth == la.question.ground_truth
        and oa.base.value == la.base.value
        and oa.llm.value == la.llm.value
        and oa.seed.value == la.seed.value
        and oa.phase == la.phase
        and oa.generated_answer == la.generated_answer
        # Tuplas de retrieval: strings são exatas; scores são float32-seguros
        and oa.retrieved_chunk_ids == la.retrieved_chunk_ids
        and oa.retrieved_chunks_text == la.retrieved_chunks_text
        and tuple(oa.retrieval_scores) == tuple(la.retrieval_scores)
    )
    metrics_ok = _mv_eq(original.metrics, loaded.metrics)
    score_ok = _feq(original.final_score.value, loaded.final_score.value)
    regime_ok = original.determinism_regime == loaded.determinism_regime
    # Campos de anotação: None ↔ int8 NULL / string NULL — exatos
    annotation_ok = (
        original.critical_failure_flag == loaded.critical_failure_flag
        and original.critical_failure_note == loaded.critical_failure_note
    )
    return ans_ok and metrics_ok and score_ok and regime_ok and annotation_ok


# ---------------------------------------------------------------------------
# P4.1 — Roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(result=_evaluation_result())
@settings(max_examples=50, database=None)
def test_parquet_roundtrip(result: object) -> None:
    """P4.1: Resultado lido após append é igual ao original (NaN-safe)."""
    from inteligenciomica_eval.domain.entities import EvaluationResult

    assert isinstance(result, EvaluationResult)

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ParquetStorage(
            base_dir=Path(tmpdir),
            run_id="test-run",
            round_id="round_1",
        )
        storage.append(result)

        frame = storage.load(round_id="round_1")
        assert len(frame.results) == 1

        loaded = frame.results[0]
        assert _result_eq(result, loaded), (
            f"Roundtrip falhou para row_id={result.answer.row_id.value[:12]}…"
        )


# ---------------------------------------------------------------------------
# P4.2 — Idempotência por row_id (ADR-009): dois writes → 1 linha
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(result=_evaluation_result())
@settings(max_examples=50, database=None)
def test_parquet_idempotency_by_row_id(result: object) -> None:
    """P4.2: Dois appends do mesmo resultado → load retorna exatamente 1 linha."""
    from inteligenciomica_eval.domain.entities import EvaluationResult

    assert isinstance(result, EvaluationResult)

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ParquetStorage(
            base_dir=Path(tmpdir),
            run_id="test-run",
            round_id="round_1",
        )
        storage.append(result)
        storage.append(result)  # segunda escrita com mesmo row_id → last-write-wins

        frame = storage.load(round_id="round_1")
        assert len(frame.results) == 1, (
            f"Esperado 1 linha após dois appends do mesmo row_id, "
            f"obtido {len(frame.results)}"
        )


# ---------------------------------------------------------------------------
# P4.3 — exists() antes e depois do append
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(result=_evaluation_result())
@settings(max_examples=50, database=None)
def test_parquet_exists_before_and_after(result: object) -> None:
    """P4.3: exists() == False antes do append e True após."""
    from inteligenciomica_eval.domain.entities import EvaluationResult

    assert isinstance(result, EvaluationResult)

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = ParquetStorage(
            base_dir=Path(tmpdir),
            run_id="test-run",
            round_id="round_1",
        )
        row_id = result.answer.row_id

        assert not storage.exists(row_id), "exists() deve ser False antes do append"

        storage.append(result)

        assert storage.exists(row_id), "exists() deve ser True após o append"
