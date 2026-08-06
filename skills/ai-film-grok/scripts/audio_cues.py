"""Shim — implementation in audio.audio_cues (W6 package layout).

Keeps `import audio_cues` / `from audio_cues import …` working for hard-compat.
"""
from audio import audio_cues as _impl
import sys as _sys

_sys.modules[__name__] = _impl
