"""Shim — implementation in cli.cli_bgm_library (W7 package layout).

Keeps `import cli_bgm_library` / `from cli_bgm_library import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_bgm_library as _impl

_sys.modules[__name__] = _impl
