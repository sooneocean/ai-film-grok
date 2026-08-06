"""Shim — implementation in cli.cli_evidence (W7 package layout).

Keeps `import cli_evidence` / `from cli_evidence import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_evidence as _impl

_sys.modules[__name__] = _impl
