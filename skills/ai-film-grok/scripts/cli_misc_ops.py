"""Shim — implementation in cli.cli_misc_ops (W7 package layout).

Keeps `import cli_misc_ops` / `from cli_misc_ops import …` working for hard-compat.
"""
from cli import cli_misc_ops as _impl
import sys as _sys

_sys.modules[__name__] = _impl
