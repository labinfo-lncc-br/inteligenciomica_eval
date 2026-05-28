"""Unit tests for PromptRegistry (TAREFA-015)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from inteligenciomica_eval.infrastructure.prompts.registry import (
    PromptRegistry,
    get_default_registry,
)

# ---------------------------------------------------------------------------
# Constantes de teste
# ---------------------------------------------------------------------------

_QUESTION = "Qual é o mecanismo de ação da penicilina?"
_GROUND_TRUTH = (
    "A penicilina inibe a síntese da parede celular bacteriana ao se ligar "
    "às proteínas de ligação à penicilina (PBPs), impedindo a transpeptidação."
)
_GENERATED = (
    "A penicilina age bloqueando as PBPs, enzimas responsáveis pela "
    "transpeptidação na síntese da parede celular."
)
_CONTEXTS = (
    "Betalactâmicos inibem transpeptidases da parede celular bacteriana.",
    "PBPs são enzimas-alvo dos antibióticos betalactâmicos.",
)

_SUBPROCESS_MODULE = (
    "inteligenciomica_eval.infrastructure.prompts.registry.subprocess.run"
)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def registry() -> PromptRegistry:
    """Instância fresca de PromptRegistry para cada teste."""
    return PromptRegistry()


# ---------------------------------------------------------------------------
# Renderização — conteúdo interpolado
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_render_biomed_rubric_includes_question(registry: PromptRegistry) -> None:
    rendered = registry.render_biomed_rubric(
        question=_QUESTION,
        ground_truth=_GROUND_TRUTH,
        generated_answer=_GENERATED,
        contexts=_CONTEXTS,
    )
    assert _QUESTION in rendered


@pytest.mark.unit
def test_render_biomed_rubric_includes_ground_truth(registry: PromptRegistry) -> None:
    rendered = registry.render_biomed_rubric(
        question=_QUESTION,
        ground_truth=_GROUND_TRUTH,
        generated_answer=_GENERATED,
        contexts=_CONTEXTS,
    )
    assert _GROUND_TRUTH in rendered


@pytest.mark.unit
def test_render_biomed_rubric_includes_generated_answer(
    registry: PromptRegistry,
) -> None:
    rendered = registry.render_biomed_rubric(
        question=_QUESTION,
        ground_truth=_GROUND_TRUTH,
        generated_answer=_GENERATED,
        contexts=_CONTEXTS,
    )
    assert _GENERATED in rendered


@pytest.mark.unit
def test_render_biomed_rubric_includes_all_contexts(registry: PromptRegistry) -> None:
    rendered = registry.render_biomed_rubric(
        question=_QUESTION,
        ground_truth=_GROUND_TRUTH,
        generated_answer=_GENERATED,
        contexts=_CONTEXTS,
    )
    for ctx in _CONTEXTS:
        assert ctx in rendered


# ---------------------------------------------------------------------------
# Renderização — seis critérios da §5.2
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_render_biomed_rubric_contains_criterio_correcao_factual(
    registry: PromptRegistry,
) -> None:
    rendered = registry.render_biomed_rubric(
        question=_QUESTION,
        ground_truth=_GROUND_TRUTH,
        generated_answer=_GENERATED,
        contexts=_CONTEXTS,
    )
    assert "CORREÇÃO FACTUAL" in rendered


@pytest.mark.unit
def test_render_biomed_rubric_contains_criterio_completude(
    registry: PromptRegistry,
) -> None:
    rendered = registry.render_biomed_rubric(
        question=_QUESTION,
        ground_truth=_GROUND_TRUTH,
        generated_answer=_GENERATED,
        contexts=_CONTEXTS,
    )
    assert "COMPLETUDE" in rendered


@pytest.mark.unit
def test_render_biomed_rubric_contains_criterio_contradicoes(
    registry: PromptRegistry,
) -> None:
    rendered = registry.render_biomed_rubric(
        question=_QUESTION,
        ground_truth=_GROUND_TRUTH,
        generated_answer=_GENERATED,
        contexts=_CONTEXTS,
    )
    assert "CONTRADIÇÕES" in rendered


@pytest.mark.unit
def test_render_biomed_rubric_contains_criterio_alucinacao(
    registry: PromptRegistry,
) -> None:
    rendered = registry.render_biomed_rubric(
        question=_QUESTION,
        ground_truth=_GROUND_TRUTH,
        generated_answer=_GENERATED,
        contexts=_CONTEXTS,
    )
    assert "ALUCINAÇÃO" in rendered


@pytest.mark.unit
def test_render_biomed_rubric_contains_criterio_ressalvas(
    registry: PromptRegistry,
) -> None:
    rendered = registry.render_biomed_rubric(
        question=_QUESTION,
        ground_truth=_GROUND_TRUTH,
        generated_answer=_GENERATED,
        contexts=_CONTEXTS,
    )
    assert "RESSALVAS" in rendered


@pytest.mark.unit
def test_render_biomed_rubric_contains_criterio_pertinencia_biomedica(
    registry: PromptRegistry,
) -> None:
    rendered = registry.render_biomed_rubric(
        question=_QUESTION,
        ground_truth=_GROUND_TRUTH,
        generated_answer=_GENERATED,
        contexts=_CONTEXTS,
    )
    assert "BIOMÉDICA" in rendered


# ---------------------------------------------------------------------------
# Renderização — saída JSON solicitada
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_render_biomed_rubric_requests_json_score_field(
    registry: PromptRegistry,
) -> None:
    rendered = registry.render_biomed_rubric(
        question=_QUESTION,
        ground_truth=_GROUND_TRUTH,
        generated_answer=_GENERATED,
        contexts=_CONTEXTS,
    )
    assert '"score"' in rendered


@pytest.mark.unit
def test_render_biomed_rubric_requests_json_feedback_field(
    registry: PromptRegistry,
) -> None:
    rendered = registry.render_biomed_rubric(
        question=_QUESTION,
        ground_truth=_GROUND_TRUTH,
        generated_answer=_GENERATED,
        contexts=_CONTEXTS,
    )
    assert '"feedback"' in rendered


# ---------------------------------------------------------------------------
# prompt_version — happy path e fallbacks
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_prompt_version_is_nonempty_string(registry: PromptRegistry) -> None:
    assert isinstance(registry.prompt_version, str)
    assert len(registry.prompt_version) > 0


@pytest.mark.unit
def test_prompt_version_fallback_unversioned_when_git_fails(
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocker.patch(
        _SUBPROCESS_MODULE,
        return_value=MagicMock(returncode=128, stdout=""),
    )
    monkeypatch.delenv("PROMPT_VERSION", raising=False)

    reg = PromptRegistry()
    assert reg.prompt_version == "unversioned"


@pytest.mark.unit
def test_prompt_version_uses_env_var_when_git_fails(
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mocker.patch(
        _SUBPROCESS_MODULE,
        return_value=MagicMock(returncode=128, stdout=""),
    )
    monkeypatch.setenv("PROMPT_VERSION", "v1.2.3-test")

    reg = PromptRegistry()
    assert reg.prompt_version == "v1.2.3-test"


@pytest.mark.unit
def test_prompt_version_fallback_unversioned_when_git_not_installed(
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FileNotFoundError (git não instalado) deve cair no fallback, não propagar."""
    mocker.patch(_SUBPROCESS_MODULE, side_effect=FileNotFoundError("git not found"))
    monkeypatch.delenv("PROMPT_VERSION", raising=False)

    reg = PromptRegistry()
    assert reg.prompt_version == "unversioned"


@pytest.mark.unit
def test_prompt_version_env_var_used_when_git_not_installed(
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FileNotFoundError (git ausente) → usa PROMPT_VERSION env var."""
    mocker.patch(_SUBPROCESS_MODULE, side_effect=FileNotFoundError("git not found"))
    monkeypatch.setenv("PROMPT_VERSION", "v2.0.0-ci")

    reg = PromptRegistry()
    assert reg.prompt_version == "v2.0.0-ci"


# ---------------------------------------------------------------------------
# get_default_registry — singleton
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_get_default_registry_returns_prompt_registry_instance() -> None:
    assert isinstance(get_default_registry(), PromptRegistry)


@pytest.mark.unit
def test_get_default_registry_is_cached() -> None:
    reg1 = get_default_registry()
    reg2 = get_default_registry()
    assert reg1 is reg2
