"""Integração do PrometheusRubricJudgeAdapter contra um vllm-judge real (TAREFA-024).

Confirma o determinismo da Camada 2 (ADR-003): a mesma entrada avaliada duas vezes
produz o mesmo score. Pulado — não falha — quando ``VLLM_JUDGE_URL`` não está
definido, mantendo o gate de unit independente de GPU/rede.
"""

from __future__ import annotations

import math
import os

import pytest

from inteligenciomica_eval.domain.ports import EvaluationSample
from inteligenciomica_eval.infrastructure.adapters.prometheus_rubric_judge import (
    PrometheusRubricJudgeAdapter,
)
from inteligenciomica_eval.infrastructure.config.adapter_configs import (
    RubricJudgeAdapterConfig,
)

pytestmark = pytest.mark.integration

_JUDGE_URL = os.environ.get("VLLM_JUDGE_URL")
_JUDGE_MODEL = os.environ.get(
    "VLLM_JUDGE_MODEL", "prometheus-eval/prometheus-8x7b-v2.0"
)

_skip_no_judge = pytest.mark.skipif(
    _JUDGE_URL is None,
    reason="VLLM_JUDGE_URL not set — rubric judge integration requires a live judge",
)

_SAMPLE = EvaluationSample(
    question_id="q_rubric_integration",
    question="Quais são os principais mecanismos de resistência a antibióticos?",
    ground_truth="Betalactamases, alteração de PBPs e redução de porinas.",
    generated_answer="Resistência via betalactamases, PBPs alteradas e perda de porinas.",
    contexts=(
        "Betalactamases inativam o anel betalactâmico.",
        "MRSA expressa PBP2a com baixa afinidade aos betalactâmicos.",
    ),
)


@_skip_no_judge
async def test_rubric_judge_is_deterministic() -> None:
    """Mesma entrada 2x -> mesmo score (determinismo do juiz, ADR-003)."""
    assert _JUDGE_URL is not None  # narrow para mypy (guardado pelo skipif)
    config = RubricJudgeAdapterConfig(
        vllm_judge_url=_JUDGE_URL, judge_model_name=_JUDGE_MODEL
    )
    adapter = PrometheusRubricJudgeAdapter(config)
    try:
        first = await adapter.score(_SAMPLE)
        second = await adapter.score(_SAMPLE)
    finally:
        await adapter.close()

    if math.isnan(first.score) or math.isnan(second.score):
        assert math.isnan(first.score) and math.isnan(second.score)
    else:
        assert first.score == pytest.approx(second.score)
