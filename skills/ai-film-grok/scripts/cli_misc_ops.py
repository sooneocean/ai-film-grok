"""Shim — implementation in cli.cli_misc_ops (W7 package layout).

Keeps `import cli_misc_ops` / `from cli_misc_ops import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_misc_ops as _impl

_sys.modules[__name__] = _impl
