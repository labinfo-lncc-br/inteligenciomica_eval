from __future__ import annotations

import pytest


@pytest.mark.unit
def test_all_submodules_are_importable() -> None:
    """Verify all package sub-namespaces are importable."""
    import inteligenciomica_eval
    import inteligenciomica_eval.application
    import inteligenciomica_eval.domain
    import inteligenciomica_eval.domain.errors
    import inteligenciomica_eval.domain.services
    import inteligenciomica_eval.infrastructure
    import inteligenciomica_eval.infrastructure.adapters
    import inteligenciomica_eval.infrastructure.config
    import inteligenciomica_eval.infrastructure.prompts
    import inteligenciomica_eval.infrastructure.repositories
    import inteligenciomica_eval.visualization

    assert inteligenciomica_eval.__version__ is not None
