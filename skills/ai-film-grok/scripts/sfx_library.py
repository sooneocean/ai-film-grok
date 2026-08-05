"""Shim — implementation in audio.sfx_library (W6 package layout).

Keeps `import sfx_library` / `from sfx_library import …` working for hard-compat.
"""
from audio import sfx_library as _impl
import sys as _sys

_sys.modules[__name__] = _impl
