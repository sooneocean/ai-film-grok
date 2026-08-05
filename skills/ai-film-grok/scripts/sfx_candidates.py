"""Shim — implementation in audio.sfx_candidates (W6 package layout).

Keeps `import sfx_candidates` / `from sfx_candidates import …` working for hard-compat.
"""
from audio import sfx_candidates as _impl
import sys as _sys

_sys.modules[__name__] = _impl
