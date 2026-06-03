"""Gate script para mutation testing do M6 (TAREFA-601).

Executa ``mutmut run`` sobre ``domain/services/``, coleta resultados via a
API Python interna do mutmut 3.x, grava um relatório legível em
``tests/mutation/mutation_report.txt`` e retorna exit code 1 se o mutation
score ficar abaixo de 80%.

Destinado a rodar FORA do CI normal (lentidão); o CI apenas verifica a
existência e validade do artefato commitado no PR da TAREFA-601.

Usage::

    uv run python scripts/mutation_gate.py
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from io import StringIO
from pathlib import Path

_MIN_SCORE: float = 80.0
_REPORT_PATH: Path = Path("tests/mutation/mutation_report.txt")

_out = sys.stdout.write


def _echo(msg: str = "") -> None:
    """Imprime ``msg`` para stdout (wrapper testável, sem T201)."""
    _out(msg + "\n")


def _mutmut_cmd() -> list[str]:
    """Retorna o comando base do mutmut.

    Usa o entry point instalado pelo uv (``mutmut`` no PATH do venv) em vez de
    ``python -m mutmut``. A diferença é importante: o entry point importa
    ``mutmut.__main__`` como submodule (registrando em ``sys.modules``), enquanto
    ``-m`` o executa como ``__main__``. Isso evita a dupla chamada de
    ``set_start_method('fork')`` durante a fase de stats do mutmut 3.x.
    """
    venv_bin = Path(sys.executable).parent
    mutmut_bin = venv_bin / "mutmut"
    if mutmut_bin.exists():
        return [str(mutmut_bin)]
    return [sys.executable, "-m", "mutmut"]


def _get_mutmut_version() -> str:
    """Retorna a string de versão instalada do mutmut."""
    result = subprocess.run(
        [*_mutmut_cmd(), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout + result.stderr).strip()


def _run_mutmut() -> int:
    """Executa ``mutmut run`` e imprime saída ao vivo. Retorna o exit code."""
    _echo("=" * 70)
    _echo("Executando mutmut run ...")
    _echo("=" * 70)
    proc = subprocess.run(
        [*_mutmut_cmd(), "run"],
        check=False,
    )
    return proc.returncode


def _collect_results() -> dict[str, dict[str, str]]:
    """Carrega dados de mutação dos arquivos .meta gerados pelo mutmut.

    Returns:
        Mapeamento ``{caminho_fonte -> {nome_mutante -> status}}``.
    """
    # Importação do internals do mutmut — só disponível no ambiente dev.
    from mutmut.__main__ import (  # type: ignore[import-untyped]
        SourceFileMutationData,
        ensure_config_loaded,
        status_by_exit_code,
        walk_source_files,
    )

    ensure_config_loaded()
    results: dict[str, dict[str, str]] = {}
    for path in walk_source_files():
        if not str(path).endswith(".py"):
            continue
        m = SourceFileMutationData(path=path)
        m.load()
        if not m.exit_code_by_key:
            continue
        results[str(path)] = {
            k: status_by_exit_code[v] for k, v in m.exit_code_by_key.items()
        }
    return results


def _get_survivor_diff(mutant_name: str) -> str:
    """Retorna o diff unificado de um mutante sobrevivente via ``mutmut show``."""
    result = subprocess.run(
        [*_mutmut_cmd(), "show", mutant_name],
        capture_output=True,
        text=True,
        check=False,
    )
    return (result.stdout + result.stderr).strip()


def _compute_score(
    results: dict[str, dict[str, str]],
) -> tuple[int, int, int, int, float]:
    """Calcula estatísticas de mutacao.

    Returns:
        ``(total, killed, survived, not_checked, score_pct)``
        onde ``score_pct = killed / (total - not_checked) * 100``.
    """
    total = killed = survived = not_checked = 0
    for statuses in results.values():
        for status in statuses.values():
            total += 1
            if status == "killed":
                killed += 1
            elif status == "survived":
                survived += 1
            elif status == "not checked":
                not_checked += 1
    checked = total - not_checked
    score = (killed / checked * 100.0) if checked > 0 else 0.0
    return total, killed, survived, not_checked, score


def _build_report(
    *,
    version: str,
    total: int,
    killed: int,
    survived: int,
    not_checked: int,
    score: float,
    survivor_details: list[tuple[str, str]],
) -> str:
    """Monta o conteudo do relatorio legivel."""
    buf = StringIO()
    now = datetime.now().astimezone()
    buf.write("Mutation Testing Report -- inteligenciomica-eval (TAREFA-601)\n")
    buf.write(f"Generated  : {now.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")
    buf.write(f"Tool       : {version}\n")
    buf.write("Target     : src/inteligenciomica_eval/domain/services/\n")
    buf.write("Tests      : tests/unit/domain/services/\n")
    buf.write("\n")
    buf.write("Summary\n")
    buf.write("-------\n")
    buf.write(f"Total mutants  : {total}\n")
    buf.write(f"Not checked    : {not_checked}\n")
    buf.write(f"Killed         : {killed}\n")
    buf.write(f"Survived       : {survived}\n")
    buf.write(f"Mutation score : {score:.1f}%\n")
    buf.write(f"Threshold      : {_MIN_SCORE:.0f}%\n")
    buf.write(f"Gate           : {'PASS' if score >= _MIN_SCORE else 'FAIL'}\n")
    buf.write("\n")

    if survivor_details:
        buf.write(f"Survivors ({len(survivor_details)})\n")
        buf.write("-" * 40 + "\n")
        for name, diff in survivor_details:
            buf.write(f"\n{'=' * 60}\n")
            buf.write(f"Mutant : {name}\n")
            buf.write(diff)
            buf.write("\n")
    else:
        buf.write("Survivors: none\n")

    return buf.getvalue()


def main() -> None:
    """Entry point -- executa o gate e escreve o relatorio."""
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    version = _get_mutmut_version()
    _echo(f"mutmut version: {version}\n")

    run_exit_code = _run_mutmut()
    # exit code 0 = todos mortos; 1 = sobreviventes (normal).
    # exit code >= 2 indica crash do mutmut: abortar para não ler cache antigo.
    if run_exit_code >= 2:
        sys.stderr.write(
            f"\n[ERROR] mutmut run terminou com código {run_exit_code}; "
            "abortando para evitar leitura de resultados antigos em cache.\n"
        )
        sys.exit(2)

    results = _collect_results()
    total, killed, survived, not_checked, score = _compute_score(results)

    survivor_details: list[tuple[str, str]] = []
    for statuses in results.values():
        for name, status in statuses.items():
            if status == "survived":
                diff = _get_survivor_diff(name)
                survivor_details.append((name, diff))

    report = _build_report(
        version=version,
        total=total,
        killed=killed,
        survived=survived,
        not_checked=not_checked,
        score=score,
        survivor_details=survivor_details,
    )

    _REPORT_PATH.write_text(report, encoding="utf-8")
    _echo(f"\nRelatorio gravado em {_REPORT_PATH}")
    _echo("\n" + report)

    if score < _MIN_SCORE:
        sys.stderr.write(
            f"\n[FAIL] Mutation score {score:.1f}% < limiar {_MIN_SCORE:.0f}%.\n"
        )
        sys.exit(1)

    _echo(f"[PASS] Mutation score {score:.1f}% >= {_MIN_SCORE:.0f}%.")


if __name__ == "__main__":  # pragma: no cover
    main()
