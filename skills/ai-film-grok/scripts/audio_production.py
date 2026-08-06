"""Shim — implementation in audio.audio_production (W6 package layout).

Keeps `import audio_production` / `from audio_production import …` working for hard-compat.
"""
from audio import audio_production as _impl
import sys as _sys

_sys.modules[__name__] = _impl
