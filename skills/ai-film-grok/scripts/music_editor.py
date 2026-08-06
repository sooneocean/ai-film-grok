"""Shim — implementation in audio.music_editor (W6 package layout).

Keeps `import music_editor` / `from music_editor import …` working for hard-compat.
"""
import sys as _sys

from audio import music_editor as _impl

_sys.modules[__name__] = _impl
