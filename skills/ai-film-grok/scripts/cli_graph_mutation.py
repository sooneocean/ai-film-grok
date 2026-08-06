"""Shim — implementation in cli.cli_graph_mutation (W7 package layout).

Keeps `import cli_graph_mutation` / `from cli_graph_mutation import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_graph_mutation as _impl

_sys.modules[__name__] = _impl
