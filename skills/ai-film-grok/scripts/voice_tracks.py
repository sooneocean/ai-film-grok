"""Shim — implementation in audio.voice_tracks (W6 package layout).

Keeps `import voice_tracks` / `from voice_tracks import …` working for hard-compat.
"""
from audio import voice_tracks as _impl
import sys as _sys

_sys.modules[__name__] = _impl
