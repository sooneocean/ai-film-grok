"""Shim — implementation in audio.audio_visual_alignment (W6 package layout).

Keeps `import audio_visual_alignment` / `from audio_visual_alignment import …` working for hard-compat.
"""
from audio import audio_visual_alignment as _impl
import sys as _sys

_sys.modules[__name__] = _impl
