"""Shim — implementation in cli.cli_review_ops (W7 package layout).

Keeps `import cli_review_ops` / `from cli_review_ops import …` working for hard-compat.
"""
from cli import cli_review_ops as _impl
import sys as _sys

_sys.modules[__name__] = _impl
