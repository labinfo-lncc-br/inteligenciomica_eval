"""DI wiring — conecta adapters reais (ou fakes) aos use cases (TAREFA-309).

ADR-001 extensão aprovada: wiring em ``infrastructure/`` conecta adapters ↔ use cases
sem framework DI de terceiros (containers de DI violam a inversão de dependência limpa;
um dataclass simples é suficiente e auditável). Referência: ADR-001, §8 blueprint.

Dois pontos de entrada públicos:
- :func:`build_container` — adapters reais; valida env vars obrigatórias.
- :func:`build_fake_container` — fakes de ``tests/`` (lazy import); usado em ``--dry-run``
  e em testes unitários sem necessidade de rede/GPU.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from inteligenciomica_eval.application.services.wave_scheduler import (
    WaveSchedulerService,
)
from inteligenciomica_eval.application.use_cases.annotation_workflow import (
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
from inteligenciomica_eval.domain.errors import ConfigValidationError
from inteligenciomica_eval.domain.ports import (
    DeterministicMetricPort,
    GeneratorFactory,
    GeneratorPort,
    MetricSuitePort,
    ModelSpec,
    ResultReaderPort,
    ResultWriterPort,
    RetrieverPort,
    RubricJudgePort,
    VLLMServerManagerPort,
)
from inteligenciomica_eval.domain.services.aggregation import AggregationService
from inteligenciomica_eval.domain.services.rank_score import RankScoreCalculator
from inteligenciomica_eval.domain.value_objects import ModelWaveSpec
from inteligenciomica_eval.infrastructure.benchmark.loader import load_questions
from inteligenciomica_eval.infrastructure.config.schema import RoundConfig
from inteligenciomica_eval.infrastructure.config.settings import RuntimeSettings

if TYPE_CHECKING:
    pass

_log = structlog.get_logger(__name__)

# Env vars obrigatórias cuja ausência impede a execução real (ADR-008).
_REQUIRED_ENDPOINTS = (
    "VLLM_GENERATOR_URL",
    "VLLM_JUDGE_URL",
    "QDRANT_URL",
)
_NOT_SET = "<not set>"


# ---------------------------------------------------------------------------
# Vista estrutural de configuração (satisfaz ExperimentConfigView + RunConfigView)
# ---------------------------------------------------------------------------


@dataclass
class _RetrievalConfig:
    """Satisfaz _RetrievalView exigido por RunConfigView (structural duck-typing)."""

    top_k: int


@dataclass
class _ExperimentConfig:
    """Adaptador de RoundConfig + registry → ExperimentConfigView + RunConfigView.

    Constrói os campos extras que o RunExperimentUseCase e RunGenerationPassUseCase
    precisam mas que não existem diretamente no RoundConfig Pydantic.
    """

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
    retrieval: _RetrievalConfig


# ---------------------------------------------------------------------------
# DIContainer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DIContainer:
    """Container de injeção de dependência para o ciclo completo de avaliação.

    Todos os campos são tipados com o Protocol/Port correto — a camada de wiring
    é a única com permissão de instanciar adapters concretos (ADR-001 §8).

    Args:
        retriever: adapter de retrieval vetorial (Qdrant ou fake).
        generator_factory: factory de gerador LLM por URL de servidor.
        metric_suite: adapter de métricas RAGAS (Camada 1).
        deterministic_metric: adapter de métricas determinísticas (BERTScore/ROUGE).
        rubric_judge: adapter do juiz biomédico (Prometheus).
        server_manager: adapter de ciclo de vida dos servidores vLLM.
        wave_scheduler: serviço de planejamento de ondas.
        gen_pass_uc: use case de geração (Passada 1).
        metrics_pass_uc: use case de métricas (Passada 2).
        judge_pass_uc: use case do juiz (Passada 3).
        experiment_uc: orquestrador do ciclo completo A+B.
        annotation_uc: use case de anotação humana (Camada 3).
        writer: port de persistência de resultados.
        reader: port de leitura de resultados.
        agg_service: serviço de agregação de domínio.
        rank_calc: calculadora de RankScore.
        benchmark_loader: callable zero-args → lista de perguntas RF1.
    """

    retriever: RetrieverPort
    generator_factory: GeneratorFactory
    metric_suite: MetricSuitePort
    deterministic_metric: DeterministicMetricPort
    rubric_judge: RubricJudgePort
    server_manager: VLLMServerManagerPort
    wave_scheduler: WaveSchedulerService
    gen_pass_uc: RunGenerationPassUseCase
    metrics_pass_uc: RunMetricsPassUseCase
    judge_pass_uc: RunJudgePassUseCase
    experiment_uc: RunExperimentUseCase
    annotation_uc: AnnotationWorkflowUseCase
    writer: ResultWriterPort
    reader: ResultReaderPort
    agg_service: AggregationService
    rank_calc: RankScoreCalculator
    benchmark_loader: Callable[[], list[Question]]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_endpoints(settings: RuntimeSettings) -> None:
    """Verifica env vars obrigatórias; levanta ConfigValidationError se ausentes."""
    missing = [
        name
        for name in _REQUIRED_ENDPOINTS
        if getattr(settings, name, _NOT_SET) == _NOT_SET
    ]
    if missing:
        raise ConfigValidationError(
            missing[0],
            f"Variável de ambiente obrigatória não configurada: {missing[0]}. "
            "Defina-a antes de executar o ciclo real.",
        )


def _entry_to_model_spec(entry: object, max_model_len: int) -> ModelSpec:
    """Converte ModelEntry do registry para ModelSpec de domínio."""
    # Convenção de porta: 8000 + gpu_index (ADR-012 layout fixo).
    port = 8000 + entry.gpu_index  # type: ignore[attr-defined]
    return ModelSpec(
        model=entry.name,  # type: ignore[attr-defined]
        port=port,
        quantization=entry.quantization,  # type: ignore[attr-defined]
        tensor_parallel_size=entry.tensor_parallel_size,  # type: ignore[attr-defined]
        max_model_len=max_model_len,
        gpu_index=entry.gpu_index,  # type: ignore[attr-defined]
        batch_invariant=entry.batch_invariant,  # type: ignore[attr-defined]
        extra_args=entry.extra_args,  # type: ignore[attr-defined]
    )


class _VLLMGeneratorFactory:
    """GeneratorFactory concreta para produção (ADR-008 — URL de env var, não YAML)."""

    def __init__(self, port_to_model: dict[int, str]) -> None:
        self._port_to_model = port_to_model

    def __call__(self, url: str) -> GeneratorPort:
        from inteligenciomica_eval.infrastructure.adapters.vllm_generator import (
            VLLMGeneratorAdapter,
        )

        # Extrai porta de URL como "http://host:PORT/v1"
        try:
            port = int(url.split(":")[2].split("/")[0])
            model = self._port_to_model.get(port, "model")
        except (IndexError, ValueError):
            model = "model"
        return VLLMGeneratorAdapter(url=url, model=model)


# ---------------------------------------------------------------------------
# build_container — adapters reais
# ---------------------------------------------------------------------------


def build_container(
    config: RoundConfig,
    settings: RuntimeSettings,
    *,
    config_dir: Path | None = None,
    serial: bool = False,
    phases: list[str] | None = None,
) -> DIContainer:
    """Instancia o DIContainer com adapters reais.

    Valida env vars obrigatórias antes de instanciar qualquer adapter. Se alguma
    variável estiver no valor sentinela ``"<not set>"``, levanta
    :class:`~inteligenciomica_eval.domain.errors.ConfigValidationError` imediatamente.

    Args:
        config: configuração validada da rodada (schema Pydantic).
        settings: settings de runtime (env vars, secrets).
        config_dir: diretório base para resolver ``model_registry_path``.
            ``None`` → usa o diretório de trabalho atual.
        serial: se ``True``, desabilita ondas concorrentes (``allow_concurrent_models=False``).
            Modo conservador; contra ADR-012; para debug ou hardware single-GPU.
        phases: filtra as fases a executar (ex: ``["A"]`` ou ``["B"]``).
            ``None`` → usa as fases definidas no YAML (``config.phases``).

    Returns:
        :class:`DIContainer` com todos os adapters instanciados.

    Raises:
        ConfigValidationError: se ``VLLM_GENERATOR_URL``, ``VLLM_JUDGE_URL`` ou
            ``QDRANT_URL`` não estiver configurada.
    """
    _validate_endpoints(settings)

    from inteligenciomica_eval.application.use_cases.annotation_workflow import (
        AnnotationConfig as AppAnnotationConfig,
    )
    from inteligenciomica_eval.domain.services.final_score import FinalScoreCalculator
    from inteligenciomica_eval.domain.services.rank_score import DEFAULT_WEIGHTS
    from inteligenciomica_eval.infrastructure.adapters.deterministic_metrics import (
        DeterministicMetricsAdapter,
    )
    from inteligenciomica_eval.infrastructure.adapters.prometheus_judge import (
        PrometheusJudgeAdapter,
    )
    from inteligenciomica_eval.infrastructure.adapters.qdrant_retriever import (
        QdrantRetrieverAdapter,
    )
    from inteligenciomica_eval.infrastructure.adapters.ragas_metrics import (
        RAGASLayer1Adapter,
    )
    from inteligenciomica_eval.infrastructure.adapters.vllm_server_manager import (
        VLLMServerManagerAdapter,
    )
    from inteligenciomica_eval.infrastructure.config.adapter_configs import (
        RagasAdapterConfig,
    )
    from inteligenciomica_eval.infrastructure.config.model_registry import (
        load_model_registry,
        to_wave_spec,
    )
    from inteligenciomica_eval.infrastructure.prompts.registry import (
        get_default_registry,
    )
    from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
        ParquetStorage,
    )

    base_dir = config_dir if config_dir is not None else Path.cwd()
    registry_path = base_dir / config.model_registry_path

    try:
        registry = load_model_registry(registry_path)
    except FileNotFoundError:
        # Registry não disponível — continua com model_registry/model_spec_map vazios.
        # A rodada real falhará ao planejar ondas; o gate de produção depende do registry.
        _log.warning(
            "model_registry_not_found",
            path=str(registry_path),
            message="Ondas não poderão ser planejadas sem o registry.",
        )
        registry_entries: list[object] = []
        wave_specs: tuple[ModelWaveSpec, ...] = ()
    else:
        registry_entries = list(registry.models)
        wave_specs = tuple(to_wave_spec(e) for e in registry.models)

    max_model_len = settings.VLLM_DEFAULT_MAX_MODEL_LEN
    model_spec_map: dict[str, ModelSpec] = {
        e.name: _entry_to_model_spec(e, max_model_len)  # type: ignore[attr-defined]
        for e in registry_entries
    }

    # Filtra fases se --phase foi especificado; caso contrário usa o YAML.
    phases_to_run = phases if phases is not None else config.phases

    exp_config = _ExperimentConfig(
        phases=phases_to_run,
        bases=config.bases,
        seeds=config.seeds,
        llms=config.llms,
        temperature=config.temperature,
        round_id=config.round_id,
        startup_timeout_s=settings.VLLM_STARTUP_TIMEOUT_S,
        failure_threshold=config.scoring.failure_threshold,
        top_k=config.retrieval.top_k,
        canonical_context_base=(
            config.experiment_b.canonical_context_source
            if config.experiment_b is not None
            else "IDx_400k"
        ),
        canonical_top_k=(
            config.experiment_b.canonical_top_k
            if config.experiment_b is not None
            else 5
        ),
        model_registry=wave_specs,
        model_spec_map=model_spec_map,
        retrieval=_RetrievalConfig(top_k=config.retrieval.top_k),
    )

    # --- Adapters de armazenamento ---
    data_dir = base_dir / "data"
    storage = ParquetStorage(base_dir=data_dir, round_id=config.round_id)

    # --- Adapters de rede ---
    collection_map = {base: base for base in config.bases}
    retriever = QdrantRetrieverAdapter(
        url=settings.QDRANT_URL,
        collection_map=collection_map,
        top_k=config.retrieval.top_k,
    )

    judge_url = settings.VLLM_JUDGE_URL
    prompt_registry = get_default_registry()
    rubric_judge = PrometheusJudgeAdapter(
        judge_url=judge_url,
        registry=prompt_registry,
        model=config.judge.model,
    )

    ragas_config = RagasAdapterConfig(
        judge_url=judge_url,
        judge_model=config.judge.model,
    )
    metric_suite = RAGASLayer1Adapter(config=ragas_config)
    deterministic_metric = DeterministicMetricsAdapter()
    server_manager = VLLMServerManagerAdapter()

    port_to_model = {spec.port: name for name, spec in model_spec_map.items()}
    generator_factory = _VLLMGeneratorFactory(port_to_model)

    # --- BenchmarkLoader — carregado cedo para obter n_questions correto ---
    questions_path_str = settings.BENCHMARK_QUESTIONS_PATH
    questions_path: Path | None = (
        Path(questions_path_str) if questions_path_str else None
    )
    _loaded_questions = load_questions(questions_path)

    def benchmark_loader() -> list[Question]:
        return list(_loaded_questions)

    # --- Serviços de domínio ---
    score_weights = dict(config.scoring.weights)
    final_score_calc = FinalScoreCalculator(weights=score_weights)
    rank_weights = DEFAULT_WEIGHTS
    rank_calc = RankScoreCalculator(weights=rank_weights)
    agg_service = AggregationService(rank_calculator=rank_calc)

    # n_questions derivado das perguntas carregadas; allow_concurrent_models controlado
    # por --serial (False = serial; True = concorrente, padrão ADR-012).
    wave_scheduler = WaveSchedulerService(
        n_questions=len(_loaded_questions),
        allow_concurrent_models=not serial,
    )

    # --- Use cases de passada ---
    gen_pass_uc = RunGenerationPassUseCase(
        retriever=retriever,
        generator=generator_factory(settings.VLLM_GENERATOR_URL),
        writer=storage,
        reader=storage,
        config=exp_config,  # type: ignore[arg-type]  # _RetrievalConfig satisfaz _RetrievalView estruturalmente
    )
    metrics_pass_uc = RunMetricsPassUseCase(
        metric_suite=metric_suite,
        deterministic=deterministic_metric,
        score_calc=final_score_calc,
        writer=storage,
        reader=storage,
    )
    judge_pass_uc = RunJudgePassUseCase(
        judge=rubric_judge,
        writer=storage,
        reader=storage,
        score_calc=final_score_calc,
    )

    # --- Anotação ---
    ann_cfg_schema = config.annotation
    annotation_uc = AnnotationWorkflowUseCase(
        reader=storage,
        writer=storage,
        config=AppAnnotationConfig(
            round_id=config.round_id,
            score_threshold=ann_cfg_schema.score_threshold if ann_cfg_schema else 0.6,
            rubric_threshold=ann_cfg_schema.rubric_threshold if ann_cfg_schema else 0.5,
            max_to_review=ann_cfg_schema.max_to_review if ann_cfg_schema else None,
        ),
    )

    # --- Orquestrador ---
    experiment_uc = RunExperimentUseCase(
        wave_scheduler=wave_scheduler,
        server_manager=server_manager,
        gen_pass_uc=gen_pass_uc,
        metrics_pass_uc=metrics_pass_uc,
        judge_pass_uc=judge_pass_uc,
        aggregation_service=agg_service,
        rank_calc=rank_calc,
        writer=storage,
        reader=storage,
        config=exp_config,
        retriever=retriever,
        generator_factory=generator_factory,
    )

    _log.info(
        "wiring_real_container_built",
        round_id=config.round_id,
        n_models_in_registry=len(registry_entries),
    )

    return DIContainer(
        retriever=retriever,
        generator_factory=generator_factory,
        metric_suite=metric_suite,
        deterministic_metric=deterministic_metric,
        rubric_judge=rubric_judge,
        server_manager=server_manager,
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
    )


# ---------------------------------------------------------------------------
# build_fake_container — fakes para dry-run e testes
# ---------------------------------------------------------------------------


def build_fake_container(config: RoundConfig) -> DIContainer:
    """Instancia o DIContainer com fakes (sem rede/GPU).

    Importa ``tests.fakes`` de forma LAZY (dentro desta função, nunca no topo
    do módulo) para evitar que o grafo de importação de produção puxe código
    de teste. Usado em ``--dry-run`` e nos testes unitários do wiring.

    Args:
        config: configuração validada da rodada.

    Returns:
        :class:`DIContainer` com todos os campos preenchidos por fakes/stubs.
    """
    # Lazy import de fakes — NUNCA no topo do módulo (ver docstring).
    # ``tests/`` é adicionado ao sys.path pelo pytest (rootdir) em contextos de teste
    # e deve estar em PYTHONPATH para uso via --dry-run fora do pytest.
    from fakes import (  # type: ignore[import-not-found]
        FakeDeterministicMetric,
        FakeGenerator,
        FakeMetricSuite,
        FakeRubricJudge,
        FakeVLLMServerManager,
        StubRetriever,
    )

    from inteligenciomica_eval.application.use_cases.annotation_workflow import (
        AnnotationConfig as AppAnnotationConfig,
    )
    from inteligenciomica_eval.domain.services.final_score import FinalScoreCalculator
    from inteligenciomica_eval.domain.services.rank_score import DEFAULT_WEIGHTS
    from inteligenciomica_eval.infrastructure.repositories.parquet_storage import (
        ParquetStorage,
    )

    data_dir = Path(tempfile.mkdtemp())
    storage = ParquetStorage(base_dir=data_dir, round_id=config.round_id)

    fake_generator = FakeGenerator()
    fake_retriever = StubRetriever()
    fake_metric_suite = FakeMetricSuite()
    fake_deterministic = FakeDeterministicMetric()
    fake_judge = FakeRubricJudge()
    fake_server_manager = FakeVLLMServerManager()

    score_weights = dict(config.scoring.weights)
    final_score_calc = FinalScoreCalculator(weights=score_weights)
    rank_weights = DEFAULT_WEIGHTS
    rank_calc = RankScoreCalculator(weights=rank_weights)
    agg_service = AggregationService(rank_calculator=rank_calc)

    # Pré-carrega as 2 primeiras perguntas do arquivo empacotado (suficiente para
    # dry-run e testes unitários; sem registry real).
    _fake_questions = load_questions(None)[:2]

    wave_scheduler = WaveSchedulerService(n_questions=len(_fake_questions))

    # ExperimentConfig mínimo compatível com as fakes (sem registry real)
    exp_config = _ExperimentConfig(
        phases=config.phases,
        bases=config.bases,
        seeds=config.seeds,
        llms=config.llms,
        temperature=config.temperature,
        round_id=config.round_id,
        startup_timeout_s=30,
        failure_threshold=config.scoring.failure_threshold,
        top_k=config.retrieval.top_k,
        canonical_context_base=(
            config.experiment_b.canonical_context_source
            if config.experiment_b is not None
            else "IDx_400k"
        ),
        canonical_top_k=(
            config.experiment_b.canonical_top_k
            if config.experiment_b is not None
            else 5
        ),
        model_registry=(),
        model_spec_map={},
        retrieval=_RetrievalConfig(top_k=config.retrieval.top_k),
    )

    def _fake_generator_factory(url: str) -> FakeGenerator:
        return FakeGenerator()

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
        score_calc=final_score_calc,
        writer=storage,
        reader=storage,
    )
    judge_pass_uc = RunJudgePassUseCase(
        judge=fake_judge,
        writer=storage,
        reader=storage,
        score_calc=final_score_calc,
    )

    ann_cfg_schema = config.annotation
    annotation_uc = AnnotationWorkflowUseCase(
        reader=storage,
        writer=storage,
        config=AppAnnotationConfig(
            round_id=config.round_id,
            score_threshold=ann_cfg_schema.score_threshold if ann_cfg_schema else 0.6,
            rubric_threshold=ann_cfg_schema.rubric_threshold if ann_cfg_schema else 0.5,
            max_to_review=ann_cfg_schema.max_to_review if ann_cfg_schema else None,
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
        return list(_fake_questions)

    _log.info("wiring_fake_container_built", round_id=config.round_id)

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
    )
