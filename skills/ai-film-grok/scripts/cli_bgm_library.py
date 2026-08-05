"""Shim — implementation in cli.cli_bgm_library (W7 package layout).

Keeps `import cli_bgm_library` / `from cli_bgm_library import …` working for hard-compat.
"""
from cli import cli_bgm_library as _impl
import sys as _sys

_sys.modules[__name__] = _impl
