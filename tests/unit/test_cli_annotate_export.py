"""Testes unitários dos subcomandos `annotate --export` e `annotate --ingest` (TAREFA-401/402, ADR-010)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from factories import make_evaluation_result, make_generated_answer, make_row_id
from fakes.storage import (
    InMemoryResultReader,
    InMemoryResultStore,
    InMemoryResultWriter,
)
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from inteligenciomica_eval.cli import app

runner = CliRunner()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ROUND_ID = "round_401"
_RUN_ID = "run-export-test"
_THRESHOLD = 0.70

_VALID_CONFIG: dict[object, object] = {
    "round_id": _ROUND_ID,
    "phases": ["A"],
    "bases": ["IDx_400k"],
    "llms": ["llama3-8b"],
    "seeds": [42],
    "temperature": 0.0,
    "retrieval": {
        "top_k": 3,
        "reranker": None,
        "embedding_model": "embed-v1",
        "chunk_strategy": "sliding",
    },
    "judge": {
        "model": "judge-model",
        "endpoint_env": "VLLM_JUDGE_URL",
        "batch_invariant": True,
        "temperature": 0.0,
    },
    "scoring": {
        "weights": {"answer_correctness": 0.6, "faithfulness": 0.4},
        "failure_threshold": 0.3,
    },
}

# Scores for the 10 synthetic results
# 4 with final_score < 0.70 (indices 0-3), 2 with NaN (4-5), 4 >= 0.70 (6-9)
_SCORES = [0.50, 0.55, 0.60, 0.65, float("nan"), float("nan"), 0.70, 0.75, 0.80, 0.90]
_RUBRIC_SCORES = [
    0.40,
    0.45,
    0.50,
    0.55,
    float("nan"),
    float("nan"),
    0.70,
    0.75,
    0.80,
    0.85,
]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    """Write a valid round config YAML to tmp_path and return its path."""
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(_VALID_CONFIG), encoding="utf-8")
    return p


@pytest.fixture()
def result_reader() -> InMemoryResultReader:
    """InMemoryResultReader pre-loaded with 10 synthetic EvaluationResult rows."""
    store = InMemoryResultStore()
    writer = InMemoryResultWriter(store, round_id=_ROUND_ID, run_id=_RUN_ID)
    for i, (fs, rb) in enumerate(zip(_SCORES, _RUBRIC_SCORES, strict=True)):
        result = make_evaluation_result(
            answer=make_generated_answer(
                row_id=make_row_id(
                    run_id=_RUN_ID,
                    question_id=f"q{i:02d}",
                    llm="llama3-8b",
                    seed=i,
                ),
                question_id=f"q{i:02d}",
                llm="llama3-8b",
                seed=i,
            ),
            final_score=fs,
            metrics=_make_metrics(rb),
        )
        writer.append(result)
    return InMemoryResultReader(store)


def _make_metrics(rubric: float):  # type: ignore[no-untyped-def]
    from factories import make_metric_vector

    return make_metric_vector(rubric_biomed_score=rubric)


# ---------------------------------------------------------------------------
# Helper: patch build_annotation_reader for all CLI tests
# ---------------------------------------------------------------------------


def _patch_reader(mocker: MockerFixture, reader: InMemoryResultReader) -> None:
    """Patch the factory so the CLI uses the in-memory reader."""
    mocker.patch(
        "inteligenciomica_eval.infrastructure.factories.build_annotation_reader",
        return_value=reader,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAnnotateExport:
    """Tests for `ielm-eval annotate --export`."""

    def test_export_creates_jsonl_with_six_lines(
        self,
        config_path: Path,
        result_reader: InMemoryResultReader,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """a) --export: 6 lines (4 final_score < 0.70 + 2 NaN) with default threshold."""
        _patch_reader(mocker, result_reader)
        export_path = tmp_path / "export.jsonl"

        result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--export",
                str(export_path),
                "--threshold",
                str(_THRESHOLD),
            ],
        )

        assert result.exit_code == 0, result.output
        assert export_path.exists()
        lines = [
            line
            for line in export_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 6  # 4 below threshold + 2 NaN

    def test_sort_by_finalscore_worst_first(
        self,
        config_path: Path,
        result_reader: InMemoryResultReader,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """b) --sort-by finalscore: NaN first, then ascending by final_score."""
        _patch_reader(mocker, result_reader)
        export_path = tmp_path / "sorted.jsonl"

        result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--export",
                str(export_path),
                "--sort-by",
                "finalscore",
            ],
        )

        assert result.exit_code == 0, result.output
        data = [
            json.loads(line)
            for line in export_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(data) == 6

        # NaN items (null in JSON) come first
        null_items = [d for d in data if d["final_score"] is None]
        non_null = [d for d in data if d["final_score"] is not None]
        assert len(null_items) == 2
        # NaN items precede non-null items
        null_positions = [i for i, d in enumerate(data) if d["final_score"] is None]
        non_null_positions = [
            i for i, d in enumerate(data) if d["final_score"] is not None
        ]
        assert max(null_positions) < min(non_null_positions)
        # Non-null are in ascending order (lowest = worst first)
        scores = [d["final_score"] for d in non_null]
        assert scores == sorted(scores)

    def test_max_items_limits_output(
        self,
        config_path: Path,
        result_reader: InMemoryResultReader,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """c) --max-items 3: exactly 3 lines exported."""
        _patch_reader(mocker, result_reader)
        export_path = tmp_path / "limited.jsonl"

        result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--export",
                str(export_path),
                "--max-items",
                "3",
            ],
        )

        assert result.exit_code == 0, result.output
        lines = [
            line
            for line in export_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 3

    def test_export_and_ingest_together_is_error(
        self,
        config_path: Path,
        tmp_path: Path,
    ) -> None:
        """d) --export + --ingest together: exit_code != 0 with friendly message."""
        export_path = tmp_path / "out.jsonl"
        ingest_path = tmp_path / "in.jsonl"

        result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--export",
                str(export_path),
                "--ingest",
                str(ingest_path),
            ],
        )

        assert result.exit_code != 0
        assert (
            "mutuamente exclusiv" in result.output.lower()
            or "exclusiv" in result.output.lower()
        )

    def test_export_creates_parent_directory(
        self,
        config_path: Path,
        result_reader: InMemoryResultReader,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """e) --export to non-existent directory: directory created, no exception."""
        _patch_reader(mocker, result_reader)
        export_path = tmp_path / "new_dir" / "subdir" / "export.jsonl"
        assert not export_path.parent.exists()

        result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--export",
                str(export_path),
            ],
        )

        assert result.exit_code == 0, result.output
        assert export_path.parent.exists()
        assert export_path.exists()

    def test_jsonl_lines_are_valid_json(
        self,
        config_path: Path,
        result_reader: InMemoryResultReader,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """f) Every line in the JSONL is valid JSON (json.loads does not raise)."""
        _patch_reader(mocker, result_reader)
        export_path = tmp_path / "valid_json.jsonl"

        result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--export",
                str(export_path),
            ],
        )

        assert result.exit_code == 0, result.output
        for line in export_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                obj = json.loads(line)  # must not raise
                assert isinstance(obj, dict)

    def test_jsonl_contains_all_required_fields(
        self,
        config_path: Path,
        result_reader: InMemoryResultReader,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """g) All required fields are present in every JSONL line."""
        _patch_reader(mocker, result_reader)
        export_path = tmp_path / "fields.jsonl"

        result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--export",
                str(export_path),
            ],
        )

        assert result.exit_code == 0, result.output
        required_fields = {
            "row_id",
            "question_id",
            "question",
            "generated_answer",
            "ground_truth",
            "final_score",
            "rubric_biomed_score",
            "rubric_feedback",
            "critical_failure_flag",
            "critical_failure_note",
        }
        for line in export_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                obj = json.loads(line)
                assert required_fields.issubset(set(obj.keys())), (
                    f"Missing fields: {required_fields - set(obj.keys())}"
                )

    def test_critical_failure_flag_is_null(
        self,
        config_path: Path,
        result_reader: InMemoryResultReader,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """critical_failure_flag is always null in exported JSONL (not yet annotated)."""
        _patch_reader(mocker, result_reader)
        export_path = tmp_path / "flags.jsonl"

        result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--export",
                str(export_path),
            ],
        )

        assert result.exit_code == 0, result.output
        for line in export_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                obj = json.loads(line)
                assert obj["critical_failure_flag"] is None, (
                    f"Expected null, got {obj['critical_failure_flag']!r}"
                )

    def test_sort_by_rubric(
        self,
        config_path: Path,
        result_reader: InMemoryResultReader,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """--sort-by rubric: NaN rubric scores first, then ascending."""
        _patch_reader(mocker, result_reader)
        export_path = tmp_path / "rubric_sort.jsonl"

        result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--export",
                str(export_path),
                "--sort-by",
                "rubric",
            ],
        )

        assert result.exit_code == 0, result.output
        data = [
            json.loads(line)
            for line in export_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        non_null = [d for d in data if d["rubric_biomed_score"] is not None]
        rubric_scores = [d["rubric_biomed_score"] for d in non_null]
        assert rubric_scores == sorted(rubric_scores)

    def test_sort_by_random_is_reproducible(
        self,
        config_path: Path,
        result_reader: InMemoryResultReader,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """--sort-by random with seed=42 produces reproducible order."""
        _patch_reader(mocker, result_reader)
        export_path_1 = tmp_path / "rand1.jsonl"
        export_path_2 = tmp_path / "rand2.jsonl"

        for export_path in (export_path_1, export_path_2):
            runner.invoke(
                app,
                [
                    "annotate",
                    "--config",
                    str(config_path),
                    "--run-id",
                    _RUN_ID,
                    "--export",
                    str(export_path),
                    "--sort-by",
                    "random",
                ],
            )

        rows_1 = [
            json.loads(line)
            for line in export_path_1.read_text().splitlines()
            if line.strip()
        ]
        rows_2 = [
            json.loads(line)
            for line in export_path_2.read_text().splitlines()
            if line.strip()
        ]
        assert [r["row_id"] for r in rows_1] == [r["row_id"] for r in rows_2]

    def test_run_id_filters_results(
        self,
        config_path: Path,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """run_id filter: only results from matching run are exported."""
        store = InMemoryResultStore()
        writer_a = InMemoryResultWriter(store, round_id=_ROUND_ID, run_id="run-a")
        writer_b = InMemoryResultWriter(store, round_id=_ROUND_ID, run_id="run-b")
        from factories import make_evaluation_result, make_generated_answer, make_row_id

        for i in range(3):
            writer_a.append(
                make_evaluation_result(
                    answer=make_generated_answer(
                        row_id=make_row_id(
                            run_id="run-a", question_id=f"qa{i}", llm="m", seed=i
                        ),
                        question_id=f"qa{i}",
                        llm="m",
                        seed=i,
                    ),
                    final_score=0.3,
                )
            )
        for i in range(2):
            writer_b.append(
                make_evaluation_result(
                    answer=make_generated_answer(
                        row_id=make_row_id(
                            run_id="run-b", question_id=f"qb{i}", llm="m", seed=i
                        ),
                        question_id=f"qb{i}",
                        llm="m",
                        seed=i,
                    ),
                    final_score=0.3,
                )
            )
        reader = InMemoryResultReader(store)
        mocker.patch(
            "inteligenciomica_eval.infrastructure.factories.build_annotation_reader",
            return_value=reader,
        )
        export_path = tmp_path / "run_a_only.jsonl"

        result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                "run-a",
                "--export",
                str(export_path),
            ],
        )

        assert result.exit_code == 0, result.output
        lines = [
            line
            for line in export_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 3  # only run-a rows, not run-b

    def test_invalid_sort_by_exits_with_error(
        self,
        config_path: Path,
        result_reader: InMemoryResultReader,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """--sort-by with invalid value: exits with code 1 and error message."""
        _patch_reader(mocker, result_reader)
        export_path = tmp_path / "bad_sort.jsonl"

        result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--export",
                str(export_path),
                "--sort-by",
                "invalid_value",
            ],
        )

        assert result.exit_code == 1
        assert "sort-by" in result.output.lower() or "invalid" in result.output.lower()

    def test_storage_error_exits_with_error(
        self,
        config_path: Path,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """StorageError from reader.load: exits with code 1 and error message."""
        from unittest.mock import MagicMock

        from inteligenciomica_eval.domain.errors import StorageError

        bad_reader = MagicMock()
        bad_reader.load.side_effect = StorageError("load", "disk full")
        mocker.patch(
            "inteligenciomica_eval.infrastructure.factories.build_annotation_reader",
            return_value=bad_reader,
        )
        export_path = tmp_path / "storage_err.jsonl"

        result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--export",
                str(export_path),
            ],
        )

        assert result.exit_code == 1
        assert "storage" in result.output.lower() or "error" in result.output.lower()


# ---------------------------------------------------------------------------
# Tests — annotate --ingest  (TAREFA-402)
# ---------------------------------------------------------------------------


def _make_writer(*row_ids: object) -> InMemoryResultWriter:
    """Return an InMemoryResultWriter pre-loaded with synthetic rows for each row_id."""
    from inteligenciomica_eval.domain.value_objects import RowId

    store = InMemoryResultStore()
    writer = InMemoryResultWriter(store, round_id=_ROUND_ID, run_id=_RUN_ID)
    for i, row_id in enumerate(row_ids):
        assert isinstance(row_id, RowId)
        result = make_evaluation_result(
            answer=make_generated_answer(
                row_id=row_id,
                question_id=f"qi{i:02d}",
                llm="llama3-8b",
                seed=i,
            ),
            final_score=0.4,
        )
        writer.append(result)
    return writer


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


@pytest.mark.unit
class TestAnnotateIngest:
    """Tests for `ielm-eval annotate --ingest` (TAREFA-402)."""

    def test_ingest_happy_path(
        self,
        config_path: Path,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """Wiring: --ingest reaches _run_ingest_annotate, exit_code=0, summary table shown."""
        row_id_0 = make_row_id(run_id=_RUN_ID, question_id="qi00", seed=0)
        row_id_1 = make_row_id(run_id=_RUN_ID, question_id="qi01", seed=1)
        writer = _make_writer(row_id_0, row_id_1)
        mocker.patch(
            "inteligenciomica_eval.infrastructure.factories.build_annotation_writer",
            return_value=writer,
        )

        ingest_path = tmp_path / "annotations.jsonl"
        _write_jsonl(
            ingest_path,
            [
                {
                    "row_id": row_id_0.value,
                    "critical_failure_flag": 0,
                    "critical_failure_note": "",
                },
                {
                    "row_id": row_id_1.value,
                    "critical_failure_flag": 1,
                    "critical_failure_note": "erro crítico",
                },
            ],
        )

        result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--ingest",
                str(ingest_path),
            ],
        )

        assert result.exit_code == 0, result.output
        # Summary table must mention "Ingeridas" (table row label) to confirm the ingest path
        assert "ingeridas" in result.output.lower()
        # Both rows were ingested — flag values stored
        assert writer.current_annotation_flag(row_id_0) == 0
        assert writer.current_annotation_flag(row_id_1) == 1

    def test_ingest_force_overwrites_existing(
        self,
        config_path: Path,
        tmp_path: Path,
        mocker: MockerFixture,
    ) -> None:
        """--force overwrites already-annotated row; without --force the row is skipped."""
        row_id = make_row_id(run_id=_RUN_ID, question_id="qi00", seed=0)
        writer = _make_writer(row_id)
        # Pre-annotate: flag=0
        writer.update_annotation(
            row_id, critical_failure_flag=0, critical_failure_note=""
        )

        ingest_path = tmp_path / "annotations.jsonl"
        _write_jsonl(
            ingest_path,
            [
                {
                    "row_id": row_id.value,
                    "critical_failure_flag": 1,
                    "critical_failure_note": "override",
                }
            ],
        )

        mocker.patch(
            "inteligenciomica_eval.infrastructure.factories.build_annotation_writer",
            return_value=writer,
        )

        # Without --force: row is skipped, flag stays 0
        result_no_force = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--ingest",
                str(ingest_path),
            ],
        )
        assert result_no_force.exit_code == 0, result_no_force.output
        assert writer.current_annotation_flag(row_id) == 0

        # With --force: row is overwritten, flag becomes 1
        result_force = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--ingest",
                str(ingest_path),
                "--force",
            ],
        )
        assert result_force.exit_code == 0, result_force.output
        assert writer.current_annotation_flag(row_id) == 1

    def test_ingest_file_not_found(
        self,
        config_path: Path,
        tmp_path: Path,
    ) -> None:
        """--ingest with non-existent file: exit_code=1 and error message displayed."""
        missing = tmp_path / "does_not_exist.jsonl"

        result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--ingest",
                str(missing),
            ],
        )

        assert result.exit_code == 1
        assert (
            "encontrado" in result.output.lower()
            or "not found" in result.output.lower()
        )
