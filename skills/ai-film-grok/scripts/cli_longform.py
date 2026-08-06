"""Shim — implementation in cli.cli_longform (W7 package layout).

Keeps `import cli_longform` / `from cli_longform import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_longform as _impl

_sys.modules[__name__] = _impl
