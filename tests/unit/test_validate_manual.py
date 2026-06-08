"""Testes para scripts/validate_manual.py — verificações de acurácia documental.

TAREFA-315: valida as extensões de detecção de arquivos referenciados inexistentes
e de claims numéricas inconsistentes sobre o conjunto empacotado de perguntas.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# ---------------------------------------------------------------------------
# Carrega o módulo scripts/validate_manual.py via importlib (não é pacote).
# ---------------------------------------------------------------------------
_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "validate_manual.py"
_spec = importlib.util.spec_from_file_location("validate_manual", _SCRIPT)
assert _spec and _spec.loader, f"Não foi possível carregar {_SCRIPT}"
_vm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_vm)  # type: ignore[union-attr]

_REPO_ROOT = Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# _local_file_errors_in_block
# ---------------------------------------------------------------------------


class TestLocalFileErrors:
    def test_detects_missing_config_jsonl(self) -> None:
        """Bloco com config/questions.jsonl inexistente deve gerar erro."""
        block = 'export BENCHMARK_QUESTIONS_PATH="config/questions.jsonl"'
        errors = _vm._local_file_errors_in_block(block, _REPO_ROOT)
        assert any("config/questions.jsonl" in e for e in errors), errors

    def test_detects_missing_questions_resistencia(self) -> None:
        """config/questions_resistencia.jsonl inexistente deve gerar erro."""
        block = (
            'export BENCHMARK_QUESTIONS_PATH="config/questions_resistencia.jsonl"\n'
            "ielm-eval run --config config/experiment_round1.yaml --run-id r1"
        )
        errors = _vm._local_file_errors_in_block(block, _REPO_ROOT)
        assert any("questions_resistencia" in e for e in errors), errors

    def test_ignores_comment_lines(self) -> None:
        """Paths em linhas de comentário (#) não são verificados."""
        block = '# export BENCHMARK_QUESTIONS_PATH="config/questions.jsonl"'
        errors = _vm._local_file_errors_in_block(block, _REPO_ROOT)
        assert errors == []

    def test_passes_existing_config_yaml(self) -> None:
        """config/experiment_round1.yaml existe — bloco corrigido não gera erro."""
        block = (
            "unset BENCHMARK_QUESTIONS_PATH\n"
            "ielm-eval run --config config/experiment_round1.yaml --run-id <run_id>"
        )
        errors = _vm._local_file_errors_in_block(block, _REPO_ROOT)
        assert errors == [], errors

    def test_ignores_config_data_output_paths(self) -> None:
        """Paths sob config/data/ (output em runtime) não são verificados."""
        block = "config/data/\n  round_id=round-1/"
        errors = _vm._local_file_errors_in_block(block, _REPO_ROOT)
        assert errors == []

    def test_ignores_placeholder_angle_brackets(self) -> None:
        """Tokens contendo <> são placeholders — não verificados."""
        block = "ielm-eval run --config <caminho_config>"
        errors = _vm._local_file_errors_in_block(block, _REPO_ROOT)
        assert errors == []


# ---------------------------------------------------------------------------
# _count_bundled_questions
# ---------------------------------------------------------------------------


class TestCountBundledQuestions:
    def test_counts_three_questions(self) -> None:
        """questions_rf1.jsonl deve ter exactamente 3 perguntas com question_id."""
        count = _vm._count_bundled_questions(_REPO_ROOT)
        assert count == 3

    def test_returns_minus_one_for_missing_file(self, tmp_path: Path) -> None:
        """tmp_path não tem o arquivo empacotado — deve retornar -1."""
        count = _vm._count_bundled_questions(tmp_path)
        assert count == -1

    def test_comment_line_not_counted(self, tmp_path: Path) -> None:
        """Linha com _comment não tem question_id — não conta."""
        qfile = (
            tmp_path / "src" / "inteligenciomica_eval" / "infrastructure" / "benchmark"
        )
        qfile.mkdir(parents=True)
        (qfile / "questions_rf1.jsonl").write_text(
            '{"_comment": "placeholder"}\n'
            '{"question_id": "q1", "text": "t", "ground_truth": "g"}\n',
            encoding="utf-8",
        )
        # A função usa _BUNDLED_QUESTIONS relativo ao repo_root fornecido
        count = _vm._count_bundled_questions(tmp_path)
        assert count == 1


# ---------------------------------------------------------------------------
# _check_numeric_claims
# ---------------------------------------------------------------------------


class TestNumericClaims:
    def test_fails_on_wrong_count_thirteen(self) -> None:
        """'13 perguntas placeholder' deve falhar — arquivo tem 3."""
        text = "usa as 13 perguntas placeholder do benchmark RF1"
        errors = _vm._check_numeric_claims(text, _REPO_ROOT)
        assert len(errors) == 1
        assert "13" in errors[0]
        assert "3" in errors[0]

    def test_passes_on_correct_count_three(self) -> None:
        """'3 perguntas placeholder' deve passar."""
        text = "O fallback empacotado tem 3 perguntas placeholder representativas."
        errors = _vm._check_numeric_claims(text, _REPO_ROOT)
        assert errors == []

    def test_no_errors_on_text_without_claim(self) -> None:
        """Texto sem padrão 'N perguntas placeholder' não gera erros."""
        text = "Execute ielm-eval run --config config/experiment_round1.yaml"
        errors = _vm._check_numeric_claims(text, _REPO_ROOT)
        assert errors == []

    def test_deduplicates_same_wrong_claim(self) -> None:
        """Mesmo claim errado repetido deve aparecer uma única vez nos erros."""
        text = (
            "As 13 perguntas placeholder estão em questions_rf1.jsonl. "
            "São 13 perguntas placeholder no total."
        )
        errors = _vm._check_numeric_claims(text, _REPO_ROOT)
        assert len(errors) == 1
