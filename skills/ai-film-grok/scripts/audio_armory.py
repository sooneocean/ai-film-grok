"""Shim — implementation in audio.audio_armory (W6 package layout).

Keeps `import audio_armory` / `from audio_armory import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_armory as _impl

_sys.modules[__name__] = _impl
