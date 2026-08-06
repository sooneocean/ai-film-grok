"""Shim — implementation in audio.sfx_candidates (W6 package layout).

Keeps `import sfx_candidates` / `from sfx_candidates import …` working for hard-compat.
"""
import sys as _sys

from audio import sfx_candidates as _impl

_sys.modules[__name__] = _impl
