"""Structural compatibility tests for all fakes (TAREFA-011).

For each port defined in §5.1, this module verifies that:
1. The fake satisfies isinstance() against its @runtime_checkable Protocol.
2. The fake produces deterministic output (identical inputs → identical outputs).
3. NaN-injection variants produce NaN where specified by ADR-007.
4. InMemoryResultWriter/Reader correctly implement exists / update_metrics / load.
"""

from __future__ import annotations

import math

import pytest
from factories import (
    make_evaluation_result,
    make_generated_answer,
    make_metric_vector,
    make_row_id,
)
from fakes import (
    FakeAnnotationReader,
    FakeDeterministicMetric,
    FakeGenerator,
    FakeGoldChunkReader,
    FakeMetricSuite,
    FakeRubricJudge,
    FakeStats,
    FakeVLLMServerManager,
    InMemoryResultReader,
    InMemoryResultStore,
    InMemoryResultWriter,
    StubRetriever,
)

from inteligenciomica_eval.domain.ports import (
    AnnotationReaderPort,
    Chunk,
    CriticalAnnotation,
    DeterministicMetricPort,
    EvaluationSample,
    GeneratorPort,
    GoldChunkReaderPort,
    MetricSuitePort,
    ModelSpec,
    ResultReaderPort,
    ResultWriterPort,
    RetrieverPort,
    RubricJudgePort,
    StatsPort,
    VLLMServerManagerPort,
)
from inteligenciomica_eval.domain.value_objects import (
    BaseId,
    DeterminismRegime,
    FinalScore,
    LLMId,
)

# ---------------------------------------------------------------------------
# Shared sample fixture
# ---------------------------------------------------------------------------

_SAMPLE = EvaluationSample(
    question_id="q_rag_001",
    question="O que é RAG?",
    ground_truth="Retrieval-Augmented Generation.",
    generated_answer="RAG combina retrieval com LLM.",
    contexts=("Contexto relevante.",),
)


# ---------------------------------------------------------------------------
# isinstance / Protocol compatibility
# ---------------------------------------------------------------------------


class TestFakesSatisfyPorts:
    """Each fake passes isinstance() against its @runtime_checkable Protocol."""

    def test_stub_retriever_satisfies_retriever_port(self) -> None:
        assert isinstance(StubRetriever(), RetrieverPort)

    def test_fake_generator_satisfies_generator_port(self) -> None:
        assert isinstance(FakeGenerator(), GeneratorPort)

    def test_fake_metric_suite_satisfies_metric_suite_port(self) -> None:
        assert isinstance(FakeMetricSuite(), MetricSuitePort)

    def test_fake_rubric_judge_satisfies_rubric_judge_port(self) -> None:
        assert isinstance(FakeRubricJudge(), RubricJudgePort)

    def test_fake_deterministic_metric_satisfies_deterministic_metric_port(
        self,
    ) -> None:
        assert isinstance(FakeDeterministicMetric(), DeterministicMetricPort)

    def test_fake_gold_chunk_reader_satisfies_gold_chunk_reader_port(self) -> None:
        assert isinstance(FakeGoldChunkReader(), GoldChunkReaderPort)

    def test_in_memory_result_writer_satisfies_result_writer_port(self) -> None:
        store = InMemoryResultStore()
        assert isinstance(InMemoryResultWriter(store), ResultWriterPort)

    def test_in_memory_result_reader_satisfies_result_reader_port(self) -> None:
        store = InMemoryResultStore()
        assert isinstance(InMemoryResultReader(store), ResultReaderPort)

    def test_fake_stats_satisfies_stats_port(self) -> None:
        assert isinstance(FakeStats(), StatsPort)

    def test_fake_annotation_reader_satisfies_annotation_reader_port(self) -> None:
        assert isinstance(FakeAnnotationReader(), AnnotationReaderPort)

    def test_fake_vllm_server_manager_satisfies_vllm_server_manager_port(self) -> None:
        assert isinstance(FakeVLLMServerManager(), VLLMServerManagerPort)


# ---------------------------------------------------------------------------
# StubRetriever
# ---------------------------------------------------------------------------


class TestStubRetriever:
    async def test_returns_default_chunk_for_unknown_question(self) -> None:
        result = await StubRetriever().search(
            base=BaseId("IDx_400k"), question="unknown?", top_k=5
        )
        assert len(result.chunks) == 1
        assert result.ids == (result.chunks[0].id,)

    async def test_returns_planted_chunks_for_known_question(self) -> None:
        planted = (Chunk(id="planted-1", text="ctx", score=0.95),)
        retriever = StubRetriever(responses={"q?": planted})
        result = await retriever.search(
            base=BaseId("IDx_400k"), question="q?", top_k=10
        )
        assert result.ids == ("planted-1",)

    async def test_top_k_caps_returned_chunks(self) -> None:
        chunks = tuple(Chunk(id=f"c{i}", text=f"t{i}", score=0.5) for i in range(5))
        retriever = StubRetriever(responses={"q": chunks})
        result = await retriever.search(base=BaseId("IDx_400k"), question="q", top_k=2)
        assert len(result.chunks) == 2

    async def test_deterministic_same_question_same_output(self) -> None:
        r = StubRetriever()
        base = BaseId("IDx_400k")
        r1 = await r.search(base=base, question="same?", top_k=1)
        r2 = await r.search(base=base, question="same?", top_k=1)
        assert r1.ids == r2.ids

    async def test_ids_and_scores_match_chunks(self) -> None:
        planted = (
            Chunk(id="a", text="txt", score=0.7),
            Chunk(id="b", text="txt2", score=0.6),
        )
        r = await StubRetriever(responses={"q": planted}).search(
            base=BaseId("IDx_400k"), question="q", top_k=5
        )
        assert r.ids == ("a", "b")
        assert r.scores == (0.7, 0.6)


# ---------------------------------------------------------------------------
# FakeGenerator
# ---------------------------------------------------------------------------


class TestFakeGenerator:
    async def test_deterministic_same_inputs_same_output(self) -> None:
        gen = FakeGenerator()
        chunk = Chunk(id="c1", text="ctx", score=0.9)
        llm = LLMId("model-a")
        out1 = await gen.generate(
            llm=llm, question="Q?", contexts=[chunk], seed=1, temperature=0.0
        )
        out2 = await gen.generate(
            llm=llm, question="Q?", contexts=[chunk], seed=1, temperature=0.0
        )
        assert out1.text == out2.text

    async def test_different_seed_different_output(self) -> None:
        gen = FakeGenerator()
        chunk = Chunk(id="c1", text="ctx", score=0.9)
        llm = LLMId("model-a")
        out1 = await gen.generate(
            llm=llm, question="Q?", contexts=[chunk], seed=1, temperature=0.0
        )
        out2 = await gen.generate(
            llm=llm, question="Q?", contexts=[chunk], seed=2, temperature=0.0
        )
        assert out1.text != out2.text

    async def test_records_calls(self) -> None:
        gen = FakeGenerator()
        chunk = Chunk(id="c1", text="ctx", score=0.9)
        await gen.generate(
            llm=LLMId("model-x"),
            question="Q?",
            contexts=[chunk],
            seed=0,
            temperature=0.1,
        )
        assert len(gen.calls) == 1
        assert gen.calls[0].question == "Q?"
        assert gen.calls[0].seed == 0

    async def test_call_count_matches_invocations(self) -> None:
        gen = FakeGenerator()
        chunk = Chunk(id="c1", text="ctx", score=0.9)
        for i in range(3):
            await gen.generate(
                llm=LLMId("m"),
                question=f"Q{i}",
                contexts=[chunk],
                seed=i,
                temperature=0.0,
            )
        assert len(gen.calls) == 3


# ---------------------------------------------------------------------------
# FakeMetricSuite
# ---------------------------------------------------------------------------


class TestFakeMetricSuite:
    async def test_returns_canonical_metrics_by_default(self) -> None:
        m = await FakeMetricSuite().score(_SAMPLE)
        assert m.answer_correctness == pytest.approx(0.80)
        assert m.faithfulness == pytest.approx(0.90)

    async def test_inject_nan_returns_all_nan(self) -> None:
        m = await FakeMetricSuite(inject_nan=True).score(_SAMPLE)
        assert math.isnan(m.answer_correctness)
        assert math.isnan(m.faithfulness)
        assert math.isnan(m.context_recall)

    async def test_fixed_override_honoured(self) -> None:
        from inteligenciomica_eval.domain.ports import Layer1Metrics

        custom = Layer1Metrics(
            answer_correctness=0.50,
            answer_similarity=0.50,
            faithfulness=0.50,
            context_precision=0.50,
            context_recall=0.50,
            answer_relevancy=0.50,
        )
        m = await FakeMetricSuite(fixed=custom).score(_SAMPLE)
        assert m.answer_correctness == pytest.approx(0.50)

    async def test_deterministic_repeated_calls(self) -> None:
        suite = FakeMetricSuite()
        m1 = await suite.score(_SAMPLE)
        m2 = await suite.score(_SAMPLE)
        assert m1.answer_correctness == m2.answer_correctness


# ---------------------------------------------------------------------------
# FakeRubricJudge
# ---------------------------------------------------------------------------


class TestFakeRubricJudge:
    async def test_returns_canonical_rubric_by_default(self) -> None:
        r = await FakeRubricJudge().score(_SAMPLE)
        assert r.score == pytest.approx(4.0)

    async def test_inject_nan_score(self) -> None:
        r = await FakeRubricJudge(inject_nan=True).score(_SAMPLE)
        assert math.isnan(r.score)

    async def test_deterministic(self) -> None:
        judge = FakeRubricJudge()
        r1 = await judge.score(_SAMPLE)
        r2 = await judge.score(_SAMPLE)
        assert r1.score == r2.score


# ---------------------------------------------------------------------------
# FakeDeterministicMetric
# ---------------------------------------------------------------------------


class TestFakeDeterministicMetric:
    def test_returns_canonical_aux_by_default(self) -> None:
        a = FakeDeterministicMetric().score(answer="ans", ground_truth="gt")
        assert a.bertscore_f1 == pytest.approx(0.82)
        assert a.rouge_l == pytest.approx(0.71)

    def test_inject_nan(self) -> None:
        a = FakeDeterministicMetric(inject_nan=True).score(answer="a", ground_truth="g")
        assert math.isnan(a.bertscore_f1)
        assert math.isnan(a.rouge_l)

    def test_deterministic(self) -> None:
        m = FakeDeterministicMetric()
        a1 = m.score(answer="x", ground_truth="y")
        a2 = m.score(answer="x", ground_truth="y")
        assert a1.bertscore_f1 == a2.bertscore_f1
        assert a1.rouge_l == a2.rouge_l


# ---------------------------------------------------------------------------
# InMemoryResultWriter / InMemoryResultReader
# ---------------------------------------------------------------------------


class TestInMemoryStorage:
    def test_exists_false_before_append(self) -> None:
        store = InMemoryResultStore()
        writer = InMemoryResultWriter(store)
        row_id = make_row_id()
        assert writer.exists(row_id) is False

    def test_exists_true_after_append(self) -> None:
        store = InMemoryResultStore()
        writer = InMemoryResultWriter(store)
        result = make_evaluation_result()
        writer.append(result)
        assert writer.exists(result.answer.row_id) is True

    def test_last_write_wins(self) -> None:
        store = InMemoryResultStore()
        writer = InMemoryResultWriter(store)
        result = make_evaluation_result()
        writer.append(result)
        writer.append(result)  # overwrite
        assert store.size == 1

    def test_update_metrics_reflects_in_reader(self) -> None:
        store = InMemoryResultStore()
        writer = InMemoryResultWriter(store, round_id="r1")
        reader = InMemoryResultReader(store)
        result = make_evaluation_result()
        writer.append(result)

        new_metrics = make_metric_vector(answer_correctness=0.99)
        writer.update_metrics(
            result.answer.row_id,
            new_metrics,
            FinalScore(0.91),
            DeterminismRegime.JUDGE,
        )

        frame = reader.load(round_id="r1")
        assert len(frame.results) == 1
        assert frame.results[0].metrics.answer_correctness == pytest.approx(0.99)
        assert frame.results[0].final_score.value == pytest.approx(0.91)

    def test_load_filters_by_round_id(self) -> None:
        store = InMemoryResultStore()
        writer_r1 = InMemoryResultWriter(store, round_id="r1")
        writer_r2 = InMemoryResultWriter(store, round_id="r2")
        reader = InMemoryResultReader(store)

        result_r1 = make_evaluation_result(
            answer=make_generated_answer(question_id="q_r1")
        )
        result_r2 = make_evaluation_result(
            answer=make_generated_answer(question_id="q_r2")
        )
        writer_r1.append(result_r1)
        writer_r2.append(result_r2)

        frame_r1 = reader.load(round_id="r1")
        frame_r2 = reader.load(round_id="r2")
        assert len(frame_r1.results) == 1
        assert len(frame_r2.results) == 1

    def test_load_filters_by_phase(self) -> None:
        store = InMemoryResultStore()
        writer = InMemoryResultWriter(store, round_id="r1")
        reader = InMemoryResultReader(store)

        result_a = make_evaluation_result(
            answer=make_generated_answer(phase="A", question_id="qa")
        )
        result_b = make_evaluation_result(
            answer=make_generated_answer(phase="B", base="fixed", question_id="qb")
        )
        writer.append(result_a)
        writer.append(result_b)

        frame_a = reader.load(round_id="r1", phase="A")
        frame_b = reader.load(round_id="r1", phase="B")
        frame_all = reader.load(round_id="r1")

        assert len(frame_a.results) == 1
        assert frame_a.results[0].answer.phase == "A"
        assert len(frame_b.results) == 1
        assert frame_b.results[0].answer.phase == "B"
        assert len(frame_all.results) == 2

    def test_load_empty_round_returns_empty_frame(self) -> None:
        store = InMemoryResultStore()
        reader = InMemoryResultReader(store)
        frame = reader.load(round_id="nonexistent")
        assert frame.results == ()

    def test_update_metrics_raises_for_unknown_row(self) -> None:
        store = InMemoryResultStore()
        writer = InMemoryResultWriter(store)
        with pytest.raises(KeyError):
            writer.update_metrics(
                make_row_id(),
                make_metric_vector(),
                FinalScore(0.8),
                DeterminismRegime.JUDGE,
            )

    def test_update_metrics_updates_score_and_preserves_answer(self) -> None:
        """update_metrics atualiza métricas + final_score (TAREFA-026); answer intacto."""
        store = InMemoryResultStore()
        writer = InMemoryResultWriter(store, round_id="r1")
        reader = InMemoryResultReader(store)
        result = make_evaluation_result(final_score=0.75)
        writer.append(result)

        writer.update_metrics(
            result.answer.row_id,
            make_metric_vector(bertscore_f1=0.55),
            FinalScore(0.42),
            DeterminismRegime.JUDGE,
        )

        frame = reader.load(round_id="r1")
        stored = frame.results[0]
        # final_score AGORA é atualizado por update_metrics (PR retroativo TAREFA-026).
        assert stored.final_score.value == pytest.approx(0.42)
        assert stored.metrics.bertscore_f1 == pytest.approx(0.55)
        # campos do answer permanecem intactos.
        assert stored.answer.generated_answer == result.answer.generated_answer


# ---------------------------------------------------------------------------
# FakeGoldChunkReader
# ---------------------------------------------------------------------------


class TestFakeGoldChunkReader:
    def test_returns_default_golds_for_unknown_question(self) -> None:
        golds = FakeGoldChunkReader().gold_for("unknown-q")
        assert isinstance(golds, list)
        assert len(golds) >= 1

    def test_returns_planted_golds(self) -> None:
        reader = FakeGoldChunkReader(mapping={"q1": ["g1", "g2"]})
        assert reader.gold_for("q1") == ["g1", "g2"]

    def test_returns_new_list_each_call(self) -> None:
        reader = FakeGoldChunkReader(mapping={"q": ["g"]})
        assert reader.gold_for("q") is not reader.gold_for("q")


# ---------------------------------------------------------------------------
# FakeAnnotationReader
# ---------------------------------------------------------------------------


class TestFakeAnnotationReader:
    def test_returns_empty_for_unknown_run(self) -> None:
        assert FakeAnnotationReader().read("unknown") == []

    def test_returns_planted_annotations(self) -> None:
        row_id = make_row_id()
        ann = CriticalAnnotation(row_id=row_id, flag=1, note="Critical failure.")
        reader = FakeAnnotationReader(mapping={"run-1": [ann]})
        result = reader.read("run-1")
        assert len(result) == 1
        assert result[0].flag == 1

    def test_returns_new_list_each_call(self) -> None:
        reader = FakeAnnotationReader()
        assert reader.read("r") is not reader.read("r")


# ---------------------------------------------------------------------------
# FakeStats
# ---------------------------------------------------------------------------


class TestFakeStats:
    def test_wilcoxon_returns_deterministic_report(self) -> None:
        from inteligenciomica_eval.domain.ports import ResultFrame

        stats = FakeStats()
        frame = ResultFrame(results=())
        w1 = stats.wilcoxon_paired(frame, "score")
        w2 = stats.wilcoxon_paired(frame, "score")
        assert w1.statistic == w2.statistic
        assert w1.p_value == pytest.approx(0.03)

    def test_friedman_returns_deterministic_report(self) -> None:
        from inteligenciomica_eval.domain.ports import ResultFrame

        stats = FakeStats()
        frame = ResultFrame(results=())
        f = stats.friedman_nemenyi(frame, "score")
        assert "A vs B" in f.post_hoc

    def test_mixed_linear_model_uses_passed_formula(self) -> None:
        from inteligenciomica_eval.domain.ports import ResultFrame

        stats = FakeStats()
        frame = ResultFrame(results=())
        formula = "score ~ llm + (1|question)"
        m = stats.mixed_linear_model(frame, formula)
        assert m.formula == formula

    def test_custom_wilcoxon_config(self) -> None:
        from inteligenciomica_eval.domain.ports import ResultFrame, WilcoxonReport

        custom = WilcoxonReport(
            statistic=99.0, p_value=0.001, effect_size=0.9, n_pairs=5
        )
        stats = FakeStats(wilcoxon=custom)
        w = stats.wilcoxon_paired(ResultFrame(results=()), "m")
        assert w.statistic == pytest.approx(99.0)


# ---------------------------------------------------------------------------
# FakeVLLMServerManager
# ---------------------------------------------------------------------------


def _gen_spec() -> ModelSpec:
    return ModelSpec(
        model="m",
        port=8000,
        quantization=None,
        tensor_parallel_size=1,
        max_model_len=8192,
        gpu_index=0,
        batch_invariant=False,
        extra_args={},
    )


class TestFakeVLLMServerManager:
    async def test_start_returns_handle_with_model(self) -> None:
        spec = ModelSpec(
            model="llama3-8b",
            port=8000,
            quantization=None,
            tensor_parallel_size=1,
            max_model_len=8192,
            gpu_index=0,
            batch_invariant=False,
            extra_args={},
        )
        mgr = FakeVLLMServerManager()
        handle = await mgr.start(spec)
        assert handle.model == "llama3-8b"
        assert handle.pid >= 9000
        assert handle.batch_invariant is False

    async def test_judge_spec_sets_batch_invariant(self) -> None:
        spec = ModelSpec(
            model="prometheus",
            port=8001,
            quantization=None,
            tensor_parallel_size=1,
            max_model_len=4096,
            gpu_index=3,
            batch_invariant=True,
            extra_args={},
        )
        mgr = FakeVLLMServerManager()
        handle = await mgr.start(spec)
        assert handle.batch_invariant is True

    async def test_consecutive_starts_get_different_ports(self) -> None:
        mgr = FakeVLLMServerManager()
        h1 = await mgr.start(_gen_spec())
        h2 = await mgr.start(_gen_spec())
        assert h1.url != h2.url

    async def test_records_all_lifecycle_calls(self) -> None:
        mgr = FakeVLLMServerManager()
        handle = await mgr.start(_gen_spec())
        await mgr.wait_healthy(handle, timeout_s=60)
        await mgr.stop(handle)

        assert len(mgr.start_calls) == 1
        assert len(mgr.wait_calls) == 1
        assert len(mgr.stop_calls) == 1
        assert mgr.wait_calls[0].timeout_s == 60

    async def test_deterministic_pid_sequence(self) -> None:
        mgr = FakeVLLMServerManager()
        h1 = await mgr.start(_gen_spec())
        h2 = await mgr.start(_gen_spec())
        assert h2.pid == h1.pid + 1

    def test_satisfies_vllm_server_manager_port(self) -> None:
        assert isinstance(FakeVLLMServerManager(), VLLMServerManagerPort)


# ---------------------------------------------------------------------------
# NaN injection tests for ADR-007 path
# ---------------------------------------------------------------------------


class TestNaNInjection:
    """Fakes that support inject_nan=True can drive ADR-007 NaN-propagation paths."""

    async def test_metric_suite_nan_all_fields(self) -> None:
        m = await FakeMetricSuite(inject_nan=True).score(_SAMPLE)
        nan_fields = (
            m.answer_correctness,
            m.answer_similarity,
            m.faithfulness,
            m.context_precision,
            m.context_recall,
            m.answer_relevancy,
        )
        assert all(math.isnan(v) for v in nan_fields)

    async def test_rubric_judge_nan_score(self) -> None:
        r = await FakeRubricJudge(inject_nan=True).score(_SAMPLE)
        assert math.isnan(r.score)
        assert r.feedback  # feedback string is still non-empty

    def test_deterministic_metric_nan_bertscore(self) -> None:
        a = FakeDeterministicMetric(inject_nan=True).score(answer="a", ground_truth="g")
        assert math.isnan(a.bertscore_f1)
