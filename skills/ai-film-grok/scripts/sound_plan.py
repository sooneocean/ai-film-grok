"""Shim — implementation in audio.sound_plan (W6 package layout).

Keeps `import sound_plan` / `from sound_plan import …` working for hard-compat.
"""
from audio import sound_plan as _impl
import sys as _sys

_sys.modules[__name__] = _impl
