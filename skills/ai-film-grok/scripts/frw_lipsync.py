"""Shim — implementation in media.frw_lipsync (W6 package layout).

Keeps `import frw_lipsync` / `from frw_lipsync import …` working for hard-compat.
"""
import sys as _sys

from media import frw_lipsync as _impl

_sys.modules[__name__] = _impl
