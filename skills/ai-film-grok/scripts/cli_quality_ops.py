"""Shim — implementation in cli.cli_quality_ops (W7 package layout).

Keeps `import cli_quality_ops` / `from cli_quality_ops import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_quality_ops as _impl

_sys.modules[__name__] = _impl
