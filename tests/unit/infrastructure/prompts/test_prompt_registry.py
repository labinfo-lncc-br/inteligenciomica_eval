"""Unit tests for PromptRegistry (TAREFA-015 + TAREFA-316)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture

from inteligenciomica_eval.domain.ports import Chunk
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


# ---------------------------------------------------------------------------
# list_rag_versions (TAREFA-316)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_list_rag_versions_includes_v1_production(registry: PromptRegistry) -> None:
    versions = registry.list_rag_versions()
    assert "v1_production" in versions


@pytest.mark.unit
def test_list_rag_versions_returns_sorted_list(registry: PromptRegistry) -> None:
    versions = registry.list_rag_versions()
    assert versions == sorted(versions)


@pytest.mark.unit
def test_list_rag_versions_returns_list_of_strings(registry: PromptRegistry) -> None:
    versions = registry.list_rag_versions()
    assert isinstance(versions, list)
    assert all(isinstance(v, str) for v in versions)


# ---------------------------------------------------------------------------
# render_rag_generation (TAREFA-316)
# ---------------------------------------------------------------------------

_PMID_CHUNK_1 = Chunk(
    id="c1", text="BRCA1 mutations increase cancer risk.", score=0.95, source="38291047"
)
_PMID_CHUNK_2 = Chunk(
    id="c2", text="BRCA2 is also a tumor suppressor.", score=0.88, source="87654321"
)
_CHUNK_NO_SOURCE = Chunk(id="c3", text="Unknown origin text.", score=0.75, source="")


@pytest.mark.unit
def test_render_rag_generation_returns_tuple(registry: PromptRegistry) -> None:
    result = registry.render_rag_generation(
        version="v1_production",
        question="What is BRCA1?",
        contexts=[_PMID_CHUNK_1],
    )
    assert isinstance(result, tuple)
    assert len(result) == 2


@pytest.mark.unit
def test_render_rag_generation_system_is_nonempty(registry: PromptRegistry) -> None:
    system, _ = registry.render_rag_generation(
        version="v1_production",
        question="What is BRCA1?",
        contexts=[_PMID_CHUNK_1],
    )
    assert len(system) > 0


@pytest.mark.unit
def test_render_rag_generation_context_format_pmid(registry: PromptRegistry) -> None:
    """Context must be formatted as '[PMID:{source}] {text}' separated by '\\n\\n'."""
    _, user = registry.render_rag_generation(
        version="v1_production",
        question="Q?",
        contexts=[_PMID_CHUNK_1, _PMID_CHUNK_2],
    )
    assert "[PMID:38291047] BRCA1 mutations increase cancer risk." in user
    assert "[PMID:87654321] BRCA2 is also a tumor suppressor." in user
    # entries separated by double newline
    assert "\n\n" in user


@pytest.mark.unit
def test_render_rag_generation_pmid_format_no_space(registry: PromptRegistry) -> None:
    """Format is '[PMID:38291047]' — no space between 'PMID:' and number."""
    _, user = registry.render_rag_generation(
        version="v1_production",
        question="Q?",
        contexts=[_PMID_CHUNK_1],
    )
    assert "[PMID:38291047]" in user
    assert "[PMID: 38291047]" not in user


@pytest.mark.unit
def test_render_rag_generation_source_empty_uses_na(registry: PromptRegistry) -> None:
    """Empty source → 'N/A' in context (replica produção para chunks sem PMID)."""
    _, user = registry.render_rag_generation(
        version="v1_production",
        question="Q?",
        contexts=[_CHUNK_NO_SOURCE],
    )
    assert "[PMID:N/A]" in user


@pytest.mark.unit
def test_render_rag_generation_question_in_user(registry: PromptRegistry) -> None:
    _, user = registry.render_rag_generation(
        version="v1_production",
        question="What is BRCA1 exactly?",
        contexts=[_PMID_CHUNK_1],
    )
    assert "What is BRCA1 exactly?" in user


@pytest.mark.unit
def test_render_rag_generation_user_follows_production_wrapper(
    registry: PromptRegistry,
) -> None:
    """User message must follow _build_prompt_with_context format verbatim."""
    _, user = registry.render_rag_generation(
        version="v1_production",
        question="Test question",
        contexts=[_PMID_CHUNK_1],
    )
    assert "Context information is below." in user
    assert "---------------------" in user
    assert (
        "Given the context information and not prior knowledge, answer the query."
        in user
    )
    assert "Query: Test question" in user


@pytest.mark.unit
def test_render_rag_generation_unknown_version_raises(registry: PromptRegistry) -> None:
    """Non-existent bundle version must raise ValueError with list of available."""
    with pytest.raises(ValueError, match="v99_fake"):
        registry.render_rag_generation(
            version="v99_fake",
            question="Q?",
            contexts=[_PMID_CHUNK_1],
        )


@pytest.mark.unit
def test_render_rag_generation_unknown_version_lists_available(
    registry: PromptRegistry,
) -> None:
    """Error message must include available versions."""
    with pytest.raises(ValueError, match="v1_production"):
        registry.render_rag_generation(
            version="nonexistent_version",
            question="Q?",
            contexts=[_PMID_CHUNK_1],
        )


@pytest.mark.unit
def test_render_biomed_rubric_still_works_after_rag_changes(
    registry: PromptRegistry,
) -> None:
    """render_biomed_rubric must remain unaffected by the TAREFA-316 additions."""
    rendered = registry.render_biomed_rubric(
        question=_QUESTION,
        ground_truth=_GROUND_TRUTH,
        generated_answer=_GENERATED,
        contexts=_CONTEXTS,
    )
    assert _QUESTION in rendered
    assert "CORREÇÃO FACTUAL" in rendered
