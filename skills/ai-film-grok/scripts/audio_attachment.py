"""Shim — implementation in audio.audio_attachment (W6 package layout).

Keeps `import audio_attachment` / `from audio_attachment import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_attachment as _impl

_sys.modules[__name__] = _impl
