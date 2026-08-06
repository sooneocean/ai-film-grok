"""Shim — implementation in audio.lipsync_canary (W6 package layout).

Keeps `import lipsync_canary` / `from lipsync_canary import …` working for hard-compat.
"""
from audio import lipsync_canary as _impl
import sys as _sys

_sys.modules[__name__] = _impl
