"""Property-based tests para ``MetricVector`` (serialização / desserialização).

Verifica três propriedades:

P2.1 — Roundtrip: ``MetricVector.from_dict(mv.to_dict()) == mv``
       (usando ``dataclasses.asdict`` como ``to_dict`` e
       ``MetricVector(**d)`` como ``from_dict``; comparação NaN-safe).
P2.2 — Idempotência: ``mv.to_dict()`` chamado duas vezes retorna dicts
       iguais (sem estado mutável).
P2.3 — Detecção de NaN: todos os campos válidos → ``has_nan() == False``;
       pelo menos um NaN → ``has_nan() == True``.
"""

from __future__ import annotations

import dataclasses
import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from inteligenciomica_eval.domain.value_objects import MetricVector

# ---------------------------------------------------------------------------
# Helpers de conversão (to_dict / from_dict / has_nan)
# ---------------------------------------------------------------------------

_METRIC_FIELDS: tuple[str, ...] = tuple(
    f.name for f in dataclasses.fields(MetricVector)
)


def _to_dict(mv: MetricVector) -> dict[str, float]:
    return dataclasses.asdict(mv)


def _from_dict(d: dict[str, float]) -> MetricVector:
    return MetricVector(**d)


def _has_nan(mv: MetricVector) -> bool:
    return bool(mv.nan_fields())


def _mv_eq_nan_safe(a: MetricVector, b: MetricVector) -> bool:
    """Igualdade NaN-safe campo a campo."""
    for name in _METRIC_FIELDS:
        va: float = getattr(a, name)
        vb: float = getattr(b, name)
        if math.isnan(va) and math.isnan(vb):
            continue
        if va != vb:
            return False
    return True


# ---------------------------------------------------------------------------
# Estratégia hypothesis — valor de cada campo pode ser [0,1] ou NaN
# ---------------------------------------------------------------------------

_metric_value = st.one_of(
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    st.just(float("nan")),
)


@st.composite
def _metric_vector_strategy(draw: st.DrawFn) -> MetricVector:
    return MetricVector(
        answer_correctness=draw(_metric_value),
        answer_similarity=draw(_metric_value),
        faithfulness=draw(_metric_value),
        context_precision=draw(_metric_value),
        context_recall=draw(_metric_value),
        answer_relevancy=draw(_metric_value),
        bertscore_f1=draw(_metric_value),
        rubric_biomed_score=draw(_metric_value),
    )


# ---------------------------------------------------------------------------
# P2.1 — Roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(mv=_metric_vector_strategy())
def test_metric_vector_roundtrip(mv: MetricVector) -> None:
    """P2.1: Roundtrip via to_dict/from_dict preserva todos os campos (NaN-safe)."""
    reconstructed = _from_dict(_to_dict(mv))
    assert _mv_eq_nan_safe(mv, reconstructed)


# ---------------------------------------------------------------------------
# P2.2 — Idempotência de to_dict
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(mv=_metric_vector_strategy())
def test_metric_vector_to_dict_idempotent(mv: MetricVector) -> None:
    """P2.2: to_dict() chamado duas vezes retorna dicts com mesmos valores."""
    d1 = _to_dict(mv)
    d2 = _to_dict(mv)
    for name in _METRIC_FIELDS:
        v1, v2 = d1[name], d2[name]
        if math.isnan(v1) and math.isnan(v2):
            continue
        assert v1 == v2, f"Campo {name!r}: {v1!r} != {v2!r}"


# ---------------------------------------------------------------------------
# P2.3a — Sem NaN → has_nan() == False
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(
    mv=st.builds(
        MetricVector,
        **{
            f: st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
            for f in _METRIC_FIELDS
        },
    )
)
def test_all_valid_fields_has_nan_false(mv: MetricVector) -> None:
    """P2.3a: MetricVector sem nenhum NaN → has_nan() retorna False."""
    assert not _has_nan(mv)


# ---------------------------------------------------------------------------
# P2.3b — Pelo menos um NaN → has_nan() == True
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(
    mv=st.builds(
        MetricVector,
        **{f: st.just(float("nan")) for f in _METRIC_FIELDS},
    )
)
def test_all_nan_fields_has_nan_true(mv: MetricVector) -> None:
    """P2.3b: MetricVector com todos os campos NaN → has_nan() retorna True."""
    assert _has_nan(mv)


@pytest.mark.property
@given(
    mv=_metric_vector_strategy(),
    nan_field=st.sampled_from(_METRIC_FIELDS),
)
@settings(max_examples=200)
def test_at_least_one_nan_field_has_nan_true(mv: MetricVector, nan_field: str) -> None:
    """P2.3b variante: MetricVector com pelo menos um NaN → has_nan() == True."""
    values = _to_dict(mv)
    values[nan_field] = float("nan")
    mv_with_nan = _from_dict(values)
    assert _has_nan(mv_with_nan)
