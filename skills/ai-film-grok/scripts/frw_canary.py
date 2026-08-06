"""Shim — implementation in media.frw_canary (W6 package layout).

Keeps `import frw_canary` / `from frw_canary import …` working for hard-compat.
"""
import sys as _sys

from media import frw_canary as _impl

_sys.modules[__name__] = _impl
