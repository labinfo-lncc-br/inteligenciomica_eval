from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

from inteligenciomica_eval.domain.errors import (
    ConfigValidationError,
    WeightsDoNotSumToOneError,
)
from inteligenciomica_eval.domain.value_objects import RankScore

# Pesos canônicos §7.3 do documento-base.
#
# Por que NÃO exigimos soma == 1.0 aqui (contraste com FinalScoreCalculator):
# A fórmula contém um termo subtrativo (-w_p * critical_failure_rate) e uma
# transformação não-linear (1 - failure_rate). Exigir soma dos 4 pesos == 1
# seria semanticamente incorreto: a penalização clínica reduz o score abaixo
# de qualquer valor que os termos positivos poderiam justificar, e este sinal
# de negatividade é *desejável* (§7.3, doc-base). A única restrição correta é
# que cada peso seja finito e não-negativo.
DEFAULT_WEIGHTS: dict[str, float] = {
    "median": 0.50,
    "one_minus_failure": 0.20,
    "win_rate": 0.15,
    "critical_failure_penalty": 0.15,
}

_VALID_WEIGHT_KEYS: frozenset[str] = frozenset(DEFAULT_WEIGHTS)


@dataclass(frozen=True, slots=True)
class RankScoreInputs:
    """Aggregados de uma configuração de modelo para cálculo do RankScore (§7.3).

    Todos os campos representam frações em ``[0.0, 1.0]``. ``NaN`` sinaliza que
    a métrica não pôde ser calculada; nesse caso ``RankScoreCalculator.compute``
    retorna ``RankScore(NaN)`` (ADR-007, sem imputação).

    Args:
        median_score: mediana do FinalScore sobre todas as perguntas da config.
        failure_rate: fração de perguntas com FinalScore abaixo do limiar de falha.
        win_rate: fração de perguntas em que esta config supera a baseline.
        critical_failure_rate: fração de perguntas marcadas como falha crítica.
    """

    median_score: float
    failure_rate: float
    win_rate: float
    critical_failure_rate: float


class RankScoreCalculator:
    """Serviço de domínio que computa o RankScore de uma configuração (§7.3 doc-base).

    Fórmula canônica::

        RankScore = w_m * median_score
                  + w_f * (1 - failure_rate)
                  + w_w * win_rate
                  - w_p * critical_failure_rate

    onde os defaults são ``(w_m, w_f, w_w, w_p) = (0.50, 0.20, 0.15, 0.15)``.

    Note:
        **Sem restrição de soma == 1.0.** Diferente do FinalScoreCalculator, os 4
        pesos não precisam somar 1.0. A fórmula tem um termo subtrativo e uma
        transformação ``(1 - failure_rate)``; exigir soma == 1 seria semanticamente
        errado. Apenas positividade e finitude são exigidas.

    Note:
        **RankScore pode ser negativo.** Uma ``critical_failure_rate`` alta com
        ``median_score`` e ``win_rate`` baixos produz score negativo — sinal
        clínico-de-segurança intencional (§7.3 doc-base). Sem clamp.

    Note:
        **NaN propagation (ADR-007).** Se qualquer campo de ``RankScoreInputs``
        for NaN, retorna ``RankScore(NaN)`` imediatamente. Sem imputação.

    Args:
        weights: mapeamento com chaves de ``DEFAULT_WEIGHTS``
            (``median``, ``one_minus_failure``, ``win_rate``,
            ``critical_failure_penalty``). Chaves ausentes recebem o valor
            default. Chaves desconhecidas levantam ``ConfigValidationError``.
            Cada valor deve ser um float finito e ``>= 0``.

    Raises:
        ConfigValidationError: se alguma chave não pertencer ao conjunto válido.
        WeightsDoNotSumToOneError: se algum peso for negativo, NaN ou infinito.
            (Exceção reutilizada para consistência — aqui a semântica é
            "peso inválido", não "soma errada".)
    """

    def __init__(self, weights: Mapping[str, float]) -> None:
        for key in weights:
            if key not in _VALID_WEIGHT_KEYS:
                raise ConfigValidationError(
                    field=key,
                    reason=(
                        f"'{key}' is not a valid RankScore weight key. "
                        f"Valid keys: {sorted(_VALID_WEIGHT_KEYS)}"
                    ),
                )
        for _key, val in weights.items():
            if not math.isfinite(val) or val < 0.0:
                raise WeightsDoNotSumToOneError(actual_sum=sum(weights.values()))
        self._weights: dict[str, float] = dict(weights)

    def compute(self, inputs: RankScoreInputs) -> RankScore:
        """Calcula o RankScore para uma configuração de modelo.

        Args:
            inputs: agregados da configuração (median_score, failure_rate,
                win_rate, critical_failure_rate).

        Returns:
            :class:`~inteligenciomica_eval.domain.value_objects.RankScore`
            com o valor calculado (pode ser negativo ou NaN).
        """
        if (
            math.isnan(inputs.median_score)
            or math.isnan(inputs.failure_rate)
            or math.isnan(inputs.win_rate)
            or math.isnan(inputs.critical_failure_rate)
        ):
            return RankScore(float("nan"))

        w_m = self._weights.get("median", DEFAULT_WEIGHTS["median"])
        w_f = self._weights.get(
            "one_minus_failure", DEFAULT_WEIGHTS["one_minus_failure"]
        )
        w_w = self._weights.get("win_rate", DEFAULT_WEIGHTS["win_rate"])
        w_p = self._weights.get(
            "critical_failure_penalty", DEFAULT_WEIGHTS["critical_failure_penalty"]
        )

        value = (
            w_m * inputs.median_score
            + w_f * (1.0 - inputs.failure_rate)
            + w_w * inputs.win_rate
            - w_p * inputs.critical_failure_rate
        )
        return RankScore(value)
