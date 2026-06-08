"""Testes de regressão do contrato de benchmark — TAREFA-313.

Prova as 3 origens de perguntas no wiring (build_container) e no dry-run do CLI:
  (a) env BENCHMARK_QUESTIONS_PATH → override de máxima prioridade
  (b) config.questions → path relativo ao YAML, quando env não definida
  (c) default empacotado → quando nenhum dos dois definido

Cada teste falharia ANTES desta tarefa porque RoundConfig.questions era campo morto.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from inteligenciomica_eval.domain.entities import Question
from inteligenciomica_eval.infrastructure.config.schema import load_round_config
from inteligenciomica_eval.infrastructure.config.settings import RuntimeSettings
from inteligenciomica_eval.infrastructure.wiring import build_container

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_CONFIG: dict[str, Any] = {
    "round_id": "q313-test",
    "phases": ["A"],
    "bases": ["IDx_400k"],
    "llms": ["stub-llm"],
    "seeds": [42],
    "temperature": 0.0,
    "retrieval": {
        "top_k": 3,
        "reranker": None,
        "embedding_model": "embed-v1",
        "chunk_strategy": "sliding",
    },
    "judge": {
        "model": "stub-judge",
        "endpoint_env": "VLLM_JUDGE_URL",
        "batch_invariant": True,
        "temperature": 0.0,
    },
    "scoring": {
        "weights": {"answer_correctness": 0.6, "faithfulness": 0.4},
        "failure_threshold": 0.3,
    },
}

_REGISTRY_YAML: dict[str, Any] = {
    "models": [
        {
            "name": "stub-llm",
            "hf_repo": "org/stub-llm",
            "vram_gb_fp16": 16.0,
            "vram_gb_awq": 8.0,
            "quantization": "awq",
            "tensor_parallel_size": 1,
            "gpu_index": 0,
            "is_judge": False,
            "batch_invariant": False,
        },
        {
            "name": "stub-judge",
            "hf_repo": "org/stub-judge",
            "vram_gb_fp16": 14.0,
            "vram_gb_awq": 7.0,
            "quantization": "awq",
            "tensor_parallel_size": 1,
            "gpu_index": 1,
            "is_judge": True,
            "batch_invariant": True,
        },
    ],
    "gpu_slots": [
        {"gpu_index": 0, "vram_gb": 40.0, "reserved_gb": 4.0},
        {"gpu_index": 1, "vram_gb": 40.0, "reserved_gb": 4.0},
    ],
}

_SETTINGS = RuntimeSettings(
    VLLM_GENERATOR_URL="http://gen:8000/v1",
    VLLM_JUDGE_URL="http://judge:8001/v1",
    QDRANT_URL="http://qdrant:6333",
    BENCHMARK_QUESTIONS_PATH="",
)


def _write_jsonl(path: Path, questions: list[dict[str, str]]) -> None:
    lines = [json.dumps(q, ensure_ascii=False) for q in questions]
    path.write_text("\n".join(lines), encoding="utf-8")


def _make_questions(n: int, prefix: str = "q") -> list[dict[str, str]]:
    return [
        {
            "question_id": f"{prefix}{i:03d}",
            "text": f"Pergunta {i}?",
            "ground_truth": f"Resposta {i}.",
        }
        for i in range(1, n + 1)
    ]


def _build(tmp_path: Path, config_data: dict[str, Any]) -> Any:
    """Monta registry + config YAML e chama build_container com mocks de rede."""
    registry_path = tmp_path / "model_registry.yaml"
    registry_path.write_text(yaml.dump(_REGISTRY_YAML), encoding="utf-8")

    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(config_data), encoding="utf-8")

    cfg = load_round_config(config_path)
    return cfg, tmp_path


# ---------------------------------------------------------------------------
# Fixtures de patch compartilhados
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_heavy(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Evita chamadas de rede e downloads de modelos HuggingFace durante os testes."""
    with (
        patch(
            "inteligenciomica_eval.infrastructure.adapters.ragas_metrics._build_embeddings",
            return_value=(MagicMock(), "hf_local"),
        ),
        patch(
            "inteligenciomica_eval.infrastructure.wiring._run_endpoint_probes",
            return_value=({}, False, {}),
        ),
    ):
        yield


# ---------------------------------------------------------------------------
# Testes das 3 origens
# ---------------------------------------------------------------------------


class TestQuestionsSource:
    def test_source_b_round_config_field_loads_relative_path(
        self, tmp_path: Path
    ) -> None:
        """Campo config.questions (b) é lido e resolvido relativo ao diretório do YAML.

        Esse teste falhava ANTES da TAREFA-313 porque RoundConfig.questions era campo morto.
        """
        q_file = tmp_path / "my_bench.jsonl"
        _write_jsonl(q_file, _make_questions(5, prefix="b"))

        config_data = dict(_BASE_CONFIG)
        config_data["questions"] = "my_bench.jsonl"  # relativo ao YAML

        cfg, config_dir = _build(tmp_path, config_data)
        container = build_container(cfg, _SETTINGS, config_dir=config_dir)

        questions = container.benchmark_loader()
        assert isinstance(questions, list)
        assert len(questions) == 5
        assert all(isinstance(q, Question) for q in questions)
        assert questions[0].question_id == "b001"
        assert questions[4].question_id == "b005"

    def test_source_a_env_overrides_round_config(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Env BENCHMARK_QUESTIONS_PATH (a) vence sobre config.questions (b).

        Garante que a precedência é honrada: se a env estiver definida, o campo
        config.questions é ignorado — mesmo que aponte para um arquivo válido.
        """
        # Arquivo referenciado pelo campo do YAML (2 perguntas)
        q_yaml_file = tmp_path / "yaml_bench.jsonl"
        _write_jsonl(q_yaml_file, _make_questions(2, prefix="yaml"))

        # Arquivo referenciado pela env (7 perguntas) — deve ganhar
        q_env_file = tmp_path / "env_bench.jsonl"
        _write_jsonl(q_env_file, _make_questions(7, prefix="env"))

        config_data = dict(_BASE_CONFIG)
        config_data["questions"] = "yaml_bench.jsonl"

        cfg, config_dir = _build(tmp_path, config_data)

        settings_with_env = RuntimeSettings(
            VLLM_GENERATOR_URL="http://gen:8000/v1",
            VLLM_JUDGE_URL="http://judge:8001/v1",
            QDRANT_URL="http://qdrant:6333",
            BENCHMARK_QUESTIONS_PATH=str(q_env_file),
        )
        container = build_container(cfg, settings_with_env, config_dir=config_dir)

        questions = container.benchmark_loader()
        assert len(questions) == 7, (
            "Env BENCHMARK_QUESTIONS_PATH deve ter precedência sobre config.questions"
        )
        assert questions[0].question_id == "env001"

    def test_source_c_packaged_default_when_neither_set(self, tmp_path: Path) -> None:
        """Default empacotado (c) é usado quando env e config.questions estão ausentes.

        O arquivo empacotado questions_rf1.jsonl contém 3 perguntas (placeholder RF1).
        """
        config_data = dict(_BASE_CONFIG)
        # Sem campo "questions" no config

        cfg, config_dir = _build(tmp_path, config_data)
        # _SETTINGS tem BENCHMARK_QUESTIONS_PATH="" (não definida)
        container = build_container(cfg, _SETTINGS, config_dir=config_dir)

        questions = container.benchmark_loader()
        assert len(questions) == 3, (
            "Sem env nem config.questions, deve carregar o default empacotado (3 questões RF1)"
        )
        assert all(isinstance(q, Question) for q in questions)

    def test_source_b_path_resolves_relative_to_yaml_not_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """config.questions resolve relativo ao YAML, não ao cwd (I1 corrigido).

        Cria o arquivo de perguntas em subdiretório e muda o cwd para outro lugar —
        o wiring deve encontrar o arquivo via config_dir, não via cwd.
        """
        # Subdir que será o diretório do YAML
        yaml_dir = tmp_path / "round_configs"
        yaml_dir.mkdir()
        q_file = yaml_dir / "bench.jsonl"
        _write_jsonl(q_file, _make_questions(4, prefix="rel"))

        # Muda cwd para um diretório diferente do YAML — o arquivo NÃO existiria via cwd
        other_dir = tmp_path / "other"
        other_dir.mkdir()
        monkeypatch.chdir(other_dir)

        config_data = dict(_BASE_CONFIG)
        config_data["questions"] = "bench.jsonl"  # relativo ao YAML dir (yaml_dir)

        registry_path = yaml_dir / "model_registry.yaml"
        registry_path.write_text(yaml.dump(_REGISTRY_YAML), encoding="utf-8")
        config_path = yaml_dir / "config.yaml"
        config_path.write_text(yaml.dump(config_data), encoding="utf-8")

        cfg = load_round_config(config_path)
        # config_dir = yaml_dir; cwd = other_dir → só resolve se usa config_dir
        container = build_container(cfg, _SETTINGS, config_dir=yaml_dir)

        questions = container.benchmark_loader()
        assert len(questions) == 4
        assert questions[0].question_id == "rel001"


# ---------------------------------------------------------------------------
# Teste do dry-run CLI (fonte consistente com o wiring real)
# ---------------------------------------------------------------------------


class TestDryRunQuestionsConsistency:
    def test_dry_run_fallback_uses_round_config_field(self, tmp_path: Path) -> None:
        """Fallback do --dry-run usa config.questions (b) quando fakes indisponíveis.

        O fallback em _run_dry_run é acionado quando build_fake_container levanta
        ImportError (fakes fora do sys.path). ANTES da TAREFA-313, o fallback usava
        apenas BENCHMARK_QUESTIONS_PATH — ignorava config.questions. Esta verificação
        confirma que a precedência correta é honrada.

        Estratégia: patcha build_fake_container para lançar ImportError (simula ambiente
        de produção sem tests/ no PYTHONPATH), observa que o dry-run exibe 9 perguntas
        provenientes de config.questions.
        """
        from typer.testing import CliRunner

        from inteligenciomica_eval.cli import app

        # 9 perguntas no arquivo referenciado pelo campo do YAML
        q_file = tmp_path / "dry_bench.jsonl"
        _write_jsonl(q_file, _make_questions(9, prefix="dr"))

        config_data = dict(_BASE_CONFIG)
        config_data["questions"] = "dry_bench.jsonl"

        registry_path = tmp_path / "model_registry.yaml"
        registry_path.write_text(yaml.dump(_REGISTRY_YAML), encoding="utf-8")
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump(config_data), encoding="utf-8")

        runner = CliRunner()
        # Faz build_fake_container lançar ImportError: simula ambiente sem fakes
        # A chamada _bfc(cfg) no CLI lança ImportError → aciona o fallback
        with patch(
            "inteligenciomica_eval.infrastructure.wiring.build_fake_container",
            side_effect=ImportError("fakes module not available in production"),
        ):
            result = runner.invoke(
                app,
                ["run", "--dry-run", "--config", str(config_path)],
                catch_exceptions=False,
            )

        assert result.exit_code == 0, result.output
        # Fallback com precedência correta: env não definida → config.questions → 9 perguntas
        assert "Perguntas carregadas: 9" in result.output, (
            f"Esperava 9 perguntas no dry-run (via fallback config.questions). "
            f"Output:\n{result.output}"
        )
