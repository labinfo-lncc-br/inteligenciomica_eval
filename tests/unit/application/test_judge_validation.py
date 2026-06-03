"""Testes unitários de JudgeValidationUseCase (TAREFA-602)."""

from __future__ import annotations

import pytest
from factories.factories import make_evaluation_result, make_metric_vector

from inteligenciomica_eval.application.judge_validation import (
    JudgeValidationConfig,
    JudgeValidationUseCase,
    _interpret_kappa,
)
from inteligenciomica_eval.domain.errors import InsufficientAnnotationError
from inteligenciomica_eval.domain.ports import KappaCalculatorPort, ResultFrame
from inteligenciomica_eval.domain.value_objects import DeterminismRegime

# ---------------------------------------------------------------------------
# Fake KappaCalculator — usa sklearn real
# ---------------------------------------------------------------------------


class _FakeKappa:
    """Adapter fake que chama sklearn.metrics.cohen_kappa_score real."""

    def compute(self, y_true: list[int], y_pred: list[int]) -> float:
        from sklearn.metrics import cohen_kappa_score

        return float(cohen_kappa_score(y_true, y_pred))


assert isinstance(_FakeKappa(), KappaCalculatorPort)


# ---------------------------------------------------------------------------
# Fake ResultReader simples (não depende de InMemoryResultStore)
# ---------------------------------------------------------------------------


class _SimpleReader:
    """ResultReaderPort fake — serve um único ResultFrame fixo."""

    def __init__(self, frame: ResultFrame) -> None:
        self._frame = frame

    def load(
        self,
        *,
        round_id: str,
        phase: str | None = None,
        run_id: str | None = None,
    ) -> ResultFrame:
        return self._frame


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_ID = "run-test"
ROUND_ID = "round_1"


def _make_reader(results: list) -> _SimpleReader:
    return _SimpleReader(ResultFrame(results=tuple(results)))


def _make_result(
    *,
    rubric_score: float,
    flag: int | None,
    regime: DeterminismRegime = DeterminismRegime.JUDGE,
    question_id: str = "q01",
) -> object:
    return make_evaluation_result(
        metrics=make_metric_vector(rubric_biomed_score=rubric_score),
        determinism_regime=regime,
        critical_failure_flag=flag,
    )


def _make_uc(
    results: list,
    *,
    threshold: float = 0.50,
    min_sample: int = 10,
) -> JudgeValidationUseCase:
    return JudgeValidationUseCase(
        reader=_make_reader(results),
        kappa_calculator=_FakeKappa(),
        config=JudgeValidationConfig(
            binarization_threshold=threshold,
            min_sample_size=min_sample,
        ),
    )


# ---------------------------------------------------------------------------
# Golden dataset:
#   20 linhas, 10 com flag=1 e 10 com flag=0.
#   Linhas 0-7 (flag=1): score=0.20 < 0.50 → judge_binary=1 (TP=8)
#   Linhas 8-9 (flag=1): score=0.80 >= 0.50 → judge_binary=0 (FN=2)
#   Linhas 10-16 (flag=0): score=0.80 >= 0.50 → judge_binary=0 (TN=7)
#   Linhas 17-19 (flag=0): score=0.20 < 0.50 → judge_binary=1 (FP=3)
#
# TP=8, FN=2, FP=3, TN=7, n=20
# Po = (8+7)/20 = 0.75
# Pe = (10/20 x 11/20) + (10/20 x 9/20) = 0.275 + 0.225 = 0.5
# κ = (0.75 - 0.5) / (1 - 0.5) = 0.5   → "moderada"
# ---------------------------------------------------------------------------

_GOLDEN_RESULTS = (
    [_make_result(rubric_score=0.20, flag=1) for _ in range(8)]  # TP
    + [_make_result(rubric_score=0.80, flag=1) for _ in range(2)]  # FN
    + [_make_result(rubric_score=0.80, flag=0) for _ in range(7)]  # TN
    + [_make_result(rubric_score=0.20, flag=0) for _ in range(3)]  # FP
)


class TestGoldenDataset:
    def test_kappa_value(self) -> None:
        uc = _make_uc(_GOLDEN_RESULTS)
        result = uc.run(RUN_ID, ROUND_ID)
        # κ = 0.5 (calculado manualmente — ver comentário acima)
        assert abs(result.cohen_kappa - 0.5) < 1e-9

    def test_kappa_interpretation(self) -> None:
        uc = _make_uc(_GOLDEN_RESULTS)
        result = uc.run(RUN_ID, ROUND_ID)
        assert result.kappa_interpretation == "moderada"

    def test_n_excluded_nan_zero(self) -> None:
        uc = _make_uc(_GOLDEN_RESULTS)
        result = uc.run(RUN_ID, ROUND_ID)
        assert result.n_excluded_nan == 0

    def test_n_valid(self) -> None:
        uc = _make_uc(_GOLDEN_RESULTS)
        result = uc.run(RUN_ID, ROUND_ID)
        assert result.n_valid == 20

    def test_n_annotated(self) -> None:
        uc = _make_uc(_GOLDEN_RESULTS)
        result = uc.run(RUN_ID, ROUND_ID)
        assert result.n_annotated == 20

    def test_confusion_matrix(self) -> None:
        uc = _make_uc(_GOLDEN_RESULTS)
        result = uc.run(RUN_ID, ROUND_ID)
        assert result.confusion_matrix == {"TP": 8, "TN": 7, "FP": 3, "FN": 2}

    def test_threshold_stored(self) -> None:
        uc = _make_uc(_GOLDEN_RESULTS, threshold=0.50)
        result = uc.run(RUN_ID, ROUND_ID)
        assert result.binarization_threshold == 0.50


class TestNExcludedNan:
    def test_nan_rows_excluded_and_counted(self) -> None:
        results = (
            [_make_result(rubric_score=0.20, flag=1) for _ in range(8)]
            + [_make_result(rubric_score=0.80, flag=1) for _ in range(2)]
            + [_make_result(rubric_score=0.80, flag=0) for _ in range(7)]
            + [_make_result(rubric_score=0.20, flag=0) for _ in range(3)]
            + [_make_result(rubric_score=float("nan"), flag=1) for _ in range(3)]
        )
        uc = _make_uc(results)
        result = uc.run(RUN_ID, ROUND_ID)
        # 23 anotadas; 3 NaN; 20 válidas
        assert result.n_annotated == 23
        assert result.n_valid == 20
        assert result.n_excluded_nan == 3


class TestInsufficientAnnotation:
    def test_raises_when_n_valid_below_min(self) -> None:
        results = [_make_result(rubric_score=0.2, flag=1) for _ in range(5)]
        with pytest.raises(InsufficientAnnotationError):
            _make_uc(results, min_sample=10).run(RUN_ID, ROUND_ID)

    def test_raises_when_all_nan(self) -> None:
        # Todas as linhas anotadas mas com NaN → n_valid=0
        results = [_make_result(rubric_score=float("nan"), flag=1) for _ in range(15)]
        with pytest.raises(InsufficientAnnotationError) as exc_info:
            _make_uc(results, min_sample=10).run(RUN_ID, ROUND_ID)
        assert exc_info.value.n_valid == 0

    def test_raises_when_no_annotations(self) -> None:
        results = [_make_result(rubric_score=0.2, flag=None) for _ in range(20)]
        with pytest.raises(InsufficientAnnotationError):
            _make_uc(results, min_sample=10).run(RUN_ID, ROUND_ID)


class TestBatchInvariant:
    def test_confirmed_true_when_all_judge(self) -> None:
        uc = _make_uc(_GOLDEN_RESULTS)
        result = uc.run(RUN_ID, ROUND_ID)
        assert result.batch_invariant_confirmed is True

    def test_confirmed_false_when_any_generator(self) -> None:
        results = (
            [_make_result(rubric_score=0.20, flag=1) for _ in range(8)]
            + [_make_result(rubric_score=0.80, flag=1) for _ in range(2)]
            + [_make_result(rubric_score=0.80, flag=0) for _ in range(7)]
            + [
                _make_result(
                    rubric_score=0.20,
                    flag=0,
                    regime=DeterminismRegime.GENERATOR,
                )
                for _ in range(3)
            ]
        )
        uc = _make_uc(results)
        result = uc.run(RUN_ID, ROUND_ID)
        assert result.batch_invariant_confirmed is False


# ---------------------------------------------------------------------------
# Interpretação de κ — escala de Landis & Koch
# ---------------------------------------------------------------------------


class TestInterpretKappa:
    @pytest.mark.parametrize(
        "kappa,expected",
        [
            (-0.1, "fraca"),
            (0.0, "fraca"),
            (0.19, "fraca"),
            (0.20, "razoável"),
            (0.39, "razoável"),
            (0.40, "moderada"),
            (0.59, "moderada"),
            (0.60, "substancial"),
            (0.79, "substancial"),
            (0.80, "quase-perfeita"),
            (1.00, "quase-perfeita"),
        ],
    )
    def test_boundaries(self, kappa: float, expected: str) -> None:
        assert _interpret_kappa(kappa) == expected
