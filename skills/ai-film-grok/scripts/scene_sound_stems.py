"""Shim — implementation in audio.scene_sound_stems (W6 package layout).

Keeps `import scene_sound_stems` / `from scene_sound_stems import …` working for hard-compat.
"""
import sys as _sys

from audio import scene_sound_stems as _impl

_sys.modules[__name__] = _impl
