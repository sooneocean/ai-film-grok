"""Shim — implementation in cli.cli_skill (W7 package layout).

Keeps `import cli_skill` / `from cli_skill import …` working for hard-compat.
"""
from cli import cli_skill as _impl
import sys as _sys

_sys.modules[__name__] = _impl
