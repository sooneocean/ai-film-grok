"""Shim — implementation in audio.scene_sound (W6 package layout).

Keeps `import scene_sound` / `from scene_sound import …` working for hard-compat.
"""
import sys as _sys

from audio import scene_sound as _impl

_sys.modules[__name__] = _impl
