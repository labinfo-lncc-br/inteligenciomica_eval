from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from inteligenciomica_eval.domain.entities import EvaluationResult
from inteligenciomica_eval.domain.value_objects import (
    BaseId,
    LLMId,
    MetricVector,
    RowId,
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
        question: enunciado da pergunta avaliada.
        ground_truth: resposta de referência humana.
        generated_answer: resposta gerada pelo LLM sob avaliação.
        contexts: tupla de textos de contexto recuperados (chunks).
    """

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

    Args:
        bertscore_f1: F1 do BERTScore; pode ser ``float('nan')`` se não computado.
    """

    bertscore_f1: float


@dataclass(frozen=True, slots=True)
class WilcoxonReport:
    """Resultado do teste de Wilcoxon pareado (StatsPort).

    Estrutura mínima para M0; será detalhada no M4 (StatsPort).

    Args:
        statistic: estatística W do teste.
        p_value: p-valor do teste (após correção se aplicável).
        effect_size: tamanho do efeito (r de Rosenthal).
        n_pairs: número de pares utilizados no teste.
    """

    statistic: float
    p_value: float
    effect_size: float
    n_pairs: int


@dataclass(frozen=True)
class FriedmanReport:
    """Resultado do Friedman + Nemenyi post-hoc (StatsPort).

    Estrutura mínima para M0; será detalhada no M4 (StatsPort).

    ``post_hoc`` é um dict mutável; a dataclass é frozen apenas no sentido de
    não permitir reatribuição do atributo — use como somente-leitura.

    Args:
        statistic: estatística chi² do teste de Friedman.
        p_value: p-valor do teste de Friedman.
        post_hoc: mapa de par→p-valor Nemenyi (ex.: ``{"A vs B": 0.03}``).
    """

    statistic: float
    p_value: float
    post_hoc: dict[str, float]


@dataclass(frozen=True)
class MLMReport:
    """Resultado do modelo linear misto (StatsPort).

    Estrutura mínima para M0; será detalhada no M4 (StatsPort).

    ``coef`` é um dict mutável; a dataclass é frozen apenas no sentido de
    não permitir reatribuição do atributo — use como somente-leitura.

    Args:
        formula: fórmula Wilkinson do modelo ajustado.
        aic: critério de informação de Akaike.
        bic: critério de informação Bayesiano.
        coef: mapa de variável→coeficiente estimado.
    """

    formula: str
    aic: float
    bic: float
    coef: dict[str, float]


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
    """Especificação de modelo para instanciação no vLLM (ADR-004/ADR-012).

    Args:
        model_id: identificador HuggingFace ou caminho local do modelo.
        tensor_parallel_size: número de GPUs para tensor parallelism (>= 1).
        gpu_memory_utilization: fração da memória GPU a alocar (em ``(0, 1]``).
    """

    model_id: str
    tensor_parallel_size: int
    gpu_memory_utilization: float


@dataclass(frozen=True, slots=True)
class ServerHandle:
    """Handle de um servidor vLLM em execução (ADR-004/ADR-012).

    Args:
        process_id: PID do processo vLLM.
        base_url: URL base do endpoint OpenAI-compatible (ex.: ``"http://localhost:8000"``).
        model_id: identificador do modelo carregado no servidor.
    """

    process_id: int
    base_url: str
    model_id: str


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

    Implementações concretas ficam em ``infrastructure/adapters/``.
    """

    def score(self, sample: EvaluationSample) -> Layer1Metrics:
        """Avalia uma amostra e retorna as métricas RAGAS.

        Args:
            sample: amostra com pergunta, ground truth, resposta e contextos.

        Returns:
            :class:`Layer1Metrics` com as seis métricas RAGAS (podem ser NaN).
        """
        ...


@runtime_checkable
class RubricJudgePort(Protocol):
    """Avalia via rubrica biomédica com LLM-juiz determinístico (Camada 2, §5.1).

    Implementações concretas ficam em ``infrastructure/adapters/``.
    """

    def score(self, sample: EvaluationSample) -> RubricResult:
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
            :class:`AuxMetrics` com bertscore_f1 (pode ser NaN).
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

    def update_metrics(self, row_id: RowId, metrics: MetricVector) -> None:
        """Atualiza o vetor de métricas de uma linha já existente.

        Args:
            row_id: identificador da linha a atualizar.
            metrics: novo vetor de métricas calculadas.
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


@runtime_checkable
class ResultReaderPort(Protocol):
    """Lê o dataset tidy para agregação e análise estatística (§5.1).

    Implementações concretas ficam em ``infrastructure/adapters/``.
    """

    def load(self, *, round_id: str, phase: str | None = None) -> ResultFrame:
        """Carrega resultados de uma rodada, opcionalmente filtrando por fase.

        Args:
            round_id: identificador da rodada (ex.: ``"round_1"``).
            phase: fase do experimento (``"A"`` ou ``"B"``); ``None`` carrega ambas.

        Returns:
            :class:`ResultFrame` com todos os resultados da seleção.
        """
        ...


@runtime_checkable
class StatsPort(Protocol):
    """Executa bateria estatística: Wilcoxon, Friedman+Nemenyi, MLM (§5.1).

    Implementações concretas ficam em ``infrastructure/adapters/``.
    Detalhamento completo das assinaturas no M4.
    """

    def wilcoxon_paired(self, frame: ResultFrame, metric: str) -> WilcoxonReport:
        """Executa o teste de Wilcoxon pareado sobre uma métrica.

        Args:
            frame: conjunto de resultados a analisar.
            metric: nome da coluna de métrica a testar.

        Returns:
            :class:`WilcoxonReport` com estatística, p-valor e effect size.
        """
        ...

    def friedman_nemenyi(self, frame: ResultFrame, metric: str) -> FriedmanReport:
        """Executa Friedman + post-hoc Nemenyi sobre uma métrica.

        Args:
            frame: conjunto de resultados a analisar.
            metric: nome da coluna de métrica a testar.

        Returns:
            :class:`FriedmanReport` com estatística, p-valor e mapa post-hoc.
        """
        ...

    def mixed_linear_model(self, frame: ResultFrame, formula: str) -> MLMReport:
        """Ajusta modelo linear misto com a fórmula Wilkinson fornecida.

        Args:
            frame: conjunto de resultados a analisar.
            formula: fórmula Wilkinson do modelo (ex.: ``"score ~ base + (1|seed)"``).

        Returns:
            :class:`MLMReport` com AIC, BIC e coeficientes estimados.
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

    Implementações concretas ficam em ``infrastructure/adapters/``.
    """

    def start(self, model: ModelSpec) -> ServerHandle:
        """Inicia um servidor vLLM com a especificação fornecida.

        Args:
            model: especificação do modelo a carregar.

        Returns:
            :class:`ServerHandle` com PID e URL do servidor iniciado.
        """
        ...

    def wait_healthy(self, handle: ServerHandle, timeout_s: int) -> None:
        """Aguarda o servidor ficar saudável (health check passando).

        Args:
            handle: handle do servidor a aguardar.
            timeout_s: tempo máximo de espera em segundos.

        Raises:
            TimeoutError: se o servidor não responder dentro do prazo.
        """
        ...

    def stop(self, handle: ServerHandle) -> None:
        """Para e libera os recursos de um servidor vLLM.

        Args:
            handle: handle do servidor a parar.
        """
        ...
