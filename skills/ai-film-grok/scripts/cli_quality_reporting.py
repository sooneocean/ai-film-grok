"""Shim — implementation in cli.cli_quality_reporting (W7 package layout).

Keeps `import cli_quality_reporting` / `from cli_quality_reporting import …` working for hard-compat.
"""
from cli import cli_quality_reporting as _impl
import sys as _sys

_sys.modules[__name__] = _impl
