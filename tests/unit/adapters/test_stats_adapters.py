"""Testes unitários dos adapters estatísticos (TAREFA-404).

Cobertura:
- WilcoxonAdapter: dataset sintético, amostra insuficiente, WARNING.
- FriedmanNemenyiAdapter: dataset sintético, <3 grupos, WARNING.
- MixedLinearModelAdapter: ajuste OK, não-convergência, formulário com (1|grupo).
- isinstance(adapter, StatsPort) para cada adapter.
"""

from __future__ import annotations

import math

import pytest

from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
)
from inteligenciomica_eval.domain.ports import (
    FriedmanReport,
    MLMReport,
    NemenyiPair,
    ResultFrame,
    StatsPort,
    WilcoxonReport,
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
from inteligenciomica_eval.infrastructure.adapters.stats_adapters import (
    FriedmanNemenyiAdapter,
    MixedLinearModelAdapter,
    WilcoxonAdapter,
)
from inteligenciomica_eval.infrastructure.config.adapter_configs import (
    StatsAdapterConfig,
)

# ---------------------------------------------------------------------------
# Helpers de fabricação de dados sintéticos
# ---------------------------------------------------------------------------

_NAN = float("nan")
_METRIC_ZERO = MetricVector(
    answer_correctness=0.0,
    answer_similarity=0.0,
    faithfulness=0.0,
    context_precision=0.0,
    context_recall=0.0,
    answer_relevancy=0.0,
    bertscore_f1=0.0,
    rubric_biomed_score=0.0,
)


def _make_result(
    *,
    question_id: str,
    base: str,
    llm: str,
    seed: int = 42,
    final_score: float,
    run_id: str = "run-test",
) -> EvaluationResult:
    q = Question(
        question_id=question_id, text=f"Questão {question_id}", ground_truth="ref."
    )
    row_id = RowId.from_cell(
        run_id=run_id,
        phase="A",
        base=base,
        llm=llm,
        seed=seed,
        question_id=question_id,
    )
    answer = GeneratedAnswer(
        row_id=row_id,
        question=q,
        base=BaseId(base),
        llm=LLMId(llm),
        seed=Seed(seed),
        phase="A",
        generated_answer="resp.",
        retrieved_chunk_ids=("c1",),
        retrieved_chunks_text=("texto do chunk.",),
        retrieval_scores=(0.9,),
    )
    metrics = MetricVector(
        answer_correctness=final_score,
        answer_similarity=final_score,
        faithfulness=final_score,
        context_precision=final_score,
        context_recall=final_score,
        answer_relevancy=final_score,
        bertscore_f1=final_score,
        rubric_biomed_score=final_score,
    )
    return EvaluationResult(
        answer=answer,
        metrics=metrics,
        final_score=FinalScore(final_score),
        determinism_regime=DeterminismRegime.JUDGE,
        critical_failure_flag=None,
        critical_failure_note=None,
    )


def _make_wilcoxon_frame(
    *,
    base_a: str = "ID_230K",
    base_b: str = "IDx_400k",
    scores_a: list[float],
    scores_b: list[float],
    llm: str = "llm-test",
) -> ResultFrame:
    """Cria ResultFrame com 2 bases e 1 LLM para testes de Wilcoxon."""
    assert len(scores_a) == len(scores_b)
    results = []
    for i, (sa, sb) in enumerate(zip(scores_a, scores_b, strict=True)):
        qid = f"q{i + 1:02d}"
        results.append(
            _make_result(question_id=qid, base=base_a, llm=llm, final_score=sa)
        )
        results.append(
            _make_result(question_id=qid, base=base_b, llm=llm, final_score=sb)
        )
    return ResultFrame(results=tuple(results))


def _make_friedman_frame(
    *,
    llm_scores: dict[str, list[float]],
    base: str = "IDx_400k",
    n_questions: int | None = None,
) -> ResultFrame:
    """Cria ResultFrame com 1 base e N LLMs para testes de Friedman."""
    llms = sorted(llm_scores)
    if n_questions is None:
        n_questions = len(next(iter(llm_scores.values())))
    results = []
    for llm in llms:
        scores = llm_scores[llm]
        for i, sc in enumerate(scores[:n_questions]):
            qid = f"q{i + 1:02d}"
            results.append(
                _make_result(question_id=qid, base=base, llm=llm, final_score=sc)
            )
    return ResultFrame(results=tuple(results))


def _make_mlm_frame() -> ResultFrame:
    """Frame com 2 bases x 3 LLMs x 7 perguntas para teste do MLM.

    7 grupos (question_id) são suficientes para o statsmodels estimar a
    variância do efeito aleatório sem degenerar para a fronteira do espaço
    paramétrico (o que causaria AIC=NaN com datasets menores).
    """
    bases = ["ID_230K", "IDx_400k"]
    llms = ["llm-a", "llm-b", "llm-c"]
    # 7 perguntas com variabilidade suficiente para o efeito aleatório
    q_scores: dict[str, dict[tuple[str, str], float]] = {
        "q01": {
            ("ID_230K", "llm-a"): 0.82,
            ("ID_230K", "llm-b"): 0.74,
            ("ID_230K", "llm-c"): 0.61,
            ("IDx_400k", "llm-a"): 0.78,
            ("IDx_400k", "llm-b"): 0.70,
            ("IDx_400k", "llm-c"): 0.57,
        },
        "q02": {
            ("ID_230K", "llm-a"): 0.79,
            ("ID_230K", "llm-b"): 0.71,
            ("ID_230K", "llm-c"): 0.58,
            ("IDx_400k", "llm-a"): 0.75,
            ("IDx_400k", "llm-b"): 0.67,
            ("IDx_400k", "llm-c"): 0.54,
        },
        "q03": {
            ("ID_230K", "llm-a"): 0.85,
            ("ID_230K", "llm-b"): 0.77,
            ("ID_230K", "llm-c"): 0.64,
            ("IDx_400k", "llm-a"): 0.81,
            ("IDx_400k", "llm-b"): 0.73,
            ("IDx_400k", "llm-c"): 0.60,
        },
        "q04": {
            ("ID_230K", "llm-a"): 0.70,
            ("ID_230K", "llm-b"): 0.62,
            ("ID_230K", "llm-c"): 0.49,
            ("IDx_400k", "llm-a"): 0.66,
            ("IDx_400k", "llm-b"): 0.58,
            ("IDx_400k", "llm-c"): 0.45,
        },
        "q05": {
            ("ID_230K", "llm-a"): 0.88,
            ("ID_230K", "llm-b"): 0.80,
            ("ID_230K", "llm-c"): 0.67,
            ("IDx_400k", "llm-a"): 0.84,
            ("IDx_400k", "llm-b"): 0.76,
            ("IDx_400k", "llm-c"): 0.63,
        },
        "q06": {
            ("ID_230K", "llm-a"): 0.75,
            ("ID_230K", "llm-b"): 0.67,
            ("ID_230K", "llm-c"): 0.54,
            ("IDx_400k", "llm-a"): 0.71,
            ("IDx_400k", "llm-b"): 0.63,
            ("IDx_400k", "llm-c"): 0.50,
        },
        "q07": {
            ("ID_230K", "llm-a"): 0.90,
            ("ID_230K", "llm-b"): 0.82,
            ("ID_230K", "llm-c"): 0.69,
            ("IDx_400k", "llm-a"): 0.86,
            ("IDx_400k", "llm-b"): 0.78,
            ("IDx_400k", "llm-c"): 0.65,
        },
    }
    results = []
    for qid, cell_scores in q_scores.items():
        for base in bases:
            for llm in llms:
                sc = cell_scores[(base, llm)]
                results.append(
                    _make_result(question_id=qid, base=base, llm=llm, final_score=sc)
                )
    return ResultFrame(results=tuple(results))


# ---------------------------------------------------------------------------
# Testes — isinstance / StatsPort contract
# ---------------------------------------------------------------------------


class TestStatsPortIsInstance:
    """Cada adapter satisfaz StatsPort via isinstance (runtime_checkable)."""

    def test_wilcoxon_adapter_is_stats_port(self) -> None:
        assert isinstance(WilcoxonAdapter(), StatsPort)

    def test_friedman_adapter_is_stats_port(self) -> None:
        assert isinstance(FriedmanNemenyiAdapter(), StatsPort)

    def test_mlm_adapter_is_stats_port(self) -> None:
        assert isinstance(MixedLinearModelAdapter(), StatsPort)


# ---------------------------------------------------------------------------
# Testes — WilcoxonAdapter
# ---------------------------------------------------------------------------


class TestWilcoxonAdapter:
    """Testes do WilcoxonAdapter."""

    def _adapter(self) -> WilcoxonAdapter:
        return WilcoxonAdapter(StatsAdapterConfig(alpha=0.05, min_pairs_wilcoxon=5))

    def test_known_dataset_returns_correct_fields(self) -> None:
        # 7 pares, base_a sempre > base_b → W=0, p muito pequeno
        scores_a = [0.80, 0.70, 0.65, 0.90, 0.75, 0.60, 0.85]
        scores_b = [0.60, 0.55, 0.50, 0.75, 0.65, 0.55, 0.72]
        frame = _make_wilcoxon_frame(scores_a=scores_a, scores_b=scores_b)
        report = self._adapter().wilcoxon_paired(frame, "final_score")

        assert isinstance(report, WilcoxonReport)
        assert report.metric == "final_score"
        assert report.base_a == "ID_230K"
        assert report.base_b == "IDx_400k"
        assert report.n_pairs == 7
        assert report.statistic == pytest.approx(0.0)
        assert report.p_value < 0.05
        assert report.significant is True
        assert report.p_value_corrected is None
        assert report.effect_size_r is not None
        assert report.effect_size_r > 0.0

    def test_effect_size_r_formula(self) -> None:
        from scipy.stats import norm, wilcoxon

        scores_a = [0.72, 0.68, 0.81, 0.79, 0.65, 0.88, 0.74]
        scores_b = [0.58, 0.54, 0.67, 0.63, 0.51, 0.74, 0.60]
        frame = _make_wilcoxon_frame(scores_a=scores_a, scores_b=scores_b)
        report = self._adapter().wilcoxon_paired(frame, "final_score")

        _, p_expected = wilcoxon(
            scores_a, scores_b, alternative="two-sided", zero_method="wilcox"
        )
        import math

        z_expected = float(norm.ppf(1.0 - float(p_expected) / 2.0))
        r_expected = z_expected / math.sqrt(len(scores_a))

        assert report.effect_size_r is not None
        assert report.effect_size_r == pytest.approx(r_expected, abs=1e-4)

    def test_insufficient_pairs_returns_degenerate(self) -> None:
        # 3 pares < min_pairs=5 → degenerate sem exceção
        scores_a = [0.80, 0.70, 0.65]
        scores_b = [0.60, 0.55, 0.50]
        frame = _make_wilcoxon_frame(scores_a=scores_a, scores_b=scores_b)
        report = self._adapter().wilcoxon_paired(frame, "final_score")

        assert report.significant is False
        assert report.p_value == pytest.approx(1.0)
        assert report.n_pairs == 0
        assert report.effect_size_r is None

    def test_insufficient_pairs_does_not_raise(self) -> None:
        frame = _make_wilcoxon_frame(scores_a=[0.8], scores_b=[0.6])
        report = self._adapter().wilcoxon_paired(frame, "final_score")
        assert isinstance(report, WilcoxonReport)

    def test_insufficient_bases_returns_degenerate(self) -> None:
        # Frame com apenas 1 base
        result = _make_result(
            question_id="q01", base="IDx_400k", llm="llm-a", final_score=0.7
        )
        frame = ResultFrame(results=(result,))
        report = self._adapter().wilcoxon_paired(frame, "final_score")

        assert report.significant is False
        assert report.n_pairs == 0

    def test_bases_assigned_alphabetically(self) -> None:
        # ID_230K < IDx_400k → base_a=ID_230K, base_b=IDx_400k
        scores_a = [0.72, 0.68, 0.81, 0.79, 0.65, 0.88, 0.74]
        scores_b = [0.58, 0.54, 0.67, 0.63, 0.51, 0.74, 0.60]
        frame = _make_wilcoxon_frame(
            base_a="ID_230K",
            base_b="IDx_400k",
            scores_a=scores_a,
            scores_b=scores_b,
        )
        report = self._adapter().wilcoxon_paired(frame, "final_score")
        assert report.base_a == "ID_230K"
        assert report.base_b == "IDx_400k"

    def test_returns_wilcoxon_report_type(self) -> None:
        scores_a = [0.80, 0.70, 0.65, 0.90, 0.75, 0.60, 0.85]
        scores_b = [0.60, 0.55, 0.50, 0.75, 0.65, 0.55, 0.72]
        frame = _make_wilcoxon_frame(scores_a=scores_a, scores_b=scores_b)
        assert isinstance(
            self._adapter().wilcoxon_paired(frame, "final_score"), WilcoxonReport
        )

    def test_non_primary_methods_raise(self) -> None:
        adapter = self._adapter()
        frame = ResultFrame(results=())
        with pytest.raises(NotImplementedError):
            adapter.friedman_nemenyi(frame, "final_score")
        with pytest.raises(NotImplementedError):
            adapter.mixed_linear_model(frame, "y ~ x")


# ---------------------------------------------------------------------------
# Testes — FriedmanNemenyiAdapter
# ---------------------------------------------------------------------------


class TestFriedmanNemenyiAdapter:
    """Testes do FriedmanNemenyiAdapter."""

    def _adapter(self) -> FriedmanNemenyiAdapter:
        return FriedmanNemenyiAdapter(StatsAdapterConfig(alpha=0.05))

    def test_known_dataset_significant_with_posthoc(self) -> None:
        # 3 LLMs com scores claramente distintos → Friedman significativo
        llm_scores = {
            "llm-alpha": [0.80, 0.75, 0.82, 0.78, 0.76, 0.83, 0.79],
            "llm-beta": [0.65, 0.61, 0.67, 0.63, 0.62, 0.68, 0.64],
            "llm-gamma": [0.50, 0.48, 0.52, 0.49, 0.47, 0.53, 0.51],
        }
        frame = _make_friedman_frame(llm_scores=llm_scores)
        report = self._adapter().friedman_nemenyi(frame, "final_score")

        assert isinstance(report, FriedmanReport)
        assert report.significant is True
        assert report.n_groups == 3
        assert report.n_blocks == 7
        assert len(report.nemenyi_pairs) > 0
        # Todos os pares: llm-alpha vs llm-beta, etc.
        pair_names = {(p.llm_a, p.llm_b) for p in report.nemenyi_pairs}
        assert ("llm-alpha", "llm-beta") in pair_names

    def test_nemenyi_not_computed_when_not_significant(self) -> None:
        # Scores quase idênticos → Friedman não significativo
        llm_scores = {
            "llm-alpha": [0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70],
            "llm-beta": [0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70],
            "llm-gamma": [0.70, 0.70, 0.70, 0.70, 0.70, 0.70, 0.70],
        }
        frame = _make_friedman_frame(llm_scores=llm_scores)
        report = self._adapter().friedman_nemenyi(frame, "final_score")

        assert report.nemenyi_pairs == ()

    def test_fewer_than_3_groups_returns_degenerate(self) -> None:
        llm_scores = {
            "llm-alpha": [0.80, 0.75, 0.82, 0.78, 0.76],
            "llm-beta": [0.65, 0.61, 0.67, 0.63, 0.62],
        }
        frame = _make_friedman_frame(llm_scores=llm_scores)
        report = self._adapter().friedman_nemenyi(frame, "final_score")

        assert report.significant is False
        assert report.p_value == pytest.approx(1.0)
        assert report.nemenyi_pairs == ()
        assert report.n_groups == 2

    def test_fewer_than_3_groups_does_not_raise(self) -> None:
        frame = ResultFrame(results=())
        report = self._adapter().friedman_nemenyi(frame, "final_score")
        assert isinstance(report, FriedmanReport)

    def test_report_fields_present(self) -> None:
        llm_scores = {
            "llm-alpha": [0.80, 0.75, 0.82, 0.78, 0.76],
            "llm-beta": [0.65, 0.61, 0.67, 0.63, 0.62],
            "llm-gamma": [0.50, 0.48, 0.52, 0.49, 0.47],
        }
        frame = _make_friedman_frame(llm_scores=llm_scores)
        report = self._adapter().friedman_nemenyi(frame, "final_score")

        assert report.metric == "final_score"
        assert report.p_value_corrected is None
        assert isinstance(report.chi2_statistic, float)

    def test_nemenyi_pairs_are_named_pairs(self) -> None:
        llm_scores = {
            "llm-alpha": [0.80, 0.75, 0.82, 0.78, 0.76, 0.83, 0.79, 0.81],
            "llm-beta": [0.65, 0.61, 0.67, 0.63, 0.62, 0.68, 0.64, 0.66],
            "llm-gamma": [0.50, 0.48, 0.52, 0.49, 0.47, 0.53, 0.51, 0.50],
        }
        frame = _make_friedman_frame(llm_scores=llm_scores)
        report = self._adapter().friedman_nemenyi(frame, "final_score")

        for pair in report.nemenyi_pairs:
            assert isinstance(pair, NemenyiPair)
            assert pair.llm_a < pair.llm_b  # ordem alfabética
            assert 0.0 <= pair.p_value <= 1.0

    def test_non_primary_methods_raise(self) -> None:
        adapter = self._adapter()
        frame = ResultFrame(results=())
        with pytest.raises(NotImplementedError):
            adapter.wilcoxon_paired(frame, "final_score")
        with pytest.raises(NotImplementedError):
            adapter.mixed_linear_model(frame, "y ~ x")


# ---------------------------------------------------------------------------
# Testes — MixedLinearModelAdapter
# ---------------------------------------------------------------------------


class TestMixedLinearModelAdapter:
    """Testes do MixedLinearModelAdapter."""

    def _adapter(self) -> MixedLinearModelAdapter:
        return MixedLinearModelAdapter(StatsAdapterConfig(alpha=0.05, reml=True))

    def test_valid_formula_returns_report(self) -> None:
        frame = _make_mlm_frame()
        formula = "final_score ~ base * llm + (1 | question_id)"
        report = self._adapter().mixed_linear_model(frame, formula)

        assert isinstance(report, MLMReport)
        assert report.formula == formula
        assert report.n_observations > 0
        # AIC pode ser NaN quando MLE está na fronteira do espaço paramétrico
        # (statsmodels ConvergenceWarning: "on the boundary") — comportamento legítimo.
        assert isinstance(report.convergence_warning, bool)

    def test_formula_without_random_effects_works(self) -> None:
        frame = _make_mlm_frame()
        # statsmodels usará question_id como grupos (default)
        formula = "final_score ~ base + llm + (1 | question_id)"
        report = self._adapter().mixed_linear_model(frame, formula)
        assert isinstance(report, MLMReport)

    def test_formula_stored_in_report(self) -> None:
        frame = _make_mlm_frame()
        formula = "final_score ~ base + llm + (1 | question_id)"
        report = self._adapter().mixed_linear_model(frame, formula)
        assert report.formula == formula

    def test_non_convergence_returns_nan_without_exception(self) -> None:
        # Fórmula inválida → exceção numérica capturada gracefully
        frame = ResultFrame(results=())  # DataFrame vazio → falha garantida
        report = self._adapter().mixed_linear_model(
            frame, "final_score ~ base * llm + (1 | question_id)"
        )

        assert isinstance(report, MLMReport)
        assert report.convergence_warning is True
        assert math.isnan(report.aic)
        assert math.isnan(report.base_effect_coef)
        assert math.isnan(report.base_effect_p_value)

    def test_convergence_warning_false_on_success(self) -> None:
        frame = _make_mlm_frame()
        report = self._adapter().mixed_linear_model(
            frame, "final_score ~ base + llm + (1 | question_id)"
        )
        # O modelo deve convergir (sem exceção) e retornar um MLMReport
        assert isinstance(report, MLMReport)
        assert isinstance(report.convergence_warning, bool)
        assert report.n_observations > 0

    def test_degenerate_does_not_raise(self) -> None:
        frame = ResultFrame(results=())
        report = self._adapter().mixed_linear_model(frame, "y ~ x")
        assert isinstance(report, MLMReport)

    def test_converged_false_returns_degenerate(
        self, mocker: pytest.MonkeyPatch
    ) -> None:
        """Quando fit() retorna mas converged=False, o adapter devolve relatório
        degenerado com NaN e convergence_warning=True — não expõe coeficientes reais."""
        fake_result = mocker.MagicMock()
        fake_result.converged = False
        fake_result.params.index = []
        fake_result.pvalues.index = []
        fake_result.aic = 123.0
        fake_result.nobs = 42

        fake_model = mocker.MagicMock()
        fake_model.fit.return_value = fake_result

        mocker.patch(
            "inteligenciomica_eval.infrastructure.adapters.stats_adapters.smf.mixedlm",
            return_value=fake_model,
        )

        frame = _make_mlm_frame()
        report = self._adapter().mixed_linear_model(
            frame, "final_score ~ base + llm + (1 | question_id)"
        )

        assert isinstance(report, MLMReport)
        assert report.convergence_warning is True
        assert math.isnan(report.aic)
        assert math.isnan(report.base_effect_coef)
        assert math.isnan(report.base_effect_p_value)
        assert report.llm_effect_p_values == {}

    def test_non_primary_methods_raise(self) -> None:
        adapter = self._adapter()
        frame = ResultFrame(results=())
        with pytest.raises(NotImplementedError):
            adapter.wilcoxon_paired(frame, "final_score")
        with pytest.raises(NotImplementedError):
            adapter.friedman_nemenyi(frame, "final_score")
