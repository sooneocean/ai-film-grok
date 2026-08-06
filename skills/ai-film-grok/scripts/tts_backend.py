"""Shim — implementation in audio.tts_backend (W6 package layout).

Keeps `import tts_backend` / `from tts_backend import …` working for hard-compat.
"""
import sys as _sys

from audio import tts_backend as _impl

_sys.modules[__name__] = _impl
