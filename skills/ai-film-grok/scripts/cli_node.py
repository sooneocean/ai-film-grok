"""Shim — implementation in cli.cli_node (W7 package layout).

Keeps `import cli_node` / `from cli_node import …` working for hard-compat.
"""
from cli import cli_node as _impl
import sys as _sys

_sys.modules[__name__] = _impl
