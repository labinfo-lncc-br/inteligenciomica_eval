from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from inteligenciomica_eval.domain.entities import Question
from inteligenciomica_eval.domain.errors import InteligenciomicaEvalError, StorageError


def load_questions(path: Path | None = None) -> list[Question]:
    """Carrega as perguntas do benchmark RF1.

    Args:
        path: caminho externo para um JSONL de perguntas.
              ``None`` → usa ``questions_rf1.jsonl`` empacotado no módulo via
              ``importlib.resources``.

    Returns:
        Lista ordenada de :class:`~inteligenciomica_eval.domain.entities.Question`
        na ordem do arquivo, excluindo linhas de comentário e linhas em branco.

    Raises:
        StorageError: se o arquivo não existir, uma linha for malformada (JSON inválido,
            campo ausente, campo vazio) ou a entidade :class:`Question` rejeitar os valores.
    """
    if path is None:
        source_name = "questions_rf1.jsonl"
        try:
            raw = (
                files("inteligenciomica_eval.infrastructure.benchmark")
                .joinpath(source_name)
                .read_text(encoding="utf-8")
            )
        except (FileNotFoundError, ModuleNotFoundError) as exc:
            raise StorageError(
                "read",
                f"Arquivo de perguntas empacotado não encontrado: {source_name}",
            ) from exc
    else:
        source_name = str(path)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise StorageError(
                "read",
                f"Arquivo de perguntas não encontrado: {source_name}",
            ) from exc

    questions: list[Question] = []
    for lineno, line in enumerate(raw.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StorageError(
                "parse",
                f"{source_name}:{lineno}: JSON inválido — {exc}",
            ) from exc

        if not isinstance(record, dict):
            raise StorageError(
                "parse",
                f"{source_name}:{lineno}: linha deve ser um objeto JSON, "
                f"encontrado {type(record).__name__!r}",
            )

        # Linhas de comentário são ignoradas silenciosamente.
        if "_comment" in record:
            continue

        try:
            question_id = record["question_id"]
            text = record["text"]
            ground_truth = record["ground_truth"]
        except KeyError as exc:
            raise StorageError(
                "parse",
                f"{source_name}:{lineno}: campo obrigatório ausente — {exc}",
            ) from exc

        try:
            questions.append(
                Question(
                    question_id=question_id,
                    text=text,
                    ground_truth=ground_truth,
                )
            )
        except (InteligenciomicaEvalError, TypeError, ValueError) as exc:
            raise StorageError(
                "parse",
                f"{source_name}:{lineno}: pergunta inválida — {exc}",
            ) from exc

    return questions
