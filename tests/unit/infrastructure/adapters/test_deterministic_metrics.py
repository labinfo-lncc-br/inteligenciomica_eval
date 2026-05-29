"""Testes unitários para DeterministicMetricsAdapter (TAREFA-018).

Estratégia (§ spec TAREFA-018 / Nota M1 item 10):

- **ROUGE-L golden**: 3 pares PT-biomédicos de ``tests/golden/det_metrics_golden.json``;
  ROUGE-L é puro-Python (sem modelo), então roda sempre. BERTScore é mockado nesses
  testes para não carregar o modelo multilíngue.
- **BERTScore golden**: usa o adapter real (sem mock). Pulado se o modelo/rede não
  estiver disponível no ambiente — mesma filosofia dos testes ``testcontainers``.
- **NaN absorvido**: ``BERTScorer.score`` mockado para levantar exceção → ``bertscore_f1``
  vira NaN sem afetar ``rouge_l`` (isolamento por campo). E vice-versa para ROUGE.
- **Carga única**: duas chamadas em sequência instanciam ``BERTScorer`` uma só vez
  (regressão da auditoria 018-B: ``cached_property`` cacheia o modelo, não um ``partial``).
- **Logging**: ``deterministic_metrics_computed`` com bertscore_f1, rouge_l, latency_ms.

Os mocks usam alvos string (``bert_score.BERTScorer`` / ``rouge_score.rouge_scorer.RougeScorer``)
em vez de acessar atributos re-exportados do módulo do adapter — mantém o teste tipável.
"""

from __future__ import annotations

import inspect
import json
import math
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import bert_score
import pytest

from inteligenciomica_eval.domain.ports import AuxMetrics, DeterministicMetricPort
from inteligenciomica_eval.infrastructure.adapters.deterministic_metrics import (
    DeterministicMetricsAdapter,
)

# ---------------------------------------------------------------------------
# Golden dataset
# ---------------------------------------------------------------------------

_GOLDEN_PATH = Path(__file__).parents[3] / "golden" / "det_metrics_golden.json"
_GOLDEN: list[dict[str, Any]] = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
_GOLDEN_IDS = [c["name"] for c in _GOLDEN]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_bert_return(f1_value: float) -> tuple[Any, Any, Any]:
    """Imita o retorno ``(P, R, F1)`` de ``BERTScorer.score``.

    ``F1.mean().item()`` resolve para ``f1_value``; P e R são irrelevantes.
    """
    f1 = MagicMock()
    f1.mean.return_value.item.return_value = f1_value
    return (MagicMock(), MagicMock(), f1)


def _mock_scorer(f1_value: float) -> MagicMock:
    """Cria um ``BERTScorer`` falso cujo ``.score(...)`` devolve ``(P, R, F1)`` fixo."""
    scorer = MagicMock()
    scorer.score.return_value = _fake_bert_return(f1_value)
    return scorer


def _patch_bert(mocker: Any, f1_value: float = 0.9) -> MagicMock:
    """Mocka ``bert_score.BERTScorer`` devolvendo um scorer com F1 fixo (sem modelo).

    Retorna o mock da *factory* ``BERTScorer`` — inspecionar ``call_count`` comprova a
    carga única do modelo (cacheada via ``cached_property``).
    """
    factory = mocker.patch("bert_score.BERTScorer", return_value=_mock_scorer(f1_value))
    return factory  # type: ignore[no-any-return]


@pytest.fixture(scope="session")
def bertscore_available() -> bool:
    """Probe único: o modelo BERTScore multilíngue carrega neste ambiente?"""
    try:
        scorer = bert_score.BERTScorer(
            lang="pt", rescale_with_baseline=False, device="cpu"
        )
        scorer.score(["ok"], ["ok"])
        return True
    except Exception:  # pragma: no cover - depende de rede/modelo
        return False


# ---------------------------------------------------------------------------
# Conformidade de protocolo
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_isinstance_deterministic_metric_port(self) -> None:
        """isinstance contra DeterministicMetricPort deve passar em runtime."""
        assert isinstance(DeterministicMetricsAdapter(), DeterministicMetricPort)

    def test_static_typing_assignment(self) -> None:
        """Atribuição port: DeterministicMetricPort = adapter — sem type: ignore."""
        port: DeterministicMetricPort = DeterministicMetricsAdapter()
        assert isinstance(port, DeterministicMetricPort)


# ---------------------------------------------------------------------------
# ROUGE-L golden (sempre roda — puro Python, sem modelo)
# ---------------------------------------------------------------------------


class TestRougeGolden:
    @pytest.mark.parametrize("case", _GOLDEN, ids=_GOLDEN_IDS)
    def test_rouge_l_golden(self, case: dict[str, Any], mocker: Any) -> None:
        """ROUGE-L de cada par golden respeita os thresholds documentados."""
        _patch_bert(mocker, f1_value=0.5)
        adapter = DeterministicMetricsAdapter()

        result = adapter.score(answer=case["answer"], ground_truth=case["ground_truth"])

        if "rouge_l_min" in case:
            assert result.rouge_l >= case["rouge_l_min"], (
                f"{case['name']}: rouge_l={result.rouge_l} < min {case['rouge_l_min']}"
            )
        if "rouge_l_max" in case:
            assert result.rouge_l <= case["rouge_l_max"], (
                f"{case['name']}: rouge_l={result.rouge_l} > max {case['rouge_l_max']}"
            )

    def test_identical_pair_rouge_above_099(self, mocker: Any) -> None:
        """Critério de aceitação: par idêntico → rouge_l > 0.99."""
        _patch_bert(mocker)
        case = next(c for c in _GOLDEN if c["name"] == "identical")
        adapter = DeterministicMetricsAdapter()
        result = adapter.score(answer=case["answer"], ground_truth=case["ground_truth"])
        assert result.rouge_l > 0.99


# ---------------------------------------------------------------------------
# BERTScore golden (pulado se modelo/rede indisponível)
# ---------------------------------------------------------------------------


class TestBertScoreGolden:
    @pytest.mark.parametrize("case", _GOLDEN, ids=_GOLDEN_IDS)
    def test_bertscore_f1_golden(
        self, case: dict[str, Any], bertscore_available: bool
    ) -> None:
        """BERTScore-F1 real de cada par golden respeita os thresholds."""
        if not bertscore_available:
            pytest.skip("modelo/rede BERTScore indisponível neste ambiente")

        adapter = DeterministicMetricsAdapter()
        result = adapter.score(answer=case["answer"], ground_truth=case["ground_truth"])

        if "bertscore_f1_min" in case:
            assert result.bertscore_f1 >= case["bertscore_f1_min"], (
                f"{case['name']}: bertscore_f1={result.bertscore_f1} "
                f"< min {case['bertscore_f1_min']}"
            )
        if "bertscore_f1_max" in case:
            assert result.bertscore_f1 <= case["bertscore_f1_max"], (
                f"{case['name']}: bertscore_f1={result.bertscore_f1} "
                f"> max {case['bertscore_f1_max']}"
            )

    def test_identical_pair_bertscore_above_099(
        self, bertscore_available: bool
    ) -> None:
        """Critério de aceitação: par idêntico → bertscore_f1 > 0.99."""
        if not bertscore_available:
            pytest.skip("modelo/rede BERTScore indisponível neste ambiente")
        case = next(c for c in _GOLDEN if c["name"] == "identical")
        adapter = DeterministicMetricsAdapter()
        result = adapter.score(answer=case["answer"], ground_truth=case["ground_truth"])
        assert result.bertscore_f1 > 0.99

    def test_different_pair_bertscore_below_06(self, bertscore_available: bool) -> None:
        """Critério de aceitação: par diferente → bertscore_f1 < 0.6."""
        if not bertscore_available:
            pytest.skip("modelo/rede BERTScore indisponível neste ambiente")
        case = next(c for c in _GOLDEN if c["name"] == "different")
        adapter = DeterministicMetricsAdapter()
        result = adapter.score(answer=case["answer"], ground_truth=case["ground_truth"])
        assert result.bertscore_f1 < 0.6


# ---------------------------------------------------------------------------
# NaN absorvido — isolamento por campo (DoD §14.2)
# ---------------------------------------------------------------------------


class TestNaNAbsorption:
    def test_bertscore_exception_yields_nan_only(self, mocker: Any) -> None:
        """BERTScorer.score levanta → bertscore_f1 NaN; rouge_l permanece válido."""
        scorer = MagicMock()
        scorer.score.side_effect = RuntimeError("bert boom")
        mocker.patch("bert_score.BERTScorer", return_value=scorer)
        adapter = DeterministicMetricsAdapter()

        result = adapter.score(
            answer="a resistência ocorre por betalactamases",
            ground_truth="a resistência ocorre por betalactamases",
        )

        assert math.isnan(result.bertscore_f1)
        assert not math.isnan(result.rouge_l)
        assert result.rouge_l > 0.99  # par idêntico → rouge perfeito

    def test_rouge_exception_yields_nan_only(self, mocker: Any) -> None:
        """RougeScorer.score levanta → rouge_l NaN; bertscore_f1 permanece válido."""
        _patch_bert(mocker, f1_value=0.83)
        broken_scorer = MagicMock()
        broken_scorer.score.side_effect = RuntimeError("rouge boom")
        mocker.patch("rouge_score.rouge_scorer.RougeScorer", return_value=broken_scorer)
        adapter = DeterministicMetricsAdapter()

        result = adapter.score(answer="resposta", ground_truth="referência")

        assert math.isnan(result.rouge_l)
        assert result.bertscore_f1 == pytest.approx(0.83)

    def test_never_raises_to_caller(self, mocker: Any) -> None:
        """Ambas as métricas falham → AuxMetrics(NaN, NaN), sem exceção propagada."""
        bert_scorer = MagicMock()
        bert_scorer.score.side_effect = ValueError("bert")
        mocker.patch("bert_score.BERTScorer", return_value=bert_scorer)
        broken_scorer = MagicMock()
        broken_scorer.score.side_effect = ValueError("rouge")
        mocker.patch("rouge_score.rouge_scorer.RougeScorer", return_value=broken_scorer)
        adapter = DeterministicMetricsAdapter()

        result = adapter.score(answer="x", ground_truth="y")

        assert isinstance(result, AuxMetrics)
        assert math.isnan(result.bertscore_f1)
        assert math.isnan(result.rouge_l)


# ---------------------------------------------------------------------------
# Carga única do modelo (lazy-load real — regressão da auditoria 018-B)
# ---------------------------------------------------------------------------


class TestModelLoadedOnce:
    def test_bert_model_loaded_once_across_calls(self, mocker: Any) -> None:
        """Duas chamadas a score() instanciam o BERTScorer uma única vez.

        Regressão (auditoria 018-B): o ``cached_property`` deve cachear a instância do
        ``BERTScorer`` (modelo em memória), não recriá-la a cada chamada — a API
        funcional ``bert_score.score`` recarregaria os pesos toda vez.
        """
        factory = _patch_bert(mocker, f1_value=0.7)
        adapter = DeterministicMetricsAdapter()

        adapter.score(answer="a", ground_truth="b")
        adapter.score(answer="c", ground_truth="d")

        assert factory.call_count == 1  # BERTScorer instanciado uma única vez
        assert factory.return_value.score.call_count == 2  # mas pontuou as duas vezes


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class TestLogging:
    def test_computed_log_has_all_fields(self, mocker: Any) -> None:
        """deterministic_metrics_computed contém bertscore_f1, rouge_l, latency_ms."""
        import structlog.testing

        _patch_bert(mocker, f1_value=0.77)
        adapter = DeterministicMetricsAdapter()

        with structlog.testing.capture_logs() as logs:
            adapter.score(answer="resposta", ground_truth="referência")

        ev = next(e for e in logs if e.get("event") == "deterministic_metrics_computed")
        assert ev["bertscore_f1"] == pytest.approx(0.77)
        assert "rouge_l" in ev
        assert isinstance(ev["latency_ms"], int)
        assert ev["latency_ms"] >= 0

    def test_bertscore_failure_logs_warning(self, mocker: Any) -> None:
        """Falha de BERTScore loga WARNING bertscore_failed."""
        import structlog.testing

        scorer = MagicMock()
        scorer.score.side_effect = RuntimeError("boom")
        mocker.patch("bert_score.BERTScorer", return_value=scorer)
        adapter = DeterministicMetricsAdapter()

        with structlog.testing.capture_logs() as logs:
            adapter.score(answer="a", ground_truth="b")

        assert any(e.get("event") == "bertscore_failed" for e in logs)


# ---------------------------------------------------------------------------
# Síncrono (Nota M1 item 1)
# ---------------------------------------------------------------------------


class TestSynchronous:
    def test_score_returns_aux_metrics_not_coroutine(self, mocker: Any) -> None:
        """score() é síncrono — retorna AuxMetrics diretamente, não corrotina."""
        _patch_bert(mocker, f1_value=0.8)
        adapter = DeterministicMetricsAdapter()
        result = adapter.score(answer="a", ground_truth="b")
        assert not inspect.iscoroutine(result)
        assert isinstance(result, AuxMetrics)
