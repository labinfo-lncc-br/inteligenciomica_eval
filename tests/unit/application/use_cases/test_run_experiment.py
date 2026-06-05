"""Testes unitários para RunExperimentUseCase (TAREFA-307, camada application).

Critérios de aceitação verificados:
- ServerStartTimeoutError em uma onda NÃO aborta a rodada; onda registrada em
  failed_waves; demais ondas executam.
- Shutdown gracioso: flag _shutdown_requested interrompe o loop ENTRE ondas;
  servidores encerrados em finally.
- Servidor juiz iniciado APÓS toda geração — verificado via sequência de chamadas
  ao server_manager mock (batch_invariant=True só aparece no último start_call).
- ExperimentReport contém aggregates + rank_scores calculados (golden).
- canonical_contexts construídos via retriever para todas as perguntas antes da
  Passada 1 quando "B" está em phases.
- GeneratorFactory invocada com URL do handle ativo antes de cada gen_pass_uc.execute.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from fakes import FakeVLLMServerManager, StubRetriever
from fakes.storage import (
    InMemoryResultReader,
    InMemoryResultStore,
    InMemoryResultWriter,
)

from inteligenciomica_eval.application.services.wave_scheduler import (
    Wave,
    WavePlan,
    WaveSchedulerService,
)
from inteligenciomica_eval.application.use_cases.run_experiment import (
    ExperimentReport,
    RunExperimentUseCase,
    _single_model_wave_plan,
)
from inteligenciomica_eval.application.use_cases.run_generation_pass import (
    GenerationPassReport,
)
from inteligenciomica_eval.application.use_cases.run_judge_pass import (
    JudgePassReport,
)
from inteligenciomica_eval.application.use_cases.run_metrics_pass import (
    MetricsPassReport,
)
from inteligenciomica_eval.domain.entities import Question
from inteligenciomica_eval.domain.errors import ServerStartTimeoutError
from inteligenciomica_eval.domain.ports import (
    Chunk,
    ModelSpec,
    ServerHandle,
)
from inteligenciomica_eval.domain.services.aggregation import (
    ConfigAggregate,
)
from inteligenciomica_eval.domain.services.rank_score import (
    DEFAULT_WEIGHTS,
    RankScoreCalculator,
    RankScoreInputs,
)
from inteligenciomica_eval.domain.value_objects import (
    BaseId,
    LLMId,
    ModelWaveSpec,
    RankScore,
)

# ---------------------------------------------------------------------------
# Constantes de teste
# ---------------------------------------------------------------------------

_RUN_ID = "run-exp-001"
_ROUND_ID = "round_exp_1"

_Q1 = Question(question_id="q1", text="O que é RAG?", ground_truth="Resp 1.")
_Q2 = Question(question_id="q2", text="O que é BERT?", ground_truth="Resp 2.")
_QUESTIONS = [_Q1, _Q2]

_GEN_MODEL = "gen-llm/v1"
_JUDGE_MODEL = "judge-llm/v1"

_GEN_WAVE_SPEC = ModelWaveSpec(
    name=_GEN_MODEL,
    vram_gb_awq=10.0,
    is_judge=False,
    tensor_parallel_size=1,
    quantization="awq",
    gpu_index=0,
    extra_args={},
)
_JUDGE_WAVE_SPEC = ModelWaveSpec(
    name=_JUDGE_MODEL,
    vram_gb_awq=8.0,
    is_judge=True,
    tensor_parallel_size=1,
    quantization="awq",
    gpu_index=3,
    extra_args={},
)

_GEN_SPEC = ModelSpec(
    model=_GEN_MODEL,
    port=8000,
    quantization="awq",
    tensor_parallel_size=1,
    max_model_len=4096,
    gpu_index=0,
    batch_invariant=False,
    extra_args={},
)
_JUDGE_SPEC = ModelSpec(
    model=_JUDGE_MODEL,
    port=8001,
    quantization="awq",
    tensor_parallel_size=1,
    max_model_len=4096,
    gpu_index=3,
    batch_invariant=True,
    extra_args={},
)


# ---------------------------------------------------------------------------
# Stubs de configuração
# ---------------------------------------------------------------------------


@dataclass
class _Config:
    phases: list[str] = field(default_factory=lambda: ["A"])
    bases: list[str] = field(default_factory=lambda: ["IDx_400k"])
    seeds: list[int] = field(default_factory=lambda: [42])
    llms: list[str] = field(default_factory=lambda: [_GEN_MODEL])
    temperature: float = 0.0
    round_id: str = _ROUND_ID
    startup_timeout_s: int = 120
    failure_threshold: float = 0.70
    top_k: int = 3
    canonical_context_base: str = "IDx_400k"
    canonical_top_k: int = 5
    model_registry: tuple[ModelWaveSpec, ...] = field(
        default_factory=lambda: (_GEN_WAVE_SPEC, _JUDGE_WAVE_SPEC)
    )
    model_spec_map: dict[str, ModelSpec] = field(
        default_factory=lambda: {_GEN_MODEL: _GEN_SPEC, _JUDGE_MODEL: _JUDGE_SPEC}
    )
    # Proveniência (TAREFA-311, ADR-014)
    server_mode: str = "managed"
    config_hash: str = "abcd1234" * 8  # 64-char dummy SHA-256
    endpoints_provenance: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Stubs de use cases de passada
# ---------------------------------------------------------------------------


@dataclass
class _GenPassStub:
    """Stub de RunGenerationPassUseCase — registra chamadas, suporta troca de _generator."""

    execute_calls: list[dict[str, Any]] = field(default_factory=list)
    n_generated_per_call: int = 1
    _generator: object = (
        None  # atribuído por RunExperimentUseCase._gen_pass_uc._generator
    )

    async def execute(
        self,
        *,
        run_id: str,
        wave_plan: WavePlan,
        questions: Sequence[Question],
        canonical_contexts: dict[str, list[Chunk]] | None = None,
    ) -> GenerationPassReport:
        self.execute_calls.append(
            {
                "run_id": run_id,
                "wave_plan": wave_plan,
                "n_questions": len(questions),
                "canonical_contexts": canonical_contexts,
                "generator_url": getattr(self._generator, "url", None),
            }
        )
        return GenerationPassReport(
            run_id=run_id,
            wave_plan=wave_plan,
            n_generated=self.n_generated_per_call,
            n_skipped=0,
            n_errors=0,
            duration_s=0.0,
            failed_cells=(),
        )


@dataclass
class _MetricsPassStub:
    """Stub de RunMetricsPassUseCase."""

    n_evaluated: int = 2

    async def execute(
        self,
        *,
        run_id: str,
        round_id: str,
        phase: str | None = None,
    ) -> MetricsPassReport:
        return MetricsPassReport(
            run_id=run_id,
            round_id=round_id,
            n_evaluated=self.n_evaluated,
            n_skipped=0,
            n_skipped_missing_generation=0,
            n_nan=0,
            n_errors=0,
            duration_s=0.0,
        )


@dataclass
class _JudgePassStub:
    """Stub de RunJudgePassUseCase."""

    n_judged: int = 2

    async def execute(
        self,
        *,
        run_id: str,
        round_id: str,
        phase: str | None = None,
    ) -> JudgePassReport:
        return JudgePassReport(
            run_id=run_id,
            round_id=round_id,
            n_judged=self.n_judged,
            n_skipped=0,
            n_skipped_missing_generation=0,
            n_nan=0,
            duration_s=0.0,
        )


# ---------------------------------------------------------------------------
# Stubs de serviços de domínio
# ---------------------------------------------------------------------------


class _FakeAggregationService:
    """Stub de AggregationService — devolve aggregates fixos ignorando inputs."""

    def __init__(self, aggregates: tuple[ConfigAggregate, ...] = ()) -> None:
        self._aggregates = aggregates

    def aggregate_all(
        self,
        results: list[Any],
        *,
        threshold: float,
    ) -> tuple[ConfigAggregate, ...]:
        return self._aggregates


class _FakeRankCalc:
    """Stub de RankScoreCalculator — retorna RankScore(0.5) para qualquer input."""

    def compute(self, inputs: RankScoreInputs) -> RankScore:
        return RankScore(0.5)


# ---------------------------------------------------------------------------
# Factory stub (GeneratorFactory)
# ---------------------------------------------------------------------------


class _FakeGeneratorPort:
    """GeneratorPort mínimo com URL rastreável."""

    def __init__(self, url: str) -> None:
        self.url = url


class _FakeGeneratorFactory:
    """GeneratorFactory que registra URLs solicitadas."""

    def __init__(self) -> None:
        self.created_urls: list[str] = []

    def __call__(self, url: str) -> _FakeGeneratorPort:
        self.created_urls.append(url)
        return _FakeGeneratorPort(url)


# ---------------------------------------------------------------------------
# Servidor que falha ao iniciar (para teste de ServerStartTimeoutError)
# ---------------------------------------------------------------------------


class _FailOnModelServerManager(FakeVLLMServerManager):
    """FakeVLLMServerManager que levanta ServerStartTimeoutError para modelos configurados."""

    def __init__(self, fail_models: set[str], **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._fail_models = fail_models

    async def wait_healthy(self, handle: ServerHandle, timeout_s: int) -> None:
        if handle.model in self._fail_models:
            raise ServerStartTimeoutError(
                handle.model,
                float(timeout_s),
                pid=handle.pid,
                reason="timeout",
            )
        await super().wait_healthy(handle, timeout_s)


# ---------------------------------------------------------------------------
# Factory de use case (helper de teste)
# ---------------------------------------------------------------------------


def _make_uc(
    *,
    config: _Config | None = None,
    server_manager: FakeVLLMServerManager | None = None,
    gen_stub: _GenPassStub | None = None,
    metrics_stub: _MetricsPassStub | None = None,
    judge_stub: _JudgePassStub | None = None,
    aggregation_service: _FakeAggregationService | None = None,
    retriever: StubRetriever | None = None,
    generator_factory: _FakeGeneratorFactory | None = None,
    rank_calc: Any = None,
) -> tuple[
    RunExperimentUseCase,
    _Config,
    FakeVLLMServerManager,
    _GenPassStub,
    _FakeGeneratorFactory,
]:
    cfg = config or _Config()
    sm = server_manager or FakeVLLMServerManager()
    gen = gen_stub or _GenPassStub()
    metrics = metrics_stub or _MetricsPassStub()
    judge = judge_stub or _JudgePassStub()
    agg = aggregation_service or _FakeAggregationService()
    ret = retriever or StubRetriever()
    fac = generator_factory or _FakeGeneratorFactory()

    store = InMemoryResultStore()
    writer = InMemoryResultWriter(store, round_id=cfg.round_id)
    reader = InMemoryResultReader(store)

    # WaveSchedulerService real para produzir WavePlan correto.
    wave_scheduler = WaveSchedulerService(allow_concurrent_models=False)
    _rank_calc = rank_calc if rank_calc is not None else _FakeRankCalc()

    uc = RunExperimentUseCase(
        wave_scheduler=wave_scheduler,
        server_manager=sm,  # type: ignore[arg-type]
        gen_pass_uc=gen,  # type: ignore[arg-type]
        metrics_pass_uc=metrics,  # type: ignore[arg-type]
        judge_pass_uc=judge,  # type: ignore[arg-type]
        aggregation_service=agg,  # type: ignore[arg-type]
        rank_calc=_rank_calc,  # type: ignore[arg-type]
        writer=writer,
        reader=reader,
        config=cfg,  # type: ignore[arg-type]
        retriever=ret,
        generator_factory=fac,  # type: ignore[arg-type]
    )
    return uc, cfg, sm, gen, fac


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Ciclo completo A+B — um modelo gerador + juiz."""

    async def test_report_fields(self) -> None:
        uc, _cfg, _sm, _gen, _fac = _make_uc()
        report = await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        assert isinstance(report, ExperimentReport)
        assert report.run_id == _RUN_ID
        assert len(report.config_hash) == 8
        assert report.n_generated == 1
        assert report.n_evaluated == 2
        assert report.n_judged == 2
        assert report.failed_waves == ()
        assert report.duration_s >= 0.0

    async def test_server_lifecycle_order(self) -> None:
        """Gerador: start→wait→(gen)→stop; juiz: start→wait→(judge)→stop."""
        uc, _cfg, sm, _gen, _fac = _make_uc()
        await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        # Dois starts: 1 gerador + 1 juiz.
        assert len(sm.start_calls) == 2
        # Dois wait_healthy correspondentes.
        assert len(sm.wait_calls) == 2
        # Dois stops.
        assert len(sm.stop_calls) == 2

    async def test_gen_pass_called_once(self) -> None:
        uc, _cfg, _sm, gen, _fac = _make_uc()
        await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        assert len(gen.execute_calls) == 1
        assert gen.execute_calls[0]["n_questions"] == len(_QUESTIONS)

    async def test_progress_callback_invoked(self) -> None:
        uc, _, _, _, _ = _make_uc()
        messages: list[str] = []
        await uc.execute(
            run_id=_RUN_ID,
            questions=_QUESTIONS,
            progress_callback=messages.append,
        )

        assert "experiment_started" in messages
        assert "metrics_pass_started" in messages
        assert "judge_pass_started" in messages
        assert "experiment_completed" in messages


class TestJudgeAfterAllGeneration:
    """Servidor juiz DEVE ser iniciado apenas após toda geração (nunca simultâneo)."""

    async def test_judge_start_after_gen_stops(self) -> None:
        """Verifica que o start do juiz acontece após todos os stops dos geradores."""
        # 2 modelos geradores → 2 ondas; juiz deve ser o terceiro start.
        gen2_spec = ModelWaveSpec(
            name="gen2-llm/v1",
            vram_gb_awq=8.0,
            is_judge=False,
            tensor_parallel_size=1,
            quantization="awq",
            gpu_index=1,
            extra_args={},
        )
        gen2_model_spec = ModelSpec(
            model="gen2-llm/v1",
            port=8002,
            quantization="awq",
            tensor_parallel_size=1,
            max_model_len=4096,
            gpu_index=1,
            batch_invariant=False,
            extra_args={},
        )
        cfg = _Config(
            llms=[_GEN_MODEL, "gen2-llm/v1"],
            model_registry=(_GEN_WAVE_SPEC, gen2_spec, _JUDGE_WAVE_SPEC),
            model_spec_map={
                _GEN_MODEL: _GEN_SPEC,
                "gen2-llm/v1": gen2_model_spec,
                _JUDGE_MODEL: _JUDGE_SPEC,
            },
        )
        uc, _, sm, _, _ = _make_uc(config=cfg)
        await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        # 3 starts: gen1, gen2, juiz.
        assert len(sm.start_calls) == 3
        gen_start_indices = [
            i for i, c in enumerate(sm.start_calls) if not c.model.batch_invariant
        ]
        judge_start_indices = [
            i for i, c in enumerate(sm.start_calls) if c.model.batch_invariant
        ]
        assert judge_start_indices, "Juiz deve ter sido iniciado"
        assert gen_start_indices, "Geradores devem ter sido iniciados"
        # Juiz só aparece após TODOS os geradores.
        assert min(judge_start_indices) > max(gen_start_indices)

    async def test_judge_batch_invariant_flag(self) -> None:
        uc, _, sm, _, _ = _make_uc()
        await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        judge_start = next((c for c in sm.start_calls if c.model.batch_invariant), None)
        gen_start = next(
            (c for c in sm.start_calls if not c.model.batch_invariant), None
        )
        assert judge_start is not None, "Juiz deve ter sido iniciado"
        assert gen_start is not None, "Gerador deve ter sido iniciado"
        assert judge_start.model.model == _JUDGE_MODEL
        assert gen_start.model.model == _GEN_MODEL


class TestServerStartTimeoutError:
    """ServerStartTimeoutError em uma onda: rodada continua, onda em failed_waves."""

    async def test_failed_wave_registered(self) -> None:
        sm = _FailOnModelServerManager(fail_models={_GEN_MODEL})
        uc, _, _, gen, _ = _make_uc(server_manager=sm)
        report = await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        # Onda do gerador falhou.
        assert 0 in report.failed_waves
        # gen_pass_uc NÃO foi chamado (servidor não iniciou).
        assert len(gen.execute_calls) == 0

    async def test_rodada_nao_abortada(self) -> None:
        """Juiz ainda roda mesmo que gerador tenha falhado."""
        sm = _FailOnModelServerManager(fail_models={_GEN_MODEL})
        uc, _, sm_spy, _, _ = _make_uc(server_manager=sm)
        await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        # Juiz (batch_invariant=True) foi iniciado apesar da falha do gerador.
        judge_starts = [c for c in sm_spy.start_calls if c.model.batch_invariant]
        assert len(judge_starts) == 1

    async def test_second_wave_runs_after_first_fails(self) -> None:
        """Quando 2 geradores, falha no primeiro não impede o segundo."""
        gen2_spec = ModelWaveSpec(
            name="gen2/v1",
            vram_gb_awq=8.0,
            is_judge=False,
            tensor_parallel_size=1,
            quantization="awq",
            gpu_index=1,
            extra_args={},
        )
        gen2_model_spec = ModelSpec(
            model="gen2/v1",
            port=8002,
            quantization="awq",
            tensor_parallel_size=1,
            max_model_len=4096,
            gpu_index=1,
            batch_invariant=False,
            extra_args={},
        )
        cfg = _Config(
            llms=[_GEN_MODEL, "gen2/v1"],
            model_registry=(_GEN_WAVE_SPEC, gen2_spec, _JUDGE_WAVE_SPEC),
            model_spec_map={
                _GEN_MODEL: _GEN_SPEC,
                "gen2/v1": gen2_model_spec,
                _JUDGE_MODEL: _JUDGE_SPEC,
            },
        )
        # Somente o primeiro gerador falha.
        sm = _FailOnModelServerManager(fail_models={_GEN_MODEL})
        gen = _GenPassStub()
        uc, _, _, _, _ = _make_uc(config=cfg, server_manager=sm, gen_stub=gen)
        report = await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        # gen2 executou (1 chamada ao execute do gen_pass).
        assert len(gen.execute_calls) == 1
        # gen1 falhou → wave_index 0 em failed_waves.
        assert 0 in report.failed_waves


class TestGracefulShutdown:
    """Flag _shutdown_requested interrompe loop entre ondas; servidores fechados."""

    async def test_shutdown_after_first_wave(self) -> None:
        """Seta _shutdown_requested via callback após o primeiro modelo executar."""
        gen2_spec = ModelWaveSpec(
            name="gen2/v1",
            vram_gb_awq=8.0,
            is_judge=False,
            tensor_parallel_size=1,
            quantization="awq",
            gpu_index=1,
            extra_args={},
        )
        gen2_model_spec = ModelSpec(
            model="gen2/v1",
            port=8002,
            quantization="awq",
            tensor_parallel_size=1,
            max_model_len=4096,
            gpu_index=1,
            batch_invariant=False,
            extra_args={},
        )
        cfg = _Config(
            llms=[_GEN_MODEL, "gen2/v1"],
            model_registry=(_GEN_WAVE_SPEC, gen2_spec, _JUDGE_WAVE_SPEC),
            model_spec_map={
                _GEN_MODEL: _GEN_SPEC,
                "gen2/v1": gen2_model_spec,
                _JUDGE_MODEL: _JUDGE_SPEC,
            },
        )
        gen = _GenPassStub()
        uc, _, _sm, _, _ = _make_uc(config=cfg, gen_stub=gen)

        def _shutdown_after_first(msg: str) -> None:
            if msg.startswith("generation:"):
                uc._shutdown_requested = True

        report = await uc.execute(
            run_id=_RUN_ID,
            questions=_QUESTIONS,
            progress_callback=_shutdown_after_first,
        )

        # Apenas o primeiro modelo gerou — o segundo foi bloqueado pelo shutdown.
        assert len(gen.execute_calls) == 1
        # Métricas e juiz NÃO executaram (shutdown antes das passadas 2 e 3).
        assert report.n_evaluated == 0
        assert report.n_judged == 0
        # aggregates e rank_scores são vazios no relatório parcial.
        assert report.aggregates == ()
        assert report.rank_scores == ()

    async def test_shutdown_before_first_wave(self) -> None:
        """Se _shutdown_requested já está True antes de qualquer onda, nenhuma executa."""
        uc, _, _sm, gen, _ = _make_uc()
        uc._shutdown_requested = True
        # Precisa ser resetado pelo execute; mas se já setarmos depois do reset...
        # A spec diz que execute reseta a flag no início — testamos o shutdown via
        # callback que age após o reset (logo após "experiment_started").

        def _shutdown_immediately(msg: str) -> None:
            if msg == "experiment_started":
                uc._shutdown_requested = True

        report = await uc.execute(
            run_id=_RUN_ID,
            questions=_QUESTIONS,
            progress_callback=_shutdown_immediately,
        )

        assert len(gen.execute_calls) == 0
        assert report.n_evaluated == 0
        assert report.n_judged == 0

    async def test_no_active_server_leak_on_shutdown(self) -> None:
        """Verifica que todos os servidores iniciados foram parados mesmo em shutdown."""
        gen = _GenPassStub()
        uc, _, sm, _, _ = _make_uc(gen_stub=gen)

        def _shutdown_after_gen(msg: str) -> None:
            if msg.startswith("generation:"):
                uc._shutdown_requested = True

        await uc.execute(
            run_id=_RUN_ID,
            questions=_QUESTIONS,
            progress_callback=_shutdown_after_gen,
        )

        # Cada start deve ter um stop correspondente (sem leaks).
        assert len(sm.stop_calls) == len(sm.start_calls)


class TestCanonicalContexts:
    """Canonical_contexts construídos via retriever antes da Passada 1 (Exp. B)."""

    async def test_retriever_called_per_question(self) -> None:
        """Para "B" in phases, retriever.search invocado para cada pergunta."""
        spy_calls: list[dict[str, object]] = []
        base_retriever = StubRetriever(
            default_chunks=(Chunk(id="canon-1", text="canonical", score=0.9),)
        )

        class _SpyRetriever:
            async def search(
                self, *, base: object, question: str, top_k: int
            ) -> object:
                spy_calls.append(
                    {"base": str(base), "question": question, "top_k": top_k}
                )
                return await base_retriever.search(
                    base=base,  # type: ignore[arg-type]
                    question=question,
                    top_k=top_k,
                )

        cfg = _Config(
            phases=["A", "B"],
            canonical_context_base="IDx_400k",
            canonical_top_k=3,
        )
        gen = _GenPassStub()
        uc, _, _, _, _ = _make_uc(
            config=cfg,
            gen_stub=gen,
            retriever=_SpyRetriever(),  # type: ignore[arg-type]
        )
        await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        # Um call de search por pergunta.
        assert len(spy_calls) == len(_QUESTIONS)
        # top_k conforme canonical_top_k.
        assert all(c["top_k"] == cfg.canonical_top_k for c in spy_calls)

    async def test_canonical_contexts_passed_to_gen_pass(self) -> None:
        """gen_pass_uc.execute recebe canonical_contexts não-None quando 'B' em phases."""
        cfg = _Config(phases=["A", "B"])
        gen = _GenPassStub()
        uc, _, _, _, _ = _make_uc(config=cfg, gen_stub=gen)
        await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        assert gen.execute_calls[0]["canonical_contexts"] is not None
        cc = gen.execute_calls[0]["canonical_contexts"]
        assert len(cc) == len(_QUESTIONS)

    async def test_no_canonical_contexts_phase_a_only(self) -> None:
        """Se apenas 'A' em phases, canonical_contexts=None é passado."""
        cfg = _Config(phases=["A"])
        gen = _GenPassStub()
        uc, _, _, _, _ = _make_uc(config=cfg, gen_stub=gen)
        await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        assert gen.execute_calls[0]["canonical_contexts"] is None


class TestGeneratorFactory:
    """GeneratorFactory: URL do handle injetada antes de cada execute de onda."""

    async def test_factory_called_with_handle_url(self) -> None:
        gen = _GenPassStub()
        fac = _FakeGeneratorFactory()
        uc, _, sm, _, _ = _make_uc(gen_stub=gen, generator_factory=fac)
        await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        # Factory chamada com URL do handle do gerador.
        assert len(fac.created_urls) == 1
        gen_handle = sm.start_calls[0].handle
        assert fac.created_urls[0] == gen_handle.url

    async def test_generator_attribute_updated(self) -> None:
        """gen_pass_uc._generator aponta para o gerador criado pela factory."""
        gen = _GenPassStub()
        fac = _FakeGeneratorFactory()
        uc, _, sm, _, _ = _make_uc(gen_stub=gen, generator_factory=fac)
        await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        # O execute_call rastreia a URL via gen._generator.url.
        assert gen.execute_calls[0]["generator_url"] == sm.start_calls[0].handle.url


class TestExperimentReportGolden:
    """ExperimentReport.aggregates + rank_scores calculados — valores golden."""

    async def test_aggregates_and_rank_scores_populated(self) -> None:
        """Quando aggregation_service devolve aggregates, report os inclui."""
        rank_calc = RankScoreCalculator(weights=DEFAULT_WEIGHTS)
        golden_score = rank_calc.compute(
            RankScoreInputs(
                median_score=0.80,
                failure_rate=0.10,
                win_rate=0.75,
                critical_failure_rate=0.05,
            )
        )
        golden_agg = ConfigAggregate(
            base=BaseId("IDx_400k"),
            llm=LLMId("gen-llm/v1"),
            mean_score=0.80,
            median_score=0.80,
            min_score=0.70,
            iqr=0.10,
            failure_rate=0.10,
            critical_failure_rate=0.05,
            win_rate=0.75,
            rank_score=golden_score,
            n_observations=2,
            n_excluded_nan=0,
        )
        agg_service = _FakeAggregationService(aggregates=(golden_agg,))
        uc, _, _, _, _ = _make_uc(aggregation_service=agg_service, rank_calc=rank_calc)
        report = await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        assert len(report.aggregates) == 1
        assert report.aggregates[0].llm == LLMId(_GEN_MODEL)
        assert len(report.rank_scores) == 1
        assert report.rank_scores[0] == golden_score
        assert math.isfinite(report.rank_scores[0].value)

    async def test_empty_aggregates_when_no_results(self) -> None:
        """aggregates e rank_scores são tuplas vazias quando não há resultados."""
        uc, _, _, _, _ = _make_uc()
        report = await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)

        assert report.aggregates == ()
        assert report.rank_scores == ()


class TestConfigHash:
    """config_hash derivado do round_id (8 hex SHA-256)."""

    async def test_config_hash_length(self) -> None:
        uc, _, _, _, _ = _make_uc()
        report = await uc.execute(run_id=_RUN_ID, questions=_QUESTIONS)
        assert len(report.config_hash) == 8

    async def test_config_hash_deterministic(self) -> None:
        uc1, _, _, _, _ = _make_uc()
        uc2, _, _, _, _ = _make_uc()
        r1 = await uc1.execute(run_id=_RUN_ID, questions=_QUESTIONS)
        r2 = await uc2.execute(run_id=_RUN_ID, questions=_QUESTIONS)
        assert r1.config_hash == r2.config_hash


class TestSingleModelWavePlan:
    """Testes para o helper _single_model_wave_plan."""

    def test_wave_contains_only_target_model(self) -> None:
        wave = Wave(
            wave_index=1,
            models=("modelA", "modelB"),
            gpu_indices=(0, 1),
            vram_required_gb=20.0,
            cells_in_wave=26,
        )
        plan = _single_model_wave_plan(wave, "modelA", gpu_index=0)
        assert len(plan.waves) == 1
        assert plan.waves[0].models == ("modelA",)
        assert plan.waves[0].wave_index == 1

    def test_wave_index_preserved(self) -> None:
        wave = Wave(
            wave_index=3,
            models=("m1",),
            gpu_indices=(2,),
            vram_required_gb=10.0,
            cells_in_wave=13,
        )
        plan = _single_model_wave_plan(wave, "m1", gpu_index=2)
        assert plan.waves[0].wave_index == 3
