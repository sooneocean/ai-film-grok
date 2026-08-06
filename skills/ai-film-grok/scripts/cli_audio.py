"""Shim — implementation in cli.cli_audio (W7 package layout).

Keeps `import cli_audio` / `from cli_audio import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_audio as _impl

_sys.modules[__name__] = _impl
