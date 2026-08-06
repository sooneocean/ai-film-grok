"""Shim — implementation in cli.cli_quality_ops (W7 package layout).

Keeps `import cli_quality_ops` / `from cli_quality_ops import …` working for hard-compat.
"""
from cli import cli_quality_ops as _impl
import sys as _sys

_sys.modules[__name__] = _impl
