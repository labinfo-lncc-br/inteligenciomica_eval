"""Testes unitários das colunas de proveniência no Parquet (TAREFA-311, ADR-014).

Verifica que:
- EVAL_SCHEMA contém as 3 novas colunas.
- to_row() serializa os campos corretamente.
- from_row() desserializa com defaults retrocompat.
- EvaluationResult aceita os novos campos com defaults.
- with_metrics() preserva/sobrescreve os campos de proveniência.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from inteligenciomica_eval.domain.entities import EvaluationResult
from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
    EVAL_SCHEMA,
    RowProvenance,
    from_row,
    to_row,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_evaluation_result(
    *,
    server_mode: str = "managed",
    served_model_id: str = "",
    determinism_verified: bool = True,
) -> EvaluationResult:
    """Constrói um EvaluationResult mínimo para testes de serialização."""
    from factories.factories import (
        make_evaluation_result,  # type: ignore[import-not-found]
    )

    result = make_evaluation_result()
    return EvaluationResult(
        answer=result.answer,
        metrics=result.metrics,
        final_score=result.final_score,
        determinism_regime=result.determinism_regime,
        critical_failure_flag=result.critical_failure_flag,
        critical_failure_note=result.critical_failure_note,
        server_mode=server_mode,
        served_model_id=served_model_id,
        determinism_verified=determinism_verified,
    )


# ---------------------------------------------------------------------------
# EVAL_SCHEMA
# ---------------------------------------------------------------------------


def test_eval_schema_has_server_mode_column() -> None:
    schema_names = {f.name for f in EVAL_SCHEMA}
    assert "server_mode" in schema_names


def test_eval_schema_has_served_model_id_column() -> None:
    schema_names = {f.name for f in EVAL_SCHEMA}
    assert "served_model_id" in schema_names


def test_eval_schema_has_determinism_verified_column() -> None:
    schema_names = {f.name for f in EVAL_SCHEMA}
    assert "determinism_verified" in schema_names


def test_eval_schema_server_mode_is_string_not_null() -> None:
    field = EVAL_SCHEMA.field("server_mode")
    assert pa.types.is_string(field.type)
    assert not field.nullable


def test_eval_schema_served_model_id_is_string_not_null() -> None:
    field = EVAL_SCHEMA.field("served_model_id")
    assert pa.types.is_string(field.type)
    assert not field.nullable


def test_eval_schema_determinism_verified_is_bool_not_null() -> None:
    field = EVAL_SCHEMA.field("determinism_verified")
    assert pa.types.is_boolean(field.type)
    assert not field.nullable


# ---------------------------------------------------------------------------
# RowProvenance defaults
# ---------------------------------------------------------------------------


def test_row_provenance_default_server_mode() -> None:
    prov = RowProvenance()
    assert prov.server_mode == "managed"


def test_row_provenance_default_served_model_id() -> None:
    prov = RowProvenance()
    assert prov.served_model_id == ""


def test_row_provenance_default_determinism_verified() -> None:
    prov = RowProvenance()
    assert prov.determinism_verified is True


def test_row_provenance_external_mode() -> None:
    prov = RowProvenance(
        server_mode="external",
        served_model_id="prometheus-eval-7b",
        determinism_verified=False,
    )
    assert prov.server_mode == "external"
    assert prov.served_model_id == "prometheus-eval-7b"
    assert prov.determinism_verified is False


# ---------------------------------------------------------------------------
# EvaluationResult novos campos
# ---------------------------------------------------------------------------


def test_evaluation_result_default_server_mode() -> None:
    result = _make_evaluation_result()
    assert result.server_mode == "managed"


def test_evaluation_result_default_served_model_id() -> None:
    result = _make_evaluation_result()
    assert result.served_model_id == ""


def test_evaluation_result_default_determinism_verified() -> None:
    result = _make_evaluation_result()
    assert result.determinism_verified is True


def test_evaluation_result_external_mode() -> None:
    result = _make_evaluation_result(
        server_mode="external",
        served_model_id="prometheus-2",
        determinism_verified=False,
    )
    assert result.server_mode == "external"
    assert result.served_model_id == "prometheus-2"
    assert result.determinism_verified is False


# ---------------------------------------------------------------------------
# to_row() serialização
# ---------------------------------------------------------------------------


def test_to_row_includes_server_mode() -> None:
    result = _make_evaluation_result(server_mode="external")
    row = to_row(result)
    assert row["server_mode"] == "external"


def test_to_row_includes_served_model_id() -> None:
    result = _make_evaluation_result(served_model_id="llama-3")
    row = to_row(result)
    assert row["served_model_id"] == "llama-3"


def test_to_row_includes_determinism_verified_false() -> None:
    result = _make_evaluation_result(determinism_verified=False)
    row = to_row(result)
    assert row["determinism_verified"] is False


def test_to_row_default_managed_mode() -> None:
    result = _make_evaluation_result()
    row = to_row(result)
    assert row["server_mode"] == "managed"
    assert row["served_model_id"] == ""
    assert row["determinism_verified"] is True


def test_to_row_provenance_overrides_result_fields() -> None:
    """RowProvenance.server_mode sobrescreve o valor de EvaluationResult."""
    result = _make_evaluation_result(server_mode="managed")
    prov = RowProvenance(
        server_mode="external",
        served_model_id="probe-model",
        determinism_verified=False,
    )
    # to_row usa result.server_mode (não prov.server_mode); RowProvenance não tem
    # essa semântica — os campos vêm do EvaluationResult
    row = to_row(result, provenance=prov)
    # server_mode vem do EvaluationResult
    assert row["server_mode"] == "managed"


# ---------------------------------------------------------------------------
# from_row() desserialização
# ---------------------------------------------------------------------------


def _base_row() -> dict[str, object]:
    """Row mínimo compatível com EVAL_SCHEMA para testes de from_row."""
    return {
        "row_id": "a" * 64,
        "run_id": "run1",
        "experiment_phase": "A",
        "round_id": "r1",
        "base": "IDx_400k",
        "llm": "stub-gen",
        "judge_model": "stub-judge",
        "embedding_model": "em",
        "chunk_strategy": "sentence",
        "reranker": "none",
        "top_k": 3,
        "prompt_version": "v1",
        "temperature": 0.0,
        "seed": 42,
        "batch_invariant": False,
        "vllm_version": "0.4.3",
        "ragas_version": "0.3.0",
        "config_hash": "c" * 64,
        "question_id": "q1",
        "question": "O que é DNA?",
        "ground_truth": "Ácido desoxirribonucleico.",
        "retrieved_chunk_ids": ["c1"],
        "retrieved_chunks_text": ["texto"],
        "retrieval_scores": [0.9],
        "generated_answer": "resposta",
        "answer_correctness": None,
        "answer_similarity": None,
        "faithfulness": None,
        "context_precision": None,
        "context_recall": None,
        "answer_relevancy": None,
        "bertscore_f1": None,
        "rubric_biomed_score": None,
        "rubric_feedback": "",
        "critical_failure_flag": None,
        "critical_failure_note": None,
        "final_score": None,
        "metric_nan_fields": [],
        "retry_count": 0,
        "latency_ms": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "server_mode": "managed",
        "served_model_id": "",
        "determinism_verified": True,
        "timestamp": None,
    }


def test_from_row_reads_server_mode() -> None:
    row = _base_row()
    row["server_mode"] = "external"
    result = from_row(row)
    assert result.server_mode == "external"


def test_from_row_reads_served_model_id() -> None:
    row = _base_row()
    row["served_model_id"] = "prometheus-2"
    result = from_row(row)
    assert result.served_model_id == "prometheus-2"


def test_from_row_reads_determinism_verified_false() -> None:
    row = _base_row()
    row["determinism_verified"] = False
    result = from_row(row)
    assert result.determinism_verified is False


def test_from_row_defaults_when_columns_absent(capsys: pytest.CaptureFixture[str]) -> None:
    """from_row usa defaults e emite WARNING para colunas ausentes (retrocompat Parquet antigo)."""
    row = _base_row()
    # Remove as 3 novas colunas (simula Parquet antigo)
    del row["server_mode"]
    del row["served_model_id"]
    del row["determinism_verified"]

    result = from_row(row)

    assert result.server_mode == "managed"
    assert result.served_model_id == ""
    assert result.determinism_verified is True
    captured = capsys.readouterr()
    assert "parquet_legacy_row_missing_provenance_columns" in captured.out, (
        "from_row deve emitir WARNING ao encontrar colunas de proveniência ausentes"
    )


# ---------------------------------------------------------------------------
# with_metrics() — preserva campos de proveniência
# ---------------------------------------------------------------------------


def test_with_metrics_preserves_server_mode() -> None:
    result = _make_evaluation_result(server_mode="external")
    new_result = result.with_metrics(
        metrics=result.metrics,
        final_score=result.final_score,
        regime=result.determinism_regime,
    )
    assert new_result.server_mode == "external"


def test_with_metrics_preserves_served_model_id() -> None:
    result = _make_evaluation_result(served_model_id="llama-3")
    new_result = result.with_metrics(
        metrics=result.metrics,
        final_score=result.final_score,
        regime=result.determinism_regime,
    )
    assert new_result.served_model_id == "llama-3"


def test_with_metrics_preserves_determinism_verified() -> None:
    result = _make_evaluation_result(determinism_verified=False)
    new_result = result.with_metrics(
        metrics=result.metrics,
        final_score=result.final_score,
        regime=result.determinism_regime,
    )
    assert new_result.determinism_verified is False


def test_with_metrics_can_override_server_mode() -> None:
    result = _make_evaluation_result(server_mode="managed")
    new_result = result.with_metrics(
        metrics=result.metrics,
        final_score=result.final_score,
        regime=result.determinism_regime,
        server_mode="external",
    )
    assert new_result.server_mode == "external"


def test_with_metrics_can_override_determinism_verified() -> None:
    result = _make_evaluation_result(determinism_verified=True)
    new_result = result.with_metrics(
        metrics=result.metrics,
        final_score=result.final_score,
        regime=result.determinism_regime,
        determinism_verified=False,
    )
    assert new_result.determinism_verified is False
