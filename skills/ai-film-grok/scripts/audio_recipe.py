"""Shim — implementation in audio.audio_recipe (W6 package layout).

Keeps `import audio_recipe` / `from audio_recipe import …` working for hard-compat.
"""
import sys as _sys

from audio import audio_recipe as _impl

_sys.modules[__name__] = _impl
