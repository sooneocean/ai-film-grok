"""Shim — implementation in media.pilot_pack (W6 package layout).

Keeps `import pilot_pack` / `from pilot_pack import …` working for hard-compat.
"""
from media import pilot_pack as _impl
import sys as _sys

_sys.modules[__name__] = _impl
