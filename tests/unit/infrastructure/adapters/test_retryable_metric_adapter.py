"""Testes unitários para os decorators de retry (TAREFA-027, ADR-007).

Cenários obrigatórios (todos com ``AsyncMock`` e ``patch('asyncio.sleep')`` para
testes rápidos e determinísticos):

- 1ª falha + 2ª sucesso → resultado correto, 1 retry;
- retries esgotados → NaN-sentinel, SEM exceção ao caller;
- NaN parcial na 1ª → retornado diretamente, SEM retry;
- exceção inesperada → propagada imediatamente;
- backoff [1.0, 2.0, 4.0] para max_retries=3 (spy de asyncio.sleep);
- isinstance(MetricSuitePort/RubricJudgePort) True;
- feedback="[retry_exhausted:3]" no NaN-sentinel do rubric judge;
- jitter=True soma jitter aleatório à espera.
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, patch

import pytest

from inteligenciomica_eval.domain.errors import MetricComputationError
from inteligenciomica_eval.domain.ports import (
    EvaluationSample,
    Layer1Metrics,
    MetricSuitePort,
    RubricJudgePort,
    RubricResult,
)
from inteligenciomica_eval.infrastructure.adapters.retryable_metric_adapter import (
    RetryableMetricSuiteAdapter,
    RetryableRubricJudgeAdapter,
    RetryConfig,
    make_retryable_metric_suite,
    make_retryable_rubric_judge,
)

_SAMPLE = EvaluationSample(
    question_id="q_retry_01",
    question="Qual o mecanismo das estatinas?",
    ground_truth="Inibem a HMG-CoA redutase.",
    generated_answer="As estatinas inibem a HMG-CoA redutase.",
    contexts=("A HMG-CoA redutase é a enzima limitante.",),
)

_GOOD_LAYER1 = Layer1Metrics(
    answer_correctness=0.80,
    answer_similarity=0.75,
    faithfulness=0.90,
    context_precision=0.85,
    context_recall=0.70,
    answer_relevancy=0.88,
)
_PARTIAL_NAN_LAYER1 = Layer1Metrics(
    answer_correctness=math.nan,  # parsing falhou no adapter interno (não é I/O)
    answer_similarity=0.75,
    faithfulness=0.90,
    context_precision=0.85,
    context_recall=0.70,
    answer_relevancy=0.88,
)
_GOOD_RUBRIC = RubricResult(score=0.80, feedback="ok")

_ERR = MetricComputationError("ragas", "judge indisponível")


def _suite(
    mock: AsyncMock, config: RetryConfig | None = None
) -> RetryableMetricSuiteAdapter:
    wrapped = AsyncMock(spec=MetricSuitePort)
    wrapped.score = mock
    return RetryableMetricSuiteAdapter(wrapped, config or RetryConfig())


def _judge(
    mock: AsyncMock, config: RetryConfig | None = None
) -> RetryableRubricJudgeAdapter:
    wrapped = AsyncMock(spec=RubricJudgePort)
    wrapped.score = mock
    return RetryableRubricJudgeAdapter(wrapped, config or RetryConfig())


# ---------------------------------------------------------------------------
# Conformidade de protocolo
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_metric_suite_isinstance(self) -> None:
        adapter = _suite(AsyncMock(return_value=_GOOD_LAYER1))
        assert isinstance(adapter, MetricSuitePort)

    def test_rubric_judge_isinstance(self) -> None:
        adapter = _judge(AsyncMock(return_value=_GOOD_RUBRIC))
        assert isinstance(adapter, RubricJudgePort)

    def test_factories_build_decorators(self) -> None:
        ms = make_retryable_metric_suite(AsyncMock(spec=MetricSuitePort))
        rj = make_retryable_rubric_judge(AsyncMock(spec=RubricJudgePort))
        assert isinstance(ms, RetryableMetricSuiteAdapter)
        assert isinstance(rj, RetryableRubricJudgeAdapter)


# ---------------------------------------------------------------------------
# Retry → sucesso
# ---------------------------------------------------------------------------


class TestRetryThenSuccess:
    async def test_first_fails_second_succeeds(self) -> None:
        mock = AsyncMock(side_effect=[_ERR, _GOOD_LAYER1])
        adapter = _suite(mock)
        with patch("asyncio.sleep", new_callable=AsyncMock) as sleep:
            result = await adapter.score(_SAMPLE)
        assert result == _GOOD_LAYER1
        assert mock.call_count == 2  # 1 falha + 1 sucesso
        assert sleep.await_count == 1  # 1 retry


# ---------------------------------------------------------------------------
# Retries esgotados → NaN-sentinel
# ---------------------------------------------------------------------------


class TestRetryExhausted:
    async def test_metric_suite_returns_nan_sentinel(self) -> None:
        mock = AsyncMock(side_effect=_ERR)  # falha em todas as chamadas
        adapter = _suite(mock)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await adapter.score(_SAMPLE)
        # NaN-sentinel: todos os campos NaN, SEM exceção ao caller.
        assert math.isnan(result.answer_correctness)
        assert math.isnan(result.answer_relevancy)
        assert mock.call_count == 4  # 1 inicial + 3 retries (max_retries=3)

    async def test_rubric_judge_nan_sentinel_feedback(self) -> None:
        mock = AsyncMock(side_effect=_ERR)
        adapter = _judge(mock)
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await adapter.score(_SAMPLE)
        assert math.isnan(result.score)
        assert result.feedback == "[retry_exhausted:3]"
        assert mock.call_count == 4

    async def test_backoff_sequence_is_1_2_4(self) -> None:
        mock = AsyncMock(side_effect=_ERR)
        adapter = _suite(
            mock
        )  # default: max_retries=3, initial_wait_s=1.0, jitter=False
        with patch("asyncio.sleep", new_callable=AsyncMock) as sleep:
            await adapter.score(_SAMPLE)
        waits = [c.args[0] for c in sleep.await_args_list]
        assert waits == [1.0, 2.0, 4.0]


# ---------------------------------------------------------------------------
# NaN parcial → retornado SEM retry (ADR-007)
# ---------------------------------------------------------------------------


class TestPartialNaNNotRetried:
    async def test_partial_nan_returned_without_retry(self) -> None:
        mock = AsyncMock(return_value=_PARTIAL_NAN_LAYER1)
        adapter = _suite(mock)
        with patch("asyncio.sleep", new_callable=AsyncMock) as sleep:
            result = await adapter.score(_SAMPLE)
        # NaN parcial devolvido como está — não é MetricComputationError.
        assert math.isnan(result.answer_correctness)
        assert result.faithfulness == pytest.approx(0.90)
        assert mock.call_count == 1  # SEM retry
        assert sleep.await_count == 0


# ---------------------------------------------------------------------------
# Exceção inesperada → propagada imediatamente
# ---------------------------------------------------------------------------


class TestUnexpectedExceptionPropagates:
    async def test_unexpected_exception_not_retried(self) -> None:
        mock = AsyncMock(side_effect=RuntimeError("bug inesperado"))
        adapter = _suite(mock)
        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as sleep,
            pytest.raises(RuntimeError, match="bug inesperado"),
        ):
            await adapter.score(_SAMPLE)
        assert mock.call_count == 1  # propaga na 1ª, sem retry
        assert sleep.await_count == 0


# ---------------------------------------------------------------------------
# Jitter
# ---------------------------------------------------------------------------


class TestJitter:
    async def test_jitter_adds_random_to_wait(self) -> None:
        mock = AsyncMock(side_effect=[_ERR, _GOOD_LAYER1])
        adapter = _suite(mock, RetryConfig(jitter=True))
        with (
            patch("asyncio.sleep", new_callable=AsyncMock) as sleep,
            patch("random.uniform", return_value=0.5),
        ):
            await adapter.score(_SAMPLE)
        # 1ª espera base = 1.0; jitter mockado = 0.5 → 1.5.
        assert sleep.await_args_list[0].args[0] == pytest.approx(1.5)
