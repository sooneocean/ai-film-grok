"""Shim — implementation in audio.make_sfx_bed (W6 package layout).

Keeps `import make_sfx_bed` / `from make_sfx_bed import …` working for hard-compat.
"""
from audio import make_sfx_bed as _impl
import sys as _sys

_sys.modules[__name__] = _impl
