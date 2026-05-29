"""PrometheusRubricJudgeAdapter — Camada 2 formal (rubrica biomédica, §5.2).

Implementa ``RubricJudgePort`` avaliando a resposta gerada segundo a rubrica
biomédica versionada de 6 dimensões (``biomed_rubric_v1.jinja2``). O score bruto
inteiro de 1 a 5 do juiz é normalizado para ``[0, 1]``; falha de parsing devolve
``RubricResult(nan, "[parse_error]")`` sem exceção; falha total de I/O levanta
``MetricComputationError`` (Nota M2 item 4, ADR-007).

ADR inline — escolha da Opção B (chamada direta) sobre a Opção A (DeepEval G-Eval):
    O pacote ``deepeval`` **não** está instalado no ambiente (uv.lock) e o seu
    ``GEval`` impõe a própria cadeia de avaliação (evaluation steps + score
    interno via logprobs), incompatível com o requisito de um **prompt versionado
    externo** que devolve um JSON estruturado ``{"score": 1-5, "feedback": {...}}``.
    A chamada direta via ``openai.AsyncOpenAI`` (mesmo padrão do
    ``PrometheusJudgeAdapter`` de TAREFA-016) dá controle total do prompt e do
    parser Pydantic, é determinística (``temperature=0.0``) e testável via respx —
    exatamente o cenário previsto na "Opção B (fallback)" do Prompt A (TAREFA-024).
"""

from __future__ import annotations

import importlib.resources
import json
import re
import time

import jinja2
import openai
import structlog
from pydantic import BaseModel, Field, ValidationError

from inteligenciomica_eval.domain.errors import MetricComputationError
from inteligenciomica_eval.domain.ports import EvaluationSample, RubricResult
from inteligenciomica_eval.domain.value_objects import DeterminismRegime
from inteligenciomica_eval.infrastructure.config.adapter_configs import (
    RubricJudgeAdapterConfig,
)

_log = structlog.get_logger(__name__)

_PROMPTS_PKG = "inteligenciomica_eval.infrastructure.prompts"
_RUBRIC_FILE = "biomed_rubric_v1.jinja2"
_VERSION_RE = re.compile(r"RUBRIC_VERSION:\s*(\S+)")
_JUDGE_SEED = 42
_JUDGE_TEMPERATURE = 0.0
_PARSE_ERROR_FEEDBACK = "[parse_error]"

# Erros que indicam falha total de I/O do servidor juiz (HTTP 5xx, timeout, conexão);
# viram MetricComputationError para o RetryableRubricJudgeAdapter (TAREFA-027) tratar.
_IO_ERROR_TYPES: tuple[type[Exception], ...] = (
    openai.APIConnectionError,
    openai.APITimeoutError,
    openai.InternalServerError,
)


class RubricOutput(BaseModel):
    """Schema Pydantic do JSON retornado pelo juiz (rag-engineer §16: nada de json.loads cego).

    Args:
        score: score global bruto, inteiro em ``[1, 5]``.
        feedback: justificativas por dimensão (+ ``"global"``).
    """

    score: int = Field(..., ge=1, le=5)
    feedback: dict[str, str]


def _load_rubric_prompt() -> tuple[jinja2.Template, str]:
    """Carrega o template da rubrica e extrai a versão da 1ª linha marcadora.

    Returns:
        Tupla ``(template, prompt_version)``. A versão vem do comentário
        ``{# RUBRIC_VERSION: ... #}`` no topo do arquivo (fonte única §5.3).

    Raises:
        ValueError: se o marcador ``RUBRIC_VERSION`` estiver ausente.
    """
    text = (
        importlib.resources.files(_PROMPTS_PKG)
        .joinpath(_RUBRIC_FILE)
        .read_text(encoding="utf-8")
    )
    match = _VERSION_RE.search(text)
    if match is None:
        raise ValueError(f"{_RUBRIC_FILE}: missing RUBRIC_VERSION marker")
    template = jinja2.Template(text, autoescape=False, keep_trailing_newline=True)
    return template, match.group(1)


class PrometheusRubricJudgeAdapter:
    """Avalia amostras via rubrica biomédica de 6 dimensões (Camada 2, §5.2).

    Implementação **canônica** de Camada 2. O ``PrometheusJudgeAdapter`` de
    M1/TAREFA-016 permanece para compatibilidade (depreciação suave) — este
    adapter é o usado pelo ``ComputeMetricsUseCase`` (TAREFA-026).

    ``determinism_regime`` é sempre ``DeterminismRegime.JUDGE`` (ADR-003,
    TAREFA-022) e ``temperature=0.0`` — nunca configurável.

    Args:
        config: :class:`RubricJudgeAdapterConfig` com URL/modelo/timeout do juiz.
    """

    def __init__(self, config: RubricJudgeAdapterConfig) -> None:
        self._config = config
        self._template, self.prompt_version = _load_rubric_prompt()
        self.determinism_regime: DeterminismRegime = DeterminismRegime.JUDGE
        self._client = openai.AsyncOpenAI(
            base_url=config.vllm_judge_url,
            api_key=config.vllm_judge_api_key,
            max_retries=0,  # retry é responsabilidade do RetryableRubricJudgeAdapter
            timeout=float(config.timeout_s),
        )

    async def score(self, sample: EvaluationSample) -> RubricResult:
        """Avalia *sample* pela rubrica biomédica (Camada 2).

        Args:
            sample: amostra com pergunta, ground truth, resposta gerada e contextos.

        Returns:
            :class:`RubricResult` com ``score`` normalizado em ``[0, 1]`` (ou
            ``math.nan`` em falha de parsing) e feedback estruturado serializado.

        Raises:
            MetricComputationError: falha total de I/O (HTTP 5xx, timeout, conexão).
        """
        prompt = self._template.render(
            question=sample.question,
            reference=sample.ground_truth,
            generated_answer=sample.generated_answer,
            retrieved_context="\n".join(sample.contexts),
        )

        t0 = time.monotonic()
        try:
            response = await self._client.chat.completions.create(
                model=self._config.judge_model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=_JUDGE_TEMPERATURE,
                extra_body={"seed": _JUDGE_SEED},
            )
        except _IO_ERROR_TYPES as exc:
            raise MetricComputationError("rubric_biomed", str(exc)) from exc

        content = response.choices[0].message.content or ""
        result = self._parse_response(content)
        latency_ms = int((time.monotonic() - t0) * 1000)

        _log.info(
            "rubric_judge_completed",
            question_id=sample.question_id,
            score=result.score,
            prompt_version=self.prompt_version,
            latency_ms=latency_ms,
            parse_error=result.feedback == _PARSE_ERROR_FEEDBACK,
            feedback_len=len(result.feedback),
        )
        return result

    def _parse_response(self, content: str) -> RubricResult:
        """Valida o JSON do juiz com Pydantic e normaliza o score para ``[0, 1]``.

        Args:
            content: string bruta retornada pelo juiz.

        Returns:
            :class:`RubricResult`; ``RubricResult(nan, "[parse_error]")`` em
            JSON malformado, score fora de ``[1, 5]`` ou campos ausentes — sem exceção.
        """
        try:
            data = json.loads(content)
            parsed = RubricOutput.model_validate(data)
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            _log.warning(
                "rubric_judge_parse_failure",
                error=str(exc),
                raw_len=len(content),
            )
            return RubricResult(score=float("nan"), feedback=_PARSE_ERROR_FEEDBACK)

        # Normalização 1→0.0, 3→0.5, 5→1.0 (score_bruto ∈ [1,5]).
        normalized = (parsed.score - 1) / 4.0
        feedback = json.dumps(parsed.feedback, ensure_ascii=False, sort_keys=True)
        return RubricResult(score=normalized, feedback=feedback)

    async def close(self) -> None:
        """Fecha o transporte httpx interno do ``AsyncOpenAI``."""
        await self._client.close()
