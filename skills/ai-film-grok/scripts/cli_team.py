"""Shim — implementation in cli.cli_team (W7 package layout).

Keeps `import cli_team` / `from cli_team import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_team as _impl

_sys.modules[__name__] = _impl
