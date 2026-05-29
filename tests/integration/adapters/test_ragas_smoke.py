"""Smoke de integração PT-BR para o RAGASLayer1Adapter (TAREFA-023, item 5).

Constrói o adapter **real** (ChatOpenAI + embeddings) apontando para o vllm-judge
e verifica que ``answer_correctness`` da amostra biomédica em português fica acima
do threshold documentado no golden. Pulado — não falha — quando ``VLLM_JUDGE_URL``
não está definido (mesma filosofia dos testcontainers), mantendo o gate de unit
independente de GPU/rede.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

from inteligenciomica_eval.domain.ports import EvaluationSample
from inteligenciomica_eval.infrastructure.adapters.ragas_metrics import (
    RAGASLayer1Adapter,
)
from inteligenciomica_eval.infrastructure.config.adapter_configs import (
    RagasAdapterConfig,
)

pytestmark = pytest.mark.integration

_GOLDEN = Path(__file__).parents[2] / "golden" / "ragas_pt_smoke.json"
_JUDGE_URL = os.environ.get("VLLM_JUDGE_URL")
_EMBED_URL = os.environ.get("VLLM_EMBED_URL")  # fallback p/ HF local se ausente

_skip_no_judge = pytest.mark.skipif(
    _JUDGE_URL is None,
    reason="VLLM_JUDGE_URL not set — RAGAS PT smoke requires a live judge endpoint",
)


@_skip_no_judge
async def test_ragas_pt_smoke_answer_correctness_above_threshold() -> None:
    """answer_correctness da amostra PT-BR ≥ threshold do golden (juiz real)."""
    payload = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    assert _JUDGE_URL is not None  # narrow para mypy (guardado pelo skipif)

    sample = EvaluationSample(
        question_id="ragas_pt_smoke",
        question=payload["question"],
        ground_truth=payload["ground_truth"],
        generated_answer=payload["generated_answer"],
        contexts=tuple(payload["contexts"]),
    )
    config = RagasAdapterConfig(judge_url=_JUDGE_URL, vllm_embed_url=_EMBED_URL)
    adapter = RAGASLayer1Adapter(config)

    result = await adapter.score(sample)

    threshold = float(payload["expected_answer_correctness_min"])
    assert not math.isnan(result.answer_correctness), "answer_correctness veio NaN"
    assert result.answer_correctness >= threshold, (
        f"answer_correctness={result.answer_correctness:.3f} < {threshold}"
    )
