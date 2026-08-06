"""Shim — implementation in cli.cli_write_spec (W7 package layout).

Keeps `import cli_write_spec` / `from cli_write_spec import …` working for hard-compat.
"""
from cli import cli_write_spec as _impl
import sys as _sys

_sys.modules[__name__] = _impl
