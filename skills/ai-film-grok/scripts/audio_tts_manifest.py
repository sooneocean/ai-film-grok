"""Shim — implementation in audio.audio_tts_manifest (W6 package layout).

Keeps `import audio_tts_manifest` / `from audio_tts_manifest import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_tts_manifest as _impl

_sys.modules[__name__] = _impl
