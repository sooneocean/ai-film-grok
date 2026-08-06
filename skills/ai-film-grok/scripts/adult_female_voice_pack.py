"""Shim — implementation in audio.adult_female_voice_pack (W6 package layout).

Keeps `import adult_female_voice_pack` / `from adult_female_voice_pack import …` working for hard-compat.
"""
import sys as _sys

from audio import adult_female_voice_pack as _impl

_sys.modules[__name__] = _impl
