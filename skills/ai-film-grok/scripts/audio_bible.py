"""Shim — implementation in audio.audio_bible (W6 package layout).

Keeps `import audio_bible` / `from audio_bible import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_bible as _impl

_sys.modules[__name__] = _impl
