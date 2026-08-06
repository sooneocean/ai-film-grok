"""Shim — implementation in cli.cli_still_challenge (W7 package layout).

Keeps `import cli_still_challenge` / `from cli_still_challenge import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_still_challenge as _impl

_sys.modules[__name__] = _impl
