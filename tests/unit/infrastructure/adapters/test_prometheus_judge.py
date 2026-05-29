"""Testes unitários para PrometheusJudgeAdapter (TAREFA-016).

Usa AsyncMock para interceptar ``openai.AsyncOpenAI.chat.completions.create``
no nível do SDK — mesmo padrão de TAREFA-014 (registrado em CLAUDE.md §11).
Não usa respx nem httpx.MockTransport: essa camada é independente de
transport e event-loop, garantindo determinismo em qualquer ambiente.

Mock injetado após construção:
    adapter._client.chat.completions.create = AsyncMock(...)
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest
from tenacity import stop_after_attempt, wait_none

from inteligenciomica_eval.domain.errors import JudgeUnavailableError
from inteligenciomica_eval.domain.ports import (
    EvaluationSample,
    RubricJudgePort,
    RubricResult,
)
from inteligenciomica_eval.infrastructure.adapters.prometheus_judge import (
    _DEFAULT_MODEL,
    _JUDGE_SEED,
    _JUDGE_TEMPERATURE,
    PrometheusJudgeAdapter,
)
from inteligenciomica_eval.infrastructure.prompts.registry import PromptRegistry

# ---------------------------------------------------------------------------
# Constantes de teste
# ---------------------------------------------------------------------------

_JUDGE_URL = "http://localhost:8001/v1"
_ENDPOINT = f"{_JUDGE_URL}/chat/completions"

_SAMPLE = EvaluationSample(
    question_id="q_resist_antibioticos",
    question="Quais são os principais mecanismos de resistência a antibióticos?",
    ground_truth="Três mecanismos: betalactamases, alteração de PBPs e redução de porinas.",
    generated_answer="As bactérias resistem via betalactamases, PBPs alteradas e porinas.",
    contexts=("Betalactamases inativam o anel betalactâmico.", "MRSA expressa PBP2a."),
)

# Objeto httpx mínimo para construir erros do SDK sem tocar na rede.
_DUMMY_REQUEST = httpx.Request("POST", _ENDPOINT)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_completion(content: str) -> MagicMock:
    """Cria um mock mínimo de ChatCompletion com *content* como mensagem."""
    comp = MagicMock()
    comp.choices = [MagicMock()]
    comp.choices[0].message.content = content
    comp.usage = MagicMock()
    comp.usage.prompt_tokens = 512
    comp.usage.completion_tokens = 32
    return comp


def _make_adapter(
    create_mock: AsyncMock | None = None,
    registry: PromptRegistry | None = None,
) -> PrometheusJudgeAdapter:
    """Constrói um PrometheusJudgeAdapter com retry instantâneo para testes.

    Moca no nível do SDK (``_client.chat.completions.create``) para
    independência total de transport / event-loop.
    """
    if registry is None:
        registry = PromptRegistry()

    adapter = PrometheusJudgeAdapter(
        judge_url=_JUDGE_URL,
        registry=registry,
        _retry_stop=stop_after_attempt(3),
        _retry_wait=wait_none(),
    )
    if create_mock is not None:
        adapter._client.chat.completions.create = create_mock  # type: ignore[method-assign]
    return adapter


# ---------------------------------------------------------------------------
# Testes de protocolo
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_isinstance_rubric_judge_port(self) -> None:
        """isinstance contra RubricJudgePort deve passar em runtime."""
        adapter = _make_adapter()
        assert isinstance(adapter, RubricJudgePort)

    def test_static_typing_assignment(self) -> None:
        """Atribuição judge: RubricJudgePort = PrometheusJudgeAdapter() deve ser válida.

        Verifica que o contrato async do port é satisfeito pelo adapter.
        Se RubricJudgePort.score for sync e PrometheusJudgeAdapter.score for async,
        mypy rejeitaria esta atribuição (bloqueador auditoria C).
        """
        judge: RubricJudgePort = _make_adapter()
        assert isinstance(judge, RubricJudgePort)

    def test_batch_invariant_always_true_in_docstring(self) -> None:
        """Confirma que batch_invariant=True está documentado como constante."""
        doc = PrometheusJudgeAdapter.__doc__ or ""
        assert "batch_invariant" in doc
        assert "True" in doc


# ---------------------------------------------------------------------------
# Testes de happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    async def test_score_parsed_from_valid_json(self) -> None:
        """Score 0.85 retornado a partir de resposta JSON válida."""
        content = '{"score": 0.85, "feedback": "Boa resposta factualmente correta."}'
        mock = AsyncMock(return_value=_mock_completion(content))
        adapter = _make_adapter(create_mock=mock)

        result = await adapter.score(_SAMPLE)

        assert isinstance(result, RubricResult)
        assert result.score == pytest.approx(0.85)
        assert "Boa resposta" in result.feedback

    async def test_score_boundary_zero(self) -> None:
        """Score 0.0 é aceito como válido."""
        content = '{"score": 0.0, "feedback": "Resposta inadequada."}'
        mock = AsyncMock(return_value=_mock_completion(content))
        adapter = _make_adapter(create_mock=mock)

        result = await adapter.score(_SAMPLE)

        assert result.score == pytest.approx(0.0)

    async def test_score_boundary_one(self) -> None:
        """Score 1.0 é aceito como válido."""
        content = '{"score": 1.0, "feedback": "Excelente."}'
        mock = AsyncMock(return_value=_mock_completion(content))
        adapter = _make_adapter(create_mock=mock)

        result = await adapter.score(_SAMPLE)

        assert result.score == pytest.approx(1.0)

    async def test_prompt_contains_question_and_ground_truth(self) -> None:
        """O prompt enviado ao juiz deve incluir question e ground_truth do sample."""
        content = '{"score": 0.9, "feedback": "OK."}'
        mock = AsyncMock(return_value=_mock_completion(content))
        adapter = _make_adapter(create_mock=mock)

        await adapter.score(_SAMPLE)

        mock.assert_called_once()
        call_kwargs = mock.call_args.kwargs
        prompt_text: str = call_kwargs["messages"][0]["content"]
        assert _SAMPLE.question in prompt_text
        assert _SAMPLE.ground_truth in prompt_text
        assert _SAMPLE.generated_answer in prompt_text

    async def test_temperature_zero_in_request(self) -> None:
        """temperature=0.0 deve estar na chamada ao SDK (juiz determinístico §9.3)."""
        content = '{"score": 0.75, "feedback": "OK."}'
        mock = AsyncMock(return_value=_mock_completion(content))
        adapter = _make_adapter(create_mock=mock)

        await adapter.score(_SAMPLE)

        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["temperature"] == _JUDGE_TEMPERATURE
        assert _JUDGE_TEMPERATURE == 0.0

    async def test_seed_constant_in_extra_body(self) -> None:
        """seed constante deve estar em extra_body (vLLM-specific, §9.3)."""
        content = '{"score": 0.75, "feedback": "OK."}'
        mock = AsyncMock(return_value=_mock_completion(content))
        adapter = _make_adapter(create_mock=mock)

        await adapter.score(_SAMPLE)

        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["extra_body"]["seed"] == _JUDGE_SEED

    async def test_model_forwarded_to_sdk(self) -> None:
        """O model identifier deve ser passado ao SDK."""
        content = '{"score": 0.8, "feedback": "OK."}'
        mock = AsyncMock(return_value=_mock_completion(content))
        adapter = _make_adapter(create_mock=mock)

        await adapter.score(_SAMPLE)

        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["model"] == _DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Testes da política NaN-or-retry
# ---------------------------------------------------------------------------


class TestNaNOrRetryPolicy:
    async def test_nan_returned_after_three_malformed_responses(self) -> None:
        """Score NaN após 3 respostas com JSON inválido (ADR-007)."""
        mock = AsyncMock(return_value=_mock_completion("isto não é json válido"))
        adapter = _make_adapter(create_mock=mock)

        result = await adapter.score(_SAMPLE)

        assert math.isnan(result.score)
        assert result.feedback == "parse_failure"

    async def test_three_attempts_made_on_malformed_response(self) -> None:
        """Exatamente 3 chamadas ao SDK antes de retornar NaN."""
        mock = AsyncMock(return_value=_mock_completion("não é json"))
        adapter = _make_adapter(create_mock=mock)

        await adapter.score(_SAMPLE)

        assert mock.call_count == 3

    async def test_nan_on_score_out_of_range(self) -> None:
        """Score fora de [0,1] é tratado como parse failure → NaN."""
        content = '{"score": 1.5, "feedback": "Score inválido."}'
        mock = AsyncMock(return_value=_mock_completion(content))
        adapter = _make_adapter(create_mock=mock)

        result = await adapter.score(_SAMPLE)

        assert math.isnan(result.score)
        assert mock.call_count == 3

    async def test_nan_on_missing_score_field(self) -> None:
        """JSON sem campo 'score' tratado como parse failure → NaN."""
        content = '{"feedback": "Sem score."}'
        mock = AsyncMock(return_value=_mock_completion(content))
        adapter = _make_adapter(create_mock=mock)

        result = await adapter.score(_SAMPLE)

        assert math.isnan(result.score)

    async def test_recovery_after_two_failures(self) -> None:
        """Recupera com score válido na 3ª tentativa após 2 falhas."""
        good_content = '{"score": 0.7, "feedback": "Recuperado."}'
        mock = AsyncMock(
            side_effect=[
                _mock_completion("lixo 1"),
                _mock_completion("lixo 2"),
                _mock_completion(good_content),
            ]
        )
        adapter = _make_adapter(create_mock=mock)

        result = await adapter.score(_SAMPLE)

        assert result.score == pytest.approx(0.7)
        assert mock.call_count == 3


# ---------------------------------------------------------------------------
# Testes de JudgeUnavailableError
# ---------------------------------------------------------------------------


class TestJudgeUnavailableError:
    async def test_connection_error_raises_judge_unavailable(self) -> None:
        """APIConnectionError deve ser propagado como JudgeUnavailableError."""
        exc = openai.APIConnectionError(
            message="connection refused",
            request=_DUMMY_REQUEST,
        )
        mock = AsyncMock(side_effect=exc)
        adapter = _make_adapter(create_mock=mock)

        with pytest.raises(JudgeUnavailableError) as exc_info:
            await adapter.score(_SAMPLE)

        assert "prometheus-eval" in exc_info.value.judge_id

    async def test_connection_error_not_retried(self) -> None:
        """Falha de conexão não deve ser retentada — é irrecuperável."""
        exc = openai.APIConnectionError(
            message="conn refused",
            request=_DUMMY_REQUEST,
        )
        mock = AsyncMock(side_effect=exc)
        adapter = _make_adapter(create_mock=mock)

        with pytest.raises(JudgeUnavailableError):
            await adapter.score(_SAMPLE)

        assert mock.call_count == 1

    async def test_timeout_error_raises_judge_unavailable(self) -> None:
        """APITimeoutError deve ser propagado como JudgeUnavailableError."""
        exc = openai.APITimeoutError(request=_DUMMY_REQUEST)
        mock = AsyncMock(side_effect=exc)
        adapter = _make_adapter(create_mock=mock)

        with pytest.raises(JudgeUnavailableError):
            await adapter.score(_SAMPLE)


# ---------------------------------------------------------------------------
# Testes de batch_invariant
# ---------------------------------------------------------------------------


class TestBatchInvariant:
    async def test_batch_invariant_true_is_constant(self) -> None:
        """batch_invariant=True deve ser uma constante não-configurável (ADR-003)."""
        import inspect

        src = inspect.getsource(PrometheusJudgeAdapter.score)
        assert "batch_invariant=True" in src

    async def test_success_log_fields(self) -> None:
        """Evento prometheus_judge_completed deve ter todos os campos obrigatórios."""

        import structlog.testing

        content = '{"score": 0.9, "feedback": "Ótimo resultado."}'
        mock = AsyncMock(return_value=_mock_completion(content))
        adapter = _make_adapter(create_mock=mock)

        with structlog.testing.capture_logs() as logs:
            await adapter.score(_SAMPLE)

        completed = [e for e in logs if e.get("event") == "prometheus_judge_completed"]
        assert len(completed) == 1
        ev = completed[0]
        assert ev["question_id"] == _SAMPLE.question_id
        assert ev["score"] == pytest.approx(0.9)
        assert ev["nan"] is False
        assert isinstance(ev["feedback_len"], int)
        assert ev["feedback_len"] > 0
        assert isinstance(ev["latency_ms"], int)
        assert ev["latency_ms"] >= 0
        assert ev["batch_invariant"] is True

    async def test_nan_log_fields(self) -> None:
        """Evento prometheus_judge_nan deve ter todos os campos obrigatórios."""
        import structlog.testing

        mock = AsyncMock(return_value=_mock_completion("json ruim"))
        adapter = _make_adapter(create_mock=mock)

        with structlog.testing.capture_logs() as logs:
            await adapter.score(_SAMPLE)

        nan_events = [e for e in logs if e.get("event") == "prometheus_judge_nan"]
        assert len(nan_events) == 1
        ev = nan_events[0]
        assert ev["question_id"] == _SAMPLE.question_id
        assert ev["nan_reason"] == "parse_failure_exhausted"
        assert isinstance(ev["raw_content"], str)
        assert isinstance(ev["latency_ms"], int)
        assert ev["batch_invariant"] is True


# ---------------------------------------------------------------------------
# Testes de lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    async def test_close_does_not_raise(self) -> None:
        """close() deve encerrar sem exceção."""
        adapter = _make_adapter()
        await adapter.close()
