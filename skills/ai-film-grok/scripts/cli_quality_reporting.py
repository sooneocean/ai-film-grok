"""Shim — implementation in cli.cli_quality_reporting (W7 package layout).

Keeps `import cli_quality_reporting` / `from cli_quality_reporting import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_quality_reporting as _impl

_sys.modules[__name__] = _impl
