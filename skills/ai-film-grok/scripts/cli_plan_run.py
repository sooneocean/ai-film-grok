"""Shim — implementation in cli.cli_plan_run (W7 package layout).

Keeps `import cli_plan_run` / `from cli_plan_run import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_plan_run as _impl

_sys.modules[__name__] = _impl
