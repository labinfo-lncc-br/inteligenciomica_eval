from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from inteligenciomica_eval.domain.entities import EvaluationResult
from inteligenciomica_eval.domain.value_objects import (
    BaseId,
    DeterminismRegime,
    FinalScore,
    LLMId,
    MetricVector,
    RowId,
)
from inteligenciomica_eval.domain.value_objects import (
    FriedmanReport as FriedmanReport,
)
from inteligenciomica_eval.domain.value_objects import (
    MLMReport as MLMReport,
)
from inteligenciomica_eval.domain.value_objects import (
    NemenyiPair as NemenyiPair,
)
from inteligenciomica_eval.domain.value_objects import (
    WilcoxonReport as WilcoxonReport,
)

# ---------------------------------------------------------------------------
# DTOs auxiliares de domínio
# Frozen dataclasses puros — sem Pydantic, sem libs de I/O (§5.2, ADR-001).
# Pydantic é reservado à fronteira de adapter (§5.2).
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Chunk:
    """Chunk recuperado de uma base vetorial.

    Args:
        id: identificador único do chunk na base.
        text: conteúdo textual do chunk.
        score: score de similaridade/relevância retornado pelo retriever.
    """

    id: str
    text: str
    score: float


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    """Resultado completo de uma operação de recuperação vetorial.

    Args:
        chunks: tupla de chunks recuperados, na ordem de relevância.
        ids: tupla de identificadores dos chunks (mesma ordem).
        scores: tupla de scores de similaridade (mesma ordem).
    """

    chunks: tuple[Chunk, ...]
    ids: tuple[str, ...]
    scores: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class GenerationOutput:
    """Saída de um gerador LLM para uma pergunta com contextos.

    Args:
        text: texto da resposta gerada.
        tokens_in: número de tokens no prompt de entrada.
        tokens_out: número de tokens gerados na resposta.
        latency_ms: latência de geração em milissegundos.
        batch_invariant: ``True`` se o juiz usou regime BATCH_INVARIANT (ADR-003);
            ``False`` para geradores vLLM (§9.2.4).
    """

    text: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    batch_invariant: bool


@dataclass(frozen=True, slots=True)
class EvaluationSample:
    """Amostra de avaliação fornecida ao MetricSuitePort e ao RubricJudgePort.

    Args:
        question_id: identificador único da pergunta — rastreado no schema §5.3
            e registrado em todos os eventos de log dos adapters de avaliação (I6).
        question: enunciado da pergunta avaliada.
        ground_truth: resposta de referência humana.
        generated_answer: resposta gerada pelo LLM sob avaliação.
        contexts: tupla de textos de contexto recuperados (chunks).
    """

    question_id: str
    question: str
    ground_truth: str
    generated_answer: str
    contexts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Layer1Metrics:
    """Métricas de Camada 1 (RAGAS) para uma amostra de avaliação.

    Cada campo pode ser ``float('nan')`` quando a métrica não foi computável.

    Args:
        answer_correctness: exatidão factual da resposta.
        answer_similarity: similaridade semântica com o ground truth.
        faithfulness: fidelidade da resposta ao contexto recuperado.
        context_precision: precisão dos chunks recuperados.
        context_recall: cobertura dos chunks relevantes.
        answer_relevancy: relevância da resposta para a pergunta.
    """

    answer_correctness: float
    answer_similarity: float
    faithfulness: float
    context_precision: float
    context_recall: float
    answer_relevancy: float


@dataclass(frozen=True, slots=True)
class RubricResult:
    """Resultado da rubrica biomédica avaliada pelo LLM-juiz (Camada 2).

    Args:
        score: score numérico da rubrica; pode ser ``float('nan')`` em caso de
            falha de parsing após retries esgotados (ADR-007).
        feedback: texto de justificativa do juiz para auditoria.
    """

    score: float
    feedback: str


@dataclass(frozen=True, slots=True)
class AuxMetrics:
    """Métricas auxiliares determinísticas de Camada 1 (sem LLM).

    Ambos os campos são mantidos para uso interno e logging (Nota M1 item 10),
    mas o ``ParquetStorage`` (§5.3) persiste apenas ``bertscore_f1`` — ``rouge_l``
    é um campo de log, não de schema.

    Args:
        bertscore_f1: F1 do BERTScore; pode ser ``float('nan')`` se não computado.
        rouge_l: F-measure do ROUGE-L; pode ser ``float('nan')`` se não computado.
    """

    bertscore_f1: float
    rouge_l: float


@dataclass(frozen=True, slots=True)
class CriticalAnnotation:
    """Anotação humana de falha crítica para uma linha de avaliação (ADR-010).

    Args:
        row_id: identificador da linha anotada.
        flag: ``1`` = falha crítica confirmada; ``0`` = sem falha.
        note: justificativa textual opcional do especialista.
    """

    row_id: RowId
    flag: int
    note: str | None


@dataclass(frozen=True, slots=True)
class ModelSpec:
    """Especificação de modelo para instanciação no vLLM (ADR-004/ADR-012, §9.3).

    O regime determinístico do juiz (BATCH_INVARIANT, ADR-003) vs. geradores
    (§9.2.4) é decidido pela **flag** :attr:`batch_invariant` — o
    ``VLLMServerManagerAdapter`` INJETA ``VLLM_BATCH_INVARIANT=1`` /
    ``VLLM_ENABLE_V1_MULTIPROCESSING=0`` no ambiente do subprocesso *sse*
    ``batch_invariant`` for ``True`` (TAREFA-302). A flag — e não dados de ambiente —
    é a fonte autoritativa do regime: geradores ficam *provadamente* sem essas
    variáveis. ``extra_args`` carrega **flags de CLI** adicionais do vLLM (nunca
    variáveis de ambiente de regime).

    Args:
        model: identificador HuggingFace ou caminho local do modelo.
        port: porta TCP local onde o servidor vLLM expõe a API OpenAI-compatible.
        quantization: esquema de quantização (ex.: ``"awq"``) ou ``None`` para fp16.
        tensor_parallel_size: número de GPUs para tensor parallelism (>= 1).
        max_model_len: comprimento máximo de contexto do modelo, em tokens.
        gpu_index: GPU dedicada ao servidor (ADR-012). O adapter injeta
            ``CUDA_VISIBLE_DEVICES=str(gpu_index)`` no subprocesso (juiz=3;
            geradores=0/1/2).
        batch_invariant: ``True`` apenas para o juiz determinístico (ADR-003) —
            dirige a injeção das variáveis de regime pelo adapter.
        extra_args: flags de CLI adicionais do vLLM (mapa nome→valor), apendadas ao
            comando como ``--nome valor``. NÃO contém variáveis de ambiente.
    """

    model: str
    port: int
    quantization: str | None
    tensor_parallel_size: int
    max_model_len: int
    gpu_index: int
    batch_invariant: bool
    extra_args: dict[str, str]


@dataclass(frozen=True, slots=True)
class ServerHandle:
    """Handle de um servidor vLLM em execução (ADR-004/ADR-012).

    Args:
        pid: PID do processo vLLM.
        url: URL base do endpoint OpenAI-compatible, com sufixo ``/v1``
            (ex.: ``"http://localhost:8000/v1"``).
        model: identificador (nome) do modelo carregado no servidor.
        batch_invariant: ``True`` se o servidor roda no regime BATCH_INVARIANT
            (juiz determinístico, ADR-003); ``False`` para geradores (§9.2.4).
        port: porta TCP onde o servidor expõe a API (compõe :attr:`url`).
        gpu_index: GPU dedicada ao servidor (ADR-012; via ``CUDA_VISIBLE_DEVICES``).
        started_at: instante de início (epoch seconds) para auditoria de ciclo de vida.
    """

    pid: int
    url: str
    model: str
    batch_invariant: bool
    port: int
    gpu_index: int
    started_at: float


@dataclass(frozen=True, slots=True)
class ResultFrame:
    """Wrapper tipado sobre uma coleção de EvaluationResult (SEM dataframe/pandas).

    Substituível por pandas/polars no adapter; no domínio permanece como
    tupla imutável de entidades (ADR-001, ADR-002).

    Args:
        results: tupla de resultados de avaliação.
    """

    results: tuple[EvaluationResult, ...]


# ---------------------------------------------------------------------------
# Ports — typing.Protocol com @runtime_checkable (§5.1, ADR-001)
# @runtime_checkable permite isinstance() nos fakes de TAREFA-011.
# ---------------------------------------------------------------------------


@runtime_checkable
class RetrieverPort(Protocol):
    """Recupera chunks de uma base vetorial do Qdrant (§5.1).

    Implementações concretas ficam em ``infrastructure/adapters/``.
    """

    async def search(
        self,
        *,
        base: BaseId,
        question: str,
        top_k: int,
    ) -> RetrievalResult:
        """Busca os top-k chunks mais relevantes para a pergunta na base.

        Args:
            base: identificador da base de conhecimento alvo.
            question: texto da pergunta a ser respondida.
            top_k: número máximo de chunks a retornar.

        Returns:
            :class:`RetrievalResult` com chunks, ids e scores.
        """
        ...


@runtime_checkable
class GeneratorPort(Protocol):
    """Gera resposta via vLLM na configuração de produção (sem batch invariance, §5.1).

    Implementações concretas ficam em ``infrastructure/adapters/``.
    """

    async def generate(
        self,
        *,
        llm: LLMId,
        question: str,
        contexts: Sequence[Chunk],
        seed: int,
        temperature: float,
    ) -> GenerationOutput:
        """Gera uma resposta para a pergunta com base nos contextos fornecidos.

        Args:
            llm: identificador do modelo LLM gerador.
            question: texto da pergunta.
            contexts: sequência de chunks recuperados a usar como contexto.
            seed: semente de reprodutibilidade (regime gerador — ADR-003).
            temperature: temperatura de amostragem do gerador.

        Returns:
            :class:`GenerationOutput` com texto, tokens e latência.
        """
        ...


@runtime_checkable
class MetricSuitePort(Protocol):
    """Calcula métricas de Camada 1 (RAGAS) via o juiz determinístico (§5.1).

    Método ``score`` é ``async`` — o adapter concreto faz chamadas de rede ao
    vllm-judge via RAGAS (Nota M1 item 1 / I4: promoção de contrato para async-first).
    Implementações concretas ficam em ``infrastructure/adapters/``.
    """

    async def score(self, sample: EvaluationSample) -> Layer1Metrics:
        """Avalia uma amostra e retorna as métricas RAGAS.

        Args:
            sample: amostra com pergunta, ground truth, resposta e contextos.

        Returns:
            :class:`Layer1Metrics` com as seis métricas RAGAS (podem ser NaN).
        """
        ...

    async def score_batch(self, samples: list[EvaluationSample]) -> list[Layer1Metrics]:
        """Avalia um lote de amostras e retorna as métricas RAGAS de cada uma.

        Extensão declarada na Nota M3 item 5 — permite que adapters RAGAS
        processem lotes mais eficientemente. A implementação sequencial padrão
        chama :meth:`score` para cada amostra; adapters concretos podem
        paralelizar quando o servidor juiz suportar concorrência > 1.

        Args:
            samples: lista de amostras a avaliar.

        Returns:
            Lista de :class:`Layer1Metrics`, uma por amostra (mesma ordem).
            Campos individuais podem ser ``float('nan')`` (ADR-007).

        Raises:
            MetricComputationError: falha total de I/O no adapter interno.
        """
        ...


@runtime_checkable
class RubricJudgePort(Protocol):
    """Avalia via rubrica biomédica com LLM-juiz determinístico (Camada 2, §5.1).

    Método ``score`` é ``async`` — o adapter concreto faz chamadas de rede ao
    vllm-judge (Nota M1 item 1 / I4: promoção de contrato para async-first).
    Implementações concretas ficam em ``infrastructure/adapters/``.
    """

    async def score(self, sample: EvaluationSample) -> RubricResult:
        """Avalia uma amostra segundo a rubrica biomédica.

        Args:
            sample: amostra com pergunta, ground truth, resposta e contextos.

        Returns:
            :class:`RubricResult` com score e feedback textual; score pode ser
            NaN após retries esgotados (ADR-007).
        """
        ...


@runtime_checkable
class DeterministicMetricPort(Protocol):
    """Métricas auxiliares de Camada 1 sem LLM (BERTScore/ROUGE, §5.1).

    Determinístico por natureza — sem chamada ao juiz.
    Implementações concretas ficam em ``infrastructure/adapters/``.
    """

    def score(self, *, answer: str, ground_truth: str) -> AuxMetrics:
        """Calcula métricas auxiliares determinísticas.

        Args:
            answer: texto da resposta gerada.
            ground_truth: resposta de referência humana.

        Returns:
            :class:`AuxMetrics` com bertscore_f1 e rouge_l (ambos podem ser NaN).
        """
        ...


@runtime_checkable
class GoldChunkReaderPort(Protocol):
    """Lê a lista de chunks-ouro por pergunta para a Rodada 2 (§5.1).

    Implementações concretas ficam em ``infrastructure/adapters/``.
    """

    def gold_for(self, question_id: str) -> list[str]:
        """Retorna os IDs dos chunks-ouro para uma pergunta específica.

        Args:
            question_id: identificador da pergunta.

        Returns:
            Lista de IDs de chunks curados como referência de retrieval.
        """
        ...


@runtime_checkable
class ResultWriterPort(Protocol):
    """Persiste e atualiza linhas tidy de forma idempotente (§5.1, ADR-009).

    Implementações concretas ficam em ``infrastructure/adapters/``.
    """

    def append(self, result: EvaluationResult) -> None:
        """Persiste uma nova linha de avaliação.

        Args:
            result: resultado de avaliação a persistir.
        """
        ...

    def update_metrics(
        self,
        row_id: RowId,
        metrics: MetricVector,
        final_score: FinalScore,
        regime: DeterminismRegime,
        *,
        critical_failure_flag: int | None = None,
        critical_failure_note: str | None = None,
    ) -> None:
        """Atualiza métricas, score final, regime e, opcionalmente, anotação humana.

        Promovido em TAREFA-026 (PR retroativo): além das métricas, persiste o
        ``final_score`` agregado e o ``regime`` de determinismo do juiz. O
        ``batch_invariant`` derivado (§4.3: ``regime is JUDGE``) também é gravado.
        Estendido em TAREFA-308: campos de anotação humana de Camada 3 (ADR-010)
        adicionados como kwargs opcionais — retrocompat total com callers existentes.
        Síncrono — armazenamento é I/O local (não é adapter de rede, Nota M1 item 1).

        Args:
            row_id: identificador da linha a atualizar.
            metrics: novo vetor de métricas calculadas (NaN → NULL no Parquet).
            final_score: score final agregado da passada de julgamento.
            regime: regime de determinismo do juiz (``JUDGE`` na passada de métricas).
            critical_failure_flag: ``0`` (sem falha), ``1`` (falha crítica), ou
                ``None`` (não atualizar flag — padrão).
            critical_failure_note: justificativa textual da anotação; ``None``
                para não atualizar o campo de nota.
        """
        ...

    def exists(self, row_id: RowId) -> bool:
        """Verifica se uma linha já foi persistida — base da resumabilidade (ADR-009).

        Args:
            row_id: identificador da linha a verificar.

        Returns:
            ``True`` se a linha já existe no armazenamento.
        """
        ...

    def update_annotation(
        self,
        row_id: RowId,
        *,
        critical_failure_flag: int,
        critical_failure_note: str = "",
    ) -> None:
        """Atualiza anotação humana de falha crítica (extensão de contrato M4 — ADR-010).

        Delta de contrato declarado na Nota de operacionalização M4: método novo que
        persiste exclusivamente os campos ``critical_failure_flag`` e
        ``critical_failure_note`` sem tocar métricas ou proveniência.

        Args:
            row_id: identificador da linha a anotar.
            critical_failure_flag: ``0`` (sem falha) ou ``1`` (falha crítica confirmada).
            critical_failure_note: justificativa textual opcional do especialista.

        Raises:
            StorageError: se a linha não existe ou ocorrer falha de I/O.
        """
        ...

    def current_annotation_flag(self, row_id: RowId) -> int | None:
        """Retorna o valor atual de ``critical_failure_flag`` para verificação de idempotência (ADR-009).

        Necessário para ``IngestHumanAnnotationUseCase`` decidir se deve pular ou
        sobrescrever uma linha já anotada quando ``force=False``.

        Args:
            row_id: identificador da linha consultada.

        Returns:
            ``0``, ``1`` se já anotada; ``None`` se não anotada ou linha ausente.

        Raises:
            StorageError: em falha de I/O inesperada.
        """
        ...


@runtime_checkable
class ResultReaderPort(Protocol):
    """Lê o dataset tidy para agregação e análise estatística (§5.1).

    Implementações concretas ficam em ``infrastructure/adapters/``.
    """

    def load(
        self,
        *,
        round_id: str,
        phase: str | None = None,
        run_id: str | None = None,
    ) -> ResultFrame:
        """Carrega resultados de uma rodada, opcionalmente filtrando por fase e run.

        Args:
            round_id: identificador da rodada (ex.: ``"round_1"``).
            phase: fase do experimento (``"A"`` ou ``"B"``); ``None`` carrega ambas.
            run_id: identificador do run; ``None`` carrega todos os runs da rodada.

        Returns:
            :class:`ResultFrame` com todos os resultados da seleção.
        """
        ...


@runtime_checkable
class StatsPort(Protocol):
    """Executa bateria estatística: Wilcoxon, Friedman+Nemenyi, MLM (§5.1, ADR-011).

    Três adapters concretos implementam este Protocol (TAREFA-404):
    ``WilcoxonAdapter``, ``FriedmanNemenyiAdapter``, ``MixedLinearModelAdapter``.
    Cada adapter implementa os 3 métodos para satisfazer ``isinstance`` com
    ``@runtime_checkable``; o método primário de cada um faz o trabalho real.
    Orquestração: ``StatisticalAnalysisUseCase`` (TAREFA-405).
    """

    def wilcoxon_paired(self, frame: ResultFrame, metric: str) -> WilcoxonReport:
        """Teste de Wilcoxon pareado entre as duas bases de conhecimento do frame.

        Pareia observações por ``(question_id, seed)``. Requer exatamente 2 bases
        distintas no ``ResultFrame``. Retorna ``significant=False`` com ``p_value=1.0``
        se ``n_pairs < min_pairs`` (padrão 5) — sem levantar exceção (ADR-007).

        Args:
            frame: conjunto de resultados contendo as duas bases a comparar.
            metric: nome da métrica a testar (``"final_score"`` ou campo de
                :class:`~.value_objects.MetricVector`).

        Returns:
            :class:`~.value_objects.WilcoxonReport` com estatística, p-valor,
            effect size r de Rosenthal e metadados de pareamento.
        """
        ...

    def friedman_nemenyi(self, frame: ResultFrame, metric: str) -> FriedmanReport:
        """Teste de Friedman + pós-hoc Nemenyi sobre os LLMs do frame.

        Bloqueia por ``(question_id, seed, base)``. Requer ≥ 3 LLMs distintos;
        retorna ``significant=False`` com ``nemenyi_pairs=()`` se < 3 grupos.
        Pós-hoc só é calculado quando ``p_value < alpha`` (padrão 0.05).

        Args:
            frame: conjunto de resultados com múltiplos LLMs.
            metric: nome da métrica a testar.

        Returns:
            :class:`~.value_objects.FriedmanReport` com chi², p-valor e pares Nemenyi.
        """
        ...

    def mixed_linear_model(self, frame: ResultFrame, formula: str) -> MLMReport:
        """Modelo linear misto via statsmodels, degradação graceful em falha numérica.

        Converte ``ResultFrame`` para ``pandas.DataFrame`` internamente. Em falha de
        convergência ou exceção numérica, retorna p-values NaN e
        ``convergence_warning=True`` — nunca propaga exceção (ADR-007).

        Args:
            frame: conjunto de resultados a analisar.
            formula: fórmula Wilkinson (ex.:
                ``"final_score ~ base * llm + (1 | question_id)"``).

        Returns:
            :class:`~.value_objects.MLMReport` com coeficientes, p-valores e AIC.
        """
        ...


@runtime_checkable
class AnnotationReaderPort(Protocol):
    """Lê anotações humanas de falhas críticas (Camada 3, §5.1, ADR-010).

    Implementações concretas ficam em ``infrastructure/adapters/``.
    """

    def read(self, run_id: str) -> list[CriticalAnnotation]:
        """Carrega todas as anotações humanas de um run.

        Args:
            run_id: identificador do run de avaliação.

        Returns:
            Lista de :class:`CriticalAnnotation` para o run.
        """
        ...


@runtime_checkable
class VLLMServerManagerPort(Protocol):
    """Orquestra ciclo de vida de servidores vLLM no GH200 (§5.1, ADR-004/ADR-012).

    Métodos ``async`` (Nota M1 item 1 / I4: promoção de contrato para async-first) —
    o adapter concreto (``VLLMServerManagerAdapter``) lança o processo via
    ``asyncio.create_subprocess_exec`` e faz polling de ``/health`` via
    ``httpx.AsyncClient``. O método de ciclo de vida ``close()`` é uma extensão do
    adapter — NÃO faz parte deste port (análogo a ``QdrantRetrieverAdapter.close``).
    Implementações concretas ficam em ``infrastructure/adapters/``.
    """

    async def start(self, model: ModelSpec) -> ServerHandle:
        """Inicia um servidor vLLM com a especificação fornecida.

        Args:
            model: especificação do modelo a carregar.

        Returns:
            :class:`ServerHandle` com PID e URL do servidor iniciado.
        """
        ...

    async def wait_healthy(self, handle: ServerHandle, timeout_s: int) -> None:
        """Aguarda o servidor ficar saudável (health check ``/health`` passando).

        Args:
            handle: handle do servidor a aguardar.
            timeout_s: tempo máximo de espera em segundos.

        Raises:
            ServerStartTimeoutError: se o servidor não responder ``200`` em ``/health``
                dentro do prazo (o processo é encerrado antes de levantar).
        """
        ...

    async def stop(self, handle: ServerHandle) -> None:
        """Para e libera os recursos de um servidor vLLM.

        Args:
            handle: handle do servidor a parar.
        """
        ...


@runtime_checkable
class GeneratorFactory(Protocol):
    """Factory para criar GeneratorPort apontando para URL de servidor vLLM.

    Declarado em ``domain/ports.py`` conforme Nota M3 item 5 — única localização
    autorizada para este Protocol. O wiring (TAREFA-309) fornece a implementação
    concreta que instancia o adapter real (ex.: ``VLLMGeneratorAdapter``).
    """

    def __call__(self, url: str) -> GeneratorPort:
        """Cria um GeneratorPort configurado para o servidor na URL fornecida.

        Args:
            url: URL base do endpoint OpenAI-compatible do servidor vLLM
                (com sufixo ``/v1``, ex.: ``"http://localhost:8000/v1"``).

        Returns:
            :class:`GeneratorPort` apontando para o servidor na URL.
        """
        ...
