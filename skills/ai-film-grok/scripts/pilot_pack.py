"""Shim — implementation in media.pilot_pack (W6 package layout).

Keeps `import pilot_pack` / `from pilot_pack import …` working for hard-compat.
"""
import sys as _sys

from media import pilot_pack as _impl

_sys.modules[__name__] = _impl
