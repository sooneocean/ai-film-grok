"""Shim — implementation in cli.cli_route (W7 package layout).

Keeps `import cli_route` / `from cli_route import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_route as _impl

_sys.modules[__name__] = _impl
