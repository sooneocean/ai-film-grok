"""Shim — implementation in cli.cli_h3 (W7 package layout).

Keeps `import cli_h3` / `from cli_h3 import …` working for hard-compat.
"""
from cli import cli_h3 as _impl
import sys as _sys

_sys.modules[__name__] = _impl
