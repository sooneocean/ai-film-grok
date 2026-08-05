"""Shim — implementation in audio.audio_recipe (W6 package layout).

Keeps `import audio_recipe` / `from audio_recipe import …` working for hard-compat.
"""
from audio import audio_recipe as _impl
import sys as _sys

_sys.modules[__name__] = _impl
