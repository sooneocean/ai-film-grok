"""Shim — implementation in cli.cli_review (W7 package layout).

Keeps `import cli_review` / `from cli_review import …` working for hard-compat.
"""
from cli import cli_review as _impl
import sys as _sys

_sys.modules[__name__] = _impl
