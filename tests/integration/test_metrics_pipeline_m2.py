"""Gate de integração M2 — pipeline de métricas (TAREFA-028, parte a).

Exercita o ``ComputeMetricsUseCase`` (TAREFA-026) fiado com os adapters **reais** de
M2 e os decorators de retry (TAREFA-027) sobre os fakes in-memory de armazenamento
(TAREFA-011), cobrindo os 4 cenários da passada de julgamento:

* **q1_normal** — métricas válidas → ``FinalScore`` calculável;
* **q2_nan_parcial** — ``answer_correctness`` NaN (falha de parsing, peso 0.45)
  → ``FinalScore`` NaN (n_nan_excluded);
* **q3_retry** — falha total de I/O na 1ª tentativa, sucesso na 2ª → calculável;
* **q4_exhaust** — falha total de I/O 3x → NaN-sentinel (ADR-007) → ``FinalScore`` NaN.

Mock — **nível SDK, NÃO respx** (CLAUDE.md §11 + memória + FAIL da TAREFA-024):
``respx`` (mesmo global) **trava** (timeout/exit 124) com o SDK OpenAI no sandbox do
auditor (asyncify→asyncio.to_thread). Diferente do gate M1 (TAREFA-021, Qdrant-gated e
portanto *pulado* no sandbox), este teste **roda** em ``pytest -m integration`` sem
Docker, então respx aqui reproduziria o FAIL. Substituição §11-compatível:

* ``RAGASLayer1Adapter`` é construído **real** com ``_metrics`` injetado (cada métrica
  é um double com ``single_turn_ascore`` AsyncMock). Exercita o ``score()`` real:
  laço por métrica, isolamento de NaN por campo, e a conversão I/O→``MetricComputationError``.
* ``PrometheusRubricJudgeAdapter`` é construído **real** com ``_client.chat.completions.create``
  mockado (AsyncMock) — padrão CLAUDE.md §11.
* ``DeterministicMetricsAdapter`` é **real** (BERTScore CPU, sem mock).

Contagem de "chamadas HTTP de Camada 1" (asserções 3/4 da spec) = ``call_args_list`` do
AsyncMock de ``answer_correctness.single_turn_ascore``: como é a 1ª métrica do laço,
é chamado exatamente **uma vez por tentativa** de ``RAGASLayer1Adapter.score()`` — o
equivalente §11-compatível de ``len(respx.calls)`` ("ou equivalente", Prompt B item 3).

Nota sobre HTTP 500 vs falha total: a spec descreve a falha de Camada 1 como "HTTP 500",
mas o ``RAGASLayer1Adapter`` trata 500 como falha de parsing (NaN por campo), e só
``APIConnectionError``/``APITimeoutError`` como falha total → ``MetricComputationError``
(ragas_metrics.py ``_IO_FAILURE_TYPES``). Por isso q3/q4 disparam ``APIConnectionError``
— a falha que realmente aciona o retry (ADR-007), fiel ao contrato do adapter (TAREFA-023).
"""

from __future__ import annotations

import json
import math
import pathlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest
from fakes.storage import (
    InMemoryResultReader,
    InMemoryResultStore,
    InMemoryResultWriter,
)

from inteligenciomica_eval.application.compute_metrics_use_case import (
    ComputeMetricsConfig,
    ComputeMetricsInput,
    ComputeMetricsUseCase,
)
from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
)
from inteligenciomica_eval.domain.services.final_score import (
    DEFAULT_WEIGHTS,
    FinalScoreCalculator,
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

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Golden + scenario constants
# ---------------------------------------------------------------------------

_GOLDEN_PATH = (
    pathlib.Path(__file__).parents[1] / "golden" / "metrics_pipeline_m2_expected.json"
)
_GOLDEN: dict[str, Any] = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))

_RUN_ID: str = _GOLDEN["run_id"]
_ROUND_ID: str = _GOLDEN["round_id"]
_PHASE: str = _GOLDEN["phase"]
_L1: dict[str, float] = _GOLDEN["layer1_normal"]

_JUDGE_URL = "http://vllm-judge-m2:8001/v1"
_DUMMY_REQUEST = httpx.Request("POST", f"{_JUDGE_URL}/chat/completions")
_BASE = "IDx_400k"
_LLM = "llm-alpha"
_SEED = 42

# Texto distinto por pergunta — discrimina o cenário dentro dos mocks de métrica RAGAS
# (RAGAS recebe ``SingleTurnSample.user_input == EvaluationSample.question``).
_QUESTIONS: dict[str, str] = {
    "q1_normal": "Qual o mecanismo de acao das estatinas?",
    "q2_nan_parcial": "Como a metformina reduz a glicemia?",
    "q3_retry": "O que causa a resistencia bacteriana a betalactamicos?",
    "q4_exhaust": "Qual o papel da proteina p53 na supressao tumoral?",
}
_GROUND_TRUTH: dict[str, str] = {
    "q1_normal": "As estatinas inibem a HMG-CoA redutase, reduzindo a sintese de colesterol.",
    "q2_nan_parcial": "A metformina reduz a producao hepatica de glicose.",
    "q3_retry": "Bacterias produzem betalactamases que hidrolisam o anel betalactamico.",
    "q4_exhaust": "A p53 regula o ciclo celular e induz apoptose ante danos no DNA.",
}
_GENERATED: dict[str, str] = {
    "q1_normal": "As estatinas atuam inibindo a HMG-CoA redutase, diminuindo o colesterol.",
    "q2_nan_parcial": "A metformina diminui a gliconeogenese hepatica.",
    "q3_retry": "As bacterias resistem produzindo betalactamases que quebram o anel.",
    "q4_exhaust": "A p53 controla o ciclo celular e aciona apoptose diante de lesoes no DNA.",
}


# ---------------------------------------------------------------------------
# RAGAS metric doubles (injetados via _metrics — sem rede, sem respx)
# ---------------------------------------------------------------------------


def _build_ragas_metrics() -> tuple[dict[str, MagicMock], AsyncMock]:
    """Constrói os 6 doubles de métrica RAGAS scriptados por cenário.

    ``answer_correctness`` (1ª métrica do laço) dirige cada cenário pelo texto da
    pergunta; as outras 5 retornam constantes finitas. Cada *fresh* build reinicia
    o contador interno do cenário de retry (q3).

    Returns:
        Tupla ``(metrics_dict, answer_correctness_ascore)``. O 2º é o AsyncMock cujo
        ``call_args_list`` conta as tentativas de Camada 1 por pergunta (equivalente
        §11 de ``respx.calls``).
    """
    q3_attempts = {"n": 0}

    def _ac_side_effect(sample: Any) -> float:
        q = sample.user_input
        if q == _QUESTIONS["q4_exhaust"]:
            # Falha total de I/O → RAGAS levanta MetricComputationError → retry (ADR-007).
            raise openai.APIConnectionError(
                message="judge down", request=_DUMMY_REQUEST
            )
        if q == _QUESTIONS["q3_retry"]:
            q3_attempts["n"] += 1
            if q3_attempts["n"] == 1:
                raise openai.APIConnectionError(
                    message="transient", request=_DUMMY_REQUEST
                )
            return _L1["answer_correctness"]
        if q == _QUESTIONS["q2_nan_parcial"]:
            # Falha de parsing/validação (NÃO I/O) → NaN só neste campo (ADR-007).
            raise ValueError("unparseable answer_correctness output")
        return _L1["answer_correctness"]

    ac_ascore = AsyncMock(side_effect=_ac_side_effect)
    ac_metric = MagicMock()
    ac_metric.single_turn_ascore = ac_ascore

    # answer_correctness PRIMEIRO (ordem de inserção = ordem do laço RAGAS).
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
    return metrics, ac_ascore


def _rubric_completion() -> MagicMock:
    """Completion OpenAI-compatible mínima com o JSON da rubrica (score bruto 4 → 0.75)."""
    comp = MagicMock()
    comp.choices = [MagicMock()]
    comp.choices[0].message.content = json.dumps(
        {
            "score": _GOLDEN["rubric_normal_raw"],
            "feedback": {"global": "Resposta adequada.", "precisao": "boa"},
        }
    )
    return comp


def _nan_metrics() -> MetricVector:
    """MetricVector todo-NaN para a linha 'gerada' (pré-julgamento)."""
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


def _seed_pending(store: InMemoryResultStore, qids: list[str]) -> None:
    """Persiste linhas 'geradas' (final_score NaN, regime GENERATOR) a julgar."""
    writer = InMemoryResultWriter(store, round_id=_ROUND_ID)
    for qid in qids:
        answer = GeneratedAnswer(
            row_id=RowId.from_cell(
                run_id=_RUN_ID,
                phase=_PHASE,
                base=_BASE,
                llm=_LLM,
                seed=_SEED,
                question_id=qid,
            ),
            question=Question(
                question_id=qid, text=_QUESTIONS[qid], ground_truth=_GROUND_TRUTH[qid]
            ),
            base=BaseId(_BASE),
            llm=LLMId(_LLM),
            seed=Seed(_SEED),
            phase=_PHASE,
            generated_answer=_GENERATED[qid],
            retrieved_chunk_ids=("c1",),
            retrieved_chunks_text=("Contexto biomedico relevante.",),
            retrieval_scores=(0.9,),
        )
        writer.append(
            EvaluationResult(
                answer=answer,
                metrics=_nan_metrics(),
                final_score=FinalScore(float("nan")),
                determinism_regime=DeterminismRegime.GENERATOR,
                critical_failure_flag=0,
                critical_failure_note=None,
            )
        )


def _build_use_case(
    store: InMemoryResultStore, *, ragas_metrics: dict[str, MagicMock]
) -> tuple[
    ComputeMetricsUseCase, InMemoryResultReader, InMemoryResultWriter, AsyncMock
]:
    """Fia o use case com os adapters reais + decorators de retry (config instantânea)."""
    writer = InMemoryResultWriter(store, round_id=_ROUND_ID)
    reader = InMemoryResultReader(store)

    ragas = RAGASLayer1Adapter(
        RagasAdapterConfig(judge_url=_JUDGE_URL), _metrics=ragas_metrics
    )
    prometheus = PrometheusRubricJudgeAdapter(
        RubricJudgeAdapterConfig(vllm_judge_url=_JUDGE_URL)
    )
    create_mock = AsyncMock(return_value=_rubric_completion())
    # SDK-level mock (§11) — substitui respx para evitar o hang do sandbox do auditor.
    prometheus._client.chat.completions.create = create_mock  # type: ignore[method-assign]

    # initial_wait_s=0.0 → backoff instantâneo (await asyncio.sleep(0)); max_retries=2
    # → até 3 tentativas (1 + 2 retries), batendo a "contagem de 3 chamadas" da spec.
    retry = RetryConfig(max_retries=2, initial_wait_s=0.0)
    metric_suite = make_retryable_metric_suite(ragas, retry)
    rubric_judge = make_retryable_rubric_judge(prometheus, retry)
    aux = DeterministicMetricsAdapter()  # BERTScore REAL (CPU, sem mock)

    use_case = ComputeMetricsUseCase(
        reader=reader,
        writer=writer,
        metric_suite=metric_suite,
        rubric_judge=rubric_judge,
        aux_metrics=aux,
        score_calculator=FinalScoreCalculator(DEFAULT_WEIGHTS),
        config=ComputeMetricsConfig(),
    )
    return use_case, reader, writer, create_mock


# ---------------------------------------------------------------------------
# Teste principal — 4 cenários
# ---------------------------------------------------------------------------


async def test_metrics_pipeline_four_scenarios() -> None:
    """Pipeline real pelos 4 cenários: normal / NaN parcial / retry / NaN-sentinel."""
    store = InMemoryResultStore()
    qids = ["q1_normal", "q2_nan_parcial", "q3_retry", "q4_exhaust"]
    _seed_pending(store, qids)
    ragas_metrics, ac_ascore = _build_ragas_metrics()
    use_case, reader, _writer, _create = _build_use_case(
        store, ragas_metrics=ragas_metrics
    )

    report = await use_case.execute(
        ComputeMetricsInput(run_id=_RUN_ID, round_id=_ROUND_ID, phase=_PHASE)
    )

    # ── Asserção 1 + 7: contagens do relatório ──────────────────────────────────
    exp = _GOLDEN["expected_report"]
    assert report.n_processed == exp["n_processed"]  # 2 (q1, q3)
    assert report.n_nan_excluded == exp["n_nan_excluded"]  # 2 (q2, q4)
    assert report.n_skipped == exp["n_skipped"]  # 0
    assert report.n_failed_terminal == exp["n_failed_terminal"]  # 0

    by_qid = {
        r.answer.question.question_id: r
        for r in reader.load(round_id=_ROUND_ID, phase=_PHASE).results
    }

    # ── Asserção 2: golden inline do FinalScore (q1 e q3 → 0.809) ────────────────
    assert by_qid["q1_normal"].final_score.value == pytest.approx(
        _GOLDEN["samples"]["q1_normal"]["expected_final_score"], abs=1e-9
    )
    assert by_qid["q3_retry"].final_score.value == pytest.approx(
        _GOLDEN["samples"]["q3_retry"]["expected_final_score"], abs=1e-9
    )
    assert math.isnan(by_qid["q2_nan_parcial"].final_score.value)
    assert math.isnan(by_qid["q4_exhaust"].final_score.value)

    # ── Asserção 3 + 4: tentativas de Camada 1 por cenário (equivalente §11 de respx) ─
    def _attempts(qid: str) -> int:
        target = _QUESTIONS[qid]
        return sum(
            1 for c in ac_ascore.call_args_list if c.args[0].user_input == target
        )

    assert _attempts("q1_normal") == 1
    assert _attempts("q2_nan_parcial") == 1
    assert _attempts("q3_retry") == 2  # 1 falha de I/O + 1 sucesso
    assert _attempts("q4_exhaust") == 3  # 3 falhas → NaN-sentinel (max_retries=2)

    # ── Asserção 6: batch_invariant=True (regime JUDGE) em TODAS as linhas julgadas ─
    assert by_qid  # 4 linhas
    assert all(r.batch_invariant for r in by_qid.values())
    assert all(r.determinism_regime is DeterminismRegime.JUDGE for r in by_qid.values())

    # ── Asserção 7: BERTScore REAL (sem mock) na q1 ─────────────────────────────
    # bertscore_f1 tem peso 0 (§7.1) → NaN não afeta o final_score acima; só é NaN se
    # o modelo estiver indisponível offline. Quando carregado, F1 é um real positivo.
    bf1 = by_qid["q1_normal"].metrics.bertscore_f1
    if not math.isnan(bf1):
        assert bf1 > 0.0


# ---------------------------------------------------------------------------
# Idempotência (ADR-009) — cenário limpo (todas as linhas finitas)
# ---------------------------------------------------------------------------


async def test_idempotent_rerun_skips_scored_rows() -> None:
    """2ª execução pula linhas já pontuadas; nenhum adapter de métrica é reinvocado.

    Usa apenas linhas que terminam com ``final_score`` finito (q1 normal + q3 com
    retry-sucesso), pois linhas NaN-sentinel são reprocessadas por design (ADR-007 /
    docstring do ``ComputeMetricsUseCase``; mesmo precedente do E2E M0, TAREFA-012).
    Demonstra o contrato de idempotência da spec sem o confundidor de NaN.
    """
    store = InMemoryResultStore()
    qids = ["q1_normal", "q3_retry"]
    _seed_pending(store, qids)
    ragas_metrics, ac_ascore = _build_ragas_metrics()
    use_case, _reader, writer, create_mock = _build_use_case(
        store, ragas_metrics=ragas_metrics
    )

    first = await use_case.execute(
        ComputeMetricsInput(run_id=_RUN_ID, round_id=_ROUND_ID, phase=_PHASE)
    )
    assert first.n_processed == 2
    assert first.n_skipped == 0

    # Espia update_metrics na 2ª rodada (preservando o comportamento real).
    update_spy = MagicMock(wraps=writer.update_metrics)
    writer.update_metrics = update_spy  # type: ignore[method-assign]
    ac_ascore.reset_mock()
    create_mock.reset_mock()

    second = await use_case.execute(
        ComputeMetricsInput(run_id=_RUN_ID, round_id=_ROUND_ID, phase=_PHASE)
    )

    assert second.n_skipped == 2  # ambas finitas → puladas (ADR-009)
    assert second.n_processed == 0
    assert update_spy.call_count == 0  # update_metrics NÃO chamado na 2ª rodada
    assert ac_ascore.call_count == 0  # Camada 1 NÃO reinvocada
    assert create_mock.call_count == 0  # Camada 2 NÃO reinvocada
