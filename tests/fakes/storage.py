from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from inteligenciomica_eval.domain.entities import EvaluationResult
from inteligenciomica_eval.domain.ports import ResultFrame
from inteligenciomica_eval.domain.value_objects import (
    DeterminismRegime,
    FinalScore,
    MetricVector,
    RowId,
)


@dataclass
class _StoredRow:
    result: EvaluationResult
    round_id: str


class InMemoryResultStore:
    """Shared backing store for InMemoryResultWriter and InMemoryResultReader.

    Create one store instance and inject it into both writer and reader to make
    them share state in E2E tests — mirrors the role of the Parquet directory.
    """

    def __init__(self) -> None:
        self._rows: dict[str, _StoredRow] = {}

    @property
    def size(self) -> int:
        """Number of rows currently held in the store."""
        return len(self._rows)


class InMemoryResultWriter:
    """In-memory ResultWriterPort mirroring ParquetStorage's write contract.

    Implements append / update_metrics / exists against a shared InMemoryResultStore
    so a paired InMemoryResultReader over the same store observes all changes.

    Args:
        store: shared backing store (one per test or test-session scope as needed).
        round_id: round identifier tagged to every appended row, mirroring the
            ParquetStorage constructor parameter of the same name.
    """

    def __init__(
        self,
        store: InMemoryResultStore,
        *,
        round_id: str = "round_1",
    ) -> None:
        self._store = store
        self._round_id = round_id

    def append(self, result: EvaluationResult) -> None:
        """Persist a new evaluation row (last-write-wins, mirrors ADR-009).

        Args:
            result: evaluation result to persist.
        """
        self._store._rows[result.answer.row_id.value] = _StoredRow(
            result=result,
            round_id=self._round_id,
        )

    def update_metrics(
        self,
        row_id: RowId,
        metrics: MetricVector,
        final_score: FinalScore,
        regime: DeterminismRegime,
        *,
        critical_failure_flag: int | None = None,
        critical_failure_note: str | None = None,
    ) -> None:
        """Update metrics, final_score, regime and optional human annotation.

        Mirrors the evolved ``ResultWriterPort.update_metrics`` contract
        (TAREFA-026 + TAREFA-308): persists métricas, ``final_score``, ``regime``
        e, opcionalmente, anotação humana de Camada 3 (ADR-010).

        Args:
            row_id: identifier of the row to update.
            metrics: new metric vector to apply.
            final_score: aggregated final score from the judging pass.
            regime: judge determinism regime.
            critical_failure_flag: human annotation flag (0 or 1); None = no update.
            critical_failure_note: annotation note text; None = no update.

        Raises:
            KeyError: if the row has not been appended yet.
        """
        stored = self._store._rows[row_id.value]
        result = stored.result.with_metrics(metrics, final_score, regime)
        if critical_failure_flag is not None:
            result = result.with_human_annotation(
                critical_failure_flag, critical_failure_note
            )
        self._store._rows[row_id.value] = dataclasses.replace(stored, result=result)

    def exists(self, row_id: RowId) -> bool:
        """Return True if the row has been appended.

        Args:
            row_id: identifier to look up.

        Returns:
            True when the row is present in the store.
        """
        return row_id.value in self._store._rows


class InMemoryResultReader:
    """In-memory ResultReaderPort reading from a shared InMemoryResultStore.

    Args:
        store: shared backing store populated by InMemoryResultWriter.
    """

    def __init__(self, store: InMemoryResultStore) -> None:
        self._store = store

    def load(self, *, round_id: str, phase: str | None = None) -> ResultFrame:
        """Return all results matching round_id and optional experiment phase.

        Args:
            round_id: round identifier to filter on.
            phase: experiment phase (``"A"`` or ``"B"``); ``None`` returns both.

        Returns:
            ResultFrame with matching EvaluationResult objects.
        """
        results = tuple(
            row.result
            for row in self._store._rows.values()
            if row.round_id == round_id
            and (phase is None or row.result.answer.phase == phase)
        )
        return ResultFrame(results=results)
