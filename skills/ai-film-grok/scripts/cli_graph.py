"""Shim — implementation in cli.cli_graph (W7 package layout).

Keeps `import cli_graph` / `from cli_graph import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_graph as _impl

_sys.modules[__name__] = _impl
