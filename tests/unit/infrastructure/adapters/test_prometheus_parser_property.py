"""Property-based tests para o parser de resposta JSON do PrometheusJudgeAdapter.

Verifica que o método ``_parse_response`` satisfaz três propriedades:

P1.1 — JSON válido com ``score ∈ [0.0, 1.0]`` e ``feedback`` como string
       nunca levanta exceção.
P1.2 — Strings arbitrárias (válidas ou não) NUNCA propagam exceção
       não-tratada (``KeyError``, ``ValueError``, ``JSONDecodeError``);
       o método retorna ``RubricResult`` ou levanta ``_ParseFailureError``.
P1.3 — Para JSON válido, ``parsed.score ∈ [0.0, 1.0]`` sempre.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from inteligenciomica_eval.domain.ports import RubricResult
from inteligenciomica_eval.infrastructure.adapters.prometheus_judge import (
    PrometheusJudgeAdapter,
    _ParseFailureError,  # type: ignore[attr-defined]
)

# ---------------------------------------------------------------------------
# Fixture de adapter mínimo — não usa rede; _parse_response é puro
# ---------------------------------------------------------------------------

_ADAPTER = PrometheusJudgeAdapter(
    judge_url="http://localhost:9999/v1",
    registry=MagicMock(),
)

# ---------------------------------------------------------------------------
# Estratégias hypothesis
# ---------------------------------------------------------------------------

_valid_score = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
_valid_feedback = st.text(min_size=0, max_size=500)

_valid_json_with_score = st.builds(
    lambda s, f: json.dumps({"score": s, "feedback": f}),
    _valid_score,
    _valid_feedback,
)

_arbitrary_string = st.text()


# ---------------------------------------------------------------------------
# P1.1 — JSON válido → sem exceção, retorna RubricResult
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(raw=_valid_json_with_score)
@settings(max_examples=200)
def test_parser_valid_json_never_raises(raw: str) -> None:
    """P1.1: JSON válido com score em [0,1] nunca levanta exceção."""
    result = _ADAPTER._parse_response(raw)  # type: ignore[attr-defined]
    assert isinstance(result, RubricResult)


# ---------------------------------------------------------------------------
# P1.2 — String arbitrária → nunca exceção não-tratada
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(s=_arbitrary_string)
@settings(max_examples=200)
def test_parser_never_raises_uncaught_exception(s: str) -> None:
    """P1.2: Strings arbitrárias produzem RubricResult ou _ParseFailureError — nunca outro erro."""
    try:
        result = _ADAPTER._parse_response(s)  # type: ignore[attr-defined]
        assert isinstance(result, RubricResult)
    except _ParseFailureError:
        pass  # comportamento correto para input inválido


# ---------------------------------------------------------------------------
# P1.3 — Para JSON válido, score sempre ∈ [0.0, 1.0]
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(raw=_valid_json_with_score)
@settings(max_examples=200)
def test_parser_score_in_range_for_valid_json(raw: str) -> None:
    """P1.3: Score parsed de JSON válido sempre pertence a [0.0, 1.0]."""
    result = _ADAPTER._parse_response(raw)  # type: ignore[attr-defined]
    assert 0.0 <= result.score <= 1.0
