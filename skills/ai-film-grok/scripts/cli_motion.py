"""Shim — implementation in cli.cli_motion (W7 package layout).

Keeps `import cli_motion` / `from cli_motion import …` working for hard-compat.
"""
from cli import cli_motion as _impl
import sys as _sys

_sys.modules[__name__] = _impl
