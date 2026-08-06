"""Shim — implementation in audio.audio_tts_render (W6 package layout).

Keeps `import audio_tts_render` / `from audio_tts_render import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_tts_render as _impl

_sys.modules[__name__] = _impl
