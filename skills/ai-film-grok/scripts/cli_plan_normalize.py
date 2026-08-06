"""Shim — implementation in cli.cli_plan_normalize (W7 package layout).

Keeps `import cli_plan_normalize` / `from cli_plan_normalize import …` working for hard-compat.
"""
from cli import cli_plan_normalize as _impl
import sys as _sys

_sys.modules[__name__] = _impl
