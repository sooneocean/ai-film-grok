"""Shim — implementation in audio.sfx_library (W6 package layout).

Keeps `import sfx_library` / `from sfx_library import …` working for hard-compat.
"""
import sys as _sys

from audio import sfx_library as _impl

_sys.modules[__name__] = _impl
