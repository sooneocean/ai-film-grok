"""Shim — implementation in media.frw_canary (W6 package layout).

Keeps `import frw_canary` / `from frw_canary import …` working for hard-compat.
"""
from media import frw_canary as _impl
import sys as _sys

_sys.modules[__name__] = _impl
