"""Shim — implementation in cli.cli_plan (W7 package layout).

Keeps `import cli_plan` / `from cli_plan import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_plan as _impl

_sys.modules[__name__] = _impl
