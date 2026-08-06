"""Shim — implementation in audio.audio_cues (W6 package layout).

Keeps `import audio_cues` / `from audio_cues import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_cues as _impl

_sys.modules[__name__] = _impl
