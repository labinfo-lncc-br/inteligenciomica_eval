"""PromptRegistry — carregador e renderizador de templates Jinja2.

Os templates ficam em ``infrastructure/prompts/`` e são versionados como código.
O campo ``prompt_version`` rastreia exatamente qual versão do bundle de geração foi
usada em cada linha do Parquet (§5.3).  A partir de TAREFA-316, ``prompt_version``
grava ``generation_prompt_version`` (bundle RAG), não o ``git describe`` do registry
(ADR-015).
"""

from __future__ import annotations

import functools
import os
import subprocess
from collections.abc import Sequence

import jinja2
import structlog

from inteligenciomica_eval.domain.ports import Chunk

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

    # ------------------------------------------------------------------
    # Bundles RAG versionados (ADR-015)
    # ------------------------------------------------------------------

    def list_rag_versions(self) -> list[str]:
        """Lista as versões de bundle RAG disponíveis no pacote.

        Cada versão corresponde a um subdiretório em ``infrastructure/prompts/rag/``
        contendo ``system.txt`` e ``user.j2``.

        Returns:
            Lista ordenada de nomes de versão disponíveis (ex.: ``["v1_production"]``).
        """
        versions: set[str] = set()
        for tpl in self._env.list_templates():
            parts = tpl.replace("\\", "/").split("/")
            if len(parts) >= 2 and parts[0] == "rag" and not parts[1].startswith("_"):
                versions.add(parts[1])
        return sorted(versions)

    def render_rag_generation(
        self,
        *,
        version: str,
        question: str,
        contexts: Sequence[Chunk],
    ) -> tuple[str, str]:
        """Renderiza o bundle de prompt de geração RAG versionado.

        Carrega ``system.txt`` (texto puro) e ``user.j2`` (Jinja2) do bundle
        ``rag/<version>/`` e constrói as mensagens ``system`` e ``user`` prontas
        para envio ao LLM gerador.

        O contexto é formatado como ``"[PMID:{source}] {text}"`` unido por ``"\\n\\n"``.
        Se ``source`` estiver vazio, usa ``"N/A"`` (replica produção, ADR-015 §D4).

        Args:
            version: identificador da versão do bundle (ex.: ``"v1_production"``).
            question: texto da pergunta a ser enviada ao LLM.
            contexts: chunks recuperados pelo retriever; ``source`` é o PMID.

        Returns:
            Tupla ``(system_content, user_content)`` pronta para
            ``messages=[{"role":"system","content":system}, {"role":"user","content":user}]``.

        Raises:
            ValueError: se ``version`` não existir, com lista de versões disponíveis.
        """
        available = self.list_rag_versions()
        if version not in available:
            raise ValueError(
                f"RAG prompt bundle {version!r} não encontrado. "
                f"Versões disponíveis: {available}"
            )
        assert self._env.loader is not None  # PackageLoader sempre presente
        system_source, _, _ = self._env.loader.get_source(
            self._env, f"rag/{version}/system.txt"
        )
        context_str = "\n\n".join(
            f"[PMID:{c.source or 'N/A'}] {c.text}" for c in contexts
        )
        user_template = self._env.get_template(f"rag/{version}/user.j2")
        user_content = user_template.render(context=context_str, question=question)
        return system_source, user_content

    # ------------------------------------------------------------------
    # Rubrica biomédica (Camada 2 — juiz)
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
