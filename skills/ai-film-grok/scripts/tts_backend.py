"""Shim — implementation in audio.tts_backend (W6 package layout).

Keeps `import tts_backend` / `from tts_backend import …` working for hard-compat.
"""
from audio import tts_backend as _impl
import sys as _sys

_sys.modules[__name__] = _impl
