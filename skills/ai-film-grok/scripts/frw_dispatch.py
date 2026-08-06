"""Shim — implementation in media.frw_dispatch (W6 package layout).

Keeps `import frw_dispatch` / `from frw_dispatch import …` working for hard-compat.
"""
import sys as _sys

from media import frw_dispatch as _impl

_sys.modules[__name__] = _impl
