"""Shim — implementation in cli.cli_director_ops (W7 package layout).

Keeps `import cli_director_ops` / `from cli_director_ops import …` working for hard-compat.
"""
from cli import cli_director_ops as _impl
import sys as _sys

_sys.modules[__name__] = _impl
