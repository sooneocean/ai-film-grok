"""Shim — implementation in cli.cli_hub_residual (R3).

Keeps `import cli_hub_residual` working for hard-compat.
"""
import sys as _sys

from cli import cli_hub_residual as _impl

_sys.modules[__name__] = _impl
