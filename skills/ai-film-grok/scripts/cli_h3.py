"""Shim — implementation in cli.cli_h3 (W7 package layout).

Keeps `import cli_h3` / `from cli_h3 import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_h3 as _impl

_sys.modules[__name__] = _impl
