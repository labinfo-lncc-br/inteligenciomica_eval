"""Testes de regressão para _VLLMGeneratorFactory — resolução do nome do modelo (TAREFA-317).

Os testes FALHARIAM contra o código anterior à TAREFA-317 (que só usava layout por porta):
- URL de túnel com served_model_by_url → deve resolver pelo served_model_id (NÃO "model")
- URL no layout managed sem served_model_by_url → deve resolver por porta (ADR-012)
- URL desconhecida e sem served → fallback "model"
"""

from __future__ import annotations

import pytest

from inteligenciomica_eval.infrastructure.wiring import _VLLMGeneratorFactory


def _make_factory(
    port_to_model: dict[int, str] | None = None,
    served_model_by_url: dict[str, str] | None = None,
) -> _VLLMGeneratorFactory:
    """Constrói _VLLMGeneratorFactory com registry mínimo para testes."""
    from unittest.mock import MagicMock

    registry = MagicMock()
    registry.render_rag_generation.return_value = ("SYS", "USER")
    return _VLLMGeneratorFactory(
        port_to_model=port_to_model or {},
        prompt_registry=registry,
        prompt_version="v1_production",
        served_model_by_url=served_model_by_url,
    )


@pytest.mark.unit
class TestVLLMGeneratorFactoryModelResolution:
    """Regressões para a resolução do nome do modelo (TAREFA-317)."""

    def test_tunnel_url_with_served_model_uses_served_id(self) -> None:
        """URL de túnel (porta arbitrária 8010) COM served_model_by_url → served_model_id.

        Este teste FALHARIA contra o código anterior à TAREFA-317, que retornava "model"
        para portas não mapeadas em port_to_model.
        """
        tunnel_url = "http://localhost:8010/v1"
        served_name = "meta-llama/Llama-3-70b-awq"

        factory = _make_factory(
            port_to_model={8000: "gpt-oss-120b"},  # porta 8010 não mapeada
            served_model_by_url={tunnel_url: served_name},
        )
        adapter = factory(tunnel_url)

        assert adapter._model == served_name, (  # type: ignore[attr-defined]
            "URL de túnel com served_model_by_url deve usar o served_model_id, não 'model'"
        )

    def test_managed_url_without_served_uses_port_layout(self) -> None:
        """URL no layout managed (porta 8000+gpu_index) SEM served_model_by_url → nome do registry.

        Preserva comportamento ADR-012: não regride o modo managed.
        """
        managed_url = "http://localhost:8001/v1"  # porta 8001 = 8000 + gpu_index=1

        factory = _make_factory(
            port_to_model={8001: "gpt-oss-120b"},
            served_model_by_url=None,  # sem served → cai no layout por porta
        )
        adapter = factory(managed_url)

        assert adapter._model == "gpt-oss-120b", (  # type: ignore[attr-defined]
            "URL managed deve resolver pelo layout de porta (ADR-012)"
        )

    def test_unknown_url_without_served_falls_back_to_model(self) -> None:
        """URL desconhecida e sem served_model_by_url → fallback "model"."""
        unknown_url = "http://localhost:9999/v1"

        factory = _make_factory(
            port_to_model={8000: "gpt-oss-120b"},
            served_model_by_url=None,
        )
        adapter = factory(unknown_url)

        assert adapter._model == "model", (  # type: ignore[attr-defined]
            "URL desconhecida sem served_model_by_url deve usar o fallback 'model'"
        )

    def test_served_model_takes_precedence_over_port_layout(self) -> None:
        """served_model_by_url tem prioridade sobre port_to_model, mesmo em URL managed.

        Garante a precedência: (a) served_probe > (b) port_layout > (c) fallback.
        """
        url = "http://localhost:8000/v1"
        factory = _make_factory(
            port_to_model={8000: "nome-do-registry"},
            served_model_by_url={url: "nome-real-servido"},
        )
        adapter = factory(url)

        assert adapter._model == "nome-real-servido"  # type: ignore[attr-defined]

    def test_empty_served_entry_falls_back_to_port_layout(self) -> None:
        """served_model_by_url com string vazia é tratado como ausente → cai no port_layout."""
        url = "http://localhost:8000/v1"
        factory = _make_factory(
            port_to_model={8000: "gpt-oss-120b"},
            served_model_by_url={url: ""},  # vazio = não sondado
        )
        adapter = factory(url)

        assert adapter._model == "gpt-oss-120b"  # type: ignore[attr-defined]

    def test_malformed_url_without_served_falls_back(self) -> None:
        """URL sem porta parsável e sem served_model_by_url → fallback "model"."""
        malformed_url = "unix:///var/run/vllm.sock"

        factory = _make_factory(port_to_model={8000: "gpt-oss-120b"})
        adapter = factory(malformed_url)

        assert adapter._model == "model"  # type: ignore[attr-defined]

    def test_none_served_model_by_url_equivalent_to_empty_dict(self) -> None:
        """Passar None é equivalente a não passar served_model_by_url (sem quebra)."""
        url = "http://localhost:8002/v1"
        factory = _make_factory(
            port_to_model={8002: "model-a"},
            served_model_by_url=None,
        )
        adapter = factory(url)

        assert adapter._model == "model-a"  # type: ignore[attr-defined]
