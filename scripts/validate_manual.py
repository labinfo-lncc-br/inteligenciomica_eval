"""Smoke-test do manual de operação (TAREFA-604, atualizado TAREFA-606).

Percorre ``docs/operations_manual.md``, extrai blocos de código shell (```bash```),
ignora blocos sob seções marcadas ``[PENDENTE: ...]``, e verifica:

1. Cada bloco com ``ielm-eval <subcmd>`` tem o subcomando registrado na CLI
   (``ielm-eval <subcmd> --help`` termina com exit code 0).
2. Cada linha com ``curl http://localhost:...`` é sintaticamente válida: deve ter
   pelo menos um argumento de URL no formato ``http://localhost:<porta>/...`` com
   porta numérica e sem caracteres ilegais de URL (espaços não escapados).
3. As flags obrigatórias citadas no manual existem na saída de
   ``ielm-eval run --help``: ``--run-id`` e ``--require-verified-determinism``.

Blocos ``curl`` são validados sintaticamente, nunca conectados.

Saída:
    PASS — todos os subcomandos e flags validados (fora de seções PENDENTE) existem.
    FAIL — lista de subcomandos inexistentes, flags ausentes ou erros de sintaxe curl.

Usage::

    python scripts/validate_manual.py
    python scripts/validate_manual.py --manual docs/operations_manual.md
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_DEFAULT_MANUAL = Path("docs/operations_manual.md")

# Heading que indica seção pendente — blocos de código dentro dela são ignorados.
_PENDING_RE = re.compile(r"(?i)\[PENDENTE[:\s]")

# Extrai o subcomando: "ielm-eval <subcmd> ..."
_CMD_RE = re.compile(r"^\s*(?:uv run )?ielm-eval\s+([a-z][a-z0-9-]*)")

# Valida URL curl: http://localhost:<porta-numérica>/caminho-sem-espaços-literais
_CURL_URL_RE = re.compile(r"http://localhost:\d+(/[^\s]*)?")


def _extract_blocks(text: str) -> list[str]:
    """Extrai blocos de código shell que NÃO estão sob seções PENDENTE.

    Usa um parser de estado linha-a-linha que rastreia TODOS os tipos de fence
    (não só bash) para evitar que o fechamento ` ``` ` de um bloco yaml/json/etc.
    seja reinterpretado como abertura de um bloco sem especificador.

    Captura conteúdo apenas de blocos cuja linguagem é bash/sh/shell ou vazia
    (sem especificador), pois são os que podem conter ``ielm-eval`` e ``curl``.

    Blocos sob seções com ``[PENDENTE: ...]`` são suprimidos.
    """
    # Linha de abertura de fence: captura o especificador de linguagem (pode ser vazio).
    open_re = re.compile(r"^```([a-zA-Z0-9_+-]*)\s*$")
    # Linha de fechamento de fence: exatamente três backticks.
    close_re = re.compile(r"^```\s*$")
    # Linguagens cujo conteúdo queremos capturar para análise.
    shell_langs = {"bash", "sh", "shell", ""}

    lines = text.splitlines()
    suppressed_level: int | None = None
    in_block = False
    capture = False  # True quando o bloco aberto é shell/vazio
    current_block: list[str] = []
    blocks: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Detecta heading e decide supressão (só fora de blocos).
        if not in_block and stripped.startswith("#"):
            heading_level = len(stripped) - len(stripped.lstrip("#"))
            if _PENDING_RE.search(stripped):
                suppressed_level = heading_level
            elif suppressed_level is not None and heading_level <= suppressed_level:
                suppressed_level = None

        if suppressed_level is not None:
            continue

        if not in_block:
            m = open_re.match(stripped)
            if m:
                lang = m.group(1).lower()
                in_block = True
                capture = lang in shell_langs
                current_block = []
        else:
            if close_re.match(stripped):
                if capture:
                    blocks.append("\n".join(current_block))
                in_block = False
                capture = False
                current_block = []
            else:
                if capture:
                    current_block.append(line)

    return blocks


def _subcmds_in_block(block: str) -> list[str]:
    """Retorna lista de subcomandos ielm-eval encontrados no bloco."""
    subcmds: list[str] = []
    for line in block.splitlines():
        m = _CMD_RE.match(line)
        if m:
            subcmd = m.group(1)
            if subcmd not in subcmds:
                subcmds.append(subcmd)
    return subcmds


def _curl_errors_in_block(block: str) -> list[str]:
    """Retorna lista de erros de sintaxe em linhas curl do bloco.

    Valida que linhas ``curl http://localhost:<porta>/...`` têm porta numérica
    e URL sem espaços literais. Não realiza conexão de rede.
    """
    errors: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not re.search(r"\bcurl\b", stripped):
            continue
        # Extrai tokens que começam com http://localhost
        for token in stripped.split():
            if not token.startswith("http://localhost"):
                continue
            if not _CURL_URL_RE.fullmatch(token):
                errors.append(
                    f"URL curl inválida (porta não-numérica ou espaço literal): {token!r}"
                )
    return errors


def _check_subcmd(subcmd: str) -> bool:
    """Retorna True se ``ielm-eval <subcmd> --help`` termina com exit code 0."""
    result = subprocess.run(
        [sys.executable, "-m", "inteligenciomica_eval.cli", subcmd, "--help"],
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return True
    # Tenta via entry point instalado no venv
    venv_bin = Path(sys.executable).parent
    ielm = venv_bin / "ielm-eval"
    if ielm.exists():
        result2 = subprocess.run(
            [str(ielm), subcmd, "--help"],
            capture_output=True,
            check=False,
        )
        return result2.returncode == 0
    return False


def _run_help_output(subcmd: str) -> str:
    """Retorna a saída de ``ielm-eval <subcmd> --help`` (stdout + stderr combinados)."""
    venv_bin = Path(sys.executable).parent
    ielm = venv_bin / "ielm-eval"
    if ielm.exists():
        result = subprocess.run(
            [str(ielm), subcmd, "--help"],
            capture_output=True,
            check=False,
            text=True,
        )
        return result.stdout + result.stderr
    result = subprocess.run(
        [sys.executable, "-m", "inteligenciomica_eval.cli", subcmd, "--help"],
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout + result.stderr


# Flags obrigatórias a validar na saída de ``ielm-eval run --help`` (TAREFA-606).
_REQUIRED_RUN_FLAGS: list[str] = [
    "--run-id",
    "--require-verified-determinism",
]


def _check_run_flags() -> list[str]:
    """Retorna lista de flags ausentes na saída de ``ielm-eval run --help``."""
    help_text = _run_help_output("run")
    return [flag for flag in _REQUIRED_RUN_FLAGS if flag not in help_text]


def main(manual_path: Path = _DEFAULT_MANUAL) -> int:
    """Ponto de entrada principal.

    Args:
        manual_path: caminho para o manual Markdown.

    Returns:
        0 em PASS; 1 em FAIL.
    """
    if not manual_path.exists():
        sys.stderr.write(f"[ERROR] Manual não encontrado: {manual_path}\n")
        return 1

    text = manual_path.read_text(encoding="utf-8")
    blocks = _extract_blocks(text)

    # --- 1. Validação de subcomandos ielm-eval ---
    all_subcmds: list[str] = []
    for block in blocks:
        all_subcmds.extend(_subcmds_in_block(block))

    seen: set[str] = set()
    unique_subcmds: list[str] = []
    for sc in all_subcmds:
        if sc not in seen:
            seen.add(sc)
            unique_subcmds.append(sc)

    failed_subcmds: list[str] = []
    if unique_subcmds:
        sys.stdout.write("Subcomandos ielm-eval:\n")
        for subcmd in unique_subcmds:
            ok = _check_subcmd(subcmd)
            status = "OK" if ok else "FAIL"
            sys.stdout.write(f"  ielm-eval {subcmd:<20} {status}\n")
            if not ok:
                failed_subcmds.append(subcmd)
        sys.stdout.write("\n")

    # --- 2. Validação sintática de URLs curl ---
    curl_errors: list[str] = []
    for block in blocks:
        curl_errors.extend(_curl_errors_in_block(block))

    if curl_errors:
        sys.stdout.write("Erros de sintaxe curl:\n")
        for err in curl_errors:
            sys.stdout.write(f"  {err}\n")
        sys.stdout.write("\n")

    # --- 3. Validação de flags obrigatórias em ielm-eval run --help ---
    missing_flags = _check_run_flags()
    if _REQUIRED_RUN_FLAGS:
        sys.stdout.write("Flags obrigatórias em `ielm-eval run --help`:\n")
        for flag in _REQUIRED_RUN_FLAGS:
            status = "OK" if flag not in missing_flags else "FAIL"
            sys.stdout.write(f"  {flag:<40} {status}\n")
        sys.stdout.write("\n")

    # --- Resultado final ---
    if failed_subcmds or curl_errors or missing_flags:
        if failed_subcmds:
            sys.stderr.write(
                f"FAIL — subcomandos inexistentes: {', '.join(failed_subcmds)}\n"
            )
        if curl_errors:
            sys.stderr.write(
                f"FAIL — {len(curl_errors)} erro(s) de sintaxe curl detectado(s)\n"
            )
        if missing_flags:
            sys.stderr.write(
                f"FAIL — flags ausentes em 'ielm-eval run --help': "
                f"{', '.join(missing_flags)}\n"
            )
        return 1

    if not unique_subcmds:
        sys.stdout.write(
            "PASS — nenhum subcomando ielm-eval encontrado fora de seções PENDENTE.\n"
        )
    else:
        sys.stdout.write(
            "PASS — todos os subcomandos e flags validados existem na CLI.\n"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manual",
        type=Path,
        default=_DEFAULT_MANUAL,
        help="Caminho para o manual Markdown (padrão: docs/operations_manual.md).",
    )
    args = parser.parse_args()
    sys.exit(main(args.manual))
