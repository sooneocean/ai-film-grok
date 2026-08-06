"""Shim — implementation in cli.cli_review (W7 package layout).

Keeps `import cli_review` / `from cli_review import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_review as _impl

_sys.modules[__name__] = _impl
