from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import structlog

from inteligenciomica_eval.domain.ports import ResultWriterPort
from inteligenciomica_eval.domain.value_objects import RowId

_log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class IngestAnnotationInput:
    """Input DTO para IngestHumanAnnotationUseCase.

    Args:
        annotations_path: arquivo JSONL editado pelo especialista.
        run_id: identificador do run de avaliação.
        force: se ``True``, reingerir linhas já anotadas (sobrescreve).
    """

    annotations_path: Path
    run_id: str
    force: bool = False


@dataclass(frozen=True)
class IngestAnnotationOutput:
    """Output DTO do IngestHumanAnnotationUseCase.

    Args:
        n_ingested: linhas com ``critical_failure_flag`` atualizado com sucesso.
        n_skipped: linhas já anotadas e ``force=False``.
        n_invalid: linhas com flag diferente de 0, 1 ou null.
        n_missing_row_id: ``row_id`` do JSONL não encontrado no Parquet.
    """

    n_ingested: int
    n_skipped: int
    n_invalid: int
    n_missing_row_id: int


class IngestHumanAnnotationUseCase:
    """Ingere anotações humanas de falha crítica de um JSONL para o Parquet (ADR-010).

    Lê o JSONL linha por linha, valida cada entrada e persiste via
    ``ResultWriterPort.update_annotation``.  Não aborta em erros por linha —
    conta-os em ``n_invalid`` ou ``n_missing_row_id`` e continua.

    Idempotência (ADR-009): se ``force=False``, linhas já anotadas são puladas
    (``n_skipped``).  Com ``force=True``, são sobrescritas (``n_ingested``).

    Args:
        writer: port de escrita/leitura de resultados; implementação concreta
            em ``infrastructure/repositories/parquet_storage.py``.
    """

    def __init__(self, writer: ResultWriterPort) -> None:
        self._writer = writer

    def execute(self, inp: IngestAnnotationInput) -> IngestAnnotationOutput:
        """Processa todas as linhas do JSONL e retorna o sumário de ingestão.

        Args:
            inp: parâmetros de entrada (caminho, run_id, force).

        Returns:
            :class:`IngestAnnotationOutput` com contadores por categoria.
        """
        n_ingested = 0
        n_skipped = 0
        n_invalid = 0
        n_missing_row_id = 0

        bound = _log.bind(run_id=inp.run_id, path=str(inp.annotations_path))

        with inp.annotations_path.open(encoding="utf-8") as fh:
            for lineno, raw_line in enumerate(fh, 1):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue

                try:
                    record: dict[str, object] = json.loads(raw_line)
                except json.JSONDecodeError:
                    bound.warning("ingest_invalid_json", lineno=lineno)
                    n_invalid += 1
                    continue

                # a. Validar flag ∈ {0, 1, null}
                flag_raw = record.get("critical_failure_flag")

                # b. null → pular silenciosamente (especialista ainda não decidiu)
                if flag_raw is None:
                    continue

                # booleans são subclasse de int em Python; rejeitá-los como inválidos
                if (
                    not isinstance(flag_raw, int)
                    or isinstance(flag_raw, bool)
                    or flag_raw not in (0, 1)
                ):
                    bound.warning("ingest_invalid_flag", lineno=lineno, flag=flag_raw)
                    n_invalid += 1
                    continue

                # Parse row_id
                row_id_str = str(record.get("row_id", ""))
                try:
                    row_id = RowId(value=row_id_str)
                except (ValueError, TypeError):
                    bound.warning(
                        "ingest_invalid_row_id",
                        lineno=lineno,
                        row_id=row_id_str[:12],
                    )
                    n_missing_row_id += 1
                    continue

                # c. Verificar existência no Parquet
                if not self._writer.exists(row_id):
                    bound.warning(
                        "ingest_row_not_found",
                        lineno=lineno,
                        row_id=row_id_str[:12],
                    )
                    n_missing_row_id += 1
                    continue

                # d. Idempotência: se já anotada e force=False → pular
                current_flag = self._writer.current_annotation_flag(row_id)
                if current_flag is not None and not inp.force:
                    n_skipped += 1
                    continue

                # e. Persistir
                note_raw = record.get("critical_failure_note")
                note: str = str(note_raw) if note_raw else ""
                self._writer.update_annotation(
                    row_id,
                    critical_failure_flag=int(flag_raw),
                    critical_failure_note=note,
                )
                n_ingested += 1

        return IngestAnnotationOutput(
            n_ingested=n_ingested,
            n_skipped=n_skipped,
            n_invalid=n_invalid,
            n_missing_row_id=n_missing_row_id,
        )
