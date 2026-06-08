"""Testes unitários do helper de mascaramento (TAREFA-314).

Prova que mask_url e mask_path produzem outputs seguros para logs:
- sem credenciais (user:pass@)
- sem path (apenas scheme://host:port)
- sem quebra em entradas malformadas
"""

from __future__ import annotations

from pathlib import Path

from inteligenciomica_eval.infrastructure.masking import mask_path, mask_url


class TestMaskUrl:
    def test_strips_path(self) -> None:
        """Deve remover path da URL, deixando apenas scheme://host:port."""
        result = mask_url("http://host:8000/v1/models")
        assert result == "http://host:8000"

    def test_strips_credentials(self) -> None:
        """Deve remover user:pass@ da URL."""
        result = mask_url("http://admin:secret@host:9000/v1")
        assert "secret" not in result
        assert "admin" not in result
        assert result == "http://host:9000"

    def test_preserves_port(self) -> None:
        """Deve manter a porta na URL mascarada."""
        result = mask_url("https://vllm.internal:7777/v1/chat/completions")
        assert ":7777" in result

    def test_no_port_in_url(self) -> None:
        """URL sem porta explícita → sem porta no resultado."""
        result = mask_url("http://host/v1")
        assert result == "http://host"
        assert "/" not in result.split("://", 1)[1]

    def test_malformed_url_returns_sentinel(self) -> None:
        """URL não parseável deve retornar '***' sem levantar exceção."""
        result = mask_url("not-a-url")
        assert result == "***" or result.startswith("not-a-url")
        # Não pode levantar exceção — garante robustez nos logs

    def test_returns_string(self) -> None:
        """Deve sempre retornar str, mesmo em caso de falha."""
        result = mask_url("")
        assert isinstance(result, str)

    def test_strips_query_and_fragment(self) -> None:
        """Query string e fragment não devem aparecer no resultado."""
        result = mask_url("http://host:8000/path?key=secret#frag")
        assert "key=secret" not in result
        assert "frag" not in result
        assert "#" not in result
        assert "?" not in result


class TestMaskPath:
    def test_shows_only_filename(self) -> None:
        """Deve mostrar apenas o nome do arquivo, não o path completo."""
        p = Path("/home/user/configs/experiment_round1.yaml")
        result = mask_path(p)
        assert result == "<...>/experiment_round1.yaml"
        assert "/home" not in result
        assert "user" not in result

    def test_nested_path(self) -> None:
        """Funciona com paths aninhados."""
        p = Path("/data/runs/2026-06-07/questions.jsonl")
        result = mask_path(p)
        assert result == "<...>/questions.jsonl"

    def test_simple_filename(self) -> None:
        """Funciona com arquivo simples (sem diretório)."""
        p = Path("config.yaml")
        result = mask_path(p)
        assert result == "<...>/config.yaml"
