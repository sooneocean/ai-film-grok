"""Shim — implementation in cli.cli_plan_project (W7 package layout).

Keeps `import cli_plan_project` / `from cli_plan_project import …` working for hard-compat.
"""
from cli import cli_plan_project as _impl
import sys as _sys

_sys.modules[__name__] = _impl
