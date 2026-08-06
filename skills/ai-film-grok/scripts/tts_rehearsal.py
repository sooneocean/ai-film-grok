"""Shim — implementation in audio.tts_rehearsal (W6 package layout).

Keeps `import tts_rehearsal` / `from tts_rehearsal import …` working for hard-compat.
"""
import sys as _sys

from audio import tts_rehearsal as _impl

_sys.modules[__name__] = _impl
