"""Integração do DeterministicMetricsAdapter com o modelo BERTScore real (TAREFA-025).

Roda o adapter **sem mocks** sobre o golden PT-BR (``det_metrics_pt_golden.json``),
confirmando (a) os thresholds de BERTScore-F1 e ROUGE-L em CPU e (b) o determinismo
(ADR-003): a mesma entrada avaliada duas vezes produz o mesmo float bit-a-bit.

Pulado — não falha — quando o modelo ``bert-base-multilingual-cased`` não está
disponível (sem rede/cache de modelo), mantendo o gate unitário independente de
download de modelo (mesma filosofia dos testes ``testcontainers``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from inteligenciomica_eval.infrastructure.adapters.deterministic_metrics import (
    DeterministicMetricsAdapter,
)
from inteligenciomica_eval.infrastructure.config.adapter_configs import (
    DeterministicAdapterConfig,
)

pytestmark = pytest.mark.integration

_GOLDEN_PATH = Path(__file__).parents[2] / "golden" / "det_metrics_pt_golden.json"
_GOLDEN: list[dict[str, Any]] = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
_GOLDEN_IDS = [c["id"] for c in _GOLDEN]


def _bertscore_available() -> bool:
    """Probe: o modelo BERTScore multilíngue carrega neste ambiente?"""
    try:
        import bert_score

        scorer = bert_score.BERTScorer(
            lang="pt", rescale_with_baseline=True, device="cpu"
        )
        scorer.score(["ok"], ["ok"])
        return True
    except Exception:  # pragma: no cover - depende de rede/modelo
        return False


_skip_no_model = pytest.mark.skipif(
    not _bertscore_available(),
    reason="modelo BERTScore (bert-base-multilingual-cased) indisponível neste ambiente",
)


@_skip_no_model
@pytest.mark.parametrize("case", _GOLDEN, ids=_GOLDEN_IDS)
def test_golden_thresholds_real_model(case: dict[str, Any]) -> None:
    """Golden PT-BR real: BERTScore-F1 e ROUGE-L respeitam os thresholds em CPU."""
    adapter = DeterministicMetricsAdapter(DeterministicAdapterConfig())
    result = adapter.score(answer=case["answer"], ground_truth=case["ground_truth"])

    if "bertscore_f1_min" in case:
        assert result.bertscore_f1 >= case["bertscore_f1_min"], (
            f"{case['id']}: bertscore_f1={result.bertscore_f1} "
            f"< min {case['bertscore_f1_min']}"
        )
    if "bertscore_f1_max" in case:
        assert result.bertscore_f1 <= case["bertscore_f1_max"], (
            f"{case['id']}: bertscore_f1={result.bertscore_f1} "
            f"> max {case['bertscore_f1_max']}"
        )
    if "rouge_l_min" in case:
        assert result.rouge_l >= case["rouge_l_min"]
    if "rouge_l_max" in case:
        assert result.rouge_l <= case["rouge_l_max"]


@_skip_no_model
def test_determinism_same_input_same_float() -> None:
    """Determinismo (ADR-003): 2 chamadas idênticas → mesmo float bit-a-bit."""
    adapter = DeterministicMetricsAdapter(DeterministicAdapterConfig())
    case = next(c for c in _GOLDEN if c["id"] == "similar")

    first = adapter.score(answer=case["answer"], ground_truth=case["ground_truth"])
    second = adapter.score(answer=case["answer"], ground_truth=case["ground_truth"])

    assert first.bertscore_f1 == second.bertscore_f1
    assert first.rouge_l == second.rouge_l
