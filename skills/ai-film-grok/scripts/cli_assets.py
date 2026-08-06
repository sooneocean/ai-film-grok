"""Shim — implementation in cli.cli_assets (W7 package layout).

Keeps `import cli_assets` / `from cli_assets import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_assets as _impl

_sys.modules[__name__] = _impl
