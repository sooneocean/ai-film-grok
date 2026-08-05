"""Shim — implementation in cli.cli_plan (W7 package layout).

Keeps `import cli_plan` / `from cli_plan import …` working for hard-compat.
"""
from cli import cli_plan as _impl
import sys as _sys

_sys.modules[__name__] = _impl
