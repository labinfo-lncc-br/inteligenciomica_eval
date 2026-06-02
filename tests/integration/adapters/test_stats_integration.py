"""Testes de integração dos adapters estatísticos — dataset de 13 pares/blocos reais.

Marcados com ``@pytest.mark.integration``. Os valores esperados são calculados
independentemente via scipy (ver ``tests/golden/stats_wilcoxon_expected.json``
e ``stats_friedman_expected.json``) e conferidos aqui como golden values.

TAREFA-404 (ADR-011, §14.2 DoD integração).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scipy.stats import friedmanchisquare, wilcoxon

from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
)
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
from inteligenciomica_eval.infrastructure.adapters.stats_adapters import (
    FriedmanNemenyiAdapter,
    WilcoxonAdapter,
)
from inteligenciomica_eval.infrastructure.config.adapter_configs import (
    StatsAdapterConfig,
)

# ---------------------------------------------------------------------------
# Caminhos para arquivos de golden
# ---------------------------------------------------------------------------

_GOLDEN_DIR = Path(__file__).parent.parent.parent / "golden"
_WILCOXON_GOLDEN = _GOLDEN_DIR / "stats_wilcoxon_expected.json"
_FRIEDMAN_GOLDEN = _GOLDEN_DIR / "stats_friedman_expected.json"


# ---------------------------------------------------------------------------
# Helpers de fabricação de dados
# ---------------------------------------------------------------------------


def _make_result(
    *,
    question_id: str,
    base: str,
    llm: str,
    seed: int = 42,
    final_score: float,
) -> EvaluationResult:
    q = Question(question_id=question_id, text=f"Q {question_id}", ground_truth="ref.")
    row_id = RowId.from_cell(
        run_id="integ-run",
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
        retrieved_chunks_text=("texto.",),
        retrieval_scores=(0.9,),
    )
    mv = MetricVector(
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
        metrics=mv,
        final_score=FinalScore(final_score),
        determinism_regime=DeterminismRegime.JUDGE,
        critical_failure_flag=None,
        critical_failure_note=None,
    )


# ---------------------------------------------------------------------------
# Testes de integração — Wilcoxon (golden)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestWilcoxonIntegration:
    """WilcoxonAdapter verificado contra golden values de scipy."""

    def _load_golden(self) -> dict:  # type: ignore[type-arg]
        return json.loads(_WILCOXON_GOLDEN.read_text())

    def _build_frame(self, golden: dict) -> ResultFrame:  # type: ignore[type-arg]
        results = []
        base_a = golden["base_a"]
        base_b = golden["base_b"]
        llm = "llm-integ"
        for pair in golden["pairs"]:
            qid = pair["question_id"]
            seed = pair["seed"]
            results.append(
                _make_result(
                    question_id=qid,
                    base=base_a,
                    llm=llm,
                    seed=seed,
                    final_score=pair["base_a_score"],
                )
            )
            results.append(
                _make_result(
                    question_id=qid,
                    base=base_b,
                    llm=llm,
                    seed=seed,
                    final_score=pair["base_b_score"],
                )
            )
        return ResultFrame(results=tuple(results))

    def test_wilcoxon_statistic_matches_scipy(self) -> None:
        golden = self._load_golden()
        frame = self._build_frame(golden)
        adapter = WilcoxonAdapter(StatsAdapterConfig(alpha=0.05, min_pairs_wilcoxon=5))
        report = adapter.wilcoxon_paired(frame, golden["metric"])

        exp = golden["expected"]
        assert report.statistic == pytest.approx(exp["statistic"], abs=1e-4)
        assert report.p_value == pytest.approx(exp["p_value"], rel=0.01)
        assert report.n_pairs == exp["n_pairs"]
        assert report.significant == exp["significant"]

    def test_wilcoxon_effect_size_matches_golden(self) -> None:
        golden = self._load_golden()
        frame = self._build_frame(golden)
        adapter = WilcoxonAdapter(StatsAdapterConfig(alpha=0.05, min_pairs_wilcoxon=5))
        report = adapter.wilcoxon_paired(frame, golden["metric"])

        exp = golden["expected"]
        assert report.effect_size_r is not None
        assert report.effect_size_r == pytest.approx(exp["effect_size_r"], rel=0.01)

    def test_wilcoxon_result_matches_direct_scipy(self) -> None:
        """Verifica que o adapter e scipy direto produzem o mesmo p-value."""
        golden = self._load_golden()
        pairs = golden["pairs"]
        x = [p["base_a_score"] for p in pairs]
        y = [p["base_b_score"] for p in pairs]

        _, p_scipy = wilcoxon(x, y, alternative="two-sided", zero_method="wilcox")

        frame = self._build_frame(golden)
        adapter = WilcoxonAdapter(StatsAdapterConfig(min_pairs_wilcoxon=5))
        report = adapter.wilcoxon_paired(frame, golden["metric"])

        assert report.p_value == pytest.approx(float(p_scipy), rel=1e-4)

    def test_base_labels_match_golden(self) -> None:
        golden = self._load_golden()
        frame = self._build_frame(golden)
        report = WilcoxonAdapter().wilcoxon_paired(frame, golden["metric"])
        assert report.base_a == golden["base_a"]
        assert report.base_b == golden["base_b"]


# ---------------------------------------------------------------------------
# Testes de integração — Friedman + Nemenyi (golden)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestFriedmanNemenyiIntegration:
    """FriedmanNemenyiAdapter verificado contra golden values de scipy."""

    def _load_golden(self) -> dict:  # type: ignore[type-arg]
        return json.loads(_FRIEDMAN_GOLDEN.read_text())

    def _build_frame(self, golden: dict) -> ResultFrame:  # type: ignore[type-arg]
        llm_names = golden["llm_names"]
        results = []
        for block in golden["blocks"]:
            qid = block["question_id"]
            seed = block["seed"]
            base = block["base"]
            for llm, score_key in zip(
                llm_names, ["llm_a_score", "llm_b_score", "llm_c_score"], strict=True
            ):
                results.append(
                    _make_result(
                        question_id=qid,
                        base=base,
                        llm=llm,
                        seed=seed,
                        final_score=block[score_key],
                    )
                )
        return ResultFrame(results=tuple(results))

    def test_friedman_statistic_matches_scipy(self) -> None:
        golden = self._load_golden()
        frame = self._build_frame(golden)
        adapter = FriedmanNemenyiAdapter(StatsAdapterConfig(alpha=0.05))
        report = adapter.friedman_nemenyi(frame, golden["metric"])

        exp = golden["expected"]
        assert report.chi2_statistic == pytest.approx(exp["chi2_statistic"], abs=1e-3)
        assert report.p_value == pytest.approx(exp["p_value"], rel=0.05)
        assert report.significant == exp["significant"]
        assert report.n_groups == exp["n_groups"]
        assert report.n_blocks == exp["n_blocks"]

    def test_nemenyi_pairs_count_and_significance(self) -> None:
        golden = self._load_golden()
        frame = self._build_frame(golden)
        adapter = FriedmanNemenyiAdapter(StatsAdapterConfig(alpha=0.05))
        report = adapter.friedman_nemenyi(frame, golden["metric"])

        assert report.significant is True
        # 3 LLMs → C(3,2) = 3 pares
        assert len(report.nemenyi_pairs) == 3

    def test_friedman_result_matches_direct_scipy(self) -> None:
        """Verifica que adapter e scipy direto produzem o mesmo chi2."""
        golden = self._load_golden()
        blocks = golden["blocks"]
        groups = [
            [b["llm_a_score"] for b in blocks],
            [b["llm_b_score"] for b in blocks],
            [b["llm_c_score"] for b in blocks],
        ]
        stat_scipy, _ = friedmanchisquare(*groups)

        frame = self._build_frame(golden)
        adapter = FriedmanNemenyiAdapter()
        report = adapter.friedman_nemenyi(frame, golden["metric"])

        assert report.chi2_statistic == pytest.approx(float(stat_scipy), abs=1e-3)

    def test_nemenyi_pair_p_values_match_golden(self) -> None:
        golden = self._load_golden()
        frame = self._build_frame(golden)
        adapter = FriedmanNemenyiAdapter(StatsAdapterConfig(alpha=0.05))
        report = adapter.friedman_nemenyi(frame, golden["metric"])

        exp_pairs = {
            (p["llm_a"], p["llm_b"]): p["p_value"]
            for p in golden["expected"]["nemenyi_pairs"]
        }
        for pair in report.nemenyi_pairs:
            key = (pair.llm_a, pair.llm_b)
            if key in exp_pairs:
                assert pair.p_value == pytest.approx(exp_pairs[key], rel=0.05)
