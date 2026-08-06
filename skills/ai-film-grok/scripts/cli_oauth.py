"""Shim — implementation in cli.cli_oauth (W7 package layout).

Keeps `import cli_oauth` / `from cli_oauth import …` working for hard-compat.
"""
from cli import cli_oauth as _impl
import sys as _sys

_sys.modules[__name__] = _impl
