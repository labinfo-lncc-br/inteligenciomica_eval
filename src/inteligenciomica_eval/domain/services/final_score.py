from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from typing import cast

from inteligenciomica_eval.domain.errors import (
    ConfigValidationError,
    WeightsDoNotSumToOneError,
)
from inteligenciomica_eval.domain.value_objects import FinalScore, MetricVector

# 2**-30 ≈ 9.313e-10: dyadic exato → fronteira testável via Lema de Sterbenz (mata mutmut_12)
_WEIGHTS_TOLERANCE: float = 2**-30

_METRIC_VECTOR_FIELDS: frozenset[str] = frozenset(
    f.name for f in dataclasses.fields(MetricVector)
)

# Pesos canônicos §7.1 do documento-base.
# answer_similarity e bertscore_f1 são auxiliares — NÃO entram aqui (anti-double-counting).
DEFAULT_WEIGHTS: dict[str, float] = {
    "answer_correctness": 0.45,
    "faithfulness": 0.20,
    "rubric_biomed_score": 0.15,
    "context_recall": 0.10,
    "context_precision": 0.05,
    "answer_relevancy": 0.05,
}


class FinalScoreCalculator:
    """Serviço de domínio que computa o FinalScore ponderado (§7.1 do documento-base).

    Fórmula canônica::

        FinalScore = 0.45 * answer_correctness
                   + 0.20 * faithfulness
                   + 0.15 * rubric_biomed_score
                   + 0.10 * context_recall
                   + 0.05 * context_precision
                   + 0.05 * answer_relevancy

    ``answer_similarity`` e ``bertscore_f1`` são métricas auxiliares e não entram
    no cálculo (§7.1, nota técnica, anti-double-counting).

    Note:
        NaN propagation (ADR-007): se qualquer métrica com peso > 0 for NaN,
        retorna ``FinalScore(NaN)``. A linha é descartada na etapa de agregação;
        não há imputação. Pesos zero são ignorados para evitar ``0 * NaN = NaN``.

    Args:
        weights: mapeamento ``{nome_campo: peso}`` — chaves devem ser campos
            válidos de :class:`~inteligenciomica_eval.domain.value_objects.MetricVector`
            e a soma dos valores deve ser 1.0 (tolerância :data:`_WEIGHTS_TOLERANCE`).

    Raises:
        ConfigValidationError: se alguma chave não for campo de MetricVector.
        WeightsDoNotSumToOneError: se ``|sum(weights) - 1.0| > _WEIGHTS_TOLERANCE``.
    """

    def __init__(self, weights: Mapping[str, float]) -> None:
        for key in weights:
            if key not in _METRIC_VECTOR_FIELDS:
                raise ConfigValidationError(
                    field=key,
                    reason=(
                        f"'{key}' is not a field of MetricVector. "
                        f"Valid fields: {sorted(_METRIC_VECTOR_FIELDS)}"
                    ),
                )
        total = sum(weights.values())
        if abs(total - 1.0) > _WEIGHTS_TOLERANCE:
            raise WeightsDoNotSumToOneError(
                actual_sum=total, tolerance=_WEIGHTS_TOLERANCE
            )
        self._weights: dict[str, float] = dict(weights)

    def compute(self, metrics: MetricVector) -> FinalScore:
        """Calcula o FinalScore para um vetor de métricas.

        NaN propagation (ADR-007): se qualquer métrica com peso > 0 for NaN,
        retorna ``FinalScore(NaN)`` imediatamente. Pesos == 0 são pulados
        para evitar que ``0 * NaN`` corrompa a soma.

        Args:
            metrics: vetor de métricas de uma resposta avaliada.

        Returns:
            :class:`~inteligenciomica_eval.domain.value_objects.FinalScore`
            com valor ponderado em [0, 1] ou NaN.
        """
        total = 0.0
        for field_name, weight in self._weights.items():
            if weight == 0.0:
                continue
            value = cast(float, getattr(metrics, field_name))
            if weight > 0.0 and math.isnan(value):
                return FinalScore(float("nan"))
            total += weight * value
        return FinalScore(total)
