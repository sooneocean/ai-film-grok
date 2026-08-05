"""Shim — implementation in audio.audio_attachment (W6 package layout).

Keeps `import audio_attachment` / `from audio_attachment import …` working for hard-compat.
"""
from audio import audio_attachment as _impl
import sys as _sys

_sys.modules[__name__] = _impl
