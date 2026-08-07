"""Shim — implementation in audio.music_director (W6 package layout).

Keeps `import music_director` / `from music_director import …` working for hard-compat.
"""
import sys as _sys

from audio import music_director as _impl

_sys.modules[__name__] = _impl
