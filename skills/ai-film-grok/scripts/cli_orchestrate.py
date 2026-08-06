"""Shim — implementation in cli.cli_orchestrate (W7 package layout).

Keeps `import cli_orchestrate` / `from cli_orchestrate import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_orchestrate as _impl

_sys.modules[__name__] = _impl
