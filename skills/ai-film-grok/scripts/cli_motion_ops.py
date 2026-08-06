"""Shim — implementation in cli.cli_motion_ops (W7 package layout).

Keeps `import cli_motion_ops` / `from cli_motion_ops import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_motion_ops as _impl

_sys.modules[__name__] = _impl
