"""Shim — implementation in audio.lipsync_challenge (W6 package layout).

Keeps `import lipsync_challenge` / `from lipsync_challenge import …` working for hard-compat.
"""
import sys as _sys

from audio import lipsync_challenge as _impl

_sys.modules[__name__] = _impl
