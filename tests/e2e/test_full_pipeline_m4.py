"""E2E M4 — Gate de decisão executiva completa (TAREFA-409).

Pipeline E2E de 5 etapas, sem GPU nem vLLM real, determinístico:
  1. Anotação: CLI annotate --export + IngestHumanAnnotationUseCase (fixture JSONL real)
  2. Agregação: AggregateResultsUseCase -> 6 ConfigAggregates (2 bases x 3 LLMs)
  3. Análise estatística: StatisticalAnalysisUseCase -> StatsReport JSON
  4. Visualização: MatplotlibVisualizationAdapter -> 6 SVGs válidos
  5. Relatório HTML: HTMLReportAdapter + smoke dos 5 subcomandos CLI

Gating:
  - E2E_ENABLED=1 (mesma convenção do M1/M2)
  - Qdrant via testcontainers (session-scope) ou QDRANT_URL; pulado sem Docker

Dados de fixture: 5 perguntas x 2 bases x 3 LLMs = 30 EvaluationResults no
Parquet, 1 com final_score NaN (q_005, ID_230K, llm-gamma). Garante:
  - 6 ConfigAggregates com n_nan_excluded >= 1
  - 5 pares válidos para Wilcoxon (>= min_pairs_wilcoxon=5)
  - 9 blocos comuns para Friedman (3 LLMs x 5 perguntas x 2 bases - 1 NaN)

Fixture de anotação: tests/fixtures/e2e_m4_annotation.jsonl (3 itens, flags 0/1/null).
Row_ids determinísticos: q_001/ID_230K/{llm-alpha, llm-beta, llm-gamma} x seed=42.
respx.mock: envolve todo HTTP para garantir ausência de vazamentos de rede.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import xml.etree.ElementTree
from collections.abc import Generator
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest
import respx
from typer.testing import CliRunner

from inteligenciomica_eval.application.aggregate_results import (
    AggregateResultsInput,
    AggregateResultsUseCase,
)
from inteligenciomica_eval.application.statistical_analysis import (
    StatisticalAnalysisUseCase,
    StatisticsInput,
)
from inteligenciomica_eval.application.use_cases.ingest_annotation import (
    IngestAnnotationInput,
    IngestHumanAnnotationUseCase,
)
from inteligenciomica_eval.cli import app
from inteligenciomica_eval.domain.entities import (
    EvaluationResult,
    GeneratedAnswer,
    Question,
)
from inteligenciomica_eval.domain.ports import ResultFrame
from inteligenciomica_eval.domain.services.aggregation import AggregationService
from inteligenciomica_eval.domain.services.rank_score import (
    DEFAULT_WEIGHTS,
    RankScoreCalculator,
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
from inteligenciomica_eval.infrastructure.adapters.html_report import HTMLReportAdapter
from inteligenciomica_eval.infrastructure.adapters.stats_adapters import (
    FriedmanNemenyiAdapter,
    MixedLinearModelAdapter,
    WilcoxonAdapter,
)
from inteligenciomica_eval.infrastructure.config.adapter_configs import (
    VisualizationAdapterConfig,
)
from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
    ParquetStorage,
)
from inteligenciomica_eval.visualization.matplotlib_adapter import (
    MatplotlibVisualizationAdapter,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.getenv("E2E_ENABLED"),
        reason="set E2E_ENABLED=1 to run the M4 E2E gate (< 90s CPU, sem GPU)",
    ),
]

# ---------------------------------------------------------------------------
# Constantes de fixture
# ---------------------------------------------------------------------------

_RUN_ID = "e2e_m4_gate_run"
_ROUND_ID = "round_1"
_PHASE = "A"
_BASES = ["ID_230K", "IDx_400k"]
_LLMS = ["llm-alpha", "llm-beta", "llm-gamma"]
_QUESTIONS = [f"q_{i:03d}" for i in range(1, 6)]  # q_001 ... q_005
_SEED = 42

# Fixture JSONL de anotação com row_ids determinísticos (q_001/ID_230K/llm-{a,b,g})
_ANNOTATION_FIXTURE = (
    Path(__file__).parent.parent / "fixtures" / "e2e_m4_annotation.jsonl"
)

# Qdrant — coleção de gold chunks de M4 gate
_COLLECTION_M4 = "bio_chunks_m4_gate"
_VECTOR_SIZE = 8
_CHUNK_TEXTS = [
    f"Contexto biomédico de referência para {q}: tratamento clínico especializado."
    for q in _QUESTIONS
]

# Final scores por (question_id, base, llm). NaN para q_005/ID_230K/llm-gamma.
_SCORES: dict[tuple[str, str, str], float] = (
    {(q, "IDx_400k", "llm-alpha"): 0.80 for q in _QUESTIONS}
    | {(q, "IDx_400k", "llm-beta"): 0.62 for q in _QUESTIONS}
    | {(q, "IDx_400k", "llm-gamma"): 0.55 for q in _QUESTIONS}
    | {(q, "ID_230K", "llm-alpha"): 0.72 for q in _QUESTIONS}
    | {(q, "ID_230K", "llm-beta"): 0.58 for q in _QUESTIONS}
    | {(q, "ID_230K", "llm-gamma"): 0.48 for q in _QUESTIONS}
)
# Substituir último elemento por NaN -> n_nan_excluded >= 1
_SCORES[(_QUESTIONS[-1], "ID_230K", "llm-gamma")] = float("nan")

_ROUND_CONFIG_YAML = """\
round_id: "round_1"
model_registry_path: "model_registry.yaml"
phases:
  - "A"
bases:
  - "IDx_400k"
  - "ID_230K"
llms:
  - "llm-alpha"
  - "llm-beta"
  - "llm-gamma"
seeds:
  - 42
temperature: 0.0
retrieval:
  top_k: 5
  reranker: null
  embedding_model: "test-embed-model"
  chunk_strategy: "fixed-512"
judge:
  model: "prometheus-8x7b-v2.0"
  endpoint_env: "VLLM_JUDGE_URL"
  batch_invariant: true
  temperature: 0.0
scoring:
  weights:
    answer_correctness:  0.25
    answer_similarity:   0.15
    faithfulness:        0.20
    context_precision:   0.10
    context_recall:      0.10
    answer_relevancy:    0.05
    bertscore_f1:        0.05
    rubric_biomed_score: 0.10
  failure_threshold: 0.30
experiment_b:
  canonical_context_source: "IDx_400k"
  canonical_top_k: 5
"""


# ---------------------------------------------------------------------------
# Docker / Qdrant availability
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    """Return True if a reachable Docker daemon is available."""
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


def _dense_vec(seed_offset: int) -> list[float]:
    """Return a deterministic unit-normalised vector keyed by an integer."""
    raw = [((seed_offset * 31 + i * 7) % 17) / 17.0 + 0.1 for i in range(_VECTOR_SIZE)]
    norm = sum(x * x for x in raw) ** 0.5 or 1.0
    return [x / norm for x in raw]


# ---------------------------------------------------------------------------
# Fixtures de infraestrutura (Qdrant — session + function scope)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qdrant_url() -> Generator[str, None, None]:
    """Yield Qdrant base URL.

    Resolution order:
      1. QDRANT_URL env var (job e2e do CI, services.qdrant).
      2. testcontainers quando Docker disponível localmente.
      3. pytest.skip se nenhum backend alcançável.
    """
    env_url = os.getenv("QDRANT_URL")
    if env_url:
        yield env_url
        return

    if not _docker_available():
        pytest.skip("no Qdrant backend: set QDRANT_URL or start a Docker daemon")

    from testcontainers.qdrant import QdrantContainer

    with QdrantContainer() as container:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(6333)
        yield f"http://{host}:{port}"


@pytest.fixture()
def populated_collection(qdrant_url: str) -> Generator[str, None, None]:
    """Cria coleção com 5 gold chunks (scope=function); deleta no teardown."""
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.http.models import Distance, PointStruct, VectorParams

    async def _setup() -> None:
        client = AsyncQdrantClient(url=qdrant_url)
        try:
            if await client.collection_exists(_COLLECTION_M4):
                await client.delete_collection(_COLLECTION_M4)
            await client.create_collection(
                _COLLECTION_M4,
                vectors_config=VectorParams(
                    size=_VECTOR_SIZE, distance=Distance.COSINE
                ),
            )
            points = [
                PointStruct(id=i, vector=_dense_vec(i), payload={"text": text})
                for i, text in enumerate(_CHUNK_TEXTS)
            ]
            await client.upsert(collection_name=_COLLECTION_M4, points=points)
        finally:
            await client.close()

    async def _teardown() -> None:
        client = AsyncQdrantClient(url=qdrant_url)
        try:
            if await client.collection_exists(_COLLECTION_M4):
                await client.delete_collection(_COLLECTION_M4)
        finally:
            await client.close()

    asyncio.run(_setup())
    yield _COLLECTION_M4
    asyncio.run(_teardown())


# ---------------------------------------------------------------------------
# Builders de dados de teste
# ---------------------------------------------------------------------------


def _make_metrics(fs: float) -> MetricVector:
    """Aproxima MetricVector a partir de final_score. NaN -> todos NaN."""
    nan = float("nan")
    if math.isnan(fs):
        return MetricVector(nan, nan, nan, nan, nan, nan, nan, nan)
    return MetricVector(
        answer_correctness=round(fs * 0.90 + 0.05, 4),
        answer_similarity=round(fs * 0.85 + 0.07, 4),
        faithfulness=round(fs * 0.92 + 0.03, 4),
        context_precision=round(fs * 0.80 + 0.08, 4),
        context_recall=round(fs * 0.88 + 0.06, 4),
        answer_relevancy=round(fs * 0.91 + 0.04, 4),
        bertscore_f1=round(fs * 0.87 + 0.05, 4),
        rubric_biomed_score=round(fs * 0.95 + 0.02, 4),
    )


def _make_eval_results() -> list[EvaluationResult]:
    """Constrói 30 EvaluationResults (5 perguntas x 2 bases x 3 LLMs, 1 NaN)."""
    results: list[EvaluationResult] = []
    for q_id in _QUESTIONS:
        for base_str in _BASES:
            for llm_str in _LLMS:
                row_id = RowId.from_cell(
                    run_id=_RUN_ID,
                    phase=_PHASE,
                    base=base_str,
                    llm=llm_str,
                    seed=_SEED,
                    question_id=q_id,
                )
                question = Question(
                    question_id=q_id,
                    text=f"Pergunta biomédica {q_id} sobre tratamento clínico?",
                    ground_truth=f"Resposta de referência biomédica para {q_id}.",
                )
                answer = GeneratedAnswer(
                    row_id=row_id,
                    question=question,
                    base=BaseId(base_str),
                    llm=LLMId(llm_str),
                    seed=Seed(_SEED),
                    phase=_PHASE,
                    generated_answer=(
                        f"Resposta gerada por {llm_str} para {q_id} "
                        f"usando base {base_str}."
                    ),
                    retrieved_chunk_ids=("chunk_001",),
                    retrieved_chunks_text=(
                        "Contexto biomédico relevante para a pergunta.",
                    ),
                    retrieval_scores=(0.9,),
                )
                fs_val = _SCORES.get((q_id, base_str, llm_str), 0.5)
                results.append(
                    EvaluationResult(
                        answer=answer,
                        metrics=_make_metrics(fs_val),
                        final_score=FinalScore(fs_val),
                        determinism_regime=DeterminismRegime.GENERATOR,
                        critical_failure_flag=None,
                        critical_failure_note=None,
                    )
                )
    return results


# ---------------------------------------------------------------------------
# Teste E2E principal — 5 etapas (TAREFA-409, §14.7)
# ---------------------------------------------------------------------------


def test_full_pipeline_m4(tmp_path: Path, populated_collection: Any) -> None:
    """Gate E2E de M4: 5 etapas de decisão executiva, < 90s em CPU."""
    runner = CliRunner()

    # Setup: diretório de dados e config YAML
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    config_path = tmp_path / "round_config.yaml"
    config_path.write_text(_ROUND_CONFIG_YAML, encoding="utf-8")

    # Escrever 30 EvaluationResults no Parquet (determinístico, sem GPU/vLLM)
    eval_results = _make_eval_results()
    storage = ParquetStorage(
        base_dir=data_dir,
        run_id=_RUN_ID,
        round_id=_ROUND_ID,
    )
    for r in eval_results:
        storage.append(r)

    result_frame = ResultFrame(results=tuple(eval_results))

    # respx.mock envolve todo HTTP — garante ausência de vazamentos de rede.
    # A pipeline de M4 (anotação→agregação→stats→viz→HTML) não faz chamadas HTTP;
    # o mock protege contra regressões acidentais.
    with respx.mock:
        # ==================================================================
        # ETAPA 1 — Anotação: export JSONL + ingestão via fixture real
        # ==================================================================
        export_path = tmp_path / "export_annotations.jsonl"

        export_result = runner.invoke(
            app,
            [
                "annotate",
                "--config",
                str(config_path),
                "--run-id",
                _RUN_ID,
                "--export",
                str(export_path),
                "--threshold",
                "0.75",
            ],
        )
        assert export_result.exit_code == 0, (
            f"annotate --export falhou (exit={export_result.exit_code}):\n"
            f"{export_result.output}"
        )
        assert export_path.exists(), "JSONL de export não foi criado"

        jsonl_lines = [
            json.loads(line)
            for line in export_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(jsonl_lines) > 0, "Export JSONL está vazio"
        assert all("critical_failure_flag" in line for line in jsonl_lines), (
            "Campo critical_failure_flag ausente em alguma linha do export"
        )
        # No export, flag deve ser null (especialista ainda não anotou)
        assert all(line["critical_failure_flag"] is None for line in jsonl_lines), (
            "Export deve conter critical_failure_flag=null para todas as linhas"
        )

        # Ingestão via fixture pré-editada (tests/fixtures/e2e_m4_annotation.jsonl)
        # Row_ids: q_001/ID_230K/llm-alpha (flag=0), /llm-beta (flag=1), /llm-gamma (null)
        assert _ANNOTATION_FIXTURE.exists(), (
            f"Fixture de anotação não encontrada: {_ANNOTATION_FIXTURE}"
        )
        writer = ParquetStorage(base_dir=data_dir, run_id=_RUN_ID, round_id=_ROUND_ID)
        ingest_uc = IngestHumanAnnotationUseCase(writer=writer)
        ingest_output = ingest_uc.execute(
            IngestAnnotationInput(annotations_path=_ANNOTATION_FIXTURE, run_id=_RUN_ID)
        )
        assert ingest_output.n_ingested > 0, (
            f"Nenhuma linha ingerida (n_ingested={ingest_output.n_ingested}); "
            f"n_missing_row_id={ingest_output.n_missing_row_id}"
        )
        assert ingest_output.n_invalid == 0, (
            f"Linhas inválidas encontradas (n_invalid={ingest_output.n_invalid})"
        )

        # ==================================================================
        # ETAPA 2 — Agregação: 6 ConfigAggregates (2 bases x 3 LLMs)
        # ==================================================================
        reader_storage = ParquetStorage(base_dir=data_dir, round_id=_ROUND_ID)
        agg_uc = AggregateResultsUseCase(
            reader=reader_storage,
            aggregation_service=AggregationService(
                rank_calculator=RankScoreCalculator(weights=DEFAULT_WEIGHTS)
            ),
            data_dir=data_dir,
        )
        agg_output = agg_uc.execute(
            AggregateResultsInput(run_id=_RUN_ID, round_id=_ROUND_ID)
        )

        assert len(agg_output.aggregates) == 6, (
            f"Esperados 6 ConfigAggregates (2x3), obtidos {len(agg_output.aggregates)}"
        )
        assert agg_output.best_config is not None, "best_config é None"
        assert agg_output.n_nan_excluded >= 1, (
            f"Esperado n_nan_excluded >= 1, obtido {agg_output.n_nan_excluded}"
        )
        # Ordenação decrescente por rank_score (NaN -> float("-inf") via _rank_key)
        first_rs = agg_output.aggregates[0].rank_score.value
        last_rs = agg_output.aggregates[-1].rank_score.value
        assert math.isnan(last_rs) or first_rs >= last_rs, (
            "Agregados não estão ordenados por rank_score decrescente"
        )

        # ==================================================================
        # ETAPA 3 — Análise estatística: StatsReport JSON
        # ==================================================================
        stats_uc = StatisticalAnalysisUseCase(
            reader=ParquetStorage(base_dir=data_dir, round_id=_ROUND_ID),
            wilcoxon_adapter=WilcoxonAdapter(),
            friedman_adapter=FriedmanNemenyiAdapter(),
            mlm_adapter=MixedLinearModelAdapter(),
            data_dir=data_dir,
        )
        stats_output = stats_uc.execute(
            StatisticsInput(run_id=_RUN_ID, round_id=_ROUND_ID)
        )

        stats_json_path = data_dir / f"{_RUN_ID}_{_ROUND_ID}_stats.json"
        assert stats_json_path.exists(), f"Stats JSON não criado em {stats_json_path}"

        assert hasattr(stats_output, "base_difference_significant"), (
            "StatsReport sem campo base_difference_significant"
        )
        assert hasattr(stats_output, "llm_difference_significant"), (
            "StatsReport sem campo llm_difference_significant"
        )
        assert hasattr(stats_output, "interaction_significant"), (
            "StatsReport sem campo interaction_significant"
        )

        # ==================================================================
        # ETAPA 4 — Visualização: 6 SVGs válidos
        # ==================================================================
        plots_dir = tmp_path / "plots"
        plots_dir.mkdir()
        viz = MatplotlibVisualizationAdapter(config=VisualizationAdapterConfig())
        aggregates = list(agg_output.aggregates)

        figure_paths = [
            viz.plot_rankscore_heatmap(aggregates, output_dir=plots_dir),
            viz.plot_finalscore_boxplots(aggregates, output_dir=plots_dir),
            viz.plot_interaction(aggregates, output_dir=plots_dir),
            viz.plot_radar(aggregates, output_dir=plots_dir, top_n=3),
            viz.plot_per_question_ranking(result_frame, output_dir=plots_dir),
            viz.plot_failure_breakdown(aggregates, output_dir=plots_dir),
        ]

        assert len(figure_paths) == 6, f"Esperados 6 plots, obtidos {len(figure_paths)}"
        for fpath in figure_paths:
            assert fpath.path.exists(), f"SVG não criado: {fpath.path}"
            assert fpath.path.stat().st_size > 0, f"SVG vazio: {fpath.path}"
            xml.etree.ElementTree.fromstring(fpath.path.read_text(encoding="utf-8"))

        # ==================================================================
        # ETAPA 5 — Relatório HTML autocontido + CLI smoke
        # ==================================================================
        report_adapter = HTMLReportAdapter()
        report_path = report_adapter.generate_html(
            run_id=_RUN_ID,
            aggregates=aggregates,
            results=result_frame,
            stats_report=stats_output,
            figure_paths=figure_paths,
            output_path=tmp_path / "report_m4_e2e.html",
        )

        html = report_path.path.read_text(encoding="utf-8")

        assert report_path.path.stat().st_size > 30_000, (
            f"HTML menor que 30KB: {report_path.path.stat().st_size} bytes"
        )

        for section_id in [
            "cabecalho",
            "ranking-executivo",
            "visualizacoes",
            "resultados-estatisticos",
            "nota-metodologica",
        ]:
            assert f'id="{section_id}"' in html, (
                f'Seção id="{section_id}" ausente no HTML'
            )

        n_svg = html.count("data:image/svg+xml;base64,")
        assert n_svg == 6, f"Esperados 6 SVGs embutidos, encontrados {n_svg}"

        assert "http" not in html.lower(), (
            "HTML contém URL externa (violação Nota M4 item 5 — autocontido)"
        )

        html_parser = HTMLParser()
        html_parser.feed(html)

        # ------------------------------------------------------------------
        # CLI smoke — --help dos 5 subcomandos obrigatórios
        # ------------------------------------------------------------------
        for subcmd in ["analyze", "report", "status", "show-config", "annotate"]:
            r = runner.invoke(app, [subcmd, "--help"])
            assert r.exit_code == 0, (
                f"--help falhou para subcomando '{subcmd}' "
                f"(exit={r.exit_code}):\n{r.output}"
            )

        r_status = runner.invoke(app, ["status", "--run-id", "run_inexistente_xyz"])
        assert r_status.exit_code == 0, (
            f"status run_inexistente deveria sair com 0, obtido {r_status.exit_code}"
        )
        assert (
            "não encontrado" in r_status.output
            or "not found" in r_status.output.lower()
        ), f"Mensagem amigável ausente na saída: {r_status.output!r}"
