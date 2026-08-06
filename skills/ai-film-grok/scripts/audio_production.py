"""Shim — implementation in audio.audio_production (W6 package layout).

Keeps `import audio_production` / `from audio_production import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_production as _impl

_sys.modules[__name__] = _impl
