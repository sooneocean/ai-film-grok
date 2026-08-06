"""Shim — implementation in cli.cli_workflow (W7 package layout).

Keeps `import cli_workflow` / `from cli_workflow import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_workflow as _impl

_sys.modules[__name__] = _impl
