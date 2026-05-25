"""Testes de contrato estrutural dos ports de domínio (TAREFA-005).

Verifica que:
1. Stubs mínimos satisfazem cada Protocol via isinstance (runtime_checkable).
2. Todos os DTOs auxiliares podem ser instanciados com valores válidos.

Não há I/O real — todos os stubs são implementações in-memory triviais.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
)
from inteligenciomica_eval.domain.ports import (
    AnnotationReaderPort,
    AuxMetrics,
    Chunk,
    CriticalAnnotation,
    DeterministicMetricPort,
    EvaluationSample,
    FriedmanReport,
    GenerationOutput,
    GeneratorPort,
    GoldChunkReaderPort,
    Layer1Metrics,
    MetricSuitePort,
    MLMReport,
    ModelSpec,
    ResultFrame,
    ResultReaderPort,
    ResultWriterPort,
    RetrievalResult,
    RetrieverPort,
    RubricJudgePort,
    RubricResult,
    ServerHandle,
    StatsPort,
    VLLMServerManagerPort,
    WilcoxonReport,
)
from inteligenciomica_eval.domain.value_objects import (
    BaseId,
    DeterminismRegime,
    FinalScore,
    LLMId,
    MetricVector,
    RowId,
    Seed,
)

# ---------------------------------------------------------------------------
# Helpers / factories de domínio
# ---------------------------------------------------------------------------

_NAN = float("nan")


def _make_row_id() -> RowId:
    return RowId.from_cell(
        run_id="run-test",
        phase="A",
        base="IDx_400k",
        llm="llama3",
        seed=42,
        question_id="q01",
    )


def _make_evaluation_result() -> EvaluationResult:
    question = Question(
        question_id="q01",
        text="O que é RAG?",
        ground_truth="Retrieval-Augmented Generation.",
    )
    answer = GeneratedAnswer(
        row_id=_make_row_id(),
        question=question,
        base=BaseId("IDx_400k"),
        llm=LLMId("llama3"),
        seed=Seed(42),
        phase="A",
        generated_answer="RAG combina retrieval com geração.",
        retrieved_chunk_ids=("c1",),
        retrieved_chunks_text=("Texto do chunk 1.",),
        retrieval_scores=(0.9,),
    )
    metrics = MetricVector(
        answer_correctness=0.8,
        answer_similarity=0.75,
        faithfulness=0.9,
        context_precision=0.85,
        context_recall=0.7,
        answer_relevancy=0.88,
        bertscore_f1=0.82,
        rubric_biomed_score=4.0,
    )
    return EvaluationResult(
        answer=answer,
        metrics=metrics,
        final_score=FinalScore(0.8),
        determinism_regime=DeterminismRegime.JUDGE,
        critical_failure_flag=None,
        critical_failure_note=None,
    )


def _make_result_frame() -> ResultFrame:
    return ResultFrame(results=(_make_evaluation_result(),))


# ---------------------------------------------------------------------------
# Stubs mínimos — implementações triviais para teste de contrato
# ---------------------------------------------------------------------------


class _StubRetriever:
    def search(self, *, base: BaseId, question: str, top_k: int) -> RetrievalResult:
        chunk = Chunk(id="c1", text="texto", score=0.9)
        return RetrievalResult(chunks=(chunk,), ids=("c1",), scores=(0.9,))


class _StubGenerator:
    async def generate(
        self,
        *,
        llm: LLMId,
        question: str,
        contexts: Sequence[Chunk],
        seed: int,
        temperature: float,
    ) -> GenerationOutput:
        return GenerationOutput(
            text="resposta",
            tokens_in=10,
            tokens_out=5,
            latency_ms=100,
            batch_invariant=False,
        )


class _StubMetricSuite:
    def score(self, sample: EvaluationSample) -> Layer1Metrics:
        return Layer1Metrics(
            answer_correctness=0.8,
            answer_similarity=0.75,
            faithfulness=0.9,
            context_precision=0.85,
            context_recall=0.7,
            answer_relevancy=0.88,
        )


class _StubRubricJudge:
    def score(self, sample: EvaluationSample) -> RubricResult:
        return RubricResult(score=4.0, feedback="Resposta adequada.")


class _StubDeterministicMetric:
    def score(self, *, answer: str, ground_truth: str) -> AuxMetrics:
        return AuxMetrics(bertscore_f1=0.82)


class _StubGoldChunkReader:
    def gold_for(self, question_id: str) -> list[str]:
        return ["chunk-gold-1", "chunk-gold-2"]


class _StubResultWriter:
    def append(self, result: EvaluationResult) -> None:
        pass

    def update_metrics(self, row_id: RowId, metrics: MetricVector) -> None:
        pass

    def exists(self, row_id: RowId) -> bool:
        return False


class _StubResultReader:
    def load(self, *, round_id: str, phase: str | None = None) -> ResultFrame:
        return _make_result_frame()


class _StubStats:
    def wilcoxon_paired(self, frame: ResultFrame, metric: str) -> WilcoxonReport:
        return WilcoxonReport(statistic=1.5, p_value=0.04, effect_size=0.3, n_pairs=13)

    def friedman_nemenyi(self, frame: ResultFrame, metric: str) -> FriedmanReport:
        return FriedmanReport(statistic=8.2, p_value=0.02, post_hoc={"A vs B": 0.03})

    def mixed_linear_model(self, frame: ResultFrame, formula: str) -> MLMReport:
        return MLMReport(formula=formula, aic=120.5, bic=130.1, coef={"base": 0.15})


class _StubAnnotationReader:
    def read(self, run_id: str) -> list[CriticalAnnotation]:
        return [CriticalAnnotation(row_id=_make_row_id(), flag=0, note=None)]


class _StubVLLMServerManager:
    def start(self, model: ModelSpec) -> ServerHandle:
        return ServerHandle(
            process_id=1234, base_url="http://localhost:8000", model_id=model.model_id
        )

    def wait_healthy(self, handle: ServerHandle, timeout_s: int) -> None:
        pass

    def stop(self, handle: ServerHandle) -> None:
        pass


# ---------------------------------------------------------------------------
# Testes de contrato — isinstance com runtime_checkable
# ---------------------------------------------------------------------------


class TestPortContracts:
    """Cada Protocol aceita seu stub via isinstance (runtime_checkable)."""

    def test_retriever_port_accepts_stub(self) -> None:
        assert isinstance(_StubRetriever(), RetrieverPort)

    def test_generator_port_accepts_stub(self) -> None:
        assert isinstance(_StubGenerator(), GeneratorPort)

    def test_metric_suite_port_accepts_stub(self) -> None:
        assert isinstance(_StubMetricSuite(), MetricSuitePort)

    def test_rubric_judge_port_accepts_stub(self) -> None:
        assert isinstance(_StubRubricJudge(), RubricJudgePort)

    def test_deterministic_metric_port_accepts_stub(self) -> None:
        assert isinstance(_StubDeterministicMetric(), DeterministicMetricPort)

    def test_gold_chunk_reader_port_accepts_stub(self) -> None:
        assert isinstance(_StubGoldChunkReader(), GoldChunkReaderPort)

    def test_result_writer_port_accepts_stub(self) -> None:
        assert isinstance(_StubResultWriter(), ResultWriterPort)

    def test_result_reader_port_accepts_stub(self) -> None:
        assert isinstance(_StubResultReader(), ResultReaderPort)

    def test_stats_port_accepts_stub(self) -> None:
        assert isinstance(_StubStats(), StatsPort)

    def test_annotation_reader_port_accepts_stub(self) -> None:
        assert isinstance(_StubAnnotationReader(), AnnotationReaderPort)

    def test_vllm_server_manager_port_accepts_stub(self) -> None:
        assert isinstance(_StubVLLMServerManager(), VLLMServerManagerPort)

    def test_object_without_methods_rejected(self) -> None:
        """Objeto sem os métodos obrigatórios não satisfaz o Protocol."""
        assert not isinstance(object(), RetrieverPort)
        assert not isinstance(object(), GeneratorPort)
        assert not isinstance(object(), ResultWriterPort)


# ---------------------------------------------------------------------------
# Testes de instanciação dos DTOs auxiliares
# ---------------------------------------------------------------------------


class TestDTOInstantiation:
    """Todos os DTOs podem ser criados com valores válidos e são imutáveis."""

    def test_chunk(self) -> None:
        c = Chunk(id="c1", text="texto do chunk", score=0.95)
        assert c.id == "c1"
        assert c.text == "texto do chunk"
        assert c.score == pytest.approx(0.95)

    def test_chunk_is_immutable(self) -> None:
        c = Chunk(id="c1", text="txt", score=0.5)
        with pytest.raises(AttributeError):
            c.id = "outro"  # type: ignore[misc]

    def test_retrieval_result(self) -> None:
        chunk = Chunk(id="c1", text="txt", score=0.9)
        r = RetrievalResult(chunks=(chunk,), ids=("c1",), scores=(0.9,))
        assert len(r.chunks) == 1
        assert r.ids == ("c1",)

    def test_generation_output(self) -> None:
        g = GenerationOutput(
            text="resposta",
            tokens_in=10,
            tokens_out=5,
            latency_ms=200,
            batch_invariant=False,
        )
        assert g.text == "resposta"
        assert g.tokens_in == 10
        assert g.latency_ms == 200

    def test_evaluation_sample(self) -> None:
        s = EvaluationSample(
            question="O que é RAG?",
            ground_truth="Retrieval-Augmented Generation.",
            generated_answer="RAG combina retrieval com LLM.",
            contexts=("Contexto 1.", "Contexto 2."),
        )
        assert s.question == "O que é RAG?"
        assert len(s.contexts) == 2

    def test_layer1_metrics(self) -> None:
        m = Layer1Metrics(
            answer_correctness=0.8,
            answer_similarity=0.75,
            faithfulness=0.9,
            context_precision=0.85,
            context_recall=0.7,
            answer_relevancy=0.88,
        )
        assert m.faithfulness == pytest.approx(0.9)

    def test_layer1_metrics_allows_nan(self) -> None:
        m = Layer1Metrics(
            answer_correctness=_NAN,
            answer_similarity=_NAN,
            faithfulness=_NAN,
            context_precision=_NAN,
            context_recall=_NAN,
            answer_relevancy=_NAN,
        )
        assert math.isnan(m.answer_correctness)

    def test_rubric_result(self) -> None:
        r = RubricResult(score=4.0, feedback="Resposta precisa.")
        assert r.score == pytest.approx(4.0)
        assert r.feedback == "Resposta precisa."

    def test_rubric_result_nan_score(self) -> None:
        r = RubricResult(score=_NAN, feedback="Parsing falhou após retries.")
        assert math.isnan(r.score)

    def test_aux_metrics(self) -> None:
        a = AuxMetrics(bertscore_f1=0.82)
        assert a.bertscore_f1 == pytest.approx(0.82)

    def test_wilcoxon_report(self) -> None:
        w = WilcoxonReport(statistic=2.3, p_value=0.02, effect_size=0.4, n_pairs=13)
        assert w.n_pairs == 13
        assert w.p_value == pytest.approx(0.02)

    def test_friedman_report(self) -> None:
        f = FriedmanReport(
            statistic=9.1,
            p_value=0.01,
            post_hoc={"A vs B": 0.03, "A vs C": 0.04},
        )
        assert f.statistic == pytest.approx(9.1)
        assert "A vs B" in f.post_hoc

    def test_mlm_report(self) -> None:
        m = MLMReport(
            formula="score ~ base + (1|seed)",
            aic=115.0,
            bic=125.5,
            coef={"base": 0.12, "Intercept": 0.5},
        )
        assert m.formula == "score ~ base + (1|seed)"
        assert m.coef["base"] == pytest.approx(0.12)

    def test_critical_annotation(self) -> None:
        row_id = _make_row_id()
        ann = CriticalAnnotation(row_id=row_id, flag=1, note="Alucinação factual.")
        assert ann.flag == 1
        assert ann.note == "Alucinação factual."

    def test_critical_annotation_no_note(self) -> None:
        row_id = _make_row_id()
        ann = CriticalAnnotation(row_id=row_id, flag=0, note=None)
        assert ann.note is None

    def test_model_spec(self) -> None:
        spec = ModelSpec(
            model_id="prometheus-8x7b-v2.0",
            tensor_parallel_size=1,
            gpu_memory_utilization=0.9,
        )
        assert spec.tensor_parallel_size == 1
        assert spec.gpu_memory_utilization == pytest.approx(0.9)

    def test_server_handle(self) -> None:
        h = ServerHandle(
            process_id=4321,
            base_url="http://localhost:8001",
            model_id="prometheus-8x7b-v2.0",
        )
        assert h.process_id == 4321
        assert h.base_url == "http://localhost:8001"

    def test_result_frame(self) -> None:
        frame = _make_result_frame()
        assert len(frame.results) == 1

    def test_result_frame_empty(self) -> None:
        frame = ResultFrame(results=())
        assert frame.results == ()


# ---------------------------------------------------------------------------
# Testes de comportamento dos stubs (smoke — valida que retornam tipos corretos)
# ---------------------------------------------------------------------------


class TestStubBehavior:
    """Stubs retornam instâncias dos DTOs esperados (validação de integração leve)."""

    def test_stub_retriever_returns_retrieval_result(self) -> None:
        result = _StubRetriever().search(
            base=BaseId("IDx_400k"), question="O que é RAG?", top_k=5
        )
        assert isinstance(result, RetrievalResult)
        assert len(result.chunks) == 1

    async def test_stub_generator_returns_generation_output(self) -> None:
        chunk = Chunk(id="c1", text="ctx", score=0.9)
        output = await _StubGenerator().generate(
            llm=LLMId("llama3"),
            question="O que é RAG?",
            contexts=[chunk],
            seed=42,
            temperature=0.1,
        )
        assert isinstance(output, GenerationOutput)
        assert output.text == "resposta"

    def test_stub_metric_suite_returns_layer1_metrics(self) -> None:
        sample = EvaluationSample(
            question="O que é RAG?",
            ground_truth="Retrieval-Augmented Generation.",
            generated_answer="RAG.",
            contexts=("ctx",),
        )
        metrics = _StubMetricSuite().score(sample)
        assert isinstance(metrics, Layer1Metrics)

    def test_stub_result_writer_exists_returns_bool(self) -> None:
        writer = _StubResultWriter()
        row_id = _make_row_id()
        assert writer.exists(row_id) is False

    def test_stub_stats_returns_reports(self) -> None:
        frame = _make_result_frame()
        stats = _StubStats()
        w = stats.wilcoxon_paired(frame, "answer_correctness")
        f = stats.friedman_nemenyi(frame, "answer_correctness")
        m = stats.mixed_linear_model(frame, "score ~ base + (1|seed)")
        assert isinstance(w, WilcoxonReport)
        assert isinstance(f, FriedmanReport)
        assert isinstance(m, MLMReport)

    def test_stub_vllm_manager_lifecycle(self) -> None:
        manager = _StubVLLMServerManager()
        spec = ModelSpec(
            model_id="llama3-8b",
            tensor_parallel_size=1,
            gpu_memory_utilization=0.85,
        )
        handle = manager.start(spec)
        assert isinstance(handle, ServerHandle)
        assert handle.model_id == "llama3-8b"
        manager.wait_healthy(handle, timeout_s=60)
        manager.stop(handle)
