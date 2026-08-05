"""Shim — implementation in audio.tts_ab (W6 package layout).

Keeps `import tts_ab` / `from tts_ab import …` working for hard-compat.
"""
from audio import tts_ab as _impl
import sys as _sys

_sys.modules[__name__] = _impl
