"""Shim — implementation in cli.cli_interactive (W7 package layout).

Keeps `import cli_interactive` / `from cli_interactive import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_interactive as _impl

_sys.modules[__name__] = _impl
