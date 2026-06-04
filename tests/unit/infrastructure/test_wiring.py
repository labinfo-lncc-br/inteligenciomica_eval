"""Testes unitários para DIContainer, build_container e build_fake_container (TAREFA-309)."""

from __future__ import annotations

import pytest
import yaml

from inteligenciomica_eval.domain.entities import Question
from inteligenciomica_eval.domain.errors import ConfigValidationError
from inteligenciomica_eval.infrastructure.config.schema import load_round_config
from inteligenciomica_eval.infrastructure.config.settings import RuntimeSettings
from inteligenciomica_eval.infrastructure.wiring import (
    DIContainer,
    build_container,
    build_fake_container,
)

# ---------------------------------------------------------------------------
# Fixture de RoundConfig mínima
# ---------------------------------------------------------------------------

_VALID_CONFIG_YAML = {
    "round_id": "wiring-test-round",
    "phases": ["A"],
    "bases": ["IDx_400k"],
    "llms": ["stub-gen-a"],
    "seeds": [42],
    "temperature": 0.0,
    "retrieval": {
        "top_k": 3,
        "reranker": None,
        "embedding_model": "embed-v1",
        "chunk_strategy": "sliding",
    },
    "judge": {
        "model": "judge-model",
        "endpoint_env": "VLLM_JUDGE_URL",
        "batch_invariant": True,
        "temperature": 0.0,
    },
    "scoring": {
        "weights": {"answer_correctness": 0.6, "faithfulness": 0.4},
        "failure_threshold": 0.3,
    },
}


@pytest.fixture()
def cfg_stub(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(_VALID_CONFIG_YAML), encoding="utf-8")
    return load_round_config(p)


# ---------------------------------------------------------------------------
# Testes de build_fake_container
# ---------------------------------------------------------------------------


class TestBuildFakeContainer:
    def test_constructs_without_error(self, cfg_stub) -> None:
        container = build_fake_container(cfg_stub)
        assert isinstance(container, DIContainer)

    def test_all_fields_present(self, cfg_stub) -> None:
        container = build_fake_container(cfg_stub)
        # Verifica que todos os campos obrigatórios estão preenchidos
        assert container.retriever is not None
        assert container.generator_factory is not None
        assert container.metric_suite is not None
        assert container.deterministic_metric is not None
        assert container.rubric_judge is not None
        assert container.server_manager is not None
        assert container.wave_scheduler is not None
        assert container.gen_pass_uc is not None
        assert container.metrics_pass_uc is not None
        assert container.judge_pass_uc is not None
        assert container.experiment_uc is not None
        assert container.annotation_uc is not None
        assert container.writer is not None
        assert container.reader is not None
        assert container.agg_service is not None
        assert container.rank_calc is not None
        assert container.benchmark_loader is not None

    def test_benchmark_loader_returns_questions(self, cfg_stub) -> None:
        container = build_fake_container(cfg_stub)
        questions = container.benchmark_loader()
        assert isinstance(questions, list)
        assert len(questions) >= 1
        for q in questions:
            assert isinstance(q, Question)

    def test_retriever_satisfies_protocol(self, cfg_stub) -> None:
        from inteligenciomica_eval.domain.ports import RetrieverPort

        container = build_fake_container(cfg_stub)
        assert isinstance(container.retriever, RetrieverPort)

    def test_metric_suite_satisfies_protocol(self, cfg_stub) -> None:
        from inteligenciomica_eval.domain.ports import MetricSuitePort

        container = build_fake_container(cfg_stub)
        assert isinstance(container.metric_suite, MetricSuitePort)

    def test_server_manager_satisfies_protocol(self, cfg_stub) -> None:
        from inteligenciomica_eval.domain.ports import VLLMServerManagerPort

        container = build_fake_container(cfg_stub)
        assert isinstance(container.server_manager, VLLMServerManagerPort)

    def test_writer_satisfies_protocol(self, cfg_stub) -> None:
        from inteligenciomica_eval.domain.ports import ResultWriterPort

        container = build_fake_container(cfg_stub)
        assert isinstance(container.writer, ResultWriterPort)

    def test_reader_satisfies_protocol(self, cfg_stub) -> None:
        from inteligenciomica_eval.domain.ports import ResultReaderPort

        container = build_fake_container(cfg_stub)
        assert isinstance(container.reader, ResultReaderPort)


# ---------------------------------------------------------------------------
# Testes de build_container — validação de env vars
# ---------------------------------------------------------------------------


class TestBuildContainerMissingEnvVars:
    def _settings_with(self, **overrides: str) -> RuntimeSettings:
        return RuntimeSettings(
            VLLM_GENERATOR_URL=overrides.get("VLLM_GENERATOR_URL", "<not set>"),
            VLLM_JUDGE_URL=overrides.get("VLLM_JUDGE_URL", "<not set>"),
            QDRANT_URL=overrides.get("QDRANT_URL", "<not set>"),
        )

    def test_missing_generator_url_raises(self, cfg_stub, tmp_path) -> None:
        settings = self._settings_with(
            VLLM_JUDGE_URL="http://judge:8001/v1",
            QDRANT_URL="http://qdrant:6333",
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            build_container(cfg_stub, settings)
        assert "VLLM_GENERATOR_URL" in str(exc_info.value)

    def test_missing_judge_url_raises(self, cfg_stub, tmp_path) -> None:
        settings = self._settings_with(
            VLLM_GENERATOR_URL="http://gen:8000/v1",
            QDRANT_URL="http://qdrant:6333",
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            build_container(cfg_stub, settings)
        assert "VLLM_JUDGE_URL" in str(exc_info.value)

    def test_missing_qdrant_url_raises(self, cfg_stub, tmp_path) -> None:
        settings = self._settings_with(
            VLLM_GENERATOR_URL="http://gen:8000/v1",
            VLLM_JUDGE_URL="http://judge:8001/v1",
        )
        with pytest.raises(ConfigValidationError) as exc_info:
            build_container(cfg_stub, settings)
        assert "QDRANT_URL" in str(exc_info.value)

    def test_all_missing_raises_first(self, cfg_stub, tmp_path) -> None:
        settings = self._settings_with()
        with pytest.raises(ConfigValidationError):
            build_container(cfg_stub, settings)


# ---------------------------------------------------------------------------
# Testes de lazy import de fakes
# ---------------------------------------------------------------------------


class TestNoFakesAtModuleLevel:
    def test_import_wiring_does_not_pull_fakes(self) -> None:
        # Garante que o código de nível de módulo de wiring.py não importa fakes.
        # Quando build_fake_container() faz `from fakes import X` *dentro* da função,
        # X fica no escopo local — nunca no namespace global do módulo wiring.
        # Nomes de classes de fakes no globals do módulo indicariam import eager.
        import inteligenciomica_eval.infrastructure.wiring as _wiring_mod

        eager_fakes = [
            name
            for name in vars(_wiring_mod)
            if name.startswith("Fake") or name.startswith("fake_")
        ]
        assert eager_fakes == [], (
            f"Fakes encontradas no namespace global de wiring: {eager_fakes}"
        )
