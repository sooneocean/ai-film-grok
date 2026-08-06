"""Shim — implementation in cli.cli_optimization (W7 package layout).

Keeps `import cli_optimization` / `from cli_optimization import …` working for hard-compat.
"""
from cli import cli_optimization as _impl
import sys as _sys

_sys.modules[__name__] = _impl
