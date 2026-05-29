"""Testes unitários para RAGASLayer1Adapter (TAREFA-017).

Usa AsyncMock injetado via ``_metrics`` para interceptar ``single_turn_ascore``
em cada objeto de métrica — mesmo padrão de TAREFA-014/016 (CLAUDE.md §11):
mockar no nível de abstração correto, sem respx ou httpx.MockTransport.

Estrutura:
- TestProtocolConformance: isinstance + atribuição estática
- TestHappyPath: 6 métricas retornadas, dentro de [0,1]
- TestNaNIsolation: falha em uma métrica → NaN apenas nela
- TestLogging: campos obrigatórios em ragas_layer1_computed
- TestSingleTurnSampleConstruction: campos corretos no SingleTurnSample RAGAS
"""

from __future__ import annotations

import math
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from inteligenciomica_eval.domain.ports import (
    EvaluationSample,
    Layer1Metrics,
    MetricSuitePort,
)
from inteligenciomica_eval.infrastructure.adapters.ragas_metrics import (
    _METRIC_FIELDS,
    RAGASLayer1Adapter,
)

# ---------------------------------------------------------------------------
# Constantes de teste
# ---------------------------------------------------------------------------

_JUDGE_URL = "http://localhost:8001/v1"

_SAMPLE = EvaluationSample(
    question_id="q_mecanismos_resistencia",
    question="Quais são os principais mecanismos de resistência a antibióticos?",
    ground_truth="Três mecanismos: betalactamases, alteração de PBPs e redução de porinas.",
    generated_answer="As bactérias resistem via betalactamases, PBPs alteradas e porinas.",
    contexts=(
        "Betalactamases inativam o anel betalactâmico.",
        "MRSA expressa PBP2a com menor afinidade a penicilinas.",
    ),
)

# Valores padrão para happy path (todos dentro de [0,1])
_DEFAULT_SCORES: dict[str, float] = {
    "answer_correctness": 0.82,
    "answer_similarity": 0.78,
    "faithfulness": 0.91,
    "context_precision": 0.85,
    "context_recall": 0.73,
    "answer_relevancy": 0.87,
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_metric_mock(return_value: float = 0.5) -> MagicMock:
    """Cria mock de objeto RAGAS com single_turn_ascore como AsyncMock."""
    m = MagicMock()
    m.single_turn_ascore = AsyncMock(return_value=return_value)
    return m


def _make_metrics(scores: dict[str, float] | None = None) -> dict[str, Any]:
    """Cria dict de mocks para todos os campos de métrica."""
    if scores is None:
        scores = _DEFAULT_SCORES
    return {
        field: _make_metric_mock(scores.get(field, 0.5)) for field in _METRIC_FIELDS
    }


def _make_adapter(
    metrics: dict[str, Any] | None = None,
) -> RAGASLayer1Adapter:
    """Constrói RAGASLayer1Adapter com métricas injetadas (sem rede/modelo)."""
    if metrics is None:
        metrics = _make_metrics()
    return RAGASLayer1Adapter(
        judge_url=_JUDGE_URL,
        _metrics=metrics,
    )


# ---------------------------------------------------------------------------
# Conformidade de protocolo
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_isinstance_metric_suite_port(self) -> None:
        """isinstance contra MetricSuitePort deve passar em runtime."""
        adapter = _make_adapter()
        assert isinstance(adapter, MetricSuitePort)

    def test_static_typing_assignment(self) -> None:
        """Atribuição suite: MetricSuitePort = RAGASLayer1Adapter() sem type: ignore.

        Detector de regressão de contrato: se MetricSuitePort.score voltar a ser
        def (síncrono), mypy rejeita esta atribuição.
        """
        suite: MetricSuitePort = _make_adapter()
        assert isinstance(suite, MetricSuitePort)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    async def test_returns_layer1_metrics(self) -> None:
        """score() deve retornar instância de Layer1Metrics."""
        adapter = _make_adapter()
        result = await adapter.score(_SAMPLE)
        assert isinstance(result, Layer1Metrics)

    async def test_six_metrics_all_in_range(self) -> None:
        """Todas as 6 métricas devem estar em [0,1] no happy path."""
        adapter = _make_adapter(_make_metrics(_DEFAULT_SCORES))
        result = await adapter.score(_SAMPLE)

        assert result.answer_correctness == pytest.approx(0.82)
        assert result.answer_similarity == pytest.approx(0.78)
        assert result.faithfulness == pytest.approx(0.91)
        assert result.context_precision == pytest.approx(0.85)
        assert result.context_recall == pytest.approx(0.73)
        assert result.answer_relevancy == pytest.approx(0.87)

    async def test_each_metric_called_once(self) -> None:
        """Cada métrica deve ter single_turn_ascore chamado exatamente uma vez."""
        metrics = _make_metrics()
        adapter = _make_adapter(metrics)

        await adapter.score(_SAMPLE)

        for field in _METRIC_FIELDS:
            metrics[field].single_turn_ascore.assert_called_once()

    async def test_metrics_called_individually_not_batch(self) -> None:
        """Métricas são calculadas individualmente, não via ragas.evaluate (batch)."""
        metrics = _make_metrics()
        adapter = _make_adapter(metrics)

        await adapter.score(_SAMPLE)

        # Cada mock deve ter sido chamado exatamente 1 vez (sem batching)
        call_counts = [metrics[f].single_turn_ascore.call_count for f in _METRIC_FIELDS]
        assert all(c == 1 for c in call_counts)


# ---------------------------------------------------------------------------
# Isolamento de NaN (ADR-007)
# ---------------------------------------------------------------------------


class TestNaNIsolation:
    async def test_faithfulness_failure_yields_nan_only_for_faithfulness(self) -> None:
        """Exceção em faithfulness → NaN apenas nesse campo; os outros 5 permanecem."""
        metrics = _make_metrics(_DEFAULT_SCORES)
        metrics["faithfulness"].single_turn_ascore = AsyncMock(
            side_effect=RuntimeError("LLM timeout")
        )
        adapter = _make_adapter(metrics)

        result = await adapter.score(_SAMPLE)

        assert math.isnan(result.faithfulness)
        assert not math.isnan(result.answer_correctness)
        assert not math.isnan(result.answer_similarity)
        assert not math.isnan(result.context_precision)
        assert not math.isnan(result.context_recall)
        assert not math.isnan(result.answer_relevancy)

    async def test_multiple_failures_yield_nan_per_field(self) -> None:
        """Falhas em múltiplos campos → NaN apenas nesses campos."""
        metrics = _make_metrics(_DEFAULT_SCORES)
        metrics["context_precision"].single_turn_ascore = AsyncMock(
            side_effect=ValueError("parse error")
        )
        metrics["context_recall"].single_turn_ascore = AsyncMock(
            side_effect=ValueError("parse error")
        )
        adapter = _make_adapter(metrics)

        result = await adapter.score(_SAMPLE)

        assert math.isnan(result.context_precision)
        assert math.isnan(result.context_recall)
        assert not math.isnan(result.answer_correctness)
        assert not math.isnan(result.faithfulness)

    async def test_exception_in_one_metric_does_not_stop_others(self) -> None:
        """Exceção em uma métrica não interrompe o cálculo das demais."""
        call_order: list[str] = []
        metrics: dict[str, Any] = {}
        for field in _METRIC_FIELDS:
            f = field  # capture

            async def _mock_score(sample: Any, _f: str = f) -> float:
                call_order.append(_f)
                if _f == "answer_correctness":
                    raise RuntimeError("fail")
                return 0.5

            m = MagicMock()
            m.single_turn_ascore = _mock_score
            metrics[field] = m

        adapter = _make_adapter(metrics)
        result = await adapter.score(_SAMPLE)

        assert math.isnan(result.answer_correctness)
        # Todos os outros campos foram calculados
        assert len(call_order) == len(_METRIC_FIELDS)

    async def test_all_metrics_fail_returns_all_nan(self) -> None:
        """Todas as métricas falham → Layer1Metrics com todos os campos NaN."""
        metrics = {
            field: MagicMock(
                single_turn_ascore=AsyncMock(side_effect=RuntimeError("fail"))
            )
            for field in _METRIC_FIELDS
        }
        adapter = _make_adapter(metrics)

        result = await adapter.score(_SAMPLE)

        assert math.isnan(result.answer_correctness)
        assert math.isnan(result.answer_similarity)
        assert math.isnan(result.faithfulness)
        assert math.isnan(result.context_precision)
        assert math.isnan(result.context_recall)
        assert math.isnan(result.answer_relevancy)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class TestLogging:
    async def test_happy_path_log_contains_judge_url(self) -> None:
        """ragas_layer1_computed deve conter judge_url."""
        import structlog.testing

        adapter = _make_adapter(_make_metrics(_DEFAULT_SCORES))

        with structlog.testing.capture_logs() as logs:
            await adapter.score(_SAMPLE)

        computed = [e for e in logs if e.get("event") == "ragas_layer1_computed"]
        assert len(computed) == 1
        assert computed[0]["judge_url"] == _JUDGE_URL

    async def test_happy_path_log_contains_all_six_metrics(self) -> None:
        """ragas_layer1_computed deve conter os 6 campos de métrica."""
        import structlog.testing

        adapter = _make_adapter(_make_metrics(_DEFAULT_SCORES))

        with structlog.testing.capture_logs() as logs:
            await adapter.score(_SAMPLE)

        ev = next(e for e in logs if e.get("event") == "ragas_layer1_computed")
        for field in _METRIC_FIELDS:
            assert field in ev, f"Campo '{field}' ausente no log"

    async def test_happy_path_log_nan_fields_empty(self) -> None:
        """nan_fields deve ser lista vazia quando todas as métricas são calculadas."""
        import structlog.testing

        adapter = _make_adapter(_make_metrics(_DEFAULT_SCORES))

        with structlog.testing.capture_logs() as logs:
            await adapter.score(_SAMPLE)

        ev = next(e for e in logs if e.get("event") == "ragas_layer1_computed")
        assert ev["nan_fields"] == []

    async def test_nan_field_log_nan_fields_populated(self) -> None:
        """nan_fields deve listar o campo que gerou NaN."""
        import structlog.testing

        metrics = _make_metrics(_DEFAULT_SCORES)
        metrics["faithfulness"].single_turn_ascore = AsyncMock(
            side_effect=RuntimeError("timeout")
        )
        adapter = _make_adapter(metrics)

        with structlog.testing.capture_logs() as logs:
            await adapter.score(_SAMPLE)

        ev = next(e for e in logs if e.get("event") == "ragas_layer1_computed")
        assert "faithfulness" in ev["nan_fields"]

    async def test_log_latency_ms_present(self) -> None:
        """latency_ms deve estar presente e ser um inteiro não-negativo."""
        import structlog.testing

        adapter = _make_adapter()

        with structlog.testing.capture_logs() as logs:
            await adapter.score(_SAMPLE)

        ev = next(e for e in logs if e.get("event") == "ragas_layer1_computed")
        assert isinstance(ev["latency_ms"], int)
        assert ev["latency_ms"] >= 0


# ---------------------------------------------------------------------------
# Construção do SingleTurnSample
# ---------------------------------------------------------------------------


class TestSingleTurnSampleConstruction:
    async def test_user_input_from_question(self) -> None:
        """user_input do SingleTurnSample deve vir de sample.question."""
        from ragas.dataset_schema import SingleTurnSample

        captured: list[SingleTurnSample] = []

        async def _capture(s: SingleTurnSample) -> float:
            captured.append(s)
            return 0.5

        metrics: dict[str, Any] = {}
        for field in _METRIC_FIELDS:
            m = MagicMock()
            m.single_turn_ascore = _capture
            metrics[field] = m

        adapter = _make_adapter(metrics)
        await adapter.score(_SAMPLE)

        assert captured[0].user_input == _SAMPLE.question
        assert captured[0].response == _SAMPLE.generated_answer
        assert captured[0].reference == _SAMPLE.ground_truth
        assert list(captured[0].retrieved_contexts) == list(_SAMPLE.contexts)
