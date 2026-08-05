"""Shim — implementation in cli.cli_status (W7 package layout).

Keeps `import cli_status` / `from cli_status import …` working for hard-compat.
"""
from cli import cli_status as _impl
import sys as _sys

_sys.modules[__name__] = _impl
