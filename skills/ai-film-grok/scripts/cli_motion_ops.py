"""Shim — implementation in cli.cli_motion_ops (W7 package layout).

Keeps `import cli_motion_ops` / `from cli_motion_ops import …` working for hard-compat.
"""
from cli import cli_motion_ops as _impl
import sys as _sys

_sys.modules[__name__] = _impl
