"""Shim — implementation in cli.cli_plan_normalize (W7 package layout).

Keeps `import cli_plan_normalize` / `from cli_plan_normalize import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_plan_normalize as _impl

_sys.modules[__name__] = _impl
