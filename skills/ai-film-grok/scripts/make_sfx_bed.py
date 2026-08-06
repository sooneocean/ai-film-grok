"""Shim — implementation in audio.make_sfx_bed (W6 package layout).

Keeps `import make_sfx_bed` / `from make_sfx_bed import …` working for hard-compat.
"""
import sys as _sys

from audio import make_sfx_bed as _impl

_sys.modules[__name__] = _impl
