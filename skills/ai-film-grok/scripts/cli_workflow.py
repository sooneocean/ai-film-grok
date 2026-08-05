"""Shim — implementation in cli.cli_workflow (W7 package layout).

Keeps `import cli_workflow` / `from cli_workflow import …` working for hard-compat.
"""
from cli import cli_workflow as _impl
import sys as _sys

_sys.modules[__name__] = _impl
