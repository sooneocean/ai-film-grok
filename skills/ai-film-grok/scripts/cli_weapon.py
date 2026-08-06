"""Shim — implementation in cli.cli_weapon (W7 package layout).

Keeps `import cli_weapon` / `from cli_weapon import …` working for hard-compat.
"""
from cli import cli_weapon as _impl
import sys as _sys

_sys.modules[__name__] = _impl
