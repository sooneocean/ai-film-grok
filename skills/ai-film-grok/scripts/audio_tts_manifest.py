"""Shim — implementation in audio.audio_tts_manifest (W6 package layout).

Keeps `import audio_tts_manifest` / `from audio_tts_manifest import …` working for hard-compat.
"""
from audio import audio_tts_manifest as _impl
import sys as _sys

_sys.modules[__name__] = _impl
