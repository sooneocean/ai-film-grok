"""Shim — implementation in cli.cli_interactive (W7 package layout).

Keeps `import cli_interactive` / `from cli_interactive import …` working for hard-compat.
"""
from cli import cli_interactive as _impl
import sys as _sys

_sys.modules[__name__] = _impl
