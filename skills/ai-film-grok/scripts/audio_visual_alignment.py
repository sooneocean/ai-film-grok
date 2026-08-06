"""Shim — implementation in audio.audio_visual_alignment (W6 package layout).

Keeps `import audio_visual_alignment` / `from audio_visual_alignment import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_visual_alignment as _impl

_sys.modules[__name__] = _impl
