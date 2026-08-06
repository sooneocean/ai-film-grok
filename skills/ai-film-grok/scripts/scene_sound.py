"""Shim — implementation in audio.scene_sound (W6 package layout).

Keeps `import scene_sound` / `from scene_sound import …` working for hard-compat.
"""
from audio import scene_sound as _impl
import sys as _sys

_sys.modules[__name__] = _impl
