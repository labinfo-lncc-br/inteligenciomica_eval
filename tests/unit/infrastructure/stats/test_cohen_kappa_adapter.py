"""Testes unitários de CohenKappaAdapter (TAREFA-602)."""

from __future__ import annotations

from inteligenciomica_eval.domain.ports import KappaCalculatorPort
from inteligenciomica_eval.infrastructure.stats.cohen_kappa_adapter import (
    CohenKappaAdapter,
)


class TestProtocolConformance:
    def test_satisfies_kappa_calculator_port(self) -> None:
        assert isinstance(CohenKappaAdapter(), KappaCalculatorPort)


class TestComputeKappa:
    def test_partial_agreement(self) -> None:
        # y_true=[0,1,0,1], y_pred=[0,1,0,0]
        # Concordâncias: pos0(0,0)✓ pos1(1,1)✓ pos2(0,0)✓ pos3(1,0)✗ → Po=0.75
        # Pe = (2/4 x 3/4)+(2/4 x 1/4) = 6/16+2/16 = 0.5
        # kappa = (0.75-0.5)/(1-0.5) = 0.5
        adapter = CohenKappaAdapter()
        kappa = adapter.compute([0, 1, 0, 1], [0, 1, 0, 0])
        assert abs(kappa - 0.5) < 1e-9

    def test_perfect_agreement(self) -> None:
        adapter = CohenKappaAdapter()
        kappa = adapter.compute([0, 1, 0, 1], [0, 1, 0, 1])
        assert abs(kappa - 1.0) < 1e-9

    def test_returns_float(self) -> None:
        adapter = CohenKappaAdapter()
        kappa = adapter.compute([0, 0, 1, 1], [0, 1, 0, 1])
        assert isinstance(kappa, float)
