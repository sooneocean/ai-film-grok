"""Shim — implementation in cli.cli_assets (W7 package layout).

Keeps `import cli_assets` / `from cli_assets import …` working for hard-compat.
"""
from cli import cli_assets as _impl
import sys as _sys

_sys.modules[__name__] = _impl
