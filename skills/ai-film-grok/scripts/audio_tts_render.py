"""Shim — implementation in audio.audio_tts_render (W6 package layout).

Keeps `import audio_tts_render` / `from audio_tts_render import …` working for hard-compat.
"""
from audio import audio_tts_render as _impl
import sys as _sys

_sys.modules[__name__] = _impl
