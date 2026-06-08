"""PrometheusJudgeAdapter - avaliação via rubrica biomédica com Prometheus-2/G-Eval.

Implementa ``RubricJudgePort`` usando o vllm-judge determinístico (secoes 9.1-9.5).
Política NaN-or-retry (Nota M1 item 3 / ADR-007): até 3 tentativas em falha de
parsing; após esgotar retries retorna ``RubricResult(score=nan)``.
``batch_invariant=True`` é constante (ADR-003, DeterminismRegime.JUDGE).
"""

from __future__ import annotations

import json
import time
from typing import Any

import openai
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from inteligenciomica_eval.domain.errors import JudgeUnavailableError
from inteligenciomica_eval.domain.ports import EvaluationSample, RubricResult
from inteligenciomica_eval.domain.value_objects import DeterminismRegime
from inteligenciomica_eval.infrastructure.prompts.registry import PromptRegistry

_log = structlog.get_logger(__name__)

_DEFAULT_MODEL = "prometheus-eval/prometheus-8x7b-v2.0"
_JUDGE_TEMPERATURE = 0.0
_JUDGE_SEED = 42


class _ParseFailureError(Exception):
    """Sinal interno de falha de parsing da resposta JSON do juiz."""


class PrometheusJudgeAdapter:
    """Avalia amostras via rubrica biomédica com o juiz Prometheus-2 (Camada 2).

    Usa ``openai.AsyncOpenAI`` apontando para o vllm-judge determinístico
    (§9.3).  O prompt é construído via :class:`PromptRegistry` injetado no
    construtor.

    ``batch_invariant`` é sempre ``True`` — este adapter representa chamadas ao
    servidor vllm-judge que roda com ``VLLM_BATCH_INVARIANT=1`` (ADR-003,
    ``DeterminismRegime.JUDGE``).  Este campo **nunca** deve ser configurável.

    Expõe :attr:`determinism_regime` (= :data:`DeterminismRegime.JUDGE`) como
    atributo de instância para que o ``ComputeMetricsUseCase`` (TAREFA-026)
    descubra o regime sem depender de herança e propague ``batch_invariant=True``
    até o Parquet (§4.3, §5.3, TAREFA-022).

    Política NaN-or-retry (Nota M1 item 3 / ADR-007):

    - Até 3 tentativas em falha de parsing JSON ou score fora de ``[0, 1]``.
    - Tentativas 1 e 2: loga WARNING e aguarda backoff exponencial.
    - Tentativa 3 (esgotada): loga ERROR com ``nan_reason`` e retorna
      ``RubricResult(score=float('nan'), feedback='parse_failure')``.
    - Servidor indisponível (``APIConnectionError`` / ``APITimeoutError``):
      levanta ``JudgeUnavailableError`` imediatamente — não é retryável.

    Args:
        judge_url: URL base do endpoint vllm-judge, incluindo ``/v1``
            (ex.: ``"http://vllm-judge:8001/v1"``).
        registry: instância de :class:`PromptRegistry` com o template da rubrica.
        model: identificador do modelo juiz (padrão: Prometheus-2 8x7B).
        _retry_stop: sobrescreve a condição de parada do tenacity (uso em testes).
        _retry_wait: sobrescreve a estratégia de espera do tenacity (uso em testes).
    """

    def __init__(
        self,
        judge_url: str,
        registry: PromptRegistry,
        *,
        model: str = _DEFAULT_MODEL,
        _retry_stop: Any = None,
        _retry_wait: Any = None,
    ) -> None:
        self._model = model
        self._registry = registry
        # Regime fixo do juiz determinístico (ADR-003) — exposto para o use case
        # descobrir o regime sem herança e propagar batch_invariant (TAREFA-022).
        self.determinism_regime: DeterminismRegime = DeterminismRegime.JUDGE
        self._client = openai.AsyncOpenAI(
            base_url=judge_url,
            api_key="EMPTY",
            max_retries=0,  # tenacity controla toda a lógica de retry
        )
        self._retry_stop = (
            _retry_stop if _retry_stop is not None else stop_after_attempt(3)
        )
        self._retry_wait = (
            _retry_wait
            if _retry_wait is not None
            else wait_exponential(multiplier=1, min=1, max=4)
        )

    # ------------------------------------------------------------------
    # RubricJudgePort interface
    # ------------------------------------------------------------------

    async def score(self, sample: EvaluationSample) -> RubricResult:
        """Avalia *sample* pela rubrica biomédica (Camada 2 — Prometheus-2).

        Args:
            sample: amostra com pergunta, ground truth, resposta gerada e contextos.

        Returns:
            :class:`~inteligenciomica_eval.domain.ports.RubricResult` com score
            em ``[0.0, 1.0]`` e feedback textual.  Score pode ser
            ``float('nan')`` após retries esgotados (ADR-007).

        Raises:
            JudgeUnavailableError: quando o servidor juiz está inacessível.
        """
        prompt = self._registry.render_biomed_rubric(
            question=sample.question,
            ground_truth=sample.ground_truth,
            generated_answer=sample.generated_answer,
            contexts=sample.contexts,
        )

        t0 = time.monotonic()
        result: RubricResult | None = None

        try:
            async for attempt in AsyncRetrying(
                stop=self._retry_stop,
                wait=self._retry_wait,
                retry=retry_if_exception_type(_ParseFailureError),
                reraise=True,
            ):
                with attempt:
                    try:
                        response = await self._client.chat.completions.create(
                            model=self._model,
                            messages=[{"role": "user", "content": prompt}],
                            temperature=_JUDGE_TEMPERATURE,
                            extra_body={"seed": _JUDGE_SEED},
                        )
                    except (
                        openai.APIConnectionError,
                        openai.APITimeoutError,
                    ) as exc:
                        raise JudgeUnavailableError(self._model, str(exc)) from exc

                    content = response.choices[0].message.content or ""
                    result = self._parse_response(content)

        except _ParseFailureError as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            _exc_str = str(exc)
            _log.error(
                "prometheus_judge_nan",
                question_id=sample.question_id,
                nan_reason="parse_failure_exhausted",
                raw_len=len(_exc_str),
                raw_snippet=_exc_str[:120],
                model=self._model,
                latency_ms=latency_ms,
                batch_invariant=True,
            )
            return RubricResult(score=float("nan"), feedback="parse_failure")

        latency_ms = int((time.monotonic() - t0) * 1000)
        assert result is not None  # garantido: exceção levantada em caso contrário

        _log.info(
            "prometheus_judge_completed",
            question_id=sample.question_id,
            score=result.score,
            nan=False,
            feedback_len=len(result.feedback),
            latency_ms=latency_ms,
            batch_invariant=True,
        )

        return result

    # ------------------------------------------------------------------
    # Parsing interno
    # ------------------------------------------------------------------

    def _parse_response(self, content: str) -> RubricResult:
        """Parseia o conteúdo JSON da resposta do juiz.

        Args:
            content: string bruta retornada pelo LLM.

        Returns:
            :class:`RubricResult` parseado.

        Raises:
            _ParseFailureError: conteúdo não é JSON válido, faltam campos, ou
                ``score`` está fora de ``[0.0, 1.0]``.
        """
        try:
            data = json.loads(content)
            score = float(data["score"])
        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            _log.warning(
                "prometheus_judge_parse_failure",
                raw_len=len(content),
                raw_snippet=content[:120],
                error=str(exc),
            )
            raise _ParseFailureError(content) from exc

        if not (0.0 <= score <= 1.0):
            _log.warning(
                "prometheus_judge_parse_failure",
                raw_content=content[:500],
                error=f"score={score} out of [0.0, 1.0]",
            )
            raise _ParseFailureError(f"score_out_of_range:{content}")

        feedback = str(data.get("feedback", ""))
        return RubricResult(score=score, feedback=feedback)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Fecha o transporte httpx interno do ``AsyncOpenAI``."""
        await self._client.close()
