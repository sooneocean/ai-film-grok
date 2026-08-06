"""Shim — implementation in cli.cli_pilot (W7 package layout).

Keeps `import cli_pilot` / `from cli_pilot import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_pilot as _impl

_sys.modules[__name__] = _impl
