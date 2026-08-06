"""Shim — implementation in audio.music_cue (W6 package layout).

Keeps `import music_cue` / `from music_cue import …` working for hard-compat.
"""
from audio import music_cue as _impl
import sys as _sys

_sys.modules[__name__] = _impl
