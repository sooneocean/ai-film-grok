"""Shim — implementation in audio.voice_cast_profiles (W6 package layout).

Keeps `import voice_cast_profiles` / `from voice_cast_profiles import …` working for hard-compat.
"""
from audio import voice_cast_profiles as _impl
import sys as _sys

_sys.modules[__name__] = _impl
