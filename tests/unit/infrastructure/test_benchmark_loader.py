"""Testes unitários para BenchmarkLoader (TAREFA-309)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from inteligenciomica_eval.domain.entities import Question
from inteligenciomica_eval.domain.errors import StorageError
from inteligenciomica_eval.infrastructure.benchmark.loader import load_questions


class TestLoadQuestionsBundled:
    """Arquivo empacotado é carregado corretamente."""

    def test_returns_list_of_questions(self) -> None:
        questions = load_questions()
        assert isinstance(questions, list)
        assert len(questions) >= 3

    def test_all_fields_non_empty(self) -> None:
        questions = load_questions()
        for q in questions:
            assert q.question_id
            assert q.text
            assert q.ground_truth

    def test_no_comment_entries_in_result(self) -> None:
        questions = load_questions()
        for q in questions:
            assert "_comment" not in q.question_id

    def test_returns_question_instances(self) -> None:
        questions = load_questions()
        for q in questions:
            assert isinstance(q, Question)


class TestLoadQuestionsExternal:
    """Arquivo externo passado via path."""

    def test_loads_external_file(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "questions.jsonl"
        lines = [
            json.dumps(
                {"question_id": "q1", "text": "Pergunta 1?", "ground_truth": "Resp 1."}
            ),
            json.dumps(
                {"question_id": "q2", "text": "Pergunta 2?", "ground_truth": "Resp 2."}
            ),
        ]
        jsonl.write_text("\n".join(lines), encoding="utf-8")

        questions = load_questions(jsonl)

        assert len(questions) == 2
        assert questions[0].question_id == "q1"
        assert questions[1].question_id == "q2"

    def test_empty_lines_ignored(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "questions.jsonl"
        jsonl.write_text(
            '\n{"question_id": "q1", "text": "P?", "ground_truth": "R."}\n\n',
            encoding="utf-8",
        )
        questions = load_questions(jsonl)
        assert len(questions) == 1


class TestSkipCommentLine:
    """Linhas _comment são ignoradas."""

    def test_comment_line_skipped(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "questions.jsonl"
        lines = [
            json.dumps({"_comment": "Arquivo de benchmark — completar para 13."}),
            json.dumps({"question_id": "q1", "text": "P1?", "ground_truth": "R1."}),
        ]
        jsonl.write_text("\n".join(lines), encoding="utf-8")

        questions = load_questions(jsonl)

        assert len(questions) == 1
        assert questions[0].question_id == "q1"

    def test_only_comment_returns_empty(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "questions.jsonl"
        jsonl.write_text(json.dumps({"_comment": "só comentário"}), encoding="utf-8")
        assert load_questions(jsonl) == []


class TestMalformedLineRaisesStorageError:
    """Linha com JSON inválido → StorageError com lineno."""

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "questions.jsonl"
        jsonl.write_text("not valid json\n", encoding="utf-8")

        with pytest.raises(StorageError) as exc_info:
            load_questions(jsonl)

        assert "1" in str(exc_info.value)  # lineno 1 na mensagem

    def test_lineno_in_message(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "questions.jsonl"
        lines = [
            json.dumps({"question_id": "q1", "text": "P?", "ground_truth": "R."}),
            "broken json {{{",
        ]
        jsonl.write_text("\n".join(lines), encoding="utf-8")

        with pytest.raises(StorageError) as exc_info:
            load_questions(jsonl)

        assert "2" in str(exc_info.value)  # lineno 2 na mensagem


class TestMissingFieldRaisesStorageError:
    """Linha sem campo obrigatório → StorageError."""

    def test_missing_ground_truth(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "questions.jsonl"
        jsonl.write_text(
            json.dumps({"question_id": "q1", "text": "P?"}), encoding="utf-8"
        )

        with pytest.raises(StorageError):
            load_questions(jsonl)

    def test_missing_text(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "questions.jsonl"
        jsonl.write_text(
            json.dumps({"question_id": "q1", "ground_truth": "R."}), encoding="utf-8"
        )

        with pytest.raises(StorageError):
            load_questions(jsonl)


class TestEmptyFieldRaisesStorageError:
    """Linha com campo vazio → StorageError (via Question.__post_init__)."""

    def test_empty_text_raises(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "questions.jsonl"
        jsonl.write_text(
            json.dumps({"question_id": "q1", "text": "", "ground_truth": "R."}),
            encoding="utf-8",
        )

        with pytest.raises(StorageError):
            load_questions(jsonl)

    def test_empty_question_id_raises(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "questions.jsonl"
        jsonl.write_text(
            json.dumps({"question_id": "", "text": "P?", "ground_truth": "R."}),
            encoding="utf-8",
        )

        with pytest.raises(StorageError):
            load_questions(jsonl)

    def test_empty_ground_truth_raises(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "questions.jsonl"
        jsonl.write_text(
            json.dumps({"question_id": "q1", "text": "P?", "ground_truth": ""}),
            encoding="utf-8",
        )

        with pytest.raises(StorageError):
            load_questions(jsonl)
