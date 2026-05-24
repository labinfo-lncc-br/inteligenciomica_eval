from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from inteligenciomica_eval.infrastructure.config.schema import RoundConfig


def config_hash(config: RoundConfig) -> str:
    """Compute a stable, canonical SHA-256 hash of a :class:`RoundConfig`.

    Normalisation strategy for hash stability:
    - ``model_dump(mode='json')`` converts all sub-models and special types
      (e.g. ``None``, ``bool``) to JSON-native Python equivalents.
    - ``json.dumps(sort_keys=True)`` guarantees stable key ordering at every
      nesting level, regardless of dict insertion order.
    - ``separators=(',', ':')`` removes optional whitespace so the canonical
      string is byte-for-byte identical across Python versions and locales.
    - ``ensure_ascii=True`` prevents encoding differences on systems with
      different locale settings.
    - The resulting UTF-8 bytes are hashed with SHA-256.

    Args:
        config: validated round configuration.

    Returns:
        64-character lowercase hexadecimal SHA-256 digest.
    """
    canonical = json.dumps(
        config.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _get_package_version(package: str) -> str:
    """Resolve a package version via importlib.metadata with env-var fallback.

    In M0 the heavy runtime packages (vllm, ragas) may not be installed in the
    development environment. Resolution order:
    1. ``importlib.metadata.version(package)`` — authoritative if installed.
    2. Env var ``{PACKAGE_NAME_UPPER}_VERSION`` (e.g. ``RAGAS_VERSION``) — for
       environments where the package is present at runtime but not in the dev
       virtualenv.
    3. ``'unknown'`` — placeholder; harmless for dry-run and CI.

    Args:
        package: package distribution name (e.g. ``'vllm'``, ``'ragas'``).

    Returns:
        Version string, or ``'unknown'`` if unresolvable.
    """
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        env_key = package.upper().replace("-", "_") + "_VERSION"
        return os.environ.get(env_key, "unknown")


@dataclass(frozen=True)
class ProvenanceInfo:
    """Config-level provenance collected once at run start (§12.2, ADR-009).

    This dataclass covers the *config-level* subset of §12.2 provenance — the
    fields that are known before any GPU call is made.  The remaining per-row
    fields (``batch_invariant``, ``prompt_version``, ``vllm`` per phase) are
    execution-level and will be set by the generator/judge adapters and the
    prompt-template loader (TAREFA-103, TAREFA-201) when they write each
    ``EvaluationResult``.

    Attributes:
        config_hash: SHA-256 of the canonical round config (see :func:`config_hash`).
        vllm_version: version of vLLM at evaluation time (placeholder in M0).
        ragas_version: version of RAGAS at evaluation time (placeholder in M0).
        collected_at: ISO-8601 UTC timestamp of when provenance was collected.
    """

    config_hash: str
    vllm_version: str
    ragas_version: str
    collected_at: str


def collect_provenance(config: RoundConfig) -> ProvenanceInfo:
    """Collect provenance metadata for a given round configuration.

    Args:
        config: validated round configuration.

    Returns:
        :class:`ProvenanceInfo` with config hash, library versions, and UTC timestamp.
    """
    return ProvenanceInfo(
        config_hash=config_hash(config),
        vllm_version=_get_package_version("vllm"),
        ragas_version=_get_package_version("ragas"),
        collected_at=datetime.now(UTC).isoformat(),
    )
