"""Testes unitários para ComputeMetricsUseCase (TAREFA-026, camada application).

Usa os fakes de TAREFA-011 (FakeMetricSuite/FakeRubricJudge/FakeDeterministicMetric)
e doubles locais (``_FrameReader``, ``_SpyWriter``, fakes roteados por question_id)
para cobrir os cenários obrigatórios:

- fluxo normal (n_processed == N);
- skip por final_score existente (n_skipped == N, writer não chamado);
- force=True reprocessa linha já pontuada;
- NaN propagado de metric_suite (n_nan_excluded++, update_metrics chamado);
- exceção inesperada por linha (n_failed_terminal++, demais continuam);
- ordem determinística por row_id (verificada via spy no writer);
- DeterminismRegime.JUDGE passado ao update_metrics (verificado via spy);
- golden de 4 linhas confere ComputeMetricsReport (default + force).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from factories import make_evaluation_result, make_generated_answer
from fakes import FakeDeterministicMetric, FakeMetricSuite, FakeRubricJudge

from inteligenciomica_eval.application.compute_metrics_use_case import (
    ComputeMetricsConfig,
    ComputeMetricsInput,
    ComputeMetricsReport,
    ComputeMetricsUseCase,
)
from inteligenciomica_eval.domain.entities import EvaluationResult
from inteligenciomica_eval.domain.ports import (
    AuxMetrics,
    EvaluationSample,
    Layer1Metrics,
    ResultFrame,
    RubricResult,
)
from inteligenciomica_eval.domain.services.final_score import (
    DEFAULT_WEIGHTS,
    FinalScoreCalculator,
)
from inteligenciomica_eval.domain.value_objects import DeterminismRegime, FinalScore

_NAN = float("nan")

# Rubrica normalizada em [0,1] (TAREFA-024) — score 4.0 (escala bruta) estouraria o
# FinalScore (peso 0.15) acima de 1.0; o adapter real entrega [0,1].
_VALID_RUBRIC = RubricResult(score=0.80, feedback="ok")
_VALID_LAYER1 = Layer1Metrics(
    answer_correctness=0.80,
    answer_similarity=0.75,
    faithfulness=0.90,
    context_precision=0.85,
    context_recall=0.70,
    answer_relevancy=0.88,
)
_ALL_NAN_LAYER1 = Layer1Metrics(
    answer_correctness=_NAN,
    answer_similarity=_NAN,
    faithfulness=_NAN,
    context_precision=_NAN,
    context_recall=_NAN,
    answer_relevancy=_NAN,
)
_VALID_AUX = AuxMetrics(bertscore_f1=0.82, rouge_l=0.71)
_NAN_BERT_AUX = AuxMetrics(bertscore_f1=_NAN, rouge_l=_NAN)


# ---------------------------------------------------------------------------
# Doubles de teste
# ---------------------------------------------------------------------------


class _FrameReader:
    """ResultReaderPort que devolve um ResultFrame fixo e registra as chamadas."""

    def __init__(self, results: tuple[EvaluationResult, ...]) -> None:
        self._results = results
        self.load_calls: list[tuple[str, str | None]] = []

    def load(self, *, round_id: str, phase: str | None = None) -> ResultFrame:
        self.load_calls.append((round_id, phase))
        return ResultFrame(results=self._results)


class _SpyWriter:
    """ResultWriterPort que registra cada update_metrics (row_id, regime, score)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def append(self, result: EvaluationResult) -> None:  # pragma: no cover - não usado
        pass

    def update_metrics(
        self,
        row_id: Any,
        metrics: Any,
        final_score: FinalScore,
        regime: DeterminismRegime,
    ) -> None:
        self.calls.append(
            {
                "row_id": row_id.value,
                "regime": regime,
                "final_score": final_score.value,
            }
        )

    def exists(self, row_id: Any) -> bool:  # pragma: no cover - não usado
        return False


class _RoutedMetricSuite:
    """MetricSuitePort que devolve all-NaN para question_ids selecionados."""

    def __init__(self, nan_ids: set[str]) -> None:
        self._nan_ids = nan_ids

    async def score(self, sample: EvaluationSample) -> Layer1Metrics:
        return _ALL_NAN_LAYER1 if sample.question_id in self._nan_ids else _VALID_LAYER1


class _RoutedAux:
    """DeterministicMetricPort que devolve NaN para respostas selecionadas."""

    def __init__(self, nan_answers: set[str]) -> None:
        self._nan_answers = nan_answers

    def score(self, *, answer: str, ground_truth: str) -> AuxMetrics:
        return _NAN_BERT_AUX if answer in self._nan_answers else _VALID_AUX


class _RaisingMetricSuite:
    """MetricSuitePort que levanta para um question_id (bug escapando do decorator)."""

    def __init__(self, raise_id: str) -> None:
        self._raise_id = raise_id

    async def score(self, sample: EvaluationSample) -> Layer1Metrics:
        if sample.question_id == self._raise_id:
            raise RuntimeError("bug inesperado de adapter")
        return _VALID_LAYER1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _nan_row(question_id: str) -> EvaluationResult:
    """Linha 'ainda não computada' (final_score NaN) — entra em to_process."""
    return make_evaluation_result(
        answer=make_generated_answer(
            question_id=question_id, generated_answer=f"ans-{question_id}"
        ),
        final_score=_NAN,
    )


def _scored_row(question_id: str, score: float) -> EvaluationResult:
    """Linha já pontuada (final_score real) — pulada por idempotência."""
    return make_evaluation_result(
        answer=make_generated_answer(
            question_id=question_id, generated_answer=f"ans-{question_id}"
        ),
        final_score=score,
    )


def _make_use_case(
    reader: _FrameReader,
    writer: _SpyWriter,
    *,
    metric_suite: Any = None,
    rubric_judge: Any = None,
    aux_metrics: Any = None,
    config: ComputeMetricsConfig | None = None,
) -> ComputeMetricsUseCase:
    return ComputeMetricsUseCase(
        reader=reader,
        writer=writer,
        metric_suite=metric_suite or FakeMetricSuite(_VALID_LAYER1),
        rubric_judge=rubric_judge or FakeRubricJudge(_VALID_RUBRIC),
        aux_metrics=aux_metrics or FakeDeterministicMetric(_VALID_AUX),
        score_calculator=FinalScoreCalculator(DEFAULT_WEIGHTS),
        config=config or ComputeMetricsConfig(),
    )


# ---------------------------------------------------------------------------
# Fluxo normal / idempotência
# ---------------------------------------------------------------------------


class TestNormalFlow:
    async def test_processes_all_pending_rows(self) -> None:
        rows = (_nan_row("q1"), _nan_row("q2"), _nan_row("q3"))
        reader, writer = _FrameReader(rows), _SpyWriter()
        uc = _make_use_case(reader, writer)

        report = await uc.execute(
            ComputeMetricsInput(run_id="run-1", round_id="rd", phase="A")
        )

        assert report.n_processed == 3
        assert report.n_skipped == 0
        assert report.n_nan_excluded == 0
        assert report.n_failed_terminal == 0
        assert len(writer.calls) == 3
        # reader consultado com os parâmetros do input.
        assert reader.load_calls == [("rd", "A")]

    async def test_returns_report_dataclass(self) -> None:
        reader, writer = _FrameReader((_nan_row("q1"),)), _SpyWriter()
        uc = _make_use_case(reader, writer)
        report = await uc.execute(ComputeMetricsInput(run_id="r", round_id="rd"))
        assert isinstance(report, ComputeMetricsReport)
        assert report.run_id == "r"


class TestIdempotency:
    async def test_skips_rows_with_existing_final_score(self) -> None:
        rows = (_scored_row("q1", 0.80), _scored_row("q2", 0.70))
        reader, writer = _FrameReader(rows), _SpyWriter()
        uc = _make_use_case(reader, writer)

        report = await uc.execute(ComputeMetricsInput(run_id="r", round_id="rd"))

        assert report.n_skipped == 2
        assert report.n_processed == 0
        assert writer.calls == []  # writer NÃO chamado para linhas puladas

    async def test_force_reprocesses_scored_row(self) -> None:
        rows = (_scored_row("q1", 0.80),)
        reader, writer = _FrameReader(rows), _SpyWriter()
        uc = _make_use_case(reader, writer)

        report = await uc.execute(
            ComputeMetricsInput(run_id="r", round_id="rd", force=True)
        )

        assert report.n_processed == 1
        assert report.n_skipped == 0
        assert len(writer.calls) == 1


# ---------------------------------------------------------------------------
# NaN propagation (ADR-007)
# ---------------------------------------------------------------------------


class TestNaNPropagation:
    async def test_nan_from_metric_suite_is_excluded_but_persisted(self) -> None:
        reader, writer = _FrameReader((_nan_row("q1"),)), _SpyWriter()
        uc = _make_use_case(
            reader, writer, metric_suite=FakeMetricSuite(inject_nan=True)
        )

        report = await uc.execute(ComputeMetricsInput(run_id="r", round_id="rd"))

        assert report.n_nan_excluded == 1
        assert report.n_processed == 0
        # update_metrics É chamado — o NaN-sentinel é persistido (ADR-007).
        assert len(writer.calls) == 1
        assert math.isnan(writer.calls[0]["final_score"])


# ---------------------------------------------------------------------------
# Falha terminal inesperada (bug escapa do decorator de retry)
# ---------------------------------------------------------------------------


class TestTerminalFailure:
    async def test_unexpected_exception_counts_and_continues(self) -> None:
        rows = (_nan_row("q1"), _nan_row("q2"), _nan_row("q3"))
        reader, writer = _FrameReader(rows), _SpyWriter()
        uc = _make_use_case(reader, writer, metric_suite=_RaisingMetricSuite("q2"))

        report = await uc.execute(ComputeMetricsInput(run_id="r", round_id="rd"))

        assert report.n_failed_terminal == 1
        assert report.n_processed == 2  # q1 e q3 seguem
        failed_q2 = make_generated_answer(question_id="q2").row_id.value
        assert report.failed_row_ids == (failed_q2,)


# ---------------------------------------------------------------------------
# Ramos de logging (progresso + WARNING de alta taxa de falha)
# ---------------------------------------------------------------------------


class TestLoggingBranches:
    async def test_progress_log_fires_at_interval(self) -> None:
        """log_progress_every=1 emite compute_metrics_progress por linha."""
        import structlog.testing

        rows = (_nan_row("q1"), _nan_row("q2"))
        reader, writer = _FrameReader(rows), _SpyWriter()
        uc = _make_use_case(
            reader, writer, config=ComputeMetricsConfig(log_progress_every=1)
        )

        with structlog.testing.capture_logs() as logs:
            await uc.execute(ComputeMetricsInput(run_id="r", round_id="rd"))

        assert any(e.get("event") == "compute_metrics_progress" for e in logs)

    async def test_high_failure_rate_emits_warning(self) -> None:
        """Taxa de falha terminal acima de failure_threshold → WARNING no summary."""
        import structlog.testing

        rows = (_nan_row("q1"),)
        reader, writer = _FrameReader(rows), _SpyWriter()
        uc = _make_use_case(
            reader,
            writer,
            metric_suite=_RaisingMetricSuite("q1"),
            config=ComputeMetricsConfig(failure_threshold=0.0),
        )

        with structlog.testing.capture_logs() as logs:
            report = await uc.execute(ComputeMetricsInput(run_id="r", round_id="rd"))

        assert report.n_failed_terminal == 1
        assert any(
            e.get("event") == "compute_metrics_high_failure_rate" for e in logs
        )


# ---------------------------------------------------------------------------
# Ordem determinística + regime
# ---------------------------------------------------------------------------


class TestDeterminismAndRegime:
    async def test_rows_processed_in_row_id_order(self) -> None:
        rows = [_nan_row(f"q{i}") for i in range(5)]
        # Embaralha: alimenta na ordem inversa de row_id para forçar o sort.
        rows_desc = tuple(
            sorted(rows, key=lambda r: r.answer.row_id.value, reverse=True)
        )
        reader, writer = _FrameReader(rows_desc), _SpyWriter()
        uc = _make_use_case(reader, writer)

        await uc.execute(ComputeMetricsInput(run_id="r", round_id="rd"))

        called_order = [c["row_id"] for c in writer.calls]
        assert called_order == sorted(called_order)
        # E o sort realmente reordenou (input estava em ordem decrescente).
        assert called_order != [r.answer.row_id.value for r in rows_desc]

    async def test_judge_regime_passed_to_update_metrics(self) -> None:
        rows = (_nan_row("q1"), _nan_row("q2"))
        reader, writer = _FrameReader(rows), _SpyWriter()
        uc = _make_use_case(reader, writer)

        await uc.execute(ComputeMetricsInput(run_id="r", round_id="rd"))

        assert writer.calls  # pelo menos uma chamada
        assert all(c["regime"] is DeterminismRegime.JUDGE for c in writer.calls)


# ---------------------------------------------------------------------------
# Golden — 4 linhas
# ---------------------------------------------------------------------------

_GOLDEN_PATH = Path(__file__).parents[2] / "golden" / "compute_metrics_expected.json"
_GOLDEN: dict[str, Any] = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))


def _build_golden_scenario() -> tuple[
    tuple[EvaluationResult, ...], _RoutedMetricSuite, _RoutedAux
]:
    """Constrói as 4 linhas e os fakes roteados a partir do golden."""
    rows: list[EvaluationResult] = []
    suite_nan_ids: set[str] = set()
    aux_nan_answers: set[str] = set()
    for spec in _GOLDEN["rows"]:
        qid = spec["question_id"]
        if spec["final_score_input"] is None:
            rows.append(_nan_row(qid))
        else:
            rows.append(_scored_row(qid, float(spec["final_score_input"])))
        if spec["nan_metric"] == "answer_correctness":
            suite_nan_ids.add(qid)
        elif spec["nan_metric"] == "bertscore_f1":
            aux_nan_answers.add(f"ans-{qid}")
    return tuple(rows), _RoutedMetricSuite(suite_nan_ids), _RoutedAux(aux_nan_answers)


def _assert_report_matches(report: ComputeMetricsReport, exp: dict[str, Any]) -> None:
    assert report.run_id == exp["run_id"]
    assert report.n_processed == exp["n_processed"]
    assert report.n_skipped == exp["n_skipped"]
    assert report.n_nan_excluded == exp["n_nan_excluded"]
    assert report.n_failed_terminal == exp["n_failed_terminal"]
    assert report.failed_row_ids == tuple(exp["failed_row_ids"])


class TestGolden:
    async def test_default_run_matches_golden(self) -> None:
        rows, metric_suite, aux = _build_golden_scenario()
        reader, writer = _FrameReader(rows), _SpyWriter()
        uc = _make_use_case(reader, writer, metric_suite=metric_suite, aux_metrics=aux)

        report = await uc.execute(
            ComputeMetricsInput(run_id=_GOLDEN["run_id"], round_id=_GOLDEN["round_id"])
        )

        _assert_report_matches(report, _GOLDEN["expected_default"])

    async def test_force_run_matches_golden(self) -> None:
        rows, metric_suite, aux = _build_golden_scenario()
        reader, writer = _FrameReader(rows), _SpyWriter()
        uc = _make_use_case(reader, writer, metric_suite=metric_suite, aux_metrics=aux)

        report = await uc.execute(
            ComputeMetricsInput(
                run_id=_GOLDEN["run_id"], round_id=_GOLDEN["round_id"], force=True
            )
        )

        _assert_report_matches(report, _GOLDEN["expected_force"])
