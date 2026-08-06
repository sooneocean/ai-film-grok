"""Shim — implementation in audio.lipsync_challenge (W6 package layout).

Keeps `import lipsync_challenge` / `from lipsync_challenge import …` working for hard-compat.
"""
from audio import lipsync_challenge as _impl
import sys as _sys

_sys.modules[__name__] = _impl
