"""Shim — implementation in audio.tts_ab (W6 package layout).

Keeps `import tts_ab` / `from tts_ab import …` working for hard-compat.
"""
import sys as _sys

from audio import tts_ab as _impl

_sys.modules[__name__] = _impl
