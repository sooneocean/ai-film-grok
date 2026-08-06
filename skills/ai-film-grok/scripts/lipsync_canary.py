"""Shim — implementation in audio.lipsync_canary (W6 package layout).

Keeps `import lipsync_canary` / `from lipsync_canary import …` working for hard-compat.
"""
import sys as _sys

from audio import lipsync_canary as _impl

_sys.modules[__name__] = _impl
