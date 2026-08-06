"""Shim — implementation in cli.cli_quality (W7 package layout).

Keeps `import cli_quality` / `from cli_quality import …` working for hard-compat.
"""
from cli import cli_quality as _impl
import sys as _sys

_sys.modules[__name__] = _impl
