"""Shim — implementation in cli.cli_post (W7 package layout).

Keeps `import cli_post` / `from cli_post import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_post as _impl

_sys.modules[__name__] = _impl
