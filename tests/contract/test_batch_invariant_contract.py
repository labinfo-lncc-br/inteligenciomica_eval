"""Contract tests for the ``batch_invariant`` / ``DeterminismRegime.JUDGE`` invariant.

TAREFA-022 — verifica a propagação ponta-a-ponta do contrato §4.3:

    ``batch_invariant is True`` ⟺ a métrica veio do juiz determinístico (regime
    ``DeterminismRegime.JUDGE``); ``False`` para o gerador (``GENERATOR``).

Cobre os 5 cenários do Prompt A:

* (a) ``PrometheusJudgeAdapter.determinism_regime == JUDGE`` — sem servidor real.
* (b) ``result.with_metrics(..., JUDGE).batch_invariant is True`` — unit puro.
* (c) Round-trip Parquet real: ``batch_invariant=True`` persistido e relido.
* (d) Invariante §4.3 garantida por construção (property derivada, não setável).
* (e) ``DeterminismRegime.GENERATOR`` → ``batch_invariant=False`` round-trip.

Nenhum cenário usa rede real nem GPU (DoD §14.2).
"""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq
import pytest
from factories.factories import (
    make_evaluation_result,
    make_metric_vector,
)

from inteligenciomica_eval.domain.entities import EvaluationResult
from inteligenciomica_eval.domain.value_objects import DeterminismRegime, FinalScore
from inteligenciomica_eval.infrastructure.adapters.prometheus_judge import (
    PrometheusJudgeAdapter,
)
from inteligenciomica_eval.infrastructure.prompts.registry import PromptRegistry
from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
    ParquetStorage,
)

pytestmark = pytest.mark.contract


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_single_parquet_column(base_dir: Path, column: str) -> object:
    """Read ``column`` from the single Parquet row written under ``base_dir``.

    Uses ``ParquetFile(...).read()`` on the individual file (never
    ``read_table`` on the Hive tree) to avoid partition auto-detection
    conflicts (CLAUDE.md §13 / TAREFA-021).

    Args:
        base_dir: ParquetStorage root directory.
        column: column name to extract.

    Returns:
        The single cell value for ``column``.
    """
    files = list(base_dir.rglob("*.parquet"))
    assert len(files) == 1, f"expected exactly one Parquet file, got {len(files)}"
    table = pq.ParquetFile(files[0]).read()
    return table.column(column)[0].as_py()


# ---------------------------------------------------------------------------
# (a) Adapter exposes the JUDGE regime without touching the network
# ---------------------------------------------------------------------------


class TestAdapterRegime:
    def test_prometheus_judge_regime_is_judge(self) -> None:
        """(a) The adapter advertises ``DeterminismRegime.JUDGE`` as an attribute.

        Instantiating the adapter only configures the OpenAI client object; no
        HTTP request is made, so this runs without a live judge server.
        """
        adapter = PrometheusJudgeAdapter(
            judge_url="http://localhost:9/v1",
            registry=PromptRegistry(),
        )
        assert adapter.determinism_regime is DeterminismRegime.JUDGE


# ---------------------------------------------------------------------------
# (b) with_metrics(..., JUDGE) sets batch_invariant True in pure unit
# ---------------------------------------------------------------------------


class TestWithMetricsRegime:
    def test_with_metrics_judge_sets_batch_invariant_true(self) -> None:
        """(b) ``with_metrics(..., JUDGE)`` yields ``batch_invariant is True``."""
        base = make_evaluation_result(determinism_regime=DeterminismRegime.GENERATOR)
        assert base.batch_invariant is False  # sanity: starts as generator

        judged = base.with_metrics(
            make_metric_vector(),
            FinalScore(0.8),
            DeterminismRegime.JUDGE,
        )
        assert judged.batch_invariant is True
        assert judged.determinism_regime is DeterminismRegime.JUDGE


# ---------------------------------------------------------------------------
# (c) + (e) Parquet round-trip per regime
# ---------------------------------------------------------------------------


class TestParquetRoundTrip:
    def test_judge_round_trip_persists_batch_invariant_true(
        self, tmp_path: Path
    ) -> None:
        """(c) JUDGE result → ``batch_invariant=True`` persisted and re-read."""
        storage = ParquetStorage(tmp_path, round_id="round_1")
        result = make_evaluation_result(determinism_regime=DeterminismRegime.JUDGE)

        storage.append(result)

        # Reconstructed entity round-trip.
        frame = storage.load(round_id="round_1")
        assert len(frame.results) == 1
        reloaded = frame.results[0]
        assert reloaded.batch_invariant is True
        assert reloaded.determinism_regime is DeterminismRegime.JUDGE

        # Raw Parquet column round-trip (not mocked).
        assert _read_single_parquet_column(tmp_path, "batch_invariant") is True

    def test_generator_round_trip_persists_batch_invariant_false(
        self, tmp_path: Path
    ) -> None:
        """(e) GENERATOR result → ``batch_invariant=False`` persisted and re-read."""
        storage = ParquetStorage(tmp_path, round_id="round_1")
        result = make_evaluation_result(determinism_regime=DeterminismRegime.GENERATOR)

        storage.append(result)

        frame = storage.load(round_id="round_1")
        assert len(frame.results) == 1
        reloaded = frame.results[0]
        assert reloaded.batch_invariant is False
        assert reloaded.determinism_regime is DeterminismRegime.GENERATOR

        assert _read_single_parquet_column(tmp_path, "batch_invariant") is False


# ---------------------------------------------------------------------------
# (d) §4.3 invariant is structural — inconsistency is not representable
# ---------------------------------------------------------------------------


class TestInvariantByConstruction:
    """DECISÃO TAREFA-022 (§4.3): ``batch_invariant`` é uma property derivada de
    ``determinism_regime`` — não há atributo independente nem setter. Logo um
    ``EvaluationResult`` com ``regime=JUDGE`` e ``batch_invariant=False`` é
    *irrepresentável*: não há exceção em runtime nem WARNING no writer porque a
    inconsistência não pode ser construída. Estes testes comprovam essa garantia.
    """

    def test_batch_invariant_is_not_a_constructor_field(self) -> None:
        """(d) Não é possível passar ``batch_invariant`` ao construtor."""
        with pytest.raises(TypeError):
            EvaluationResult(  # type: ignore[call-arg]
                answer=make_evaluation_result().answer,
                metrics=make_metric_vector(),
                final_score=FinalScore(0.8),
                determinism_regime=DeterminismRegime.JUDGE,
                critical_failure_flag=None,
                critical_failure_note=None,
                batch_invariant=False,
            )

    def test_batch_invariant_is_a_read_only_property(self) -> None:
        """(d) ``batch_invariant`` é uma property derivada sem setter."""
        descriptor = type(make_evaluation_result()).__dict__["batch_invariant"]
        assert isinstance(descriptor, property)
        assert descriptor.fset is None  # nenhum setter → derivado, não armazenado

        # Atribuição direta falha (frozen dataclass + property sem setter); o tipo
        # exato da exceção varia entre versões de Python, mas a mutação é proibida.
        result = make_evaluation_result(determinism_regime=DeterminismRegime.JUDGE)
        with pytest.raises((AttributeError, TypeError)):
            result.batch_invariant = False  # type: ignore[misc]

    @pytest.mark.parametrize(
        ("regime", "expected"),
        [
            (DeterminismRegime.JUDGE, True),
            (DeterminismRegime.GENERATOR, False),
        ],
    )
    def test_invariant_is_coherent_for_every_regime(
        self, regime: DeterminismRegime, expected: bool
    ) -> None:
        """(d) ``batch_invariant`` segue o regime para todos os valores possíveis."""
        result = make_evaluation_result(determinism_regime=regime)
        assert result.batch_invariant is expected
