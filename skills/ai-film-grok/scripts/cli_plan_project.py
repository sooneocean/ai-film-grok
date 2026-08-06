"""Shim — implementation in cli.cli_plan_project (W7 package layout).

Keeps `import cli_plan_project` / `from cli_plan_project import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_plan_project as _impl

_sys.modules[__name__] = _impl
