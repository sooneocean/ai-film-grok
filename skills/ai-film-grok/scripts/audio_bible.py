"""Shim — implementation in audio.audio_bible (W6 package layout).

Keeps `import audio_bible` / `from audio_bible import …` working for hard-compat.
"""
from audio import audio_bible as _impl
import sys as _sys

_sys.modules[__name__] = _impl
