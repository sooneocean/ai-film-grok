"""Shim — implementation in cli.cli_bootstrap (W7 package layout).

Keeps `import cli_bootstrap` / `from cli_bootstrap import …` working for hard-compat.
"""
from cli import cli_bootstrap as _impl
import sys as _sys

_sys.modules[__name__] = _impl
