"""Shim — implementation in audio.lipsync_pilot (W6 package layout).

Keeps `import lipsync_pilot` / `from lipsync_pilot import …` working for hard-compat.
"""
import sys as _sys

from audio import lipsync_pilot as _impl

_sys.modules[__name__] = _impl
