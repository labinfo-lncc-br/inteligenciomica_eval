from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__: str = _pkg_version("inteligenciomica-eval")
except PackageNotFoundError:
    __version__ = "unknown"
