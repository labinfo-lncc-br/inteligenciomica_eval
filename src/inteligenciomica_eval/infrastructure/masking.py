"""Helpers de mascaramento para logs seguros (ADR-008, TAREFA-314).

Ponto único de verdade para mascaramento de URLs e paths em eventos structlog.
Nenhum endpoint/credencial cru deve aparecer em logs de infraestrutura.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


def mask_url(url: str) -> str:
    """Mascara credenciais e path de URL para exibição segura em logs (ADR-008).

    Remove ``user:password@`` se presentes; reduz a ``scheme://host:port``
    sem path, query ou fragment.

    Args:
        url: URL possivelmente com credenciais ou path sensível.

    Returns:
        URL reduzida a ``scheme://host:port`` (sem nenhum path).
        Retorna ``"***"`` se a URL não puder ser parseada.
    """
    try:
        p = urlparse(url)
        if not p.hostname:
            return "***"
        masked = f"{p.scheme}://{p.hostname}"
        if p.port:
            masked += f":{p.port}"
        return masked
    except Exception:
        return "***"


def mask_path(p: Path) -> str:
    """Exibe apenas o nome do arquivo para log de auditoria.

    Evita vazar o layout de diretórios do disco em eventos de log.

    Args:
        p: caminho de arquivo.

    Returns:
        String ``<...>/{filename}`` mostrando apenas o nome do arquivo.
    """
    return f"<...>/{p.name}"
