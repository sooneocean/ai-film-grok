"""Shim — implementation in cli.cli_plan_mutation (W7 package layout).

Keeps `import cli_plan_mutation` / `from cli_plan_mutation import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_plan_mutation as _impl

_sys.modules[__name__] = _impl
