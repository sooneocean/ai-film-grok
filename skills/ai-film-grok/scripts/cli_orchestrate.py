"""Shim — implementation in cli.cli_orchestrate (W7 package layout).

Keeps `import cli_orchestrate` / `from cli_orchestrate import …` working for hard-compat.
"""
from cli import cli_orchestrate as _impl
import sys as _sys

_sys.modules[__name__] = _impl
