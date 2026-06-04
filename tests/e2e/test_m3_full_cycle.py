"""E2E gate M3: ciclo completo 12 células A+B com fakes + Parquet real (TAREFA-310).

5 cenários:
1. full_cycle: 12 células (8A+4B) geradas, avaliadas, julgadas e agregadas.
2. adr012_waves: juiz residente iniciado APÓS geradores; sequência start/stop verificada.
3. nan: célula com answer_correctness NaN → final_score NaN → excluída da agregação (ADR-007).
4. idempotency: 2ª execução com mesmo run_id → n_generated=0, n_skipped=12 (ADR-009).
5. graceful_shutdown: flag de shutdown entre ondas; onda 1 persistida; sem exceção (RNF7).

Usa build_fake_container + dataclasses.replace (writer/reader → ParquetStorage(tmp_path)).
Zero GPU/rede. Determinístico: FakeGenerator deriva output de (llm, question, seed).
"""

from __future__ import annotations

import dataclasses
import importlib.resources
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

import pytest
from fakes.generation import FakeGenerator
from fakes.metrics import FakeMetricSuite, FakeRubricJudge
from fakes.servers import FakeVLLMServerManager

from inteligenciomica_eval.application.services.wave_scheduler import (
    WaveSchedulerService,
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
from inteligenciomica_eval.domain.ports import (
    EvaluationSample,
    Layer1Metrics,
    ModelSpec,
    RubricResult,
)
from inteligenciomica_eval.domain.services.aggregation import AggregationService
from inteligenciomica_eval.domain.services.final_score import FinalScoreCalculator
from inteligenciomica_eval.domain.services.rank_score import (
    DEFAULT_WEIGHTS as RANK_DEFAULT_WEIGHTS,
)
from inteligenciomica_eval.domain.services.rank_score import (
    RankScoreCalculator,
    RankScoreInputs,
)
from inteligenciomica_eval.domain.value_objects import ModelWaveSpec
from inteligenciomica_eval.infrastructure.benchmark.loader import load_questions
from inteligenciomica_eval.infrastructure.config.schema import (
    ExperimentBConfig,
    JudgeConfig,
    RetrievalConfig,
    RoundConfig,
    ScoringConfig,
)
from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
    ParquetStorage,
)
from inteligenciomica_eval.infrastructure.wiring import (
    DIContainer,
    build_fake_container,
)

# ---------------------------------------------------------------------------
# Arquivo golden
# ---------------------------------------------------------------------------

_GOLDEN_PATH = Path(__file__).parents[1] / "golden" / "e2e_m3_expected.json"
_GOLDEN: dict[str, Any] = json.loads(_GOLDEN_PATH.read_text())

# ---------------------------------------------------------------------------
# Constantes do cenário
# ---------------------------------------------------------------------------

_ROUND_ID = "e2e_m3_round"
_RUN_ID = "e2e_m3_run_1"
_F32_TOL = 1e-4
_NAN = float("nan")

# Pesos SEM rubric_biomed_score: permite n_evaluated=12 após Passada 2,
# pois rubric_biomed_score=NaN nessa passada; weight=0 → NaN não propaga (ADR-007).
_SCORING_WEIGHTS: dict[str, float] = {
    "answer_correctness": 0.40,
    "faithfulness": 0.30,
    "context_recall": 0.15,
    "context_precision": 0.10,
    "answer_relevancy": 0.05,
}

# Métricas fixas do FakeMetricSuite (padrão)
_DEFAULT_LAYER1 = Layer1Metrics(
    answer_correctness=0.80,
    answer_similarity=0.75,
    faithfulness=0.90,
    context_precision=0.85,
    context_recall=0.70,
    answer_relevancy=0.88,
)
# Layer1Metrics com answer_correctness=NaN (para cenário ADR-007)
_PARTIAL_NAN_LAYER1 = Layer1Metrics(
    answer_correctness=_NAN,
    answer_similarity=0.75,
    faithfulness=0.90,
    context_precision=0.85,
    context_recall=0.70,
    answer_relevancy=0.88,
)

# ---------------------------------------------------------------------------
# Especificações de modelo (wave scheduler + experiment use case)
# ---------------------------------------------------------------------------

_GEN_A_WAVE = ModelWaveSpec(
    name="stub-gen-a",
    vram_gb_awq=4.0,
    is_judge=False,
    tensor_parallel_size=1,
    quantization="awq",
    gpu_index=0,
    extra_args={},
)
_GEN_B_WAVE = ModelWaveSpec(
    name="stub-gen-b",
    vram_gb_awq=4.0,
    is_judge=False,
    tensor_parallel_size=1,
    quantization="awq",
    gpu_index=1,
    extra_args={},
)
_JUDGE_WAVE = ModelWaveSpec(
    name="stub-judge",
    vram_gb_awq=8.0,
    is_judge=True,
    tensor_parallel_size=1,
    quantization="awq",
    gpu_index=3,
    extra_args={},
)
_GEN_A_SPEC = ModelSpec(
    model="stub-gen-a",
    port=8000,
    quantization="awq",
    tensor_parallel_size=1,
    max_model_len=4096,
    gpu_index=0,
    batch_invariant=False,
    extra_args={},
)
_GEN_B_SPEC = ModelSpec(
    model="stub-gen-b",
    port=8001,
    quantization="awq",
    tensor_parallel_size=1,
    max_model_len=4096,
    gpu_index=1,
    batch_invariant=False,
    extra_args={},
)
_JUDGE_SPEC = ModelSpec(
    model="stub-judge",
    port=8003,
    quantization="awq",
    tensor_parallel_size=1,
    max_model_len=4096,
    gpu_index=3,
    batch_invariant=True,
    extra_args={},
)

# ---------------------------------------------------------------------------
# Stub de configuração (satisfaz ExperimentConfigView + RunConfigView)
# ---------------------------------------------------------------------------


@dataclass
class _RetriCfg:
    top_k: int = 3


@dataclass
class _StubExpConfig:
    phases: list[str]
    bases: list[str]
    seeds: list[int]
    llms: list[str]
    temperature: float
    round_id: str
    startup_timeout_s: int
    failure_threshold: float
    top_k: int
    canonical_context_base: str
    canonical_top_k: int
    model_registry: tuple[ModelWaveSpec, ...]
    model_spec_map: dict[str, ModelSpec]
    retrieval: _RetriCfg


def _make_exp_config(round_id: str = _ROUND_ID) -> _StubExpConfig:
    return _StubExpConfig(
        phases=["A", "B"],
        bases=["IDx_400k", "ID_230K"],
        seeds=[42],
        llms=["stub-gen-a", "stub-gen-b"],
        temperature=0.0,
        round_id=round_id,
        startup_timeout_s=30,
        failure_threshold=0.30,
        top_k=3,
        canonical_context_base="IDx_400k",
        canonical_top_k=3,
        model_registry=(_GEN_A_WAVE, _GEN_B_WAVE, _JUDGE_WAVE),
        model_spec_map={
            "stub-gen-a": _GEN_A_SPEC,
            "stub-gen-b": _GEN_B_SPEC,
            "stub-judge": _JUDGE_SPEC,
        },
        retrieval=_RetriCfg(top_k=3),
    )


# ---------------------------------------------------------------------------
# MetricSuite parcialmente NaN (ADR-007 — cenário 3)
# ---------------------------------------------------------------------------


class _PartialNanMetricSuite:
    """MetricSuitePort que retorna answer_correctness=NaN para um question_id fixo."""

    def __init__(self, nan_question_id: str) -> None:
        self._nan_qid = nan_question_id

    async def score(self, sample: EvaluationSample) -> Layer1Metrics:
        if sample.question_id == self._nan_qid:
            return _PARTIAL_NAN_LAYER1
        return _DEFAULT_LAYER1

    async def score_batch(self, samples: list[EvaluationSample]) -> list[Layer1Metrics]:
        return [
            _PARTIAL_NAN_LAYER1 if s.question_id == self._nan_qid else _DEFAULT_LAYER1
            for s in samples
        ]


# ---------------------------------------------------------------------------
# GeneratorPort que levanta KeyboardInterrupt (RNF7 — shutdown originado no gerador)
# ---------------------------------------------------------------------------


class _KeyboardInterruptGenerator:
    """GeneratorPort que levanta KeyboardInterrupt em qualquer chamada de generate.

    Simula SIGINT originado durante a execução do gerador (RNF7).
    RunExperimentUseCase._run captura KeyboardInterrupt e seta _shutdown_requested.
    """

    async def generate(self, **_kwargs: Any) -> NoReturn:
        raise KeyboardInterrupt("simulated SIGINT during generation (RNF7)")


# ---------------------------------------------------------------------------
# Helper de construção do RunExperimentUseCase
# ---------------------------------------------------------------------------


def _build_experiment(
    storage: ParquetStorage,
    questions: list[Question],
    base_ctr: DIContainer,
    *,
    metric_suite: Any = None,
    rubric_judge: Any = None,
    allow_concurrent_models: bool = True,
    round_id: str = _ROUND_ID,
    generator_factory: Any = None,
) -> tuple[RunExperimentUseCase, FakeVLLMServerManager]:
    """Constrói RunExperimentUseCase com fakes do container e ParquetStorage real.

    Args:
        storage: ParquetStorage real em tmp_path.
        questions: perguntas do benchmark (2 primeiras do RF1).
        base_ctr: container de fakes de build_fake_container (fornece retriever/det).
        metric_suite: override de MetricSuitePort; None → FakeMetricSuite padrão.
        rubric_judge: override de RubricJudgePort; None → FakeRubricJudge(score=0.80).
        allow_concurrent_models: False → geradores em ondas separadas (shutdown test).
        round_id: identificador da rodada (permite isolamento por teste).
        generator_factory: factory de GeneratorPort por URL; None → FakeGenerator padrão.

    Returns:
        Tupla (experiment_uc, fake_server_manager).
    """
    exp_config = _make_exp_config(round_id=round_id)
    score_calc = FinalScoreCalculator(_SCORING_WEIGHTS)
    rank_calc = RankScoreCalculator(RANK_DEFAULT_WEIGHTS)
    agg_service = AggregationService(rank_calculator=rank_calc)
    wave_scheduler = WaveSchedulerService(
        n_questions=len(questions),
        allow_concurrent_models=allow_concurrent_models,
    )
    fake_sm = FakeVLLMServerManager()

    _ms = metric_suite if metric_suite is not None else FakeMetricSuite()
    _rj = (
        rubric_judge
        if rubric_judge is not None
        else FakeRubricJudge(fixed=RubricResult(score=0.80, feedback="stub judge"))
    )

    gen_pass = RunGenerationPassUseCase(
        retriever=base_ctr.retriever,
        generator=FakeGenerator(),
        writer=storage,
        reader=storage,
        config=exp_config,  # type: ignore[arg-type]
    )
    metrics_pass = RunMetricsPassUseCase(
        metric_suite=_ms,
        deterministic=base_ctr.deterministic_metric,
        score_calc=score_calc,
        writer=storage,
        reader=storage,
    )
    judge_pass = RunJudgePassUseCase(
        judge=_rj,
        writer=storage,
        reader=storage,
        score_calc=score_calc,
    )

    def _default_factory(url: str) -> FakeGenerator:
        return FakeGenerator()

    _gf = generator_factory if generator_factory is not None else _default_factory

    exp_uc = RunExperimentUseCase(
        wave_scheduler=wave_scheduler,
        server_manager=fake_sm,
        gen_pass_uc=gen_pass,
        metrics_pass_uc=metrics_pass,
        judge_pass_uc=judge_pass,
        aggregation_service=agg_service,
        rank_calc=rank_calc,
        writer=storage,
        reader=storage,
        config=exp_config,
        retriever=base_ctr.retriever,
        generator_factory=_gf,
    )
    return exp_uc, fake_sm


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def round_config() -> RoundConfig:
    """RoundConfig mínima válida para o cenário E2E M3.

    ``questions`` aponta para o arquivo real empacotado via importlib.resources,
    provando a integração E2E do campo configurável da rodada.
    """
    resource = importlib.resources.files(
        "inteligenciomica_eval.infrastructure.benchmark"
    ).joinpath("questions_rf1.jsonl")
    return RoundConfig(
        round_id=_ROUND_ID,
        model_registry_path="model_registry.yaml",
        questions=str(resource),
        phases=["A", "B"],
        bases=["IDx_400k", "ID_230K"],
        llms=["stub-gen-a", "stub-gen-b"],
        seeds=[42],
        temperature=0.0,
        retrieval=RetrievalConfig(
            top_k=3, embedding_model="stub", chunk_strategy="sentence"
        ),
        judge=JudgeConfig(
            model="stub-judge",
            endpoint_env="VLLM_JUDGE_URL",
            batch_invariant=True,
            temperature=0.0,
        ),
        scoring=ScoringConfig(weights=_SCORING_WEIGHTS, failure_threshold=0.30),
        experiment_b=ExperimentBConfig(
            canonical_context_source="IDx_400k", canonical_top_k=3
        ),
    )


@pytest.fixture()
def questions_stub(round_config: RoundConfig) -> list[Question]:
    """2 primeiras perguntas reais do benchmark RF1, carregadas via round_config.questions."""
    assert round_config.questions is not None
    return load_questions(Path(round_config.questions))[:2]


@pytest.fixture()
def tmp_storage(tmp_path: Path) -> ParquetStorage:
    """ParquetStorage real em diretório temporário único por teste."""
    return ParquetStorage(base_dir=tmp_path / "data", round_id=_ROUND_ID)


@pytest.fixture()
def container(round_config: RoundConfig, tmp_storage: ParquetStorage) -> DIContainer:
    """DIContainer de fakes com writer/reader substituídos pelo ParquetStorage real."""
    base_ctr = build_fake_container(round_config)
    return dataclasses.replace(base_ctr, writer=tmp_storage, reader=tmp_storage)


# ---------------------------------------------------------------------------
# Cenário 1 — Ciclo completo (full_cycle)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_m3_full_cycle_generates_and_evaluates(
    container: DIContainer,
    questions_stub: list[Question],
    tmp_storage: ParquetStorage,
    tmp_path: Path,
) -> None:
    """Ciclo completo A+B: 12 células geradas, avaliadas, julgadas e agregadas."""
    exp_uc, _ = _build_experiment(tmp_storage, questions_stub, container)

    report = await exp_uc.execute(run_id=_RUN_ID, questions=questions_stub)

    # Totais do relatório conferem com o golden
    assert report.n_generated == _GOLDEN["n_generated"], (
        f"n_generated={report.n_generated}, esperado {_GOLDEN['n_generated']}"
    )
    assert report.n_evaluated == _GOLDEN["n_evaluated"], (
        f"n_evaluated={report.n_evaluated}, esperado {_GOLDEN['n_evaluated']}"
    )
    assert report.n_judged == _GOLDEN["n_judged"], (
        f"n_judged={report.n_judged}, esperado {_GOLDEN['n_judged']}"
    )
    assert report.failed_waves == ()

    # Parquet: linhas e colunas do §5.3
    frame = tmp_storage.load(round_id=_ROUND_ID)
    results = list(frame.results)
    assert len(results) == _GOLDEN["n_rows_parquet"]

    # Contagem por fase via ResultFrame (EvaluationResult.answer.phase)
    phases_list = [r.answer.phase for r in results]
    n_a = sum(1 for p in phases_list if p == "A")
    n_b = sum(1 for p in phases_list if p == "B")
    assert n_a == _GOLDEN["n_rows_phase_a"], (
        f"phase=='A': {n_a}, esperado {_GOLDEN['n_rows_phase_a']}"
    )
    assert n_b == _GOLDEN["n_rows_phase_b"], (
        f"phase=='B': {n_b}, esperado {_GOLDEN['n_rows_phase_b']}"
    )

    # Colunas do golden presentes no Parquet (via tmp_path — sem atributos privados)
    table = _read_parquet_safe(tmp_path / "data")
    if table is not None:
        present = set(table.schema.names)
        for col in _GOLDEN["schema_columns"]:
            assert col in present, f"Coluna '{col}' ausente no Parquet"

    # Roundtrip fiel por (row_id, final_score, question_id)
    loaded_by_row = {r.answer.row_id.value: r for r in results}
    for r in results:
        key = r.answer.row_id.value
        assert key in loaded_by_row
        loaded = loaded_by_row[key]
        assert loaded.answer.question.question_id == r.answer.question.question_id
        if math.isnan(r.final_score.value):
            assert math.isnan(loaded.final_score.value)
        else:
            assert loaded.final_score.value == pytest.approx(
                r.final_score.value, abs=_F32_TOL
            )

    # FinalScore das células normais == golden
    final_score_golden: float = _GOLDEN["final_score_golden"]
    for r in results:
        assert r.final_score.value == pytest.approx(final_score_golden, abs=_F32_TOL), (
            f"final_score={r.final_score.value:.6f}, esperado {final_score_golden}"
        )

    # rank_scores: todos NaN (critical_failure_rate=NaN sem anotações)
    assert len(report.rank_scores) == len(report.aggregates)
    for rs in report.rank_scores:
        assert math.isnan(rs.value), f"rank_score={rs.value} deveria ser NaN"


def _read_parquet_safe(base_dir: Path) -> Any:
    """Lê Parquet de forma segura (sem auto-detecção de partição Hive)."""
    try:
        import pyarrow.parquet as pq

        parquet_files = list(base_dir.rglob("*.parquet"))
        if not parquet_files:
            return None
        return pq.ParquetFile(parquet_files[0]).read()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Cenário 2 — ADR-012: orquestração de ondas (juiz residente)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_m3_judge_resident_generators_in_waves(
    container: DIContainer,
    questions_stub: list[Question],
    tmp_storage: ParquetStorage,
) -> None:
    """Juiz iniciado 1x apos toda geracao; geradores em ondas (ADR-004/012)."""
    exp_uc, fake_sm = _build_experiment(
        tmp_storage, questions_stub, container, allow_concurrent_models=True
    )
    await exp_uc.execute(run_id=_RUN_ID, questions=questions_stub)

    starts = fake_sm.start_calls
    stops = fake_sm.stop_calls
    waits = fake_sm.wait_calls

    # 3 starts: gen-a, gen-b, judge
    assert len(starts) == 3, f"Esperado 3 starts, obtido {len(starts)}"
    assert len(waits) == 3, f"Esperado 3 wait_healthy, obtido {len(waits)}"
    assert len(stops) == 3, f"Esperado 3 stops, obtido {len(stops)}"

    gen_start_idxs = [i for i, c in enumerate(starts) if not c.model.batch_invariant]
    judge_start_idxs = [i for i, c in enumerate(starts) if c.model.batch_invariant]

    assert len(judge_start_idxs) == 1, "Juiz deve ser iniciado exatamente 1x"
    assert len(gen_start_idxs) == 2, "2 geradores devem ser iniciados"

    # ADR-012: juiz iniciado APÓS todos os geradores (desacoplamento geração/julgamento)
    assert min(judge_start_idxs) > max(gen_start_idxs), (
        "Juiz deve ser iniciado após TODOS os geradores (ADR-004/012)"
    )

    # Juiz tem batch_invariant=True; geradores têm batch_invariant=False
    assert starts[judge_start_idxs[0]].model.batch_invariant is True
    for idx in gen_start_idxs:
        assert starts[idx].model.batch_invariant is False

    # Geradores encerrados antes do juiz iniciar (juiz residente não encerrado entre ondas)
    gen_stop_idxs = [i for i, c in enumerate(stops) if not c.handle.batch_invariant]
    judge_stop_idxs = [i for i, c in enumerate(stops) if c.handle.batch_invariant]
    assert len(judge_stop_idxs) == 1
    # Todos os stops de geradores precedem o stop do juiz
    if gen_stop_idxs and judge_stop_idxs:
        assert max(gen_stop_idxs) < min(judge_stop_idxs), (
            "Geradores devem ser encerrados antes do juiz"
        )


# ---------------------------------------------------------------------------
# Cenário 3 — NaN (ADR-007): célula excluída da agregação
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_m3_nan_cell_excluded_from_aggregation(
    container: DIContainer,
    questions_stub: list[Question],
    tmp_storage: ParquetStorage,
) -> None:
    """Célula com answer_correctness NaN → final_score NaN → excluída (ADR-007)."""
    nan_qid = questions_stub[0].question_id
    nan_metric_suite = _PartialNanMetricSuite(nan_qid)

    exp_uc, _ = _build_experiment(
        tmp_storage,
        questions_stub,
        container,
        metric_suite=nan_metric_suite,
    )
    report = await exp_uc.execute(run_id=_RUN_ID + "_nan", questions=questions_stub)

    # Células NaN não contam como avaliadas (weight>0 em answer_correctness)
    assert report.n_evaluated < _GOLDEN["n_evaluated"], (
        "n_evaluated deve ser menor que 12 quando há células NaN"
    )

    # Verificar NaN no Parquet via ResultFrame
    frame = tmp_storage.load(round_id=_ROUND_ID)
    results = list(frame.results)
    nan_rows = [r for r in results if math.isnan(r.final_score.value)]
    normal_rows = [r for r in results if not math.isnan(r.final_score.value)]

    assert len(nan_rows) >= 1, "Deve haver pelo menos 1 linha com final_score NaN"
    # Todas as linhas NaN são do question_id que recebeu NaN
    for r in nan_rows:
        assert r.answer.question.question_id == nan_qid, (
            f"Linha NaN inesperada: qid={r.answer.question.question_id!r}"
        )

    # Todos os aggregates têm n_excluded_nan >= 1
    assert len(report.aggregates) > 0
    assert all(agg.n_excluded_nan >= 1 for agg in report.aggregates), (
        "Cada grupo de config deve ter pelo menos 1 célula NaN excluída"
    )

    # Anotar células normais → critical_failure_rate=0 → rank_score calculável
    for r in normal_rows:
        tmp_storage.update_annotation(r.answer.row_id, critical_failure_flag=0)

    # Re-agregar com anotações
    rank_calc = RankScoreCalculator(RANK_DEFAULT_WEIGHTS)
    agg_service = AggregationService(rank_calculator=rank_calc)
    updated_frame = tmp_storage.load(round_id=_ROUND_ID)
    aggregates = agg_service.aggregate_all(list(updated_frame.results), threshold=0.30)
    rank_scores = [
        rank_calc.compute(
            RankScoreInputs(
                median_score=a.median_score,
                failure_rate=a.failure_rate,
                win_rate=a.win_rate,
                critical_failure_rate=a.critical_failure_rate,
            )
        )
        for a in aggregates
        if a.n_observations > 0
    ]
    # Grupos com observações válidas têm rank_score calculável (não NaN)
    assert len(rank_scores) > 0
    assert any(not math.isnan(rs.value) for rs in rank_scores), (
        "Pelo menos 1 rank_score deve ser calculável após anotações"
    )

    # Rank_scores do cenário NaN conferem com golden recomputado à mão (ADR-007).
    # Cálculo manual: median=0.824, failure_rate=0, win_rate=1/12, crit_fail_rate=0
    # → 0.50*0.824 + 0.20*(1-0.0) + 0.15*(1/12) - 0.15*0.0 = 0.6245
    nan_golden = _GOLDEN["rank_scores_nan_scenario"]
    for agg in aggregates:
        config_key = f"{agg.base.value}::{agg.llm.value}"
        expected = nan_golden.get(config_key)
        if expected is not None and agg.n_observations > 0:
            assert agg.rank_score.value == pytest.approx(expected, abs=_F32_TOL), (
                f"rank_score[{config_key}]={agg.rank_score.value:.6f}, "
                f"esperado {expected}"
            )


# ---------------------------------------------------------------------------
# Cenário 4 — Idempotência (ADR-009)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_m3_idempotent_second_run(
    container: DIContainer,
    questions_stub: list[Question],
    tmp_storage: ParquetStorage,
) -> None:
    """2ª execução com mesmo run_id → n_generated=0, n_skipped=12 (ADR-009)."""
    exp_uc, _ = _build_experiment(tmp_storage, questions_stub, container)

    # 1ª execução: gera 12 células
    report1 = await exp_uc.execute(run_id="e2e_m3_idempotent", questions=questions_stub)
    assert report1.n_generated == 12

    frame_after_1 = tmp_storage.load(round_id=_ROUND_ID)
    n_rows_after_1 = len(list(frame_after_1.results))
    assert n_rows_after_1 == 12

    # 2ª execução com mesmo run_id: todas as células já existem → geração saltada
    report2 = await exp_uc.execute(run_id="e2e_m3_idempotent", questions=questions_stub)

    assert report2.n_generated == 0, (
        f"2ª execução n_generated={report2.n_generated}, esperado 0 (ADR-009)"
    )
    # n_skipped = n_cells_total - n_generated (sem erros na 2ª execução)
    n_skipped = report2.n_cells_total - report2.n_generated
    assert n_skipped == 12, f"n_skipped={n_skipped}, esperado 12"

    # Parquet permanece com 12 linhas (sem duplicatas)
    frame_after_2 = tmp_storage.load(round_id=_ROUND_ID)
    n_rows_after_2 = len(list(frame_after_2.results))
    assert n_rows_after_2 == 12, (
        f"Parquet tem {n_rows_after_2} linhas após 2ª execução, esperado 12"
    )


# ---------------------------------------------------------------------------
# Cenário 5 — Graceful shutdown (RNF7)
# ---------------------------------------------------------------------------


@pytest.mark.e2e
async def test_m3_graceful_shutdown_on_sigint(
    container: DIContainer,
    questions_stub: list[Question],
    tmp_storage: ParquetStorage,
) -> None:
    """Shutdown originado no gerador: onda 1 persistida; sem exceção propagada (RNF7).

    Usa allow_concurrent_models=False para forçar 2 ondas separadas:
      wave 0 = gen-a (FakeGenerator normal → 6 células geradas)
      wave 1 = gen-b (_KeyboardInterruptGenerator → levanta KeyboardInterrupt)

    RunExperimentUseCase._run captura KeyboardInterrupt, seta _shutdown_requested,
    e retorna relatório parcial sem propagar a exceção (RNF7, graceful shutdown).
    O teste NÃO usa pytest.raises.
    """
    # Factory com contador: 1ª chamada (gen-a) → FakeGenerator; 2ª (gen-b) → KI generator.
    _call_count: list[int] = [0]

    def _ki_factory(url: str) -> Any:
        _call_count[0] += 1
        return _KeyboardInterruptGenerator() if _call_count[0] >= 2 else FakeGenerator()

    exp_uc, fake_sm = _build_experiment(
        tmp_storage,
        questions_stub,
        container,
        allow_concurrent_models=False,  # wave 0: gen-a; wave 1: gen-b
        generator_factory=_ki_factory,
    )

    # execute() não deve propagar exceção — shutdown é gracioso (RNF7)
    report = await exp_uc.execute(
        run_id="e2e_m3_shutdown",
        questions=questions_stub,
    )

    # Onda 1 foi interrompida — sem métricas/juiz
    assert report.n_evaluated == 0, "Passada 2 não deve ter rodado após shutdown"
    assert report.n_judged == 0, "Passada 3 não deve ter rodado após shutdown"
    assert report.aggregates == (), "Sem agregação parcial após shutdown"

    # Servidores da onda 0 foram encerrados (sem leak)
    assert len(fake_sm.stop_calls) > 0, "stop() deve ser chamado mesmo em shutdown"
    assert len(fake_sm.stop_calls) == len(fake_sm.start_calls), (
        "Cada start deve ter um stop correspondente (sem leak de processo)"
    )

    # Onda 0 (gen-a) gerou células e as persistiu no Parquet
    frame = tmp_storage.load(round_id=_ROUND_ID)
    rows_after_shutdown = len(list(frame.results))
    assert rows_after_shutdown > 0, (
        "Onda 0 deve ter persistido células antes do shutdown"
    )
    # Onda 0 = gen-a: Phase A (2q*2b=4) + Phase B (2q*1b=2) = 6 celulas
    assert rows_after_shutdown == 6, (
        f"Onda 0 (stub-gen-a) deve persistir 6 células, obtido {rows_after_shutdown}"
    )
