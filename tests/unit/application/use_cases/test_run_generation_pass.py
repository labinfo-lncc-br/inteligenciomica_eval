"""Testes unitários para RunGenerationPassUseCase (TAREFA-304, camada application).

Usa os fakes de TAREFA-011 (StubRetriever, FakeGenerator, InMemoryResultStore/Writer/Reader)
e doubles locais para cobrir os critérios de aceitação:

- Célula existente (exists=True) pulada; n_skipped correto (ADR-009).
- Experimento B sem canonical_contexts → ConfigValidationError.
- GenerationError não aborta demais células; retries até max_retries.
- Célula com max_retries esgotados → failed_cells; linha NÃO persiste.
- Experimento B usa canonical_contexts; Experimento A chama o retriever.
- Linhas geradas têm MetricVector com todos os campos NaN.
- determinism_regime=GENERATOR em todas as linhas geradas.
- GenerationPassReport com todos os campos preenchidos.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest
from fakes import FakeGenerator, StubRetriever
from fakes.storage import (
    InMemoryResultReader,
    InMemoryResultStore,
    InMemoryResultWriter,
)

from inteligenciomica_eval.application.services.wave_scheduler import Wave, WavePlan
from inteligenciomica_eval.application.use_cases.run_generation_pass import (
    GenerationPassReport,
    RunGenerationPassUseCase,
)
from inteligenciomica_eval.domain.entities import Question
from inteligenciomica_eval.domain.errors import ConfigValidationError, GenerationError
from inteligenciomica_eval.domain.ports import Chunk, GenerationOutput, RetrievalResult
from inteligenciomica_eval.domain.value_objects import (
    BaseId,
    DeterminismRegime,
    LLMId,
    RowId,
)

# ---------------------------------------------------------------------------
# Constantes de teste
# ---------------------------------------------------------------------------

_LLM = "test-llm/v1"
_RUN_ID = "run-test-001"

_Q1 = Question(
    question_id="q1", text="What is genomics?", ground_truth="Study of genes."
)
_Q2 = Question(
    question_id="q2", text="What is proteomics?", ground_truth="Study of proteins."
)

_CANONICAL_CHUNK = Chunk(id="canon-1", text="Canonical context.", score=1.0)


# ---------------------------------------------------------------------------
# Stubs de configuração
# ---------------------------------------------------------------------------


@dataclass
class _Retrieval:
    top_k: int = 3


@dataclass
class _Config:
    phases: list[str] = field(default_factory=lambda: ["A"])
    bases: list[str] = field(default_factory=lambda: ["IDx_400k"])
    seeds: list[int] = field(default_factory=lambda: [42])
    temperature: float = 0.0
    retrieval: _Retrieval = field(default_factory=_Retrieval)


# ---------------------------------------------------------------------------
# Doubles de gerador
# ---------------------------------------------------------------------------


class _FailingGenerator:
    """GeneratorPort que levanta GenerationError nas primeiras ``fail_times`` chamadas.

    Após esgotar as falhas, delega ao FakeGenerator para simular recuperação.
    """

    def __init__(self, fail_times: int = 999) -> None:
        self.calls = 0
        self.fail_times = fail_times
        self._fake = FakeGenerator()

    async def generate(
        self,
        *,
        llm: LLMId,
        question: str,
        contexts: Sequence[Chunk],
        seed: int,
        temperature: float,
    ) -> GenerationOutput:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise GenerationError("forced test failure")
        return await self._fake.generate(
            llm=llm,
            question=question,
            contexts=contexts,
            seed=seed,
            temperature=temperature,
        )


class _SpyRetriever:
    """RetrieverPort que registra chamadas e devolve chunks plantados."""

    def __init__(self, chunks: tuple[Chunk, ...] = ()) -> None:
        self.calls: int = 0
        self._chunks = chunks or (Chunk(id="spy-1", text="spy context", score=0.9),)

    async def search(
        self, *, base: BaseId, question: str, top_k: int
    ) -> RetrievalResult:
        self.calls += 1
        selected = self._chunks[:top_k]
        return RetrievalResult(
            chunks=selected,
            ids=tuple(c.id for c in selected),
            scores=tuple(c.score for c in selected),
        )


# ---------------------------------------------------------------------------
# Helpers de wave plan e factory do use case
# ---------------------------------------------------------------------------


def _make_plan(
    models: tuple[str, ...] = (_LLM,),
    gpu_indices: tuple[int, ...] = (0,),
) -> WavePlan:
    wave = Wave(
        wave_index=0,
        models=models,
        gpu_indices=gpu_indices,
        vram_required_gb=26.0,
        cells_in_wave=1,
    )
    return WavePlan(waves=(wave,), total_cells=1, estimated_vram_peak_gb=26.0)


_SINGLE_WAVE_PLAN = _make_plan()


def _make_uc(
    *,
    config: _Config | None = None,
    generator: FakeGenerator | _FailingGenerator | None = None,
    retriever: StubRetriever | _SpyRetriever | None = None,
    max_retries: int = 3,
    store: InMemoryResultStore | None = None,
) -> tuple[RunGenerationPassUseCase, InMemoryResultStore]:
    s = store or InMemoryResultStore()
    uc = RunGenerationPassUseCase(
        retriever=retriever or StubRetriever(),  # type: ignore[arg-type]
        generator=generator or FakeGenerator(),  # type: ignore[arg-type]
        writer=InMemoryResultWriter(s, round_id=_RUN_ID),
        reader=InMemoryResultReader(s),
        config=config or _Config(),
        max_retries=max_retries,
    )
    return uc, s


# ---------------------------------------------------------------------------
# Testes — Passada de geração (Experimento A)
# ---------------------------------------------------------------------------


class TestPhaseAGeneration:
    async def test_generates_single_cell(self) -> None:
        uc, store = _make_uc()
        report = await uc.execute(
            run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1]
        )
        assert report.n_generated == 1
        assert report.n_skipped == 0
        assert report.n_errors == 0
        assert store.size == 1

    async def test_generates_multiple_questions(self) -> None:
        uc, store = _make_uc()
        report = await uc.execute(
            run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1, _Q2]
        )
        assert report.n_generated == 2
        assert store.size == 2

    async def test_uses_retriever_for_contexts(self) -> None:
        spy = _SpyRetriever()
        uc, _ = _make_uc(retriever=spy)
        await uc.execute(run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1])
        assert spy.calls == 1  # retriever chamado 1x por célula

    async def test_retriever_contexts_stored_in_answer(self) -> None:
        spy_chunk = Chunk(id="ret-1", text="retrieved text", score=0.95)
        spy = _SpyRetriever(chunks=(spy_chunk,))
        uc, store = _make_uc(retriever=spy)
        await uc.execute(run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1])
        row = next(iter(store._rows.values()))
        assert "ret-1" in row.result.answer.retrieved_chunk_ids
        assert "retrieved text" in row.result.answer.retrieved_chunks_text

    async def test_multiple_seeds_generate_separate_cells(self) -> None:
        cfg = _Config(seeds=[42, 99])
        uc, store = _make_uc(config=cfg)
        report = await uc.execute(
            run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1]
        )
        assert report.n_generated == 2  # 1 LLM x 1 question x 2 seeds
        assert store.size == 2

    async def test_multiple_bases_generate_separate_cells(self) -> None:
        cfg = _Config(bases=["IDx_400k", "ID_230K"])
        uc, store = _make_uc(config=cfg)
        report = await uc.execute(
            run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1]
        )
        assert report.n_generated == 2  # 1 LLM x 2 bases x 1 seed x 1 question
        assert store.size == 2


# ---------------------------------------------------------------------------
# Testes — Idempotência (ADR-009)
# ---------------------------------------------------------------------------


class TestIdempotency:
    async def test_existing_cell_is_skipped(self) -> None:
        uc, store = _make_uc()
        # Primeira passada: gera a célula.
        await uc.execute(run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1])
        assert store.size == 1
        # Segunda passada: deve pular.
        report = await uc.execute(
            run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1]
        )
        assert report.n_skipped == 1
        assert report.n_generated == 0
        assert store.size == 1  # nenhuma linha nova

    async def test_skip_incremented_not_generated(self) -> None:
        uc, _ = _make_uc()
        await uc.execute(
            run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1, _Q2]
        )
        report = await uc.execute(
            run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1, _Q2]
        )
        assert report.n_skipped == 2
        assert report.n_generated == 0


# ---------------------------------------------------------------------------
# Testes — Experimento B (canonical_contexts)
# ---------------------------------------------------------------------------


class TestPhaseB:
    async def test_phase_b_without_canonical_raises(self) -> None:
        cfg = _Config(phases=["B"])
        uc, _ = _make_uc(config=cfg)
        with pytest.raises(ConfigValidationError, match="canonical_contexts"):
            await uc.execute(
                run_id=_RUN_ID,
                wave_plan=_SINGLE_WAVE_PLAN,
                questions=[_Q1],
                canonical_contexts=None,
            )

    async def test_phase_b_uses_canonical_not_retriever(self) -> None:
        cfg = _Config(phases=["B"])
        spy = _SpyRetriever()
        uc, _ = _make_uc(config=cfg, retriever=spy)
        canonical = {_Q1.question_id: [_CANONICAL_CHUNK]}
        report = await uc.execute(
            run_id=_RUN_ID,
            wave_plan=_SINGLE_WAVE_PLAN,
            questions=[_Q1],
            canonical_contexts=canonical,
        )
        assert report.n_generated == 1
        assert spy.calls == 0  # retriever NÃO chamado no Experimento B

    async def test_phase_b_canonical_chunks_in_answer(self) -> None:
        cfg = _Config(phases=["B"])
        uc, store = _make_uc(config=cfg)
        canonical = {_Q1.question_id: [_CANONICAL_CHUNK]}
        await uc.execute(
            run_id=_RUN_ID,
            wave_plan=_SINGLE_WAVE_PLAN,
            questions=[_Q1],
            canonical_contexts=canonical,
        )
        row = next(iter(store._rows.values()))
        assert row.result.answer.retrieved_chunk_ids == (_CANONICAL_CHUNK.id,)
        assert row.result.answer.retrieved_chunks_text == (_CANONICAL_CHUNK.text,)

    async def test_phase_b_uses_fixed_base(self) -> None:
        cfg = _Config(phases=["B"])
        uc, store = _make_uc(config=cfg)
        canonical = {_Q1.question_id: [_CANONICAL_CHUNK]}
        await uc.execute(
            run_id=_RUN_ID,
            wave_plan=_SINGLE_WAVE_PLAN,
            questions=[_Q1],
            canonical_contexts=canonical,
        )
        row = next(iter(store._rows.values()))
        assert row.result.answer.base.value == "fixed"

    async def test_both_phases_runs_a_and_b(self) -> None:
        cfg = _Config(phases=["A", "B"])
        uc, store = _make_uc(config=cfg)
        canonical = {_Q1.question_id: [_CANONICAL_CHUNK]}
        report = await uc.execute(
            run_id=_RUN_ID,
            wave_plan=_SINGLE_WAVE_PLAN,
            questions=[_Q1],
            canonical_contexts=canonical,
        )
        # 1 LLM x (1 base phase A + 1 fixed base phase B) x 1 seed x 1 question = 2
        assert report.n_generated == 2
        assert store.size == 2


# ---------------------------------------------------------------------------
# Testes — Tratamento de erros (GenerationError + retry)
# ---------------------------------------------------------------------------


class TestErrorHandling:
    async def test_generation_error_does_not_abort_other_cells(self) -> None:
        # Falha na q1 (sempre), q2 gera com sucesso.
        class _SelectiveFail:
            async def generate(
                self,
                *,
                llm: LLMId,
                question: str,
                contexts: Sequence[Chunk],
                seed: int,
                temperature: float,
            ) -> GenerationOutput:
                if question == _Q1.text:
                    raise GenerationError("fail q1")
                return GenerationOutput(
                    text="ok",
                    tokens_in=1,
                    tokens_out=1,
                    latency_ms=0,
                    batch_invariant=False,
                )

        uc, store = _make_uc(generator=_SelectiveFail(), max_retries=1)  # type: ignore[arg-type]
        report = await uc.execute(
            run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1, _Q2]
        )
        assert report.n_generated == 1
        assert report.n_errors == 1
        assert store.size == 1

    async def test_max_retries_exhausted_adds_to_failed_cells(self) -> None:
        gen = _FailingGenerator(fail_times=999)
        uc, store = _make_uc(generator=gen, max_retries=3)
        report = await uc.execute(
            run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1]
        )
        assert report.n_errors == 1
        assert len(report.failed_cells) == 1
        assert store.size == 0  # linha NÃO persiste após falha permanente

    async def test_max_retries_exhausted_attempts_correct_count(self) -> None:
        gen = _FailingGenerator(fail_times=999)
        uc, _ = _make_uc(generator=gen, max_retries=3)
        await uc.execute(run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1])
        assert gen.calls == 3  # tentou exatamente max_retries vezes

    async def test_partial_retry_succeeds(self) -> None:
        # Falha nas 2 primeiras tentativas, sucesso na 3ª.
        gen = _FailingGenerator(fail_times=2)
        uc, store = _make_uc(generator=gen, max_retries=3)
        report = await uc.execute(
            run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1]
        )
        assert report.n_generated == 1
        assert report.n_errors == 0
        assert gen.calls == 3  # 2 falhas + 1 sucesso
        assert store.size == 1

    async def test_failed_cell_row_id_recorded(self) -> None:
        gen = _FailingGenerator(fail_times=999)
        uc, _ = _make_uc(generator=gen, max_retries=1)
        report = await uc.execute(
            run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1]
        )
        expected_row_id = RowId.from_cell(
            run_id=_RUN_ID,
            phase="A",
            base="IDx_400k",
            llm=_LLM,
            seed=42,
            question_id=_Q1.question_id,
        )
        assert report.failed_cells == (expected_row_id.value,)


# ---------------------------------------------------------------------------
# Testes — Integridade das linhas geradas (MetricVector, regime, final_score)
# ---------------------------------------------------------------------------


class TestGeneratedRowIntegrity:
    async def test_all_metric_fields_are_nan(self) -> None:
        uc, store = _make_uc()
        await uc.execute(run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1])
        row = next(iter(store._rows.values()))
        m = row.result.metrics
        assert math.isnan(m.answer_correctness)
        assert math.isnan(m.answer_similarity)
        assert math.isnan(m.faithfulness)
        assert math.isnan(m.context_precision)
        assert math.isnan(m.context_recall)
        assert math.isnan(m.answer_relevancy)
        assert math.isnan(m.bertscore_f1)
        assert math.isnan(m.rubric_biomed_score)

    async def test_determinism_regime_is_generator(self) -> None:
        uc, store = _make_uc()
        await uc.execute(run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1])
        row = next(iter(store._rows.values()))
        assert row.result.determinism_regime is DeterminismRegime.GENERATOR

    async def test_final_score_is_nan(self) -> None:
        uc, store = _make_uc()
        await uc.execute(run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1])
        row = next(iter(store._rows.values()))
        assert math.isnan(row.result.final_score.value)

    async def test_batch_invariant_false_for_generator_regime(self) -> None:
        uc, store = _make_uc()
        await uc.execute(run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1])
        row = next(iter(store._rows.values()))
        # batch_invariant deriva de regime (§4.3): GENERATOR → False.
        assert row.result.batch_invariant is False

    async def test_critical_failure_fields_are_none(self) -> None:
        uc, store = _make_uc()
        await uc.execute(run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1])
        row = next(iter(store._rows.values()))
        assert row.result.critical_failure_flag is None
        assert row.result.critical_failure_note is None


# ---------------------------------------------------------------------------
# Testes — GenerationPassReport
# ---------------------------------------------------------------------------


class TestGenerationPassReport:
    async def test_report_fields_populated(self) -> None:
        uc, _ = _make_uc()
        report = await uc.execute(
            run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1]
        )
        assert isinstance(report, GenerationPassReport)
        assert report.run_id == _RUN_ID
        assert report.wave_plan is _SINGLE_WAVE_PLAN
        assert report.n_generated == 1
        assert report.n_skipped == 0
        assert report.n_errors == 0
        assert report.duration_s >= 0.0
        assert report.failed_cells == ()

    async def test_report_duration_is_positive(self) -> None:
        uc, _ = _make_uc()
        report = await uc.execute(
            run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1]
        )
        assert report.duration_s >= 0.0

    async def test_report_is_frozen(self) -> None:
        uc, _ = _make_uc()
        report = await uc.execute(
            run_id=_RUN_ID, wave_plan=_SINGLE_WAVE_PLAN, questions=[_Q1]
        )
        with pytest.raises((AttributeError, TypeError)):
            report.n_generated = 0  # type: ignore[misc]

    async def test_multiple_waves_all_cells_generated(self) -> None:
        wave_a = Wave(
            wave_index=0,
            models=("llm-a/v1",),
            gpu_indices=(0,),
            vram_required_gb=26.0,
            cells_in_wave=1,
        )
        wave_b = Wave(
            wave_index=1,
            models=("llm-b/v1",),
            gpu_indices=(1,),
            vram_required_gb=26.0,
            cells_in_wave=1,
        )
        plan = WavePlan(
            waves=(wave_a, wave_b), total_cells=2, estimated_vram_peak_gb=26.0
        )
        uc, store = _make_uc()
        report = await uc.execute(run_id=_RUN_ID, wave_plan=plan, questions=[_Q1])
        # 2 ondas x 1 LLM x 1 questao x 1 seed x 1 base = 2 celulas
        assert report.n_generated == 2
        assert store.size == 2
