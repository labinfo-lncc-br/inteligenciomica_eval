from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from inteligenciomica_eval.domain.errors import (
    InteligenciomicaEvalError,
    InvalidCriticalFailureFlagError,
    InvalidPhaseError,
    RetrievalTupleLengthMismatchError,
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

_VALID_PHASES: frozenset[str] = frozenset({"A", "B"})
_PHASE_B_BASE: str = "fixed"


@dataclass(frozen=True, slots=True)
class Question:
    """Pergunta fixa do benchmark — as 13 perguntas do conjunto de avaliação.

    Imutável por design: as perguntas são fixas para o ciclo de vida do
    experimento e não devem ser alteradas após construção.

    Args:
        question_id: identificador único da pergunta (não-vazio).
        text: enunciado da pergunta (não-vazio).
        ground_truth: resposta de referência (não-vazia).

    Raises:
        InteligenciomicaEvalError: se qualquer campo obrigatório for vazio.
    """

    question_id: str
    text: str
    ground_truth: str

    def __post_init__(self) -> None:
        if not self.question_id:
            raise InteligenciomicaEvalError("Question.question_id must not be empty.")
        if not self.text:
            raise InteligenciomicaEvalError("Question.text must not be empty.")
        if not self.ground_truth:
            raise InteligenciomicaEvalError("Question.ground_truth must not be empty.")


@dataclass(frozen=True, slots=True)
class GeneratedAnswer:
    """Resposta gerada por um LLM para uma pergunta em uma configuração específica.

    Identidade por ``row_id`` (SHA-256 determinístico, ADR-009). Imutável.

    Args:
        row_id: identificador determinístico da linha (ADR-009).
        question: pergunta correspondente.
        base: base de conhecimento usada na recuperação.
        llm: modelo gerador da resposta.
        seed: semente de reprodutibilidade.
        phase: fase do experimento — ``'A'`` (RAG dinâmico) ou ``'B'`` (fixed).
        generated_answer: texto da resposta gerada pelo LLM.
        retrieved_chunk_ids: IDs dos chunks recuperados (mesma ordem dos demais).
        retrieved_chunks_text: textos dos chunks recuperados.
        retrieval_scores: scores de similaridade/relevância dos chunks.

    Raises:
        InvalidPhaseError: se ``phase`` não for ``'A'`` ou ``'B'``.
        RetrievalTupleLengthMismatchError: se as três tuplas tiverem comprimentos
            diferentes.
        InteligenciomicaEvalError: se o Experimento B não usar ``base='fixed'``.
    """

    row_id: RowId
    question: Question
    base: BaseId
    llm: LLMId
    seed: Seed
    phase: str
    generated_answer: str
    retrieved_chunk_ids: tuple[str, ...]
    retrieved_chunks_text: tuple[str, ...]
    retrieval_scores: tuple[float, ...]

    def __post_init__(self) -> None:
        if self.phase not in _VALID_PHASES:
            raise InvalidPhaseError(self.phase)

        n = len(self.retrieved_chunk_ids)
        if len(self.retrieved_chunks_text) != n or len(self.retrieval_scores) != n:
            raise RetrievalTupleLengthMismatchError(
                chunk_ids_len=n,
                chunks_text_len=len(self.retrieved_chunks_text),
                scores_len=len(self.retrieval_scores),
            )

        if self.phase == "B" and self.base.value != _PHASE_B_BASE:
            raise InteligenciomicaEvalError(
                f"Experiment B requires base='fixed', got {self.base.value!r} (§5.3)."
            )


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    """Agregado raiz da avaliação — resposta gerada + métricas + anotações (§4.3).

    Compõe um :class:`GeneratedAnswer` com as métricas computadas pelas
    camadas 1+2, o score final, o regime de determinismo e, opcionalmente,
    a anotação humana de falha crítica (Camada 3, ADR-010).

    Imutável: modificações produzem novas instâncias via :meth:`with_metrics`
    e :meth:`with_human_annotation`.

    Args:
        answer: resposta gerada que originou esta avaliação.
        metrics: vetor de métricas calculadas (pode ter campos NaN).
        final_score: score agregado final; NaN enquanto não computado.
        determinism_regime: regime do juiz usado na avaliação.
        critical_failure_flag: ``1`` = falha crítica confirmada; ``0`` = sem
            falha; ``None`` = ainda não anotado.
        critical_failure_note: justificativa textual da anotação (opcional).

    Raises:
        InteligenciomicaEvalError: se ``determinism_regime`` não for uma
            instância de :class:`DeterminismRegime`.
        InvalidCriticalFailureFlagError: se ``critical_failure_flag`` não for
            ``None``, ``0`` ou ``1``.
    """

    answer: GeneratedAnswer
    metrics: MetricVector
    final_score: FinalScore
    determinism_regime: DeterminismRegime
    critical_failure_flag: int | None
    critical_failure_note: str | None

    def __post_init__(self) -> None:
        # Validação estrutural: regime não pode ser ausente nem de tipo inválido.
        # A coerência semântica métrica→regime é responsabilidade do use case.
        if not isinstance(self.determinism_regime, DeterminismRegime):
            raise InteligenciomicaEvalError(
                "EvaluationResult.determinism_regime must be a DeterminismRegime "
                f"instance, got {type(self.determinism_regime).__name__!r}."
            )
        if (
            self.critical_failure_flag is not None
            and self.critical_failure_flag
            not in (
                0,
                1,
            )
        ):
            raise InvalidCriticalFailureFlagError(self.critical_failure_flag)

    # ------------------------------------------------------------------
    # Consultas puras
    # ------------------------------------------------------------------

    def is_failure(self, threshold: float) -> bool:
        """Retorna ``True`` se o score final for estritamente abaixo do limiar.

        Segue a definição de FailureRate em §7.2: ``final_score < threshold``.
        ``NaN`` não satisfaz a condição (retorna ``False``).

        Args:
            threshold: limiar de corte (ex.: ``0.6``).

        Returns:
            ``True`` se ``final_score.value < threshold``.
        """
        return bool(self.final_score.value < threshold)

    def is_critical_failure(self) -> bool:
        """Retorna ``True`` somente se a falha crítica foi anotada como ``1``.

        ``None`` (não anotado) e ``0`` retornam ``False``.

        Returns:
            ``True`` se ``critical_failure_flag == 1``.
        """
        return self.critical_failure_flag == 1

    # ------------------------------------------------------------------
    # Mutação imutável — retornam nova instância
    # ------------------------------------------------------------------

    def with_metrics(
        self,
        metrics: MetricVector,
        final_score: FinalScore,
        regime: DeterminismRegime,
    ) -> EvaluationResult:
        """Retorna nova instância com métricas, score e regime atualizados (§5.4).

        Usado após a passada de julgamento para preencher os resultados
        computados sem mutar o objeto original.

        Args:
            metrics: novo vetor de métricas.
            final_score: novo score final agregado.
            regime: regime de determinismo do juiz utilizado.

        Returns:
            Nova :class:`EvaluationResult` com os campos atualizados.
        """
        return dataclasses.replace(
            self,
            metrics=metrics,
            final_score=final_score,
            determinism_regime=regime,
        )

    def with_human_annotation(
        self,
        flag: int,
        note: str | None,
    ) -> EvaluationResult:
        """Retorna nova instância com a anotação humana de falha crítica (ADR-010).

        Args:
            flag: ``0`` (sem falha) ou ``1`` (falha crítica confirmada).
            note: justificativa opcional para a anotação.

        Returns:
            Nova :class:`EvaluationResult` com a anotação aplicada.

        Raises:
            InvalidCriticalFailureFlagError: se ``flag`` não for ``0`` ou ``1``.
        """
        return dataclasses.replace(
            self,
            critical_failure_flag=flag,
            critical_failure_note=note,
        )
