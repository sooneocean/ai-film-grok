"""Shim — implementation in cli.cli_comfy (W7 package layout).

Keeps `import cli_comfy` / `from cli_comfy import …` working for hard-compat.
"""
from cli import cli_comfy as _impl
import sys as _sys

_sys.modules[__name__] = _impl
