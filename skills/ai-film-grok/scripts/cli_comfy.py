"""Shim — implementation in cli.cli_comfy (W7 package layout).

Keeps `import cli_comfy` / `from cli_comfy import …` working for hard-compat.
"""
import sys as _sys

from cli import cli_comfy as _impl

_sys.modules[__name__] = _impl
