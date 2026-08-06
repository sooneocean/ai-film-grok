"""Shim — implementation in audio.audio_armory (W6 package layout).

Keeps `import audio_armory` / `from audio_armory import …` working for hard-compat.
"""
from audio import audio_armory as _impl
import sys as _sys

_sys.modules[__name__] = _impl
