"""Shim — implementation in media.weapon_router (W6 package layout).

Keeps `import weapon_router` / `from weapon_router import …` working for hard-compat.
"""
import sys as _sys

from media import weapon_router as _impl

_sys.modules[__name__] = _impl
