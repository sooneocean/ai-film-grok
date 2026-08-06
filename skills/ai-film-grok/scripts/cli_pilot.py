"""Shim — implementation in cli.cli_pilot (W7 package layout).

Keeps `import cli_pilot` / `from cli_pilot import …` working for hard-compat.
"""
from cli import cli_pilot as _impl
import sys as _sys

_sys.modules[__name__] = _impl
