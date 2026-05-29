"""AnnotationReaderAdapter — anotações humanas de falhas críticas (Camada 3, §5.3).

Implementa ``AnnotationReaderPort`` lendo um arquivo JSONL produzido offline pelo
especialista biomédico (ADR-010). O adapter apenas lê — a escrita é externa ao sistema
(ex.: ``ielm-eval annotate``).

Notas de design:

- **Síncrono** (Nota M1 item 1): leitura local de arquivo, sem I/O de rede.
- **Camada 3 é offline e parcial**: se o arquivo não existir, a Camada 3 fica
  *desabilitada* (estado normal em M1) — :meth:`read` sempre retorna ``[]``, sem erro.
  Arquivo ausente **não** é falha; arquivo presente mas malformado **é** (``StorageError``
  na construção, não em ``read``).
- **Carga ansiosa na construção**: o JSONL é lido no ``__init__`` para um índice
  ``run_id → list[CriticalAnnotation]``. Erros de formato aparecem cedo (na construção),
  não na primeira leitura.
- **Conversão para o domínio**: ``row_id`` (str hex) vira ``RowId``; ``flag`` é validado
  em ``{0, 1}``; ``note`` é opcional (``str | None``).
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import structlog

from inteligenciomica_eval.domain.errors import StorageError
from inteligenciomica_eval.domain.ports import CriticalAnnotation
from inteligenciomica_eval.domain.value_objects import RowId

_log = structlog.get_logger(__name__)

_VALID_FLAGS = (0, 1)


class AnnotationReaderAdapter:
    """Lê anotações humanas de falhas críticas de um JSONL (Camada 3, ADR-010).

    Formato JSONL (uma anotação por linha)::

        {"run_id": "round_1", "row_id": "<hex_sha256>", "flag": 0, "note": "opcional"}

    O campo ``note`` é opcional (ausente ou ``null`` → ``None``).

    Args:
        annotation_file: caminho do arquivo JSONL de anotações.

    Raises:
        StorageError: na **construção**, se o arquivo existir mas estiver malformado
            (JSON inválido, campos ``run_id``/``row_id``/``flag`` ausentes, ``row_id``
            não-hex, ou ``flag`` fora de ``{0, 1}``).
    """

    def __init__(self, annotation_file: pathlib.Path) -> None:
        self._annotation_file: pathlib.Path = annotation_file
        self._by_run: dict[str, list[CriticalAnnotation]] = self._load(annotation_file)

    # ------------------------------------------------------------------
    # AnnotationReaderPort interface
    # ------------------------------------------------------------------

    def read(self, run_id: str) -> list[CriticalAnnotation]:
        """Retorna as anotações do *run_id*.

        Args:
            run_id: identificador do run de avaliação.

        Returns:
            ``list[CriticalAnnotation]`` (cópia fresca) com as anotações do run;
            **lista vazia** ``[]`` se o run não tiver anotações ou o arquivo estiver
            ausente. Nunca ``None``.
        """
        return list(self._by_run.get(run_id, []))

    def reload(self, annotation_file: pathlib.Path | None = None) -> int:
        """Recarrega o arquivo em memória.

        Args:
            annotation_file: novo caminho a carregar; se ``None``, recarrega o arquivo
                corrente.

        Returns:
            Número total de anotações carregadas (somadas sobre todos os ``run_id``).

        Raises:
            StorageError: se o (novo) arquivo existir mas estiver malformado.
        """
        if annotation_file is not None:
            self._annotation_file = annotation_file
        self._by_run = self._load(self._annotation_file)
        return sum(len(annotations) for annotations in self._by_run.values())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load(self, path: pathlib.Path) -> dict[str, list[CriticalAnnotation]]:
        """Carrega o JSONL em ``run_id → [CriticalAnnotation]`` (vazio se arquivo ausente)."""
        if not path.exists():
            _log.info("annotation file not found, Camada 3 disabled", path=str(path))
            return {}

        by_run: dict[str, list[CriticalAnnotation]] = {}
        with path.open(encoding="utf-8") as fh:
            for lineno, raw_line in enumerate(fh, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                run_id, annotation = self._parse_line(line, lineno)
                by_run.setdefault(run_id, []).append(annotation)

        _log.info(
            "annotations_loaded",
            path=str(path),
            runs=len(by_run),
            total=sum(len(annotations) for annotations in by_run.values()),
        )
        return by_run

    def _parse_line(self, line: str, lineno: int) -> tuple[str, CriticalAnnotation]:
        """Converte uma linha JSONL em ``(run_id, CriticalAnnotation)`` ou levanta StorageError."""
        try:
            record: Any = json.loads(line)
            run_id = record["run_id"]
            row_id = RowId(value=record["row_id"])
            flag = record["flag"]
            note = record.get("note")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise StorageError(
                "read",
                f"Invalid annotation at line {lineno} in "
                f"{self._annotation_file.name}: {exc}",
            ) from exc

        if flag not in _VALID_FLAGS:
            raise StorageError(
                "read",
                f"Invalid flag {flag!r} at line {lineno} in "
                f"{self._annotation_file.name}: expected 0 or 1",
            )

        return run_id, CriticalAnnotation(row_id=row_id, flag=flag, note=note)
