"""Shim — implementation in cli.cli_motion (W7 package layout).

Keeps `import cli_motion` / `from cli_motion import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_motion as _impl

_sys.modules[__name__] = _impl
