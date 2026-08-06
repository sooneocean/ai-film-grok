"""Shim — implementation in audio.voice_armory (W6 package layout).

Keeps `import voice_armory` / `from voice_armory import …` working for hard-compat.
"""
from audio import voice_armory as _impl
import sys as _sys

_sys.modules[__name__] = _impl
