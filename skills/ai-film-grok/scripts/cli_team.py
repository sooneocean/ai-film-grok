"""Shim — implementation in cli.cli_team (W7 package layout).

Keeps `import cli_team` / `from cli_team import …` working for hard-compat.
"""
from cli import cli_team as _impl
import sys as _sys

_sys.modules[__name__] = _impl
