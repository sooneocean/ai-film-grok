"""Shim — implementation in cli.cli_workshop (W7 package layout).

Keeps `import cli_workshop` / `from cli_workshop import …` working for hard-compat.
"""
from cli import cli_workshop as _impl
import sys as _sys

_sys.modules[__name__] = _impl
