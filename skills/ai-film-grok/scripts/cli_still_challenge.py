"""Shim — implementation in cli.cli_still_challenge (W7 package layout).

Keeps `import cli_still_challenge` / `from cli_still_challenge import …` working for hard-compat.
"""
from cli import cli_still_challenge as _impl
import sys as _sys

_sys.modules[__name__] = _impl
