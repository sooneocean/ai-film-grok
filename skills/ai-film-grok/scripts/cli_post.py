"""Shim — implementation in cli.cli_post (W7 package layout).

Keeps `import cli_post` / `from cli_post import …` working for hard-compat.
"""
from cli import cli_post as _impl
import sys as _sys

_sys.modules[__name__] = _impl
