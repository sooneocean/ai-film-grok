"""Shim — implementation in cli.cli_media (W7 package layout).

Keeps `import cli_media` / `from cli_media import …` working for hard-compat.
"""
from cli import cli_media as _impl
import sys as _sys

_sys.modules[__name__] = _impl
