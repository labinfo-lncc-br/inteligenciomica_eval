from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import structlog

from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
)
from inteligenciomica_eval.domain.errors import StorageError
from inteligenciomica_eval.domain.ports import ResultFrame
from inteligenciomica_eval.domain.value_objects import (
    BaseId,
    DeterminismRegime,
    FinalScore,
    LLMId,
    MetricVector,
    RowId,
    Seed,
)

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# PyArrow schema — §5.3 tidy schema with explicit nullability.
# Metric float32 columns: nullable=True so NULL means "not yet computed" (§5.4
# "WHERE answer_correctness IS NULL"). NaN (computation failure after judging)
# is also mapped to NULL on write and reconstructed to NaN on read via
# _nan_to_none / _none_to_nan, preserving the semantic distinction from
# int8 NULL (critical_failure_flag not yet annotated).
# ---------------------------------------------------------------------------

EVAL_SCHEMA: pa.Schema = pa.schema(
    [
        pa.field("row_id", pa.string(), nullable=False),
        pa.field("run_id", pa.string(), nullable=False),
        pa.field("experiment_phase", pa.string(), nullable=False),
        pa.field("round_id", pa.string(), nullable=False),
        pa.field("base", pa.string(), nullable=False),
        pa.field("llm", pa.string(), nullable=False),
        pa.field("judge_model", pa.string(), nullable=False),
        pa.field("embedding_model", pa.string(), nullable=False),
        pa.field("chunk_strategy", pa.string(), nullable=False),
        pa.field("reranker", pa.string(), nullable=False),
        pa.field("top_k", pa.int32(), nullable=False),
        pa.field("prompt_version", pa.string(), nullable=False),
        pa.field("temperature", pa.float32(), nullable=False),
        pa.field("seed", pa.int32(), nullable=False),
        pa.field("batch_invariant", pa.bool_(), nullable=False),
        pa.field("vllm_version", pa.string(), nullable=False),
        pa.field("ragas_version", pa.string(), nullable=False),
        pa.field("config_hash", pa.string(), nullable=False),
        pa.field("question_id", pa.string(), nullable=False),
        pa.field("question", pa.string(), nullable=False),
        pa.field("ground_truth", pa.string(), nullable=False),
        pa.field("retrieved_chunk_ids", pa.list_(pa.string()), nullable=False),
        pa.field("retrieved_chunks_text", pa.list_(pa.string()), nullable=False),
        pa.field("retrieval_scores", pa.list_(pa.float32()), nullable=False),
        pa.field("generated_answer", pa.string(), nullable=False),
        pa.field("answer_correctness", pa.float32(), nullable=True),
        pa.field("answer_similarity", pa.float32(), nullable=True),
        pa.field("faithfulness", pa.float32(), nullable=True),
        pa.field("context_precision", pa.float32(), nullable=True),
        pa.field("context_recall", pa.float32(), nullable=True),
        pa.field("answer_relevancy", pa.float32(), nullable=True),
        pa.field("bertscore_f1", pa.float32(), nullable=True),
        pa.field("rubric_biomed_score", pa.float32(), nullable=True),
        pa.field("rubric_feedback", pa.string(), nullable=False),
        pa.field("critical_failure_flag", pa.int8(), nullable=True),
        pa.field("critical_failure_note", pa.string(), nullable=True),
        pa.field("final_score", pa.float32(), nullable=True),
        pa.field("metric_nan_fields", pa.list_(pa.string()), nullable=False),
        pa.field("retry_count", pa.int8(), nullable=False),
        pa.field("latency_ms", pa.int32(), nullable=False),
        pa.field("tokens_in", pa.int32(), nullable=False),
        pa.field("tokens_out", pa.int32(), nullable=False),
        pa.field("timestamp", pa.timestamp("us", tz="UTC"), nullable=False),
    ]
)

_METRIC_FIELDS: tuple[str, ...] = (
    "answer_correctness",
    "answer_similarity",
    "faithfulness",
    "context_precision",
    "context_recall",
    "answer_relevancy",
    "bertscore_f1",
    "rubric_biomed_score",
)

_PATH_RE: re.Pattern[str] = re.compile(r"(/[^\s:,]+)+")


# ---------------------------------------------------------------------------
# Provenance container
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RowProvenance:
    """Config and execution provenance not carried by EvaluationResult (§5.3).

    Args:
        run_id: identifier of the complete evaluation run.
        round_id: identifier of the evaluation round (e.g. ``"round_1"``).
        judge_model: name of the LLM judge model.
        embedding_model: embedding model used for retrieval.
        chunk_strategy: chunking strategy descriptor.
        reranker: reranker name, or ``"none"`` when absent.
        top_k: number of chunks retrieved.
        prompt_version: version tag of the RAG prompt template.
        temperature: generator temperature.
        vllm_version: vLLM version string for reproducibility.
        ragas_version: RAGAS version string for reproducibility.
        config_hash: SHA-256 of the canonical round config YAML.
    """

    run_id: str = ""
    round_id: str = ""
    judge_model: str = ""
    embedding_model: str = ""
    chunk_strategy: str = ""
    reranker: str = "none"
    top_k: int = 0
    prompt_version: str = ""
    temperature: float = 0.0
    vllm_version: str = "unknown"
    ragas_version: str = "unknown"
    config_hash: str = ""


# ---------------------------------------------------------------------------
# NaN / None bridge
# ---------------------------------------------------------------------------


def _nan_to_none(v: float) -> float | None:
    """Map Python NaN to None so Parquet stores NULL for nullable float columns."""
    return None if math.isnan(v) else v


def _none_to_nan(v: float | None) -> float:
    """Map Parquet NULL (Python None) back to NaN for MetricVector reconstruction."""
    return float("nan") if v is None else float(v)


def _safe_msg(exc: Exception) -> str:
    """Return a path-free error message to avoid leaking filesystem layout."""
    return _PATH_RE.sub("<path>", str(exc))


# ---------------------------------------------------------------------------
# Row mapper  — EvaluationResult <-> dict[str, Any]
# ---------------------------------------------------------------------------


def to_row(
    result: EvaluationResult,
    provenance: RowProvenance | None = None,
) -> dict[str, Any]:  # Any: heterogeneous Parquet column types
    """Serialize an EvaluationResult to a flat dict conforming to EVAL_SCHEMA.

    NaN metrics and NaN final_score are stored as None (Parquet NULL) so that
    §5.4 "WHERE answer_correctness IS NULL" filtering works.  The semantic
    distinction from ``critical_failure_flag=None`` (int8 NULL) is maintained
    by column type: float NULL → NaN on read; int8 NULL → None on read.

    Args:
        result: evaluation result to serialize.
        provenance: config/execution provenance; defaults to empty RowProvenance.

    Returns:
        Dict whose keys match every column in EVAL_SCHEMA.
    """
    prov = provenance or RowProvenance()
    ans = result.answer
    m = result.metrics
    return {
        "row_id": ans.row_id.value,
        "run_id": prov.run_id,
        "experiment_phase": ans.phase,
        "round_id": prov.round_id,
        "base": ans.base.value,
        "llm": ans.llm.value,
        "judge_model": prov.judge_model,
        "embedding_model": prov.embedding_model,
        "chunk_strategy": prov.chunk_strategy,
        "reranker": prov.reranker,
        "top_k": prov.top_k,
        "prompt_version": prov.prompt_version,
        "temperature": prov.temperature,
        "seed": ans.seed.value,
        # Fonte única: property derivada de determinism_regime (§4.3, TAREFA-022).
        # Valor idêntico ao cálculo anterior — sem mudança de comportamento.
        "batch_invariant": result.batch_invariant,
        "vllm_version": prov.vllm_version,
        "ragas_version": prov.ragas_version,
        "config_hash": prov.config_hash,
        "question_id": ans.question.question_id,
        "question": ans.question.text,
        "ground_truth": ans.question.ground_truth,
        "retrieved_chunk_ids": list(ans.retrieved_chunk_ids),
        "retrieved_chunks_text": list(ans.retrieved_chunks_text),
        "retrieval_scores": list(ans.retrieval_scores),
        "generated_answer": ans.generated_answer,
        # NaN → NULL: enables §5.4 WHERE IS NULL filtering
        "answer_correctness": _nan_to_none(m.answer_correctness),
        "answer_similarity": _nan_to_none(m.answer_similarity),
        "faithfulness": _nan_to_none(m.faithfulness),
        "context_precision": _nan_to_none(m.context_precision),
        "context_recall": _nan_to_none(m.context_recall),
        "answer_relevancy": _nan_to_none(m.answer_relevancy),
        "bertscore_f1": _nan_to_none(m.bertscore_f1),
        "rubric_biomed_score": _nan_to_none(m.rubric_biomed_score),
        # Not in EvaluationResult — filled by rubric adapter in M2+; "" until then
        "rubric_feedback": "",
        # int8 NULL = not yet annotated (distinct semantic from float NULL above)
        "critical_failure_flag": result.critical_failure_flag,
        "critical_failure_note": result.critical_failure_note,
        "final_score": _nan_to_none(result.final_score.value),
        "metric_nan_fields": list(m.nan_fields()),
        # Not in EvaluationResult — filled by generation adapter in M1+; 0 until then
        "retry_count": 0,
        "latency_ms": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "timestamp": datetime.now(UTC),
    }


def from_row(row: dict[str, Any]) -> EvaluationResult:  # Any: heterogeneous Parquet row
    """Deserialize a flat Parquet row dict to an EvaluationResult.

    Parquet NULL metric columns become NaN (float).  Parquet NULL
    ``critical_failure_flag`` becomes Python None.  ``determinism_regime`` is
    inferred from the stored ``batch_invariant`` boolean.

    Args:
        row: dict with keys matching EVAL_SCHEMA column names.

    Returns:
        Reconstructed :class:`EvaluationResult`.
    """
    question = Question(
        question_id=str(row["question_id"]),
        text=str(row["question"]),
        ground_truth=str(row["ground_truth"]),
    )
    answer = GeneratedAnswer(
        row_id=RowId(value=str(row["row_id"])),
        question=question,
        base=BaseId(str(row["base"])),
        llm=LLMId(str(row["llm"])),
        seed=Seed(int(row["seed"])),
        phase=str(row["experiment_phase"]),
        generated_answer=str(row["generated_answer"]),
        retrieved_chunk_ids=tuple(str(x) for x in row["retrieved_chunk_ids"]),
        retrieved_chunks_text=tuple(str(x) for x in row["retrieved_chunks_text"]),
        retrieval_scores=tuple(float(x) for x in row["retrieval_scores"]),
    )
    metrics = MetricVector(
        answer_correctness=_none_to_nan(row.get("answer_correctness")),
        answer_similarity=_none_to_nan(row.get("answer_similarity")),
        faithfulness=_none_to_nan(row.get("faithfulness")),
        context_precision=_none_to_nan(row.get("context_precision")),
        context_recall=_none_to_nan(row.get("context_recall")),
        answer_relevancy=_none_to_nan(row.get("answer_relevancy")),
        bertscore_f1=_none_to_nan(row.get("bertscore_f1")),
        rubric_biomed_score=_none_to_nan(row.get("rubric_biomed_score")),
    )
    final_score = FinalScore(_none_to_nan(row.get("final_score")))

    batch_inv = row.get("batch_invariant", True)
    regime = DeterminismRegime.JUDGE if batch_inv else DeterminismRegime.GENERATOR

    raw_flag = row.get("critical_failure_flag")
    flag: int | None = int(raw_flag) if raw_flag is not None else None

    return EvaluationResult(
        answer=answer,
        metrics=metrics,
        final_score=final_score,
        determinism_regime=regime,
        critical_failure_flag=flag,
        critical_failure_note=row.get("critical_failure_note"),
    )


# ---------------------------------------------------------------------------
# Table builder helper
# ---------------------------------------------------------------------------


def _row_to_table(row: dict[str, Any]) -> pa.Table:  # Any: heterogeneous column values
    """Convert a single-row dict to a typed PyArrow Table conforming to EVAL_SCHEMA.

    Args:
        row: dict with a value for every EVAL_SCHEMA column.

    Returns:
        Single-row :class:`pa.Table`.
    """
    arrays: dict[str, pa.Array] = {
        field.name: pa.array([row[field.name]], type=field.type)
        for field in EVAL_SCHEMA
    }
    return pa.table(arrays, schema=EVAL_SCHEMA)


# ---------------------------------------------------------------------------
# ParquetStorage
# ---------------------------------------------------------------------------


class ParquetStorage:
    """Parquet-backed persistence for EvaluationResult rows (§5.3, ADR-002, ADR-009).

    Implements both ``ResultWriterPort`` and ``ResultReaderPort`` against a
    local directory tree partitioned as:
    ``{base_dir}/round_id={r}/experiment_phase={p}/base={b}/llm={l}/``

    **Idempotency (ADR-009):** each row is written to its own file named
    ``{row_id_hex}.parquet``.  ``append`` is last-write-wins: if the file
    already exists it is overwritten.  The pipeline use-case consults
    :meth:`exists` to skip upstream computation; ``append`` itself never
    silently drops data.  Re-running with the same ``run_id`` resumes without
    duplicating rows.

    **Thread / process safety:** not safe for concurrent writes (M0 scope).

    Args:
        base_dir: root directory for all Parquet files.
        run_id: identifier of the complete evaluation run.
        round_id: identifier of the round (used for partitioning and ``load``).
        judge_model: LLM judge model name.
        embedding_model: embedding model used for retrieval.
        chunk_strategy: chunking strategy descriptor.
        reranker: reranker name, or ``"none"`` when absent.
        top_k: number of retrieved chunks.
        prompt_version: version tag of the RAG prompt template.
        temperature: generator temperature.
        vllm_version: vLLM version string.
        ragas_version: RAGAS version string.
        config_hash: SHA-256 of the canonical round config YAML.
    """

    def __init__(
        self,
        base_dir: Path,
        *,
        run_id: str = "",
        round_id: str = "",
        judge_model: str = "",
        embedding_model: str = "",
        chunk_strategy: str = "",
        reranker: str = "none",
        top_k: int = 0,
        prompt_version: str = "",
        temperature: float = 0.0,
        vllm_version: str = "unknown",
        ragas_version: str = "unknown",
        config_hash: str = "",
    ) -> None:
        self._base_dir = base_dir
        self._provenance = RowProvenance(
            run_id=run_id,
            round_id=round_id,
            judge_model=judge_model,
            embedding_model=embedding_model,
            chunk_strategy=chunk_strategy,
            reranker=reranker,
            top_k=top_k,
            prompt_version=prompt_version,
            temperature=temperature,
            vllm_version=vllm_version,
            ragas_version=ragas_version,
            config_hash=config_hash,
        )
        self._log: structlog.stdlib.BoundLogger = log.bind(
            component="ParquetStorage",
            run_id=run_id,
            round_id=round_id,
        )

    # ------------------------------------------------------------------
    # ResultWriterPort
    # ------------------------------------------------------------------

    def append(self, result: EvaluationResult) -> None:
        """Persist an evaluation row using last-write-wins semantics (ADR-009).

        Writes ``{partition_dir}/{row_id}.parquet``.  If the file already
        exists it is **overwritten** (last-write-wins): the caller (pipeline
        use-case) is responsible for consulting :meth:`exists` beforehand and
        skipping the upstream computation when the row is already complete.
        ``append`` itself never silently drops data.

        Args:
            result: evaluation result to persist.

        Raises:
            StorageError: on any I/O failure.
        """
        row_id_hex = result.answer.row_id.value
        try:
            row = to_row(result, self._provenance)
            table = _row_to_table(row)

            partition_dir = (
                self._base_dir
                / f"round_id={row['round_id']}"
                / f"experiment_phase={row['experiment_phase']}"
                / f"base={row['base']}"
                / f"llm={row['llm']}"
            )
            partition_dir.mkdir(parents=True, exist_ok=True)
            file_path = partition_dir / f"{row_id_hex}.parquet"
            is_overwrite = file_path.exists()
            pq.write_table(table, file_path)
            if is_overwrite:
                self._log.info("row_overwritten", row_id=row_id_hex[:12])
            else:
                self._log.info("row_appended", row_id=row_id_hex[:12])

        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("append", _safe_msg(exc)) from exc

    def update_metrics(
        self,
        row_id: RowId,
        metrics: MetricVector,
        final_score: FinalScore,
        regime: DeterminismRegime,
    ) -> None:
        """Update metrics, final_score and regime of an existing row (§5.4).

        Promoted in TAREFA-026 (retroactive PR): besides the eight metric columns
        and ``metric_nan_fields``, also overwrites ``final_score`` and the derived
        ``batch_invariant`` (§4.3: ``regime is JUDGE``). All other columns
        (provenance, answer, flags) are left unchanged. NaN ``final_score`` (ADR-007
        NaN-sentinel) becomes NULL on write, like the metric columns.

        Args:
            row_id: identifier of the row to update.
            metrics: new metric values; NaN fields become NULL in Parquet.
            final_score: aggregated final score from the judging pass (NaN → NULL).
            regime: judge determinism regime — drives ``batch_invariant``.

        Raises:
            StorageError: if the row does not exist or on I/O failure.
        """
        try:
            file_path = self._find_file(row_id.value)
            if file_path is None:
                raise StorageError(
                    "update_metrics",
                    f"Row {row_id.value[:12]}… not found — run append first",
                )

            # ParquetFile.read() bypasses Hive partition auto-detection that
            # would conflict with columns already stored in the file.
            table = pq.ParquetFile(file_path).read()
            nan_fields_list: list[str] = list(metrics.nan_fields())

            update_values: dict[str, list[Any]] = {  # Any: mixed float/None/list
                "answer_correctness": [_nan_to_none(metrics.answer_correctness)],
                "answer_similarity": [_nan_to_none(metrics.answer_similarity)],
                "faithfulness": [_nan_to_none(metrics.faithfulness)],
                "context_precision": [_nan_to_none(metrics.context_precision)],
                "context_recall": [_nan_to_none(metrics.context_recall)],
                "answer_relevancy": [_nan_to_none(metrics.answer_relevancy)],
                "bertscore_f1": [_nan_to_none(metrics.bertscore_f1)],
                "rubric_biomed_score": [_nan_to_none(metrics.rubric_biomed_score)],
                "metric_nan_fields": [nan_fields_list],
                "final_score": [_nan_to_none(final_score.value)],
                # §4.3 invariant: batch_invariant ⟺ regime is JUDGE (TAREFA-022).
                "batch_invariant": [regime is DeterminismRegime.JUDGE],
            }

            for col_name, values in update_values.items():
                col_idx = table.schema.get_field_index(col_name)
                pa_type = EVAL_SCHEMA.field(col_name).type
                table = table.set_column(
                    col_idx, col_name, pa.array(values, type=pa_type)
                )

            pq.write_table(table, file_path)
            self._log.info(
                "metrics_updated",
                row_id=row_id.value[:12],
                batch_invariant=regime is DeterminismRegime.JUDGE,
            )

        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("update_metrics", _safe_msg(exc)) from exc

    def exists(self, row_id: RowId) -> bool:
        """Return True if the row exists and its generated_answer is non-null.

        Completeness criterion (ADR-009): file present AND generated_answer
        non-null signals that the generation pass has written this row.

        Args:
            row_id: identifier to look up.

        Returns:
            ``True`` if the row is present and complete.

        Raises:
            StorageError: on unexpected I/O errors.
        """
        try:
            file_path = self._find_file(row_id.value)
            if file_path is None:
                return False
            table = pq.ParquetFile(file_path).read(columns=["generated_answer"])
            col = table.column("generated_answer")
            return len(col) > 0 and col[0].as_py() is not None
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("exists", _safe_msg(exc)) from exc

    # ------------------------------------------------------------------
    # ResultReaderPort
    # ------------------------------------------------------------------

    def load(self, *, round_id: str, phase: str | None = None) -> ResultFrame:
        """Load all results for a round, optionally filtered by phase.

        Args:
            round_id: identifier of the round to load (e.g. ``"round_1"``).
            phase: ``"A"`` or ``"B"``; ``None`` loads both phases.

        Returns:
            :class:`ResultFrame` with reconstructed :class:`EvaluationResult` objects.

        Raises:
            StorageError: on I/O failure.
        """
        try:
            round_dir = self._base_dir / f"round_id={round_id}"
            if not round_dir.exists():
                return ResultFrame(results=())

            search_root = (
                round_dir / f"experiment_phase={phase}" if phase else round_dir
            )
            if not search_root.exists():
                return ResultFrame(results=())

            files = sorted(search_root.rglob("*.parquet"))
            if not files:
                return ResultFrame(results=())

            tables = [pq.ParquetFile(f).read() for f in files]
            combined = pa.concat_tables(tables)
            rows_dict = combined.to_pydict()
            n = len(rows_dict["row_id"])
            results = tuple(
                from_row({k: v[i] for k, v in rows_dict.items()}) for i in range(n)
            )
            return ResultFrame(results=results)

        except StorageError:
            raise
        except Exception as exc:
            raise StorageError("load", _safe_msg(exc)) from exc

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_file(self, row_id_hex: str) -> Path | None:
        """Locate the Parquet file for row_id_hex via recursive glob.

        Args:
            row_id_hex: 64-char hex SHA-256 digest.

        Returns:
            :class:`Path` or ``None`` if not found.
        """
        if not self._base_dir.exists():
            return None
        matches = list(self._base_dir.rglob(f"{row_id_hex}.parquet"))
        return matches[0] if matches else None
