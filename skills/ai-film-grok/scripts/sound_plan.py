"""Shim — implementation in audio.sound_plan (W6 package layout).

Keeps `import sound_plan` / `from sound_plan import …` working for hard-compat.
"""
import sys as _sys

from audio import sound_plan as _impl

_sys.modules[__name__] = _impl
