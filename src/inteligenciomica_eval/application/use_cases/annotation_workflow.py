"""AnnotationWorkflowUseCase — fila de revisão e ingestão de anotações humanas.

Implementa o fluxo de Camada 3 (ADR-010): a partir dos resultados já avaliados
pelas Passadas 1, 2 e 3, constrói uma fila priorizada de respostas para revisão
humana por um especialista biomédico, e persiste as anotações via
``writer.update_metrics``.

**Rastreabilidade M4**: esta tarefa antecipa TAREFA-401/402 do M4 (§14.7).
M4 deve referenciar e, se necessário, estender sem reimplementar.

Desvios conscientes em relação à spec (TAREFA-308):
1. ``config: AnnotationConfig`` é um dataclass de aplicação — NÃO importa
   ``schema.AnnotationConfig`` (infrastructure) por exigência do import-linter
   (Contract 2/4). O wiring (TAREFA-309) converte os campos de ``schema.AnnotationConfig``
   + ``round_id`` do ``RoundConfig`` para esta classe.
2. ``annotate`` valida ``flag ∈ {0, 1}`` com ``ScoreOutOfRangeError`` antes de chamar
   ``with_human_annotation`` (que internamente levanta ``InvalidCriticalFailureFlagError``).
   A dupla validação é intencional: ``ScoreOutOfRangeError`` é o contrato público do
   use case; ``with_human_annotation`` é o invariante ADR-010 da entidade.
3. Nota de tratamento NaN na fila: ``NaN < limiar`` é ``False`` em Python, portanto
   linhas com ``final_score=NaN`` E ``rubric_biomed_score=NaN`` NÃO entram na fila
   de revisão (ambos os filtros são False). Esta é a interpretação literal da spec.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass

import structlog

from inteligenciomica_eval.domain.entities import EvaluationResult
from inteligenciomica_eval.domain.errors import ScoreOutOfRangeError, StorageError
from inteligenciomica_eval.domain.ports import ResultReaderPort, ResultWriterPort
from inteligenciomica_eval.domain.value_objects import RowId

_log = structlog.get_logger(__name__)

_VALID_FLAGS: frozenset[int] = frozenset({0, 1})


@dataclass(frozen=True, slots=True)
class AnnotationConfig:
    """Configuração do fluxo de anotação humana (use case de aplicação).

    Construída pelo wiring (TAREFA-309) a partir de ``schema.AnnotationConfig``
    e do ``round_id`` do ``RoundConfig`` pai.

    Args:
        round_id: identificador do round de avaliação (filtro do reader).
        score_threshold: limiar de ``final_score`` — respostas abaixo entram na fila.
        rubric_threshold: limiar de ``rubric_biomed_score`` — respostas abaixo entram.
        max_to_review: máximo de itens retornados pela fila; ``None`` = sem limite.
    """

    round_id: str
    score_threshold: float = 0.6
    rubric_threshold: float = 0.5
    max_to_review: int | None = None


@dataclass(frozen=True, slots=True)
class AnnotationSummary:
    """Resumo de uma sessão de anotação.

    Args:
        n_annotated: número de itens anotados com sucesso.
        n_skipped: número de itens pulados pelo usuário na sessão interativa.
        n_pending: número de itens na fila que não foram processados (por ex.,
            porque o usuário saiu antes de concluir).
    """

    n_annotated: int
    n_skipped: int
    n_pending: int


class AnnotationWorkflowUseCase:
    """Gerencia a fila de revisão e ingestão de anotações humanas (Camada 3, ADR-010).

    Antecipa TAREFA-401/402 do M4 (§14.7): M4 deve referenciar e, se necessário,
    estender sem reimplementar.

    Args:
        reader: port de leitura de resultados de avaliação.
        writer: port de persistência de anotações (update_metrics + kwargs de Camada 3).
        config: parâmetros da fila e do round de anotação.
    """

    def __init__(
        self,
        *,
        reader: ResultReaderPort,
        writer: ResultWriterPort,
        config: AnnotationConfig,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._config = config

    def get_review_queue(self, *, run_id: str) -> tuple[EvaluationResult, ...]:
        """Constrói a fila priorizada de respostas para revisão humana.

        Filtra respostas que (a) ainda não foram anotadas (``critical_failure_flag``
        é ``None``) e (b) estão abaixo dos limiares de score ou rubrica.
        Ordena por ``final_score`` ASC — piores primeiro; ``NaN`` é tratado como
        ``-inf`` (situação de maior incerteza → prioridade máxima). Respeita
        ``max_to_review``.

        Args:
            run_id: identificador da rodada (apenas para logging; a carga filtra
                por ``config.round_id``).

        Returns:
            Tupla de :class:`EvaluationResult` na fila de revisão, ordenada por
            ``final_score`` ASC (piores / mais incertos primeiro).
        """
        frame = self._reader.load(round_id=self._config.round_id)

        pending: list[EvaluationResult] = []
        n_already_annotated = 0
        n_above_threshold = 0

        for result in frame.results:
            if result.critical_failure_flag is not None:
                n_already_annotated += 1
                continue

            fs = result.final_score.value
            rb = result.metrics.rubric_biomed_score

            below_score = not math.isnan(fs) and fs < self._config.score_threshold
            below_rubric = not math.isnan(rb) and rb < self._config.rubric_threshold

            if below_score or below_rubric:
                pending.append(result)
            else:
                n_above_threshold += 1

        pending.sort(key=_sort_key)

        if self._config.max_to_review is not None:
            pending = pending[: self._config.max_to_review]

        _log.info(
            "review_queue_built",
            run_id=run_id,
            round_id=self._config.round_id,
            n_queue=len(pending),
            n_already_annotated=n_already_annotated,
            n_above_threshold=n_above_threshold,
        )
        return tuple(pending)

    def annotate(self, *, row_id: RowId, flag: int, note: str) -> None:
        """Persiste uma anotação humana de falha crítica (ADR-010).

        Valida ``flag ∈ {0, 1}`` (``ScoreOutOfRangeError`` se inválido), carrega
        a entidade correspondente, chama ``with_human_annotation`` (invariante de
        imutabilidade da entidade ADR-010) e persiste via ``writer.update_metrics``
        com os campos de anotação de Camada 3.

        Args:
            row_id: identificador da linha a anotar.
            flag: ``0`` (sem falha crítica) ou ``1`` (falha crítica confirmada).
            note: justificativa textual da anotação (pode ser vazia).

        Raises:
            ScoreOutOfRangeError: se ``flag`` não for ``0`` ou ``1``.
            StorageError: se ``row_id`` não for encontrado no round configurado.
        """
        if flag not in _VALID_FLAGS:
            raise ScoreOutOfRangeError(float(flag), 0, 1)

        frame = self._reader.load(round_id=self._config.round_id)
        result = next((r for r in frame.results if r.answer.row_id == row_id), None)
        if result is None:
            raise StorageError(
                "read",
                f"Row {row_id.value!r} not found in round {self._config.round_id!r}",
            )

        # ADR-010: with_human_annotation preserva a imutabilidade da entidade —
        # retorna nova instância com a anotação aplicada. Usamos o resultado para
        # extrair os campos validados antes de persistir.
        note_value: str | None = note if note else None
        updated = result.with_human_annotation(flag, note_value)

        self._writer.update_metrics(
            row_id,
            result.metrics,
            result.final_score,
            result.determinism_regime,
            critical_failure_flag=updated.critical_failure_flag,
            critical_failure_note=updated.critical_failure_note,
        )

        _log.info(
            "annotation_persisted",
            round_id=self._config.round_id,
            row_id=row_id.value,
            flag=flag,
            has_note=bool(note),
        )

    def batch_annotate_from_csv(self, csv_content: str) -> AnnotationSummary:
        """Processa anotações em lote de um CSV sem prompt interativo (modo --csv).

        CSV esperado: colunas ``{row_id, flag, note}`` (header obrigatório; ``note``
        é opcional — interpretada como vazia quando ausente ou em branco).
        Persiste cada linha via :meth:`annotate`. Erros por linha são logados e
        acumulados em vez de abortar o lote.

        Args:
            csv_content: conteúdo do CSV como string UTF-8.

        Returns:
            :class:`AnnotationSummary` com contagens de sucesso e erros.

        Raises:
            StorageError: se o CSV estiver malformado (header ausente ou sem
                coluna ``row_id`` / ``flag``).
        """
        reader = csv.DictReader(io.StringIO(csv_content))
        if reader.fieldnames is None or not {"row_id", "flag"}.issubset(
            set(reader.fieldnames)
        ):
            raise StorageError(
                "read",
                "CSV deve ter colunas: row_id, flag (e opcionalmente note)",
            )

        n_annotated = 0
        n_errors = 0
        for lineno, row in enumerate(reader, start=2):
            try:
                row_id = RowId(value=row["row_id"])
                flag = int(row["flag"])
                note = row.get("note", "") or ""
                self.annotate(row_id=row_id, flag=flag, note=note)
                n_annotated += 1
            except (StorageError, ScoreOutOfRangeError, ValueError) as exc:
                n_errors += 1
                _log.warning(
                    "batch_annotate_line_error",
                    lineno=lineno,
                    error=str(exc),
                )

        _log.info(
            "batch_annotate_completed",
            round_id=self._config.round_id,
            n_annotated=n_annotated,
            n_errors=n_errors,
        )
        return AnnotationSummary(
            n_annotated=n_annotated,
            n_skipped=0,
            n_pending=0,
        )


def _sort_key(result: EvaluationResult) -> tuple[int, float]:
    """Chave de ordenação: NaN → início (pior/mais incerto), depois ASC por final_score."""
    fs = result.final_score.value
    if math.isnan(fs):
        return (0, 0.0)
    return (1, fs)
