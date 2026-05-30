"""RetryableMetricAdapter — decorators de retry async + NaN-sentinel (ADR-007, TAREFA-027).

Dois decorators que envolvem os ports de avaliação de Camada 1/2 adicionando retry
com backoff exponencial e degradação explícita para NaN (ADR-007: "retry máx → NaN
explícito", §12 risco "NaN frequente"). São a fronteira de resiliência da passada de
julgamento: o ``ComputeMetricsUseCase`` (TAREFA-026) injeta **sempre** o adapter
decorado, nunca o nu (Nota M2 item 4).

Política de retry (idêntica nos dois decorators, async):

* ``MetricComputationError`` (falha total de I/O sinalizada pelo adapter interno) é
  **retryável**: aguarda ``initial_wait_s * 2**attempt`` e tenta de novo, até esgotar
  ``max_retries`` retries; então devolve um **NaN-sentinel** (sem levantar exceção).
* **NaN parcial** no resultado (campo NaN sem exceção — parsing falhou no adapter
  interno, ADR-007) **NÃO** é retryável: é decisão do adapter interno, devolvido como está.
* Qualquer **outra exceção** (bug inesperado) é **propagada imediatamente** — não retry.

Contagem: ``max_retries=3`` ⟹ até **4 chamadas** ao adapter interno (1 inicial + 3
retries) e **3 esperas** ``[1.0, 2.0, 4.0]`` (uma antes de cada retry). O NaN-sentinel é
devolvido quando o índice da tentativa atinge ``max_retries`` — daí
``feedback="[retry_exhausted:3]"`` (``n`` = retries esgotados = ``max_retries``).

Espera via ``await asyncio.sleep`` (nunca ``time.sleep`` — congelaria o event loop).
"""

from __future__ import annotations

import asyncio
import math
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

import structlog

from inteligenciomica_eval.domain.errors import MetricComputationError
from inteligenciomica_eval.domain.ports import (
    EvaluationSample,
    Layer1Metrics,
    MetricSuitePort,
    RubricJudgePort,
    RubricResult,
)

_log = structlog.get_logger(__name__)

_T = TypeVar("_T")
_NAN = math.nan


@dataclass(frozen=True, slots=True)
class RetryConfig:
    """Configuração do backoff exponencial dos decorators de retry.

    Args:
        max_retries: número de retries após a tentativa inicial (3 ⟹ 4 chamadas).
        initial_wait_s: espera base do backoff; a espera é ``initial_wait_s * 2**i``.
        jitter: quando ``True``, soma um jitter aleatório em ``[0, wait]`` à espera.
            **Off por default** para determinismo nos testes (backoff exato).
    """

    max_retries: int = 3
    initial_wait_s: float = 1.0
    jitter: bool = False


def _nan_layer1() -> Layer1Metrics:
    """NaN-sentinel da Camada 1: todos os campos ``math.nan`` (ADR-007)."""
    return Layer1Metrics(
        answer_correctness=_NAN,
        answer_similarity=_NAN,
        faithfulness=_NAN,
        context_precision=_NAN,
        context_recall=_NAN,
        answer_relevancy=_NAN,
    )


def _nan_rubric(n_retries: int) -> RubricResult:
    """NaN-sentinel da rubrica: ``score=nan`` + ``feedback="[retry_exhausted:N]"``."""
    return RubricResult(score=_NAN, feedback=f"[retry_exhausted:{n_retries}]")


async def _score_with_retry(
    *,
    call: Callable[[], Awaitable[_T]],
    make_sentinel: Callable[[int], _T],
    config: RetryConfig,
    question_id: str,
) -> _T:
    """Executa ``call`` com retry async; devolve o sentinel ao esgotar (ADR-007).

    Args:
        call: factory da corrotina a executar (``lambda: wrapped.score(sample)``).
        make_sentinel: produz o NaN-sentinel dado o índice da tentativa esgotada.
        config: parâmetros de retry/backoff.
        question_id: id da pergunta — rastreado nos logs.

    Returns:
        O resultado de ``call`` (inclusive com NaN parcial), ou o NaN-sentinel.
    """
    attempt = 0
    while True:
        try:
            return await call()
        except MetricComputationError as exc:
            if attempt >= config.max_retries:
                _log.warning(
                    "metric_retry_exhausted",
                    question_id=question_id,
                    retry_exhausted=True,
                    n_attempts=attempt,
                    n_calls=attempt + 1,
                    error_type=type(exc).__name__,
                )
                return make_sentinel(attempt)

            wait_s = config.initial_wait_s * (2.0**attempt)
            if config.jitter:
                wait_s += random.uniform(0.0, wait_s)
            _log.warning(
                "metric_retry_attempt",
                question_id=question_id,
                attempt=attempt,
                wait_s=wait_s,
                error_type=type(exc).__name__,
            )
            await asyncio.sleep(wait_s)
            attempt += 1


class RetryableMetricSuiteAdapter:
    """Decora um :class:`MetricSuitePort` com retry async + NaN-sentinel (ADR-007).

    Args:
        wrapped: o ``MetricSuitePort`` interno (ex.: ``RAGASLayer1Adapter``).
        config: :class:`RetryConfig`.
    """

    def __init__(self, wrapped: MetricSuitePort, config: RetryConfig) -> None:
        self._wrapped = wrapped
        self._config = config

    async def score(self, sample: EvaluationSample) -> Layer1Metrics:
        """Avalia *sample* com retry; NaN-sentinel (todos os campos NaN) ao esgotar."""
        return await _score_with_retry(
            call=lambda: self._wrapped.score(sample),
            make_sentinel=lambda _n: _nan_layer1(),
            config=self._config,
            question_id=sample.question_id,
        )

    async def score_batch(self, samples: list[EvaluationSample]) -> list[Layer1Metrics]:
        """Avalia um lote delegando ao adapter interno (sem retry adicional).

        O retry de batch é responsabilidade do caller (ex.: ``RunMetricsPassUseCase.
        _process_batch``). Este método satisfaz a interface :class:`MetricSuitePort`
        (Nota M3 item 5) e garante ``isinstance(adapter, MetricSuitePort) == True``.

        Args:
            samples: lista de amostras a avaliar.

        Returns:
            Lista de :class:`Layer1Metrics` do adapter interno.

        Raises:
            MetricComputationError: propagada do adapter interno em falha de I/O.
        """
        return await self._wrapped.score_batch(samples)


class RetryableRubricJudgeAdapter:
    """Decora um :class:`RubricJudgePort` com retry async + NaN-sentinel (ADR-007).

    Args:
        wrapped: o ``RubricJudgePort`` interno (ex.: ``PrometheusRubricJudgeAdapter``).
        config: :class:`RetryConfig`.
    """

    def __init__(self, wrapped: RubricJudgePort, config: RetryConfig) -> None:
        self._wrapped = wrapped
        self._config = config

    async def score(self, sample: EvaluationSample) -> RubricResult:
        """Avalia *sample* com retry; NaN-sentinel ``[retry_exhausted:N]`` ao esgotar."""
        return await _score_with_retry(
            call=lambda: self._wrapped.score(sample),
            make_sentinel=_nan_rubric,
            config=self._config,
            question_id=sample.question_id,
        )


def make_retryable_metric_suite(
    adapter: MetricSuitePort, config: RetryConfig | None = None
) -> RetryableMetricSuiteAdapter:
    """Factory: envolve um ``MetricSuitePort`` com o decorator de retry."""
    return RetryableMetricSuiteAdapter(adapter, config or RetryConfig())


def make_retryable_rubric_judge(
    adapter: RubricJudgePort, config: RetryConfig | None = None
) -> RetryableRubricJudgeAdapter:
    """Factory: envolve um ``RubricJudgePort`` com o decorator de retry."""
    return RetryableRubricJudgeAdapter(adapter, config or RetryConfig())
