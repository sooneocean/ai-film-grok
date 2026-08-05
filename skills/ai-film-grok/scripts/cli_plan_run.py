"""Shim — implementation in cli.cli_plan_run (W7 package layout).

Keeps `import cli_plan_run` / `from cli_plan_run import …` working for hard-compat.
"""
from cli import cli_plan_run as _impl
import sys as _sys

_sys.modules[__name__] = _impl
