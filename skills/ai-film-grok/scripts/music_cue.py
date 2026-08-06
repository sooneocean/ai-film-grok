"""Shim — implementation in audio.music_cue (W6 package layout).

Keeps `import music_cue` / `from music_cue import …` working for hard-compat.
"""
import sys as _sys

from audio import music_cue as _impl

_sys.modules[__name__] = _impl
