"""Shim — implementation in cli.cli_workshop (W7 package layout).

Keeps `import cli_workshop` / `from cli_workshop import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_workshop as _impl

_sys.modules[__name__] = _impl
