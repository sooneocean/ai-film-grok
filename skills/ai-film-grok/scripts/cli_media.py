"""Shim — implementation in cli.cli_media (W7 package layout).

Keeps `import cli_media` / `from cli_media import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_media as _impl

_sys.modules[__name__] = _impl
