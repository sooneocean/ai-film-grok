"""Shim — implementation in cli.cli_graph (W7 package layout).

Keeps `import cli_graph` / `from cli_graph import …` working for hard-compat.
"""
from cli import cli_graph as _impl
import sys as _sys

_sys.modules[__name__] = _impl
