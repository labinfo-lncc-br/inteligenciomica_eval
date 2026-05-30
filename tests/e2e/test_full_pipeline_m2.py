"""E2E M2 — pipeline completo de avaliação (TAREFA-028, parte b) — FECHA O M2.

Estende o E2E de M1 (TAREFA-021) com a passada de julgamento real de M2: 2 perguntas
PT-BR x 2 LLMs x 1 seed = 4 respostas normais + 1 resposta extra (``q03_nan``, só em
``llm-alpha``) com NaN forçado por falha total de I/O 3x (``APIConnectionError`` →
``MetricComputationError`` → NaN-sentinel, ADR-007).

Fluxo: seed das linhas geradas no ``ParquetStorage`` (tmp_path) → ``run_m2_metrics_pass``
(``ComputeMetricsUseCase`` + ``RetryableMetric*`` + adapters reais de M2) →
``AggregationService`` + ``RankScoreCalculator`` → ``ConfigAggregate``.

Adapters **reais**: ``RAGASLayer1Adapter`` (``_metrics`` injetado),
``PrometheusRubricJudgeAdapter`` (``_client`` mockado SDK), ``DeterministicMetricsAdapter``
(BERTScore CPU). Mock no **nível SDK substitui respx** (CLAUDE.md §11 + memória + FAIL da
TAREFA-024): respx trava com o SDK OpenAI no sandbox do auditor. "Sem rede real" é
satisfeito por construção (nenhuma chamada HTTP é emitida — tudo mockado no SDK).

Gating: ``E2E_ENABLED`` (igual ao smoke M1, TAREFA-021) — a construção carrega o modelo
BERTScore (custoso para o gate unitário rápido). Sem ``E2E_ENABLED``, ``pytest -m e2e``
coleta e **pula** (rápido e seguro no sandbox do auditor).

Leitura do Parquet: ``pq.ParquetFile(f).read()`` por arquivo, **não** ``pd.read_parquet``
sobre a árvore Hive — esta dispara auto-detecção de partição e conflita o ``round_id``
string x dictionary (``ArrowTypeError``, decisão TAREFA-021).
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pyarrow.parquet as pq
import pytest

from e2e._harness import run_m2_metrics_pass
from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
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
from inteligenciomica_eval.infrastructure.adapters.deterministic_metrics import (
    DeterministicMetricsAdapter,
)
from inteligenciomica_eval.infrastructure.adapters.prometheus_rubric_judge import (
    PrometheusRubricJudgeAdapter,
)
from inteligenciomica_eval.infrastructure.adapters.ragas_metrics import (
    RAGASLayer1Adapter,
)
from inteligenciomica_eval.infrastructure.adapters.retryable_metric_adapter import (
    RetryConfig,
    make_retryable_metric_suite,
    make_retryable_rubric_judge,
)
from inteligenciomica_eval.infrastructure.config.adapter_configs import (
    RagasAdapterConfig,
    RubricJudgeAdapterConfig,
)
from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
    ParquetStorage,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("E2E_ENABLED"),
        reason="set E2E_ENABLED=1 to run the full-stack E2E M2 (loads BERTScore)",
    ),
]

# ---------------------------------------------------------------------------
# Golden + scenario
# ---------------------------------------------------------------------------

_GOLDEN_PATH = pathlib.Path(__file__).parents[1] / "golden" / "e2e_m2_expected.json"
_GOLDEN: dict[str, Any] = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))

_RUN_ID: str = _GOLDEN["run_id"]
_ROUND_ID: str = _GOLDEN["round_id"]
_PHASE: str = _GOLDEN["phase"]
_BASE: str = _GOLDEN["base"]
_SEED: int = _GOLDEN["seed"]
_THRESHOLD: float = _GOLDEN["failure_threshold"]
_LLMS: list[str] = _GOLDEN["llms"]
_NAN_QID: str = _GOLDEN["nan_question_id"]
_NAN_LLM: str = _GOLDEN["nan_config_llm"]
_TOTAL_ROWS: int = _GOLDEN["total_rows"]
_NORMAL_FINAL: float = _GOLDEN["normal_final_score"]
_L1: dict[str, float] = _GOLDEN["layer1_normal"]
_METRIC_COLS: list[str] = _GOLDEN["metric_score_columns"]

_QUESTIONS: dict[str, dict[str, str]] = {q["id"]: q for q in _GOLDEN["questions"]}
_JUDGE_URL = "http://vllm-judge-m2-e2e:8001/v1"
_DUMMY_REQUEST = httpx.Request("POST", f"{_JUDGE_URL}/chat/completions")
_F32_TOL = 1e-4
_TIME_BUDGET_S = 60.0


# ---------------------------------------------------------------------------
# Adapter doubles (SDK-level — sem respx)
# ---------------------------------------------------------------------------


def _build_ragas_metrics() -> dict[str, MagicMock]:
    """6 doubles de métrica RAGAS: ``q03_nan`` → falha total de I/O; resto → finito."""
    nan_text = _QUESTIONS[_NAN_QID]["text"]

    def _ac_side_effect(sample: Any) -> float:
        if sample.user_input == nan_text:
            raise openai.APIConnectionError(
                message="judge down", request=_DUMMY_REQUEST
            )
        return _L1["answer_correctness"]

    ac_metric = MagicMock()
    ac_metric.single_turn_ascore = AsyncMock(side_effect=_ac_side_effect)
    metrics: dict[str, MagicMock] = {"answer_correctness": ac_metric}
    for field in (
        "answer_similarity",
        "faithfulness",
        "context_precision",
        "context_recall",
        "answer_relevancy",
    ):
        m = MagicMock()
        m.single_turn_ascore = AsyncMock(return_value=_L1[field])
        metrics[field] = m
    return metrics


def _rubric_completion() -> MagicMock:
    comp = MagicMock()
    comp.choices = [MagicMock()]
    comp.choices[0].message.content = json.dumps(
        {
            "score": _GOLDEN["rubric_normal_raw"],
            "feedback": {"global": "Resposta adequada.", "precisao": "boa"},
        }
    )
    return comp


def _build_adapters() -> tuple[Any, Any, DeterministicMetricsAdapter]:
    """RAGAS + Prometheus reais (mockados no SDK) + BERTScore real, com retry."""
    ragas = RAGASLayer1Adapter(
        RagasAdapterConfig(judge_url=_JUDGE_URL), _metrics=_build_ragas_metrics()
    )
    prometheus = PrometheusRubricJudgeAdapter(
        RubricJudgeAdapterConfig(vllm_judge_url=_JUDGE_URL)
    )
    prometheus._client.chat.completions.create = AsyncMock(  # type: ignore[method-assign]
        return_value=_rubric_completion()
    )
    retry = RetryConfig(max_retries=2, initial_wait_s=0.0)
    metric_suite = make_retryable_metric_suite(ragas, retry)
    rubric_judge = make_retryable_rubric_judge(prometheus, retry)
    aux = DeterministicMetricsAdapter()  # BERTScore REAL (CPU)
    return metric_suite, rubric_judge, aux


# ---------------------------------------------------------------------------
# Seed da passada de geração (linhas NaN-final, regime GENERATOR)
# ---------------------------------------------------------------------------


def _nan_metrics() -> MetricVector:
    nan = float("nan")
    return MetricVector(
        answer_correctness=nan,
        answer_similarity=nan,
        faithfulness=nan,
        context_precision=nan,
        context_recall=nan,
        answer_relevancy=nan,
        bertscore_f1=nan,
        rubric_biomed_score=nan,
    )


def _cells() -> list[tuple[str, str]]:
    """Células (llm, question_id): q01/q02 nos 2 LLMs + q03_nan só em llm-alpha."""
    out: list[tuple[str, str]] = []
    for llm in _LLMS:
        out.append((llm, "q01"))
        out.append((llm, "q02"))
    out.append((_NAN_LLM, _NAN_QID))
    return out


def _seed_generation(storage: ParquetStorage) -> None:
    """Persiste as linhas geradas (final_score NaN) — passada 1 do §3.4."""
    for llm, qid in _cells():
        q = _QUESTIONS[qid]
        answer = GeneratedAnswer(
            row_id=RowId.from_cell(
                run_id=_RUN_ID,
                phase=_PHASE,
                base=_BASE,
                llm=llm,
                seed=_SEED,
                question_id=qid,
            ),
            question=Question(
                question_id=qid, text=q["text"], ground_truth=q["ground_truth"]
            ),
            base=BaseId(_BASE),
            llm=LLMId(llm),
            seed=Seed(_SEED),
            phase=_PHASE,
            generated_answer=q["generated"],
            retrieved_chunk_ids=("c1",),
            retrieved_chunks_text=("Contexto biomedico relevante.",),
            retrieval_scores=(0.9,),
        )
        storage.append(
            EvaluationResult(
                answer=answer,
                metrics=_nan_metrics(),
                final_score=FinalScore(float("nan")),
                determinism_regime=DeterminismRegime.GENERATOR,
                critical_failure_flag=0,  # anotado → critical_failure_rate computável
                critical_failure_note=None,
            )
        )


def _make_storage(base_dir: pathlib.Path) -> ParquetStorage:
    return ParquetStorage(
        base_dir,
        run_id=_RUN_ID,
        round_id=_ROUND_ID,
        judge_model="prometheus-eval/prometheus-8x7b-v2.0",
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        chunk_strategy="sentence",
        top_k=3,
        prompt_version="rubric_v1",
        temperature=0.0,
        ragas_version="stub",
    )


# ---------------------------------------------------------------------------
# E2E M2 — pipeline completo
# ---------------------------------------------------------------------------


async def test_full_pipeline_m2(tmp_path: pathlib.Path) -> None:
    """Pipeline M2 fim-a-fim: julgamento real → Parquet → agregação → golden."""
    storage = _make_storage(tmp_path / "results")
    _seed_generation(storage)
    metric_suite, rubric_judge, aux = _build_adapters()

    t0 = time.monotonic()
    report, aggregates = await run_m2_metrics_pass(
        storage=storage,
        run_id=_RUN_ID,
        round_id=_ROUND_ID,
        phase=_PHASE,
        metric_suite=metric_suite,
        rubric_judge=rubric_judge,
        aux_metrics=aux,
        failure_threshold=_THRESHOLD,
    )
    elapsed = time.monotonic() - t0

    # ── Relatório (n_processed=4, n_nan_excluded=1) ─────────────────────────────
    exp = _GOLDEN["expected_report"]
    assert report.n_processed == exp["n_processed"]
    assert report.n_nan_excluded == exp["n_nan_excluded"]  # >= 1 (asserção 4)
    assert report.n_nan_excluded >= 1
    assert report.n_skipped == exp["n_skipped"]
    assert report.n_failed_terminal == exp["n_failed_terminal"]

    # ── Schema §5.3 + batch_invariant: leitura crua por arquivo (bypass Hive) ───
    row_files = sorted((tmp_path / "results").rglob("*.parquet"))
    assert len(row_files) == _TOTAL_ROWS
    normal_ac_values: list[float] = []
    for f in row_files:
        table = pq.ParquetFile(f).read()
        cols = set(table.column_names)
        # Asserção 10: todos os 8 campos de métrica + rubric_feedback presentes.
        for col in [*_METRIC_COLS, "rubric_feedback"]:
            assert col in cols, f"coluna ausente no Parquet: {col}"
        # Asserção 11: batch_invariant=True em TODAS as linhas (regime JUDGE).
        assert table.column("batch_invariant")[0].as_py() is True
        # rubric_feedback presente e não-null (string vazia é legítima — wiring futuro).
        assert table.column("rubric_feedback")[0].as_py() is not None
        ac = table.column("answer_correctness")[0].as_py()
        fs = table.column("final_score")[0].as_py()
        if fs is not None:  # linha normal (não NaN-sentinel)
            assert ac is not None, "answer_correctness null por bug numa linha normal"
            normal_ac_values.append(ac)
    assert len(normal_ac_values) == 4  # 4 normais com answer_correctness preenchido

    # ── final_score das 4 respostas normais == golden (0.809) ───────────────────
    frame = storage.load(round_id=_ROUND_ID, phase=_PHASE)
    by_key = {
        (r.answer.llm.value, r.answer.question.question_id): r for r in frame.results
    }
    for llm, qid in _cells():
        result = by_key[(llm, qid)]
        if qid == _NAN_QID:
            assert math.isnan(result.final_score.value)
        else:
            assert result.final_score.value == pytest.approx(
                _NORMAL_FINAL, abs=_F32_TOL
            )
        assert result.batch_invariant is True

    # ── Agregação: golden de ConfigAggregate (asserções 4, 12, 15) ──────────────
    agg_by_llm = {a.llm.value: a for a in aggregates}
    for cfg in _GOLDEN["configs"]:
        agg = agg_by_llm[cfg["llm"]]
        assert agg.n_observations == cfg["n_observations"]
        assert agg.n_excluded_nan == cfg["n_excluded_nan"]
        assert agg.median_score == pytest.approx(cfg["median_score"], abs=_F32_TOL)
        assert agg.mean_score == pytest.approx(cfg["mean_score"], abs=_F32_TOL)
        assert agg.min_score == pytest.approx(cfg["min_score"], abs=_F32_TOL)
        assert agg.iqr == pytest.approx(cfg["iqr"], abs=_F32_TOL)
        assert agg.failure_rate == pytest.approx(cfg["failure_rate"], abs=_F32_TOL)
        assert agg.critical_failure_rate == pytest.approx(
            cfg["critical_failure_rate"], abs=_F32_TOL
        )
        assert agg.win_rate == pytest.approx(cfg["win_rate"], abs=_F32_TOL)
        assert agg.rank_score.value == pytest.approx(cfg["rank_score"], abs=_F32_TOL)
    # n_nan_excluded propagado até o ConfigAggregate (asserção 12).
    assert agg_by_llm[_NAN_LLM].n_excluded_nan >= 1

    # ── Tempo < 60s (asserção 6/14) ─────────────────────────────────────────────
    assert elapsed < _TIME_BUDGET_S, (
        f"E2E M2 levou {elapsed:.1f}s (> {_TIME_BUDGET_S}s)"
    )


async def test_full_pipeline_m2_idempotent_rerun(tmp_path: pathlib.Path) -> None:
    """2ª execução pula as 4 linhas finitas (ADR-009); a linha NaN-sentinel reprocessa.

    A spec textual diz ``n_skipped == 5``, mas linhas com ``final_score`` NaN são
    'incompletas' e reprocessadas por design (docstring do ``ComputeMetricsUseCase``;
    mesmo precedente do E2E M0, TAREFA-012). Assertamos ``n_skipped == 4`` (as finitas)
    e a reprodução determinística do NaN-sentinel.
    """
    storage = _make_storage(tmp_path / "results")
    _seed_generation(storage)

    metric_suite, rubric_judge, aux = _build_adapters()
    first, _ = await run_m2_metrics_pass(
        storage=storage,
        run_id=_RUN_ID,
        round_id=_ROUND_ID,
        phase=_PHASE,
        metric_suite=metric_suite,
        rubric_judge=rubric_judge,
        aux_metrics=aux,
        failure_threshold=_THRESHOLD,
    )
    assert first.n_processed == 4
    assert first.n_nan_excluded == 1

    # Adapters frescos na 2ª rodada (contadores zerados).
    metric_suite2, rubric_judge2, aux2 = _build_adapters()
    second, _ = await run_m2_metrics_pass(
        storage=storage,
        run_id=_RUN_ID,
        round_id=_ROUND_ID,
        phase=_PHASE,
        metric_suite=metric_suite2,
        rubric_judge=rubric_judge2,
        aux_metrics=aux2,
        failure_threshold=_THRESHOLD,
    )
    exp = _GOLDEN["expected_report_rerun"]
    assert second.n_skipped == exp["n_skipped"]  # 4 finitas puladas
    assert second.n_processed == exp["n_processed"]  # 0
    assert second.n_nan_excluded == exp["n_nan_excluded"]  # 1 (NaN reprocessada)

    # Nenhuma linha duplicada no Parquet (last-write-wins, ADR-009).
    row_files = list((tmp_path / "results").rglob("*.parquet"))
    assert len(row_files) == _TOTAL_ROWS
