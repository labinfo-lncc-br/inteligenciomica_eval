"""Property-based tests para ``config_hash`` (provenance.py).

Dois níveis de cobertura:

**Nível 1 — função de produção** ``config_hash(RoundConfig)``:
  P3.1r — Estabilidade: mesma instância → mesmo hash (determinístico).
  P3.2r — Sensibilidade: campo diferente → hash diferente.
  P3.3r — Cross-instance: duas instâncias com dados idênticos → mesmo hash.

**Nível 2 — algoritmo interno** via helper local ``_canonical_dict_hash``:
  P3.1 / P3.2 / P3.3 com entradas arbitrárias (st.dictionaries) — permite
  cobrir casos impossíveis de expressar em RoundConfig válidos, e serve de
  regressão se a implementação da serialização canônica mudar.

A separação é intencional: os testes do nível 1 detectam drift na função real;
os do nível 2 verificam as propriedades matemáticas do algoritmo.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from inteligenciomica_eval.infrastructure.config.provenance import config_hash
from inteligenciomica_eval.infrastructure.config.schema import RoundConfig

# ---------------------------------------------------------------------------
# Factory de RoundConfig mínimo válido
# ---------------------------------------------------------------------------

_FIXED_RETRIEVAL = {
    "top_k": 5,
    "embedding_model": "bge-m3",
    "chunk_strategy": "sentence",
}
_FIXED_JUDGE = {
    "model": "prometheus",
    "endpoint_env": "VLLM_JUDGE_URL",
    "batch_invariant": True,
    "temperature": 0.0,
}
_FIXED_SCORING = {
    "weights": {"metric_a": 0.5, "metric_b": 0.5},
    "failure_threshold": 0.6,
}


def _make_round_config(**overrides: object) -> RoundConfig:
    """Constrói um RoundConfig mínimo e válido com valores fixos."""
    base: dict[str, object] = {
        "round_id": "round_1",
        "phases": ["A"],
        "bases": ["IDx_400k"],
        "llms": ["llama3-8b"],
        "seeds": [42],
        "temperature": 0.0,
        "retrieval": _FIXED_RETRIEVAL,
        "judge": _FIXED_JUDGE,
        "scoring": _FIXED_SCORING,
    }
    base.update(overrides)
    return RoundConfig.model_validate(base)


# ---------------------------------------------------------------------------
# Estratégias para campos variáveis de RoundConfig
# ---------------------------------------------------------------------------

_llm_id = st.from_regex(r"[a-z][a-z0-9\-]{0,18}[a-z0-9]", fullmatch=True)

_round_config_strategy = st.builds(
    _make_round_config,
    round_id=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(whitelist_categories=("L", "N")),
    ),
    temperature=st.floats(
        min_value=0.0,
        max_value=2.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    seeds=st.lists(
        st.integers(min_value=0, max_value=999),
        min_size=1,
        max_size=3,
    ),
    llms=st.lists(_llm_id, min_size=1, max_size=3),
    bases=st.lists(
        st.sampled_from(["IDx_400k", "ID_230K"]),
        min_size=1,
        max_size=2,
        unique=True,
    ),
)

# ---------------------------------------------------------------------------
# P3.1r — Estabilidade sobre RoundConfig real
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(cfg=_round_config_strategy)
@settings(max_examples=200)
def test_config_hash_stability(cfg: RoundConfig) -> None:
    """P3.1r: config_hash(cfg) == config_hash(cfg) para qualquer RoundConfig válido."""
    h1 = config_hash(cfg)
    h2 = config_hash(cfg)
    assert h1 == h2


# ---------------------------------------------------------------------------
# P3.2r — Sensibilidade sobre RoundConfig real
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(cfg=_round_config_strategy, new_id=st.text(min_size=1, max_size=20))
@settings(max_examples=200)
def test_config_hash_sensitivity_round_id(cfg: RoundConfig, new_id: str) -> None:
    """P3.2r: Mudar round_id em um RoundConfig altera o hash."""
    assume(new_id != cfg.round_id)
    mutated = _make_round_config(
        round_id=new_id,
        temperature=cfg.temperature,
        seeds=list(cfg.seeds),
        llms=list(cfg.llms),
        bases=list(cfg.bases),
    )
    assert config_hash(cfg) != config_hash(mutated)


@pytest.mark.property
@given(
    cfg=_round_config_strategy, extra_seed=st.integers(min_value=1000, max_value=9999)
)
@settings(max_examples=200)
def test_config_hash_sensitivity_seeds(cfg: RoundConfig, extra_seed: int) -> None:
    """P3.2r: Adicionar seed à lista altera o hash."""
    assume(extra_seed not in cfg.seeds)
    mutated = _make_round_config(
        round_id=cfg.round_id,
        temperature=cfg.temperature,
        seeds=[*list(cfg.seeds), extra_seed],
        llms=list(cfg.llms),
        bases=list(cfg.bases),
    )
    assert config_hash(cfg) != config_hash(mutated)


# ---------------------------------------------------------------------------
# P3.3r — Cross-instance: mesmos dados → mesmo hash
# ---------------------------------------------------------------------------


@pytest.mark.property
@given(cfg=_round_config_strategy)
@settings(max_examples=200)
def test_config_hash_cross_instance_consistency(cfg: RoundConfig) -> None:
    """P3.3r: Duas RoundConfig com dados idênticos produzem o mesmo hash."""
    twin = _make_round_config(
        round_id=cfg.round_id,
        temperature=cfg.temperature,
        seeds=list(cfg.seeds),
        llms=list(cfg.llms),
        bases=list(cfg.bases),
    )
    assert config_hash(cfg) == config_hash(twin)


# ---------------------------------------------------------------------------
# Helper local — algoritmo canônico (nível 2: propriedades do algoritmo)
# ---------------------------------------------------------------------------


def _canonical_dict_hash(d: dict[str, object]) -> str:
    """Espelha o algoritmo de config_hash para dicts arbitrários.

    Permite verificar propriedades do algoritmo com entradas hypothesis
    irrestitas, sem a necessidade de construir RoundConfig válidos.
    Serve de regressão: se ``config_hash`` mudar a serialização canônica,
    este helper deve ser atualizado para acompanhar.
    """
    canonical = json.dumps(
        d,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_letter_chars = st.characters(whitelist_categories=("L",))
_simple_key = st.text(min_size=1, max_size=20, alphabet=_letter_chars)
_simple_value = st.one_of(
    st.text(max_size=50),
    st.integers(min_value=-10_000, max_value=10_000),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
)
_simple_config = st.dictionaries(
    keys=_simple_key,
    values=_simple_value,
    min_size=1,
    max_size=10,
)
_MUTATION_SENTINEL = "__mutated_sentinel_value_12345__"


@pytest.mark.property
@given(d=_simple_config)
@settings(max_examples=200)
def test_algorithm_stability(d: dict[str, object]) -> None:
    """P3.1: O algoritmo canônico é determinístico para o mesmo dict."""
    assert _canonical_dict_hash(d) == _canonical_dict_hash(d)


@pytest.mark.property
@given(d=_simple_config)
@settings(max_examples=200)
def test_algorithm_sensitivity(d: dict[str, object]) -> None:
    """P3.2: Mutar um campo altera o hash do algoritmo canônico."""
    key = next(iter(d))
    assume(d[key] != _MUTATION_SENTINEL)
    d_mutated = {**d, key: _MUTATION_SENTINEL}
    assume(
        json.dumps({key: d[key]}, sort_keys=True)
        != json.dumps({key: _MUTATION_SENTINEL}, sort_keys=True)
    )
    assert _canonical_dict_hash(d) != _canonical_dict_hash(d_mutated)


@pytest.mark.property
@given(d=_simple_config)
@settings(max_examples=200)
def test_algorithm_canonicality(d: dict[str, object]) -> None:
    """P3.3: Ordem das chaves não afeta o hash canônico (sort_keys=True)."""
    d_reversed = dict(reversed(list(d.items())))
    assert _canonical_dict_hash(d) == _canonical_dict_hash(d_reversed)


@pytest.mark.property
@given(d=_simple_config, items=st.data())
@settings(max_examples=200)
def test_algorithm_canonicality_shuffled(
    d: dict[str, object],
    items: st.DataObject,
) -> None:
    """P3.3 variante: permutação arbitrária das chaves → hash idêntico."""
    keys = list(d.keys())
    shuffled_keys = items.draw(st.permutations(keys))
    d_shuffled = {k: d[k] for k in shuffled_keys}
    assert _canonical_dict_hash(d) == _canonical_dict_hash(d_shuffled)
