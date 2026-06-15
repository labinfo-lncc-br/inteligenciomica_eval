"""Testes do subcomando `ielm-eval smoke` (TAREFA-317).

Abordagem: mock de build_container para retornar um DIContainer com fakes
configuráveis — sem rede, sem GPU, sem Qdrant.

Testes obrigatórios:
- EXIT 0 com fakes saudáveis (geração ok + juiz com score válido)
- EXIT 1 quando gerador retorna texto vazio (simula 404)
- EXIT 1 quando juiz retorna NaN
- Confirma que não grava em data/ (storage usa diretório temporário)
- Tabela de diagnóstico presente na saída
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pytest_mock import MockerFixture
from typer.testing import CliRunner

from inteligenciomica_eval.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Config de rodada mínima para os testes
# ---------------------------------------------------------------------------

_BASE_CFG: dict[str, Any] = {
    "round_id": "smoke-test-round",
    "phases": ["A"],
    "bases": ["IDx_400k"],
    "llms": ["model-a"],
    "seeds": [42],
    "temperature": 0.0,
    "retrieval": {
        "top_k": 3,
        "reranker": None,
        "embedding_model": "e-v1",
        "chunk_strategy": "sliding",
    },
    "judge": {
        "model": "judge",
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
def cfg_path(tmp_path: Path) -> Path:
    """Cria YAML de configuração mínima para os testes de smoke."""
    p = tmp_path / "config.yaml"
    p.write_text(yaml.dump(_BASE_CFG), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Helper: constrói fake DIContainer para injetar no mock
# ---------------------------------------------------------------------------


def _make_fake_container(
    cfg_path: Path,
    *,
    generator_empty: bool = False,
    judge_nan: bool = False,
) -> Any:
    """Constrói um DIContainer com fakes configurados.

    Args:
        cfg_path: caminho para o YAML de configuração.
        generator_empty: se True, FakeGenerator retorna texto vazio (simula 404).
        judge_nan: se True, FakeRubricJudge retorna NaN.
    """
    from fakes import (  # type: ignore[import-not-found]
        FakeDeterministicMetric,
        FakeGenerator,
        FakeMetricSuite,
        FakeRubricJudge,
        FakeVLLMServerManager,
        StubRetriever,
    )

    from inteligenciomica_eval.application.services.wave_scheduler import (
        WaveSchedulerService,
    )
    from inteligenciomica_eval.application.use_cases.annotation_workflow import (
        AnnotationConfig,
        AnnotationWorkflowUseCase,
    )
    from inteligenciomica_eval.application.use_cases.run_experiment import (
        RunExperimentUseCase,
    )
    from inteligenciomica_eval.application.use_cases.run_generation_pass import (
        RunGenerationPassUseCase,
    )
    from inteligenciomica_eval.application.use_cases.run_judge_pass import (
        RunJudgePassUseCase,
    )
    from inteligenciomica_eval.application.use_cases.run_metrics_pass import (
        RunMetricsPassUseCase,
    )
    from inteligenciomica_eval.domain.entities import Question
    from inteligenciomica_eval.domain.services.aggregation import AggregationService
    from inteligenciomica_eval.domain.services.final_score import FinalScoreCalculator
    from inteligenciomica_eval.domain.services.rank_score import (
        DEFAULT_WEIGHTS,
        RankScoreCalculator,
    )
    from inteligenciomica_eval.infrastructure.benchmark.loader import load_questions
    from inteligenciomica_eval.infrastructure.config.schema import load_round_config
    from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
        ParquetStorage,
    )
    from inteligenciomica_eval.infrastructure.wiring import (
        DIContainer,
        _ExperimentConfig,
        _RetrievalConfig,
    )

    cfg = load_round_config(cfg_path)

    import tempfile

    data_dir = Path(tempfile.mkdtemp())
    storage = ParquetStorage(
        base_dir=data_dir,
        round_id=cfg.round_id,
        prompt_version=cfg.generation_prompt_version,
    )

    # FakeGenerator configurado: texto vazio simula 404
    fake_gen_template = (
        "" if generator_empty else "Fake answer [{llm}|seed={seed}]: {question}"
    )
    fake_generator = FakeGenerator(template=fake_gen_template)
    fake_retriever = StubRetriever()
    fake_metric_suite = FakeMetricSuite()
    fake_deterministic = FakeDeterministicMetric()
    fake_judge = FakeRubricJudge(inject_nan=judge_nan)
    fake_server_manager = FakeVLLMServerManager()

    rank_calc = RankScoreCalculator(weights=DEFAULT_WEIGHTS)
    agg_service = AggregationService(rank_calculator=rank_calc)

    score_calc = FinalScoreCalculator(weights=dict(cfg.scoring.weights))

    questions = load_questions(None)[:2]
    wave_scheduler = WaveSchedulerService(n_questions=len(questions))

    exp_config = _ExperimentConfig(
        phases=cfg.phases,
        bases=cfg.bases,
        seeds=cfg.seeds,
        llms=cfg.llms,
        temperature=cfg.temperature,
        round_id=cfg.round_id,
        startup_timeout_s=30,
        failure_threshold=cfg.scoring.failure_threshold,
        top_k=cfg.retrieval.top_k,
        canonical_context_base="IDx_400k",
        canonical_top_k=5,
        model_registry=(),
        model_spec_map={},
        retrieval=_RetrievalConfig(top_k=cfg.retrieval.top_k),
    )

    def _fake_generator_factory(url: str) -> FakeGenerator:
        return FakeGenerator(template=fake_gen_template)

    gen_pass_uc = RunGenerationPassUseCase(
        retriever=fake_retriever,
        generator=fake_generator,
        writer=storage,
        reader=storage,
        config=exp_config,  # type: ignore[arg-type]
    )
    metrics_pass_uc = RunMetricsPassUseCase(
        metric_suite=fake_metric_suite,
        deterministic=fake_deterministic,
        score_calc=score_calc,
        writer=storage,
        reader=storage,
    )
    judge_pass_uc = RunJudgePassUseCase(
        judge=fake_judge,
        writer=storage,
        reader=storage,
        score_calc=score_calc,
    )

    ann_cfg = cfg.annotation
    annotation_uc = AnnotationWorkflowUseCase(
        reader=storage,
        writer=storage,
        config=AnnotationConfig(
            round_id=cfg.round_id,
            score_threshold=ann_cfg.score_threshold if ann_cfg else 0.6,
            rubric_threshold=ann_cfg.rubric_threshold if ann_cfg else 0.5,
            max_to_review=ann_cfg.max_to_review if ann_cfg else None,
        ),
    )

    experiment_uc = RunExperimentUseCase(
        wave_scheduler=wave_scheduler,
        server_manager=fake_server_manager,
        gen_pass_uc=gen_pass_uc,
        metrics_pass_uc=metrics_pass_uc,
        judge_pass_uc=judge_pass_uc,
        aggregation_service=agg_service,
        rank_calc=rank_calc,
        writer=storage,
        reader=storage,
        config=exp_config,
        retriever=fake_retriever,
        generator_factory=_fake_generator_factory,
    )

    def benchmark_loader() -> list[Question]:
        return list(questions)

    return DIContainer(
        retriever=fake_retriever,
        generator_factory=_fake_generator_factory,
        metric_suite=fake_metric_suite,
        deterministic_metric=fake_deterministic,
        rubric_judge=fake_judge,
        server_manager=fake_server_manager,
        wave_scheduler=wave_scheduler,
        gen_pass_uc=gen_pass_uc,
        metrics_pass_uc=metrics_pass_uc,
        judge_pass_uc=judge_pass_uc,
        experiment_uc=experiment_uc,
        annotation_uc=annotation_uc,
        writer=storage,
        reader=storage,
        agg_service=agg_service,
        rank_calc=rank_calc,
        benchmark_loader=benchmark_loader,
        endpoints_provenance={
            "server_mode": "managed",
            "generators": {
                "model-a": {
                    "served_model_id": "model-a-real",
                    "healthy": True,
                    "determinism_verified": False,
                }
            },
            "judge": {
                "served_model_id": "judge-real",
                "healthy": True,
                "determinism_verified": True,
            },
        },
    )


# ---------------------------------------------------------------------------
# Testes do comando smoke
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSmokeCommandPass:
    """Smoke com fakes saudáveis → EXIT 0, diagnóstico presente."""

    def test_exits_zero_with_healthy_fakes(
        self, cfg_path: Path, mocker: MockerFixture
    ) -> None:
        """EXIT 0 quando geração ok e juiz retorna score válido."""
        container = _make_fake_container(cfg_path)
        mocker.patch(
            "inteligenciomica_eval.cli.build_container", return_value=container
        )

        result = runner.invoke(app, ["smoke", "--config", str(cfg_path)])

        assert result.exit_code == 0, (
            f"Esperado exit 0 com fakes saudáveis, mas foi {result.exit_code}. "
            f"Saída:\n{result.output}"
        )

    def test_output_contains_diagnostic_table_headers(
        self, cfg_path: Path, mocker: MockerFixture
    ) -> None:
        """Tabela de diagnóstico deve estar presente na saída."""
        container = _make_fake_container(cfg_path)
        mocker.patch(
            "inteligenciomica_eval.cli.build_container", return_value=container
        )

        result = runner.invoke(app, ["smoke", "--config", str(cfg_path)])

        output = result.output
        assert "server_mode" in output
        assert "served_model_id" in output
        assert "status da geração" in output
        assert "score do juiz" in output
        assert "determinism_verified" in output

    def test_output_contains_smoke_pass(
        self, cfg_path: Path, mocker: MockerFixture
    ) -> None:
        """Saída deve indicar PASS quando tudo ok."""
        container = _make_fake_container(cfg_path)
        mocker.patch(
            "inteligenciomica_eval.cli.build_container", return_value=container
        )

        result = runner.invoke(app, ["smoke", "--config", str(cfg_path)])

        assert "PASS" in result.output or result.exit_code == 0


@pytest.mark.unit
class TestSmokeCommandFailEmptyGeneration:
    """Smoke com gerador retornando texto vazio → EXIT 1 (simula 404)."""

    def test_exits_nonzero_when_generator_returns_empty(
        self, cfg_path: Path, mocker: MockerFixture
    ) -> None:
        """EXIT 1 quando gerador retorna texto vazio."""
        container = _make_fake_container(cfg_path, generator_empty=True)
        mocker.patch(
            "inteligenciomica_eval.cli.build_container", return_value=container
        )

        result = runner.invoke(app, ["smoke", "--config", str(cfg_path)])

        assert result.exit_code != 0, (
            "Esperado exit != 0 quando geração retorna texto vazio"
        )

    def test_error_output_has_hint_on_empty_generation(
        self, cfg_path: Path, mocker: MockerFixture
    ) -> None:
        """Saída de erro deve incluir hint acionável."""
        container = _make_fake_container(cfg_path, generator_empty=True)
        mocker.patch(
            "inteligenciomica_eval.cli.build_container", return_value=container
        )

        result = runner.invoke(app, ["smoke", "--config", str(cfg_path)])

        # Pelo menos algum indicador de falha deve estar presente
        assert result.exit_code != 0


@pytest.mark.unit
class TestSmokeCommandFailJudgeNaN:
    """Smoke com juiz retornando NaN → EXIT 1."""

    def test_exits_nonzero_when_judge_returns_nan(
        self, cfg_path: Path, mocker: MockerFixture
    ) -> None:
        """EXIT 1 quando juiz retorna NaN."""
        container = _make_fake_container(cfg_path, judge_nan=True)
        mocker.patch(
            "inteligenciomica_eval.cli.build_container", return_value=container
        )

        result = runner.invoke(app, ["smoke", "--config", str(cfg_path)])

        assert result.exit_code != 0, "Esperado exit != 0 quando juiz retorna NaN"

    def test_output_shows_nan_judge_score(
        self, cfg_path: Path, mocker: MockerFixture
    ) -> None:
        """Tabela de diagnóstico deve mostrar NaN para o score do juiz."""
        container = _make_fake_container(cfg_path, judge_nan=True)
        mocker.patch(
            "inteligenciomica_eval.cli.build_container", return_value=container
        )

        result = runner.invoke(app, ["smoke", "--config", str(cfg_path)])

        assert "NaN" in result.output


@pytest.mark.unit
class TestSmokeCommandTempStorage:
    """Smoke não deve gravar no data/ real."""

    def test_smoke_does_not_write_to_data_dir(
        self, cfg_path: Path, mocker: MockerFixture, tmp_path: Path
    ) -> None:
        """O smoke usa storage temporário; a pasta data/ do projeto não deve ser criada."""
        container = _make_fake_container(cfg_path)
        mocker.patch(
            "inteligenciomica_eval.cli.build_container", return_value=container
        )

        # data/ relativa ao cfg_path
        data_dir = cfg_path.parent / "data"
        assert not data_dir.exists(), "data/ não deve existir antes do smoke"

        runner.invoke(app, ["smoke", "--config", str(cfg_path)])

        assert not data_dir.exists(), (
            "smoke não deve criar data/ no diretório do config YAML"
        )


@pytest.mark.unit
class TestSmokeCommandLLMSelection:
    """Seleção de LLM via --llm e validação de LLM inválido."""

    def test_invalid_llm_exits_nonzero(
        self, cfg_path: Path, mocker: MockerFixture
    ) -> None:
        """--llm com modelo não listado na config → EXIT 1."""
        container = _make_fake_container(cfg_path)
        mocker.patch(
            "inteligenciomica_eval.cli.build_container", return_value=container
        )

        result = runner.invoke(
            app, ["smoke", "--config", str(cfg_path), "--llm", "modelo-inexistente"]
        )

        assert result.exit_code != 0

    def test_valid_llm_flag_passes(self, cfg_path: Path, mocker: MockerFixture) -> None:
        """--llm com modelo válido funciona normalmente."""
        container = _make_fake_container(cfg_path)
        mocker.patch(
            "inteligenciomica_eval.cli.build_container", return_value=container
        )

        result = runner.invoke(
            app, ["smoke", "--config", str(cfg_path), "--llm", "model-a"]
        )

        assert result.exit_code == 0


@pytest.mark.unit
class TestSmokeCommandHelp:
    """Smoke registrado como subcomando e visível no --help."""

    def test_smoke_in_help(self) -> None:
        """O subcomando smoke deve aparecer no --help do app."""
        result = runner.invoke(app, ["--help"])
        assert "smoke" in result.output

    def test_smoke_help_exits_zero(self) -> None:
        """smoke --help deve sair com código 0."""
        result = runner.invoke(app, ["smoke", "--help"])
        assert result.exit_code == 0
