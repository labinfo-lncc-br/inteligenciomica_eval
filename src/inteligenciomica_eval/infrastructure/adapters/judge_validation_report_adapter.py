"""JudgeValidationReportAdapter — gera relatório Markdown via template Jinja2.

Usa o template ``infrastructure/prompts/judge_validation_report.j2`` carregado
via PackageLoader (mesmo padrão do HTMLReportAdapter — TAREFA-408).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import jinja2

from inteligenciomica_eval.application.judge_validation import JudgeValidationResult


class JudgeValidationReportAdapter:
    """Gera ``docs/judge_validation_report.md`` via template Jinja2.

    Args:
        _env: instância Jinja2 opcional (injetável para testes).
    """

    def __init__(self, _env: jinja2.Environment | None = None) -> None:
        if _env is not None:
            self._env = _env
        else:
            loader = jinja2.PackageLoader(
                "inteligenciomica_eval",
                package_path="infrastructure/prompts",
            )
            self._env = jinja2.Environment(
                loader=loader,
                autoescape=False,
                keep_trailing_newline=True,
                undefined=jinja2.Undefined,
            )

    def generate_report(
        self,
        result: JudgeValidationResult,
        path: Path,
        *,
        run_id: str = "",
        round_id: str = "",
    ) -> None:
        """Renderiza o relatório e grava em ``path``.

        Args:
            result: resultado da validação (saída de ``JudgeValidationUseCase.run``).
            path: caminho de destino do arquivo Markdown.
            run_id: identificador do run (para o cabeçalho do relatório).
            round_id: identificador da rodada (para o cabeçalho do relatório).
        """
        template = self._env.get_template("judge_validation_report.j2")
        content = template.render(
            result=result,
            run_id=run_id,
            round_id=round_id,
            generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
