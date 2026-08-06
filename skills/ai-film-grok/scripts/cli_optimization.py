"""Shim — implementation in cli.cli_optimization (W7 package layout).

Keeps `import cli_optimization` / `from cli_optimization import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_optimization as _impl

_sys.modules[__name__] = _impl
