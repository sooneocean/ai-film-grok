"""Shim — implementation in cli.cli_longform (W7 package layout).

Keeps `import cli_longform` / `from cli_longform import …` working for hard-compat.
"""
from cli import cli_longform as _impl
import sys as _sys

_sys.modules[__name__] = _impl
