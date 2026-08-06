"""Shim — implementation in media.frw_ab (W6 package layout).

Keeps `import frw_ab` / `from frw_ab import …` working for hard-compat.
"""
from media import frw_ab as _impl
import sys as _sys

_sys.modules[__name__] = _impl
