from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated, Any

import pydantic
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from inteligenciomica_eval.domain.errors import ConfigValidationError

# Bases válidas para rodadas de avaliação (§12.1).
# Nota: o VO domain.BaseId também aceita "fixed", reservado ao Experimento B internamente.
# A round config usa um conjunto diferente e mais restrito; duplicar a lógica aqui é
# intencional para manter a fronteira do schema independente dos VOs de domínio.
_ALLOWED_BASES: frozenset[str] = frozenset({"IDx_400k", "ID_230K"})

# Fontes canônicas de contexto para o Experimento B (§12.1)
_ALLOWED_CANONICAL_SOURCES: frozenset[str] = frozenset({"IDx_400k", "expert_curated"})

# Env var names: uppercase letters/digits/underscores, starting with letter or underscore.
# ADR-008: o YAML referencia nomes de variáveis de ambiente, nunca valores literais.
_ENV_VAR_RE: re.Pattern[str] = re.compile(r"^[A-Z_][A-Z0-9_]*$")


class RetrievalConfig(BaseModel):
    """Configuração do subsistema de retrieval (§12.1)."""

    top_k: Annotated[int, Field(ge=1)]
    reranker: str | None = None
    embedding_model: str
    chunk_strategy: str


class JudgeConfig(BaseModel):
    """Configuração do modelo juiz (§12.1)."""

    model: str
    endpoint_env: str
    batch_invariant: bool
    temperature: Annotated[float, Field(ge=0.0)]

    @field_validator("endpoint_env")
    @classmethod
    def _validate_endpoint_env(cls, v: str) -> str:
        # ADR-008: the YAML must reference env var names (e.g. VLLM_JUDGE_URL),
        # never literal endpoint URLs. Enforced here so the constraint is
        # visible at the YAML boundary rather than only in documentation.
        if not _ENV_VAR_RE.match(v):
            raise ValueError(
                f"endpoint_env must be a valid env var name "
                f"(uppercase letters/digits/underscores, e.g. VLLM_JUDGE_URL), "
                f"got: {v!r}"
            )
        return v

    @field_validator("batch_invariant")
    @classmethod
    def _require_batch_invariant(cls, v: bool) -> bool:
        # Decision: RAISE ConfigValidationError (not just a warning).
        # Reason: ADR-003 mandates determinism for the judge. batch_invariant=False
        # allows the LLM runtime to reorganise batches, producing different scores
        # for the same input across runs, which breaks the reproducibility guarantee
        # of the evaluation framework. Failing fast at config load time is safer than
        # letting a non-deterministic run pollute the results.
        if not v:
            raise ValueError(
                "batch_invariant must be True (ADR-003): judge must be deterministic "
                "for reproducible evaluation. Set batch_invariant: true and temperature: 0."
            )
        return v


class ScoringConfig(BaseModel):
    """Configuração de ponderação de métricas e threshold de falha clínica (§12.1)."""

    weights: dict[str, float]
    failure_threshold: Annotated[float, Field(ge=0.0, le=1.0)]

    @field_validator("weights")
    @classmethod
    def _check_weights_sum(cls, v: dict[str, float]) -> dict[str, float]:
        if not v:
            raise ValueError("weights must not be empty")
        total = sum(v.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"weights sum to {total:.10f}, expected 1.0 (tolerance=1e-9). "
                "Adjust weights so they total exactly 1.0."
            )
        return v


class ExperimentBConfig(BaseModel):
    """Configuração específica do Experimento B — contexto canônico (§12.1, §5.3)."""

    canonical_context_source: str
    canonical_top_k: Annotated[int, Field(ge=1)]

    @field_validator("canonical_context_source")
    @classmethod
    def _validate_canonical_source(cls, v: str) -> str:
        if v not in _ALLOWED_CANONICAL_SOURCES:
            raise ValueError(
                f"canonical_context_source must be one of "
                f"{sorted(_ALLOWED_CANONICAL_SOURCES)!r}, got: {v!r}"
            )
        return v


class RoundConfig(BaseModel):
    """Configuração completa de uma rodada de avaliação (§12.1).

    Todos os campos são obrigatórios, exceto ``experiment_b`` (None se não houver fase B).
    """

    round_id: str
    phases: list[str]
    bases: list[str]
    llms: list[str]
    seeds: list[int]
    temperature: Annotated[float, Field(ge=0.0)]
    retrieval: RetrievalConfig
    judge: JudgeConfig
    scoring: ScoringConfig
    experiment_b: ExperimentBConfig | None = None

    @field_validator("phases")
    @classmethod
    def _validate_phases(cls, v: list[str]) -> list[str]:
        allowed = {"A", "B"}
        invalid = [p for p in v if p not in allowed]
        if invalid:
            raise ValueError(
                f"Invalid phase(s): {invalid!r}. Allowed values: {sorted(allowed)}"
            )
        return v

    @field_validator("bases")
    @classmethod
    def _validate_bases(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("bases must not be empty")
        unknown = [b for b in v if b not in _ALLOWED_BASES]
        if unknown:
            raise ValueError(
                f"Unknown base(s): {unknown!r}. "
                f"Allowed values: {sorted(_ALLOWED_BASES)}"
            )
        return v

    @field_validator("llms")
    @classmethod
    def _validate_llms(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("llms must not be empty")
        invalid = [llm for llm in v if not llm or " " in llm]
        if invalid:
            raise ValueError(
                f"LLM identifiers must be non-empty strings with no spaces: {invalid!r}"
            )
        return v

    @field_validator("seeds")
    @classmethod
    def _validate_seeds(cls, v: list[int]) -> list[int]:
        if not v:
            raise ValueError("seeds must not be empty")
        negative = [s for s in v if s < 0]
        if negative:
            raise ValueError(
                f"All seeds must be non-negative integers (>= 0), "
                f"got negative value(s): {negative!r}"
            )
        return v

    @model_validator(mode="after")
    def _experiment_b_required_for_phase_b(self) -> RoundConfig:
        if "B" in self.phases and self.experiment_b is None:
            raise ValueError(
                "experiment_b config is required when phase 'B' is listed in phases"
            )
        return self


def load_round_config(path: Path) -> RoundConfig:
    """Load and validate a round configuration from a YAML file.

    Converts any Pydantic validation error into a :class:`ConfigValidationError`
    pointing at the first failing field (fail-fast behaviour, §14.2).

    Args:
        path: filesystem path to the YAML round config file.

    Returns:
        Validated :class:`RoundConfig` instance.

    Raises:
        ConfigValidationError: if the YAML fails schema or rule validation.
        FileNotFoundError: if ``path`` does not exist.
    """
    # yaml.safe_load inherently returns Any; Pydantic validates immediately after.
    raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigValidationError("(root)", "YAML must be a mapping at top level")
    try:
        return RoundConfig.model_validate(raw)
    except pydantic.ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(loc) for loc in first["loc"])
        reason = first["msg"]
        raise ConfigValidationError(field, reason) from exc
