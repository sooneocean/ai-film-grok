"""Shim — implementation in cli.cli_status (W7 package layout).

Keeps `import cli_status` / `from cli_status import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_status as _impl

_sys.modules[__name__] = _impl
