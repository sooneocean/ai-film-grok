"""Shim — implementation in audio.lipsync_pilot (W6 package layout).

Keeps `import lipsync_pilot` / `from lipsync_pilot import …` working for hard-compat.
"""
from audio import lipsync_pilot as _impl
import sys as _sys

_sys.modules[__name__] = _impl
