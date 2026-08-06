"""Shim — implementation in audio.tts_rehearsal (W6 package layout).

Keeps `import tts_rehearsal` / `from tts_rehearsal import …` working for hard-compat.
"""
from audio import tts_rehearsal as _impl
import sys as _sys

_sys.modules[__name__] = _impl
