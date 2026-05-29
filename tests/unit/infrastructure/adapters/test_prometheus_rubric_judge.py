"""Testes unitários para PrometheusRubricJudgeAdapter (TAREFA-024).

HTTP do juiz mockado no **nível do SDK** (``adapter._client.chat.completions.create
= AsyncMock(...)``), o mesmo padrão de TAREFA-014/016 registrado em CLAUDE.md §11.
Não usa ``respx`` nem ``httpx.MockTransport``: o SDK OpenAI v2 usa ``asyncify``
(``asyncio.to_thread``) na primeira chamada, o que pode travar o transporte
interceptado por respx em ambientes sandboxed/containers (timeout observado na
auditoria TAREFA-024-B). O mock no nível do SDK é 100% determinístico e
independente de anyio/sniffio/httpx.

Cenários:
- Protocolo: isinstance RubricJudgePort; determinism_regime == JUDGE; prompt_version.
- Normalização: score 1→0.0, 3→0.5, 5→1.0 (3 pontos).
- Parse falho (JSON inválido, score fora de [1,5], campos ausentes) → NaN sem exceção.
- I/O total (HTTP 5xx, conexão) → MetricComputationError.
- temperature=0.0 e seed=42 na chamada ao SDK (verificado via call_args).
- Prompt versionado contém exatamente 6 dimensões.
"""

from __future__ import annotations

import importlib.resources
import json
import math
import re
from unittest.mock import AsyncMock, MagicMock

import httpx
import openai
import pytest

from inteligenciomica_eval.domain.errors import MetricComputationError
from inteligenciomica_eval.domain.ports import EvaluationSample, RubricJudgePort
from inteligenciomica_eval.domain.value_objects import DeterminismRegime
from inteligenciomica_eval.infrastructure.adapters.prometheus_rubric_judge import (
    _JUDGE_SEED,
    _JUDGE_TEMPERATURE,
    _PARSE_ERROR_FEEDBACK,
    _PROMPTS_PKG,
    _RUBRIC_FILE,
    PrometheusRubricJudgeAdapter,
)
from inteligenciomica_eval.infrastructure.config.adapter_configs import (
    RubricJudgeAdapterConfig,
)

_JUDGE_URL = "http://localhost:8001/v1"
_ENDPOINT = f"{_JUDGE_URL}/chat/completions"

# Objeto httpx mínimo para construir erros do SDK sem tocar na rede.
_DUMMY_REQUEST = httpx.Request("POST", _ENDPOINT)

_SAMPLE = EvaluationSample(
    question_id="q_rubric_01",
    question="Qual o mecanismo de ação das estatinas?",
    ground_truth="Inibem a HMG-CoA redutase, reduzindo a síntese de colesterol.",
    generated_answer="As estatinas inibem a enzima HMG-CoA redutase.",
    contexts=("A HMG-CoA redutase é a enzima limitante da via do mevalonato.",),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_completion(content: str) -> MagicMock:
    """Cria um mock mínimo de ChatCompletion carregando *content* na message."""
    comp = MagicMock()
    comp.choices = [MagicMock()]
    comp.choices[0].message.content = content
    comp.usage = MagicMock()
    comp.usage.prompt_tokens = 64
    comp.usage.completion_tokens = 32
    return comp


def _rubric_json(score: int) -> str:
    """JSON válido da rubrica com o score bruto dado e feedback completo."""
    return json.dumps(
        {
            "score": score,
            "feedback": {
                "correcao_factual": "ok",
                "completude": "ok",
                "contradicoes_internas": "nenhuma",
                "alucinacao": "nenhuma",
                "ressalvas_omitidas": "nenhuma",
                "pertinencia_biomedica": "ok",
                "global": "boa resposta",
            },
        }
    )


def _make_adapter(create_mock: AsyncMock | None = None) -> PrometheusRubricJudgeAdapter:
    """Constrói o adapter; injeta *create_mock* no nível do SDK quando fornecido.

    Moca em ``_client.chat.completions.create`` para independência total de
    transport / event-loop (CLAUDE.md §11).
    """
    adapter = PrometheusRubricJudgeAdapter(
        RubricJudgeAdapterConfig(vllm_judge_url=_JUDGE_URL, judge_model_name="judge")
    )
    if create_mock is not None:
        adapter._client.chat.completions.create = create_mock  # type: ignore[method-assign]
    return adapter


# ---------------------------------------------------------------------------
# Conformidade de protocolo
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    def test_isinstance_rubric_judge_port(self) -> None:
        """isinstance contra RubricJudgePort deve passar em runtime."""
        assert isinstance(_make_adapter(), RubricJudgePort)

    def test_static_typing_assignment(self) -> None:
        """Atribuição estática judge: RubricJudgePort = adapter (regressão async)."""
        judge: RubricJudgePort = _make_adapter()
        assert isinstance(judge, RubricJudgePort)

    def test_determinism_regime_is_judge(self) -> None:
        """determinism_regime == JUDGE (TAREFA-022, propagação batch_invariant)."""
        assert _make_adapter().determinism_regime is DeterminismRegime.JUDGE

    def test_prompt_version_accessible(self) -> None:
        """adapter.prompt_version é exposto (para o schema §5.3)."""
        assert _make_adapter().prompt_version == "biomed_rubric_v1"


# ---------------------------------------------------------------------------
# Normalização do score 1-5 → [0,1]
# ---------------------------------------------------------------------------


class TestNormalization:
    @pytest.mark.parametrize(
        ("raw_score", "expected"),
        [(1, 0.0), (3, 0.5), (5, 1.0)],
    )
    async def test_score_normalization(self, raw_score: int, expected: float) -> None:
        """score bruto 1/3/5 → 0.0/0.5/1.0 (fórmula (s-1)/4)."""
        mock = AsyncMock(return_value=_mock_completion(_rubric_json(raw_score)))
        adapter = _make_adapter(create_mock=mock)

        result = await adapter.score(_SAMPLE)

        assert result.score == pytest.approx(expected)

    async def test_feedback_serialized_not_parse_error(self) -> None:
        """Sucesso → feedback é JSON serializado (não o sentinel de parse_error)."""
        mock = AsyncMock(return_value=_mock_completion(_rubric_json(4)))
        adapter = _make_adapter(create_mock=mock)

        result = await adapter.score(_SAMPLE)

        assert result.feedback != _PARSE_ERROR_FEEDBACK
        assert "global" in result.feedback


# ---------------------------------------------------------------------------
# Falha de parsing → NaN sem exceção (ADR-007)
# ---------------------------------------------------------------------------


class TestParseFailure:
    @pytest.mark.parametrize(
        "content",
        [
            "isto não é json",  # JSON malformado
            json.dumps({"score": 7, "feedback": {}}),  # score fora de [1,5]
            json.dumps({"score": 0, "feedback": {}}),  # score fora de [1,5]
            json.dumps({"feedback": {"global": "x"}}),  # campo score ausente
            json.dumps({"score": 3}),  # campo feedback ausente
            json.dumps({"score": "três", "feedback": {}}),  # score não-int
        ],
    )
    async def test_parse_failure_returns_nan_without_exception(
        self, content: str
    ) -> None:
        """Parse falho → RubricResult(NaN, '[parse_error]') sem levantar."""
        mock = AsyncMock(return_value=_mock_completion(content))
        adapter = _make_adapter(create_mock=mock)

        result = await adapter.score(_SAMPLE)

        assert math.isnan(result.score)
        assert result.feedback == _PARSE_ERROR_FEEDBACK


# ---------------------------------------------------------------------------
# Falha total de I/O → MetricComputationError
# ---------------------------------------------------------------------------


class TestIOFailure:
    async def test_http_500_raises_metric_computation_error(self) -> None:
        """HTTP 5xx (InternalServerError) → MetricComputationError (não NaN)."""
        exc = openai.InternalServerError(
            "server error",
            response=httpx.Response(500, request=_DUMMY_REQUEST),
            body=None,
        )
        mock = AsyncMock(side_effect=exc)
        adapter = _make_adapter(create_mock=mock)

        with pytest.raises(MetricComputationError):
            await adapter.score(_SAMPLE)

    async def test_connection_error_raises_metric_computation_error(self) -> None:
        """Erro de conexão → MetricComputationError."""
        exc = openai.APIConnectionError(
            message="connection refused", request=_DUMMY_REQUEST
        )
        mock = AsyncMock(side_effect=exc)
        adapter = _make_adapter(create_mock=mock)

        with pytest.raises(MetricComputationError):
            await adapter.score(_SAMPLE)


# ---------------------------------------------------------------------------
# Determinismo: temperature=0.0 / seed=42 na chamada ao SDK (ADR-003)
# ---------------------------------------------------------------------------


class TestDeterminism:
    async def test_temperature_zero_in_request_body(self) -> None:
        """A chamada ao SDK deve ter temperature=0.0 e seed=42 em extra_body."""
        mock = AsyncMock(return_value=_mock_completion(_rubric_json(4)))
        adapter = _make_adapter(create_mock=mock)

        await adapter.score(_SAMPLE)

        call_kwargs = mock.call_args.kwargs
        assert call_kwargs["temperature"] == _JUDGE_TEMPERATURE
        assert _JUDGE_TEMPERATURE == 0.0
        assert call_kwargs["extra_body"]["seed"] == _JUDGE_SEED


# ---------------------------------------------------------------------------
# Prompt versionado: exatamente 6 dimensões
# ---------------------------------------------------------------------------


class TestRubricPrompt:
    def test_prompt_has_exactly_six_dimensions(self) -> None:
        """O arquivo de prompt deve conter EXATAMENTE 6 dimensões numeradas."""
        text = (
            importlib.resources.files(_PROMPTS_PKG)
            .joinpath(_RUBRIC_FILE)
            .read_text(encoding="utf-8")
        )
        numbered = re.findall(r"^\d+\. ", text, flags=re.MULTILINE)
        assert len(numbered) == 6

    def test_prompt_mentions_each_canonical_dimension(self) -> None:
        """As 6 dimensões canônicas (§5.2) estão nomeadas no prompt."""
        text = (
            importlib.resources.files(_PROMPTS_PKG)
            .joinpath(_RUBRIC_FILE)
            .read_text(encoding="utf-8")
        )
        for token in (
            "Correção factual",
            "Completude",
            "Contradições internas",
            "Alucinação",
            "Ressalvas omitidas",
            "Pertinência biomédica",
        ):
            assert token in text, f"dimensão ausente: {token}"
