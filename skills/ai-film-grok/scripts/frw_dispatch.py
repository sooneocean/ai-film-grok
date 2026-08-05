"""Shim — implementation in media.frw_dispatch (W6 package layout).

Keeps `import frw_dispatch` / `from frw_dispatch import …` working for hard-compat.
"""
from media import frw_dispatch as _impl
import sys as _sys

_sys.modules[__name__] = _impl
