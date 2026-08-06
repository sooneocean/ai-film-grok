"""Shim — implementation in cli.cli_quality (W7 package layout).

Keeps `import cli_quality` / `from cli_quality import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_quality as _impl

_sys.modules[__name__] = _impl
