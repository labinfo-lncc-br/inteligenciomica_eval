"""PromptRegistry — carregador e renderizador de templates Jinja2.

Os templates ficam em ``infrastructure/prompts/*.j2`` e são versionados como código.
O campo ``prompt_version`` rastreia exatamente qual versão do template foi usada em
cada linha do Parquet (§11.2 do documento de arquitetura).
"""

from __future__ import annotations

import functools
import os
import subprocess
from collections.abc import Sequence

import jinja2
import structlog

_log = structlog.get_logger(__name__)


class PromptRegistry:
    """Carrega e renderiza templates Jinja2 de prompt da avaliação biomédica.

    Imutável após construção — templates não são recarregados em produção.
    A versão capturada via ``git describe`` identifica o exato conjunto de templates
    usado em cada rodada de avaliação.

    Args:
        Nenhum argumento público.  Use :func:`get_default_registry` para obter
        a instância singleton cacheada.
    """

    def __init__(self) -> None:
        self._env = jinja2.Environment(
            loader=jinja2.PackageLoader(
                "inteligenciomica_eval",
                "infrastructure/prompts",
            ),
            autoescape=False,
            keep_trailing_newline=True,
        )
        self._version: str = self._capture_version()

    # ------------------------------------------------------------------
    # Versão
    # ------------------------------------------------------------------

    @staticmethod
    def _capture_version() -> str:
        """Captura a versão do prompt via ``git describe``; fallbacks em cascata.

        Trata ``OSError`` (inclui ``FileNotFoundError``) para ambientes onde o
        binário ``git`` não está instalado — o fallback ainda é aplicado.
        """
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--dirty"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except OSError:
            pass  # git não encontrado — continua para os fallbacks

        env_version = os.environ.get("PROMPT_VERSION")
        if env_version:
            return env_version

        _log.warning(
            "prompt_version_unversioned",
            reason="git indisponível e PROMPT_VERSION não definida",
        )
        return "unversioned"

    @property
    def prompt_version(self) -> str:
        """Versão dos templates capturada uma única vez na instanciação."""
        return self._version

    # ------------------------------------------------------------------
    # Renderização
    # ------------------------------------------------------------------

    def render_biomed_rubric(
        self,
        *,
        question: str,
        ground_truth: str,
        generated_answer: str,
        contexts: Sequence[str],
    ) -> str:
        """Renderiza o template da rubrica biomédica (Camada 2 — Prometheus-2/G-Eval).

        Args:
            question: Pergunta original formulada ao sistema RAG.
            ground_truth: Resposta de referência (anotação humana).
            generated_answer: Resposta gerada pelo LLM sob avaliação.
            contexts: Trechos de contexto recuperados pelo retriever.

        Returns:
            Prompt completo pronto para envio ao juiz LLM.
        """
        template = self._env.get_template("biomed_rubric.j2")
        return template.render(
            question=question,
            ground_truth=ground_truth,
            generated_answer=generated_answer,
            contexts=tuple(contexts),
        )


@functools.cache
def get_default_registry() -> PromptRegistry:
    """Retorna a instância singleton do :class:`PromptRegistry`.

    Construída uma única vez por processo via ``functools.cache``.
    Usar esta função em produção; criar instâncias diretas apenas em testes.

    Returns:
        Instância cacheada do :class:`PromptRegistry`.
    """
    return PromptRegistry()
