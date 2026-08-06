"""Shim — implementation in audio.voice_armory (W6 package layout).

Keeps `import voice_armory` / `from voice_armory import …` working for hard-compat.
"""
import sys as _sys

from audio import voice_armory as _impl

_sys.modules[__name__] = _impl
